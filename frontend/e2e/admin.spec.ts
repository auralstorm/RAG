import { expect, test } from '@playwright/test';
import type { BrowserContext, Page } from '@playwright/test';

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (!value)
    throw new Error('Run make frontend-e2e to provision isolated servers.');
  return value;
}

test('production Admin preserves sessions, current permissions and recovery across the Pro layout', async ({
  browser,
}, testInfo) => {
  const adminOrigin = requiredEnvironment('ENTERPRISE_RAG_E2E_ADMIN_ORIGIN');
  const chatOrigin = requiredEnvironment('ENTERPRISE_RAG_E2E_CHAT_ORIGIN');
  const contexts: BrowserContext[] = [];
  const errors: string[] = [];
  async function login(
    username: string,
    password: string,
    application: 'admin' | 'chat' = 'admin',
    viewport?: { width: number; height: number },
  ) {
    const context = await browser.newContext({
      baseURL: application === 'admin' ? adminOrigin : chatOrigin,
      ...(viewport ? { viewport } : {}),
    });
    contexts.push(context);
    const page = await context.newPage();
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/login');
    await page
      .getByLabel(application === 'admin' ? '管理员账号' : '测试账号', {
        exact: true,
      })
      .fill(username);
    await page.getByLabel('密码', { exact: true }).fill(password);
    await page.getByRole('button', { name: '登录', exact: true }).click();
    return page;
  }
  async function focus(page: Page) {
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  }
  async function dashboard(page: Page) {
    await expect(
      page.getByRole('heading', { name: '企业知识管理', exact: true }),
    ).toBeVisible();
  }
  try {
    const admin = await login('fixture', 'synthetic-private-password-1234');
    await dashboard(admin);
    await expect(admin.getByRole('link', { name: '打开开发预览' })).toHaveCount(
      0,
    );
    await admin.reload();
    await dashboard(admin);
    await expect(
      admin
        .getByRole('navigation', { name: '管理导航' })
        .getByRole('link', { name: '服务概览' }),
    ).toHaveAttribute('aria-current', 'page');
    await admin.getByRole('button', { name: '收起导航' }).click();
    await expect(
      admin.getByRole('button', { name: '展开导航' }),
    ).toHaveAttribute('aria-expanded', 'false');
    await admin.getByRole('button', { name: '展开导航' }).click();

    // Real HTTP success, an injected outage, then recovery must clear the old result.
    await admin.getByRole('button', { name: '检查连接' }).click();
    await expect(admin.getByRole('cell', { name: '可连接' })).toBeVisible();
    await admin.route('**/backend/health/live', (route) =>
      route.fulfill({ status: 503, json: {} }),
    );
    await admin.getByRole('button', { name: '检查连接' }).click();
    await expect(admin.getByText('暂时无法连接服务，请重试。')).toBeVisible();
    await expect(admin.getByRole('cell', { name: '可连接' })).toHaveCount(0);
    await admin.unroute('**/backend/health/live');
    await admin.getByRole('button', { name: '重试连接' }).click();
    await expect(admin.getByRole('cell', { name: '可连接' })).toBeVisible();

    const knowledge = await login('KB_ADMIN', 'synthetic-rbac-password-1234');
    await dashboard(knowledge);
    expect(
      (await knowledge.request.get('/backend/api/v1/admin/roles')).status(),
    ).toBe(403);
    const audit = await login('AUDIT_READONLY', 'synthetic-rbac-password-1234');
    await dashboard(audit);
    const employee = await login('EMPLOYEE', 'synthetic-rbac-password-1234');
    await expect(
      employee.getByRole('heading', { name: '暂无访问权限', exact: true }),
    ).toBeVisible();
    await expect(
      employee.getByRole('navigation', { name: '管理导航' }),
    ).toHaveCount(0);
    await employee.getByRole('button', { name: '退出登录' }).click();
    await expect(
      employee.getByRole('heading', { name: '登录企业知识管理', exact: true }),
    ).toBeVisible();
    const chat = await login(
      'EMPLOYEE',
      'synthetic-rbac-password-1234',
      'chat',
    );
    await expect(
      chat.getByRole('heading', { name: '新对话', exact: true }),
    ).toBeVisible();
    const scopes = await chat.request.get(
      '/backend/api/v1/authorization/chat/knowledge-bases',
    );
    expect((await scopes.json()).items).toHaveLength(0);

    for (const width of [1440, 768, 390, 320]) {
      await admin.setViewportSize({ width, height: 900 });
      await employee.setViewportSize({ width, height: 900 });
      await chat.setViewportSize({ width, height: 900 });
      if (width < 768) {
        const open = admin.getByRole('button', { name: '展开导航' });
        await open.focus();
        await open.press('Enter');
        await expect(
          admin.getByRole('navigation', { name: '管理导航' }),
        ).toBeVisible();
        await admin.getByRole('button', { name: '关闭导航' }).click();
        await expect(open).toBeFocused();
        await open.click();
        await admin
          .getByRole('navigation', { name: '管理导航' })
          .getByRole('link', { name: '服务概览' })
          .click();
        await expect(
          admin.getByRole('navigation', { name: '管理导航' }),
        ).not.toBeVisible();
      }
      for (const page of [admin, employee, chat]) {
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          )
          .toBe(true);
      }
      await admin.screenshot({
        path: testInfo.outputPath(`admin-${width}.png`),
        fullPage: true,
      });
      await employee.screenshot({
        path: testInfo.outputPath(`login-${width}.png`),
        fullPage: true,
      });
    }

    const mobile = await login(
      'fixture',
      'synthetic-private-password-1234',
      'admin',
      { width: 320, height: 900 },
    );
    await dashboard(mobile);
    await expect(
      mobile.getByRole('button', { name: '展开导航' }),
    ).toBeVisible();
    await expect(
      mobile.getByRole('navigation', { name: '管理导航' }),
    ).not.toBeVisible();
    await mobile.reload();
    await dashboard(mobile);
    await expect(
      mobile.getByRole('navigation', { name: '管理导航' }),
    ).not.toBeVisible();

    await audit.route('**/api/v1/authorization/admin/me', (route) =>
      route.fulfill({ status: 503, json: {} }),
    );
    await focus(audit);
    await expect(
      audit.getByRole('heading', { name: '暂时无法确认登录状态', exact: true }),
    ).toBeVisible();
    await expect(
      audit.getByRole('navigation', { name: '管理导航' }),
    ).toHaveCount(0);
    await audit.unroute('**/api/v1/authorization/admin/me');
    await focus(audit);
    await dashboard(audit);
    await audit.route('**/api/v1/authorization/admin/me', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({
        json: { ...body, subject_id: '00000000-0000-4000-8000-000000000001' },
      });
    });
    await focus(audit);
    await expect(
      audit.getByRole('heading', { name: '暂时无法确认登录状态', exact: true }),
    ).toBeVisible();
    await audit.unroute('**/api/v1/authorization/admin/me');
    await focus(audit);
    await dashboard(audit);

    const subject = (
      await (
        await knowledge.request.get('/backend/api/v1/auth/admin/me')
      ).json()
    ).user.id;
    const session = await (
      await admin.request.get('/backend/api/v1/auth/admin/me')
    ).json();
    const version = (
      await (
        await admin.request.get('/backend/api/v1/authorization/admin/me')
      ).json()
    ).policy_version;
    const revoked = await admin.request.put(
      `/backend/api/v1/admin/users/${subject}/roles`,
      {
        headers: { Origin: adminOrigin, 'X-CSRF-Token': session.csrf_token },
        data: { role_ids: [], expected_policy_version: version, confirm: true },
      },
    );
    expect(revoked.status()).toBe(204);
    await focus(knowledge);
    await expect(
      knowledge.getByRole('heading', { name: '暂无访问权限', exact: true }),
    ).toBeVisible();
    await expect(
      knowledge.getByRole('button', { name: '检查连接' }),
    ).toHaveCount(0);
    await expect(
      knowledge.getByRole('navigation', { name: '管理导航' }),
    ).toHaveCount(0);

    for (const context of contexts) {
      const cookies = (await context.cookies()).filter((cookie) =>
        cookie.name.startsWith('er_'),
      );
      expect(cookies.every((cookie) => cookie.httpOnly)).toBe(true);
      for (const page of context.pages()) {
        expect(
          await page.evaluate(() =>
            [...Object.keys(localStorage), ...Object.keys(sessionStorage)].some(
              (key) => /permission|role|token/i.test(key),
            ),
          ),
        ).toBe(false);
      }
    }
    await audit.context().clearCookies();
    await focus(audit);
    await expect(
      audit.getByRole('heading', { name: '登录企业知识管理', exact: true }),
    ).toBeVisible();
    await expect(audit.getByText('登录已过期，请重新登录。')).toBeVisible();
    await admin.goto('/preview');
    await expect(
      admin.getByRole('heading', { name: '页面不存在', exact: true }),
    ).toBeVisible();
    await admin.goto('/unknown-page');
    await expect(
      admin.getByRole('heading', { name: '页面不存在', exact: true }),
    ).toBeVisible();
    expect((await admin.request.get('/assets/missing.js')).status()).toBe(404);
    const asset = (await (await admin.request.get('/')).text()).match(
      /src="([^"]+\.js)"/,
    );
    if (!asset?.[1]) throw new Error('Production entry script missing.');
    expect(
      (await admin.request.get(asset[1])).headers()['content-type'],
    ).toMatch(/javascript/);
    expect(errors).toEqual([]);
  } finally {
    await Promise.allSettled(contexts.map((context) => context.close()));
  }
});
