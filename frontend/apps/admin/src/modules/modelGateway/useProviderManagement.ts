import { useEffect, useRef, useState } from 'react';

import { apiClient } from '@admin/api/apiClient';
import {
  HttpError,
  type ProviderAdminView,
  type CreateProvider,
  type UpdateProvider,
} from '@enterprise-rag/api-client';
import { useSessionActions, useSessionState } from '@enterprise-rag/ui';

import { useProviderList, type ProviderListQuery } from './useProviderList';

export interface ProviderFormValues {
  readonly name: string;
  readonly provider_type: string;
  readonly base_url: string;
  readonly timeout_seconds: number;
  readonly remarks?: string;
  readonly credential?: string | undefined;
  readonly proxy_url?: string | undefined;
  readonly clear_proxy?: boolean;
  readonly confirm: boolean;
}

function failureText(error: unknown): string {
  const status = error instanceof HttpError ? error.status : undefined;
  const text =
    status === 409
      ? '配置或权限已变化，请刷新列表并重新打开编辑。'
      : status === 422
        ? '配置格式不正确，请检查服务地址、类型和密钥。'
        : status === 404
          ? '供应商已删除，请刷新列表。'
          : status === 401 || status === 403
            ? '登录已失效或权限已撤销，请重新确认登录状态。'
            : '操作结果尚未确认，请刷新列表核对后再操作。';
  return error instanceof HttpError && error.requestId
    ? `${text} 请求编号：${error.requestId}`
    : text;
}

export function useProviderManagement() {
  const session = useSessionState();
  const actions = useSessionActions();
  const canManage =
    session.status === 'authenticated' &&
    session.authorization.permissionCodes.includes('provider.manage');
  const policyVersion =
    session.status === 'authenticated'
      ? session.authorization.policyVersion
      : undefined;
  const [query, setQuery] = useState<ProviderListQuery>({
    page: 1,
    page_size: 20,
  });
  const [revision, setRevision] = useState(0);
  const state = useProviderList(query, revision);
  const [editor, setEditor] = useState<{ provider?: ProviderAdminView } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);
  const [denied, setDenied] = useState<401 | 403>();
  const pending = useRef(false);
  const active = useRef(false);
  const mutation = useRef<AbortController | null>(null);
  const listDenied = state.status === 'error' ? state.accessDenied : undefined;
  const accessDenied = denied ?? listDenied;
  const revalidate = actions.revalidate;

  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      mutation.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (accessDenied) void revalidate?.();
  }, [accessDenied, revalidate]);

  function refresh() {
    setRevision((value) => value + 1);
  }
  function closeEditor() {
    if (!pending.current) setEditor(null);
  }

  async function write(
    operation: (signal: AbortSignal) => Promise<unknown>,
    success: string,
    after?: () => void,
  ) {
    if (pending.current || !canManage || !policyVersion || accessDenied) return;
    pending.current = true;
    const controller = new AbortController();
    mutation.current = controller;
    setBusy(true);
    setNotice(null);
    try {
      await operation(controller.signal);
      if (!active.current) return;
      setEditor(null);
      setNotice({ type: 'success', text: success });
      after?.();
      refresh();
    } catch (error) {
      if (!active.current) return;
      setEditor(null);
      setNotice({ type: 'error', text: failureText(error) });
      if (
        error instanceof HttpError &&
        (error.status === 401 || error.status === 403)
      )
        setDenied(error.status);
      else refresh();
    } finally {
      pending.current = false;
      mutation.current = null;
      if (active.current) setBusy(false);
    }
  }

  function save(values: ProviderFormValues) {
    if (!policyVersion || !editor || !values.confirm) return;
    const common: CreateProvider = {
      name: values.name.trim(),
      provider_type: values.provider_type,
      base_url: values.base_url,
      timeout_seconds: values.timeout_seconds,
      remarks: values.remarks ?? '',
      expected_policy_version: policyVersion,
      confirm: true,
      ...(values.credential ? { credential: values.credential } : {}),
      ...(values.proxy_url ? { proxy_url: values.proxy_url } : {}),
    };
    const provider = editor.provider;
    return write(
      (signal) =>
        provider
          ? apiClient.providers.update(
              provider.id,
              {
                ...common,
                expected_config_version: provider.config_version,
                clear_proxy: values.clear_proxy ?? false,
              },
              signal,
            )
          : apiClient.providers.create(common, signal),
      provider ? '供应商配置已更新。' : '供应商已创建。',
    );
  }

  function changeStatus(provider: ProviderAdminView) {
    if (!policyVersion) return;
    const payload: UpdateProvider = {
      expected_policy_version: policyVersion,
      expected_config_version: provider.config_version,
      confirm: true,
      clear_proxy: false,
      status: provider.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE',
    };
    return write(
      (signal) => apiClient.providers.update(provider.id, payload, signal),
      provider.status === 'ACTIVE' ? '供应商已停用。' : '供应商已启用。',
    );
  }

  function remove(provider: ProviderAdminView) {
    if (!policyVersion) return;
    return write(
      (signal) =>
        apiClient.providers.delete(
          provider.id,
          {
            expected_policy_version: policyVersion,
            expected_config_version: provider.config_version,
            confirm: true,
          },
          signal,
        ),
      '供应商已删除。',
      () => {
        if (state.items.length === 1 && query.page > 1)
          setQuery((current) => ({ ...current, page: current.page - 1 }));
      },
    );
  }

  return {
    state,
    query,
    setQuery,
    canManage,
    busy,
    notice,
    accessDenied,
    editor: canManage && !accessDenied ? editor : null,
    openEditor: (provider?: ProviderAdminView) => {
      if (canManage && !pending.current)
        setEditor(provider ? { provider } : {});
    },
    closeEditor,
    refresh,
    save,
    changeStatus,
    remove,
  };
}
