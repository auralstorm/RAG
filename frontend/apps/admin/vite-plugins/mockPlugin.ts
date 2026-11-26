import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Plugin, ViteDevServer } from 'vite';

import type { MockRequest, MockResponse } from '../mock/types';

const pluginDir = fileURLToPath(new URL('.', import.meta.url));

type MockHandler = (req: MockRequest, res: MockResponse) => void | Promise<void>;
type MockValue = MockHandler | unknown;

interface MockEntry {
  methods: string[];
  regex: RegExp;
  paramNames: string[];
  handler: MockValue;
}

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] as const;

const mockRoot = path.resolve(pluginDir, '../mock');
const pagesDir = path.resolve(pluginDir, '../src/pages');

function collectMockFiles(): string[] {
  const files: string[] = [];
  if (fs.existsSync(mockRoot)) {
    for (const f of fs.readdirSync(mockRoot)) {
      if (/\.(ts|js)$/.test(f)) files.push(path.join(mockRoot, f));
    }
  }
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.name === '_mock.ts') files.push(p);
    }
  };
  walk(pagesDir);
  return files;
}

/**
 * 把 原 Umi mock 的 key（可能带 METHOD，method 与 path 间可能是多个空格，
 * path 段可能含 :param）拆成方法集合与路径正则。
 */
function parseKey(
  rawKey: string,
): { methods: string[]; regex: RegExp; paramNames: string[] } | null {
  const trimmed = rawKey.trim();
  const parts = trimmed.split(/\s+/).filter(Boolean);
  let methods: string[];
  let pathPart: string;

  if (
    parts.length >= 2 &&
    (HTTP_METHODS as readonly string[]).includes(parts[0] ?? '')
  ) {
    methods = [parts[0] ?? ''];
    pathPart = parts.slice(1).join('/');
  } else {
    methods = [...HTTP_METHODS];
    pathPart = trimmed;
  }

  if (!pathPart.startsWith('/')) return null;

  const paramNames: string[] = [];
  const pattern = pathPart
    .split('/')
    .map((seg) => {
      if (seg.startsWith(':')) {
        paramNames.push(seg.slice(1));
        return '([^/]+)';
      }
      return seg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    })
    .join('/');

  return { methods, regex: new RegExp(`^${pattern}$`), paramNames };
}

async function loadMockEntries(server: ViteDevServer): Promise<MockEntry[]> {
  const entries: MockEntry[] = [];
  for (const file of collectMockFiles()) {
    const mod = await server.ssrLoadModule(file);
    const exp = (mod.default ?? mod) as Record<string, MockValue>;
    if (!exp || typeof exp !== 'object') continue;
    for (const [key, handler] of Object.entries(exp)) {
      const parsed = parseKey(key);
      if (parsed) entries.push({ ...parsed, handler });
    }
  }
  return entries;
}

/**
 * 对应原 Umi mock 插件：dev server 中间件拦截 METHOD 加 /api 路径，
 * 复用 mock 目录与页面 _mock.ts 的 express 风格处理器。
 * 兼容：多空格分隔、省略 method、路径参数 :param、直接返回数据数组/对象。
 */
export function proMockPlugin(): Plugin {
  let entries: MockEntry[] = [];
  let loadPromise: Promise<MockEntry[]> | null = null;

  async function ensureLoaded(server: ViteDevServer): Promise<MockEntry[]> {
    if (!loadPromise) {
      loadPromise = loadMockEntries(server).catch((e) => {
        console.error('[pro-mock] load failed', e);
        return [];
      });
    }
    entries = await loadPromise;
    return entries;
  }

  return {
    name: 'pro-mock',
    configureServer(server) {
      // 预热加载，避免首个请求命中未就绪状态
      void ensureLoaded(server);

      server.middlewares.use(async (req, res, next) => {
        if (!req.url || !req.method) return next();
        await ensureLoaded(server);

        const { pathname, searchParams } = new URL(req.url, 'http://localhost');
        const method = req.method.toUpperCase();

        let matched: MockEntry | undefined;
        let params: Record<string, string> = {};
        for (const entry of entries) {
          if (!entry.methods.includes(method)) continue;
          const m = entry.regex.exec(pathname);
          if (m) {
            matched = entry;
            params = Object.fromEntries(
              entry.paramNames.map((n, i) => [n, m[i + 1] ?? '']),
            );
            break;
          }
        }
        if (!matched) return next();

        const query = Object.fromEntries(searchParams);
        const chunks: Buffer[] = [];
        for await (const chunk of req) chunks.push(chunk as Buffer);
        const raw = Buffer.concat(chunks).toString('utf-8');
        let body: unknown;
        if (raw) {
          try {
            body = JSON.parse(raw);
          } catch {
            body = raw;
          }
        }

        const adaptedReq = Object.assign(req, { query, body, params });
        const adaptedRes: MockResponse = {
          statusCode: 200,
          status(code: number) {
            this.statusCode = code;
            return this;
          },
          send(payload: unknown) {
            res.statusCode = this.statusCode ?? 200;
            if (typeof payload === 'string') {
              res.setHeader('Content-Type', 'text/plain;charset=utf-8');
              res.end(payload);
            } else {
              res.setHeader('Content-Type', 'application/json;charset=utf-8');
              res.end(JSON.stringify(payload));
            }
          },
          json(payload: unknown) {
            this.send(payload);
          },
          setHeader(k: string, v: string) {
            res.setHeader(k, v);
            return this;
          },
          end() {
            res.end();
          },
        };

        try {
          if (typeof matched.handler === 'function') {
            await matched.handler(adaptedReq, adaptedRes);
          } else {
            adaptedRes.json(matched.handler);
          }
        } catch (e) {
          next(e as Error);
        }
      });
    },
  };
}
