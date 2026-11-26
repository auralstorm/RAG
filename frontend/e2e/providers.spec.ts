import { expect, test } from '@playwright/test';

test('Provider management handles CRUD, masked credentials, failures and responsive layouts', async ({
  browser,
}, testInfo) => {
  const origin = process.env['ENTERPRISE_RAG_E2E_ADMIN_ORIGIN'];
  if (!origin)
    throw new Error('Run make frontend-e2e to provision isolated servers.');
  const context = await browser.newContext({
    baseURL: origin,
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    await page.goto('/login');
    await page.getByLabel('管理员账号', { exact: true }).fill('fixture');
    await page
      .getByLabel('密码', { exact: true })
      .fill('synthetic-private-password-1234');
    await page.getByRole('button', { name: '登录', exact: true }).click();
    await page.getByRole('link', { name: '模型供应商', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: '模型供应商', exact: true }),
    ).toBeVisible();
    await expect(page.getByText('暂无供应商配置。')).toBeVisible();
    await page.getByRole('button', { name: '新建供应商', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog
      .getByLabel('供应商名称', { exact: true })
      .fill('浏览器合成供应商');
    await dialog
      .getByLabel('供应商类型', { exact: true })
      .fill('openai_compatible');
    await dialog
      .getByLabel('服务地址', { exact: true })
      .fill('https://api.example.com/v1');
    await dialog.getByLabel('请求超时（秒）', { exact: true }).fill('45');
    await dialog
      .getByLabel('API Key', { exact: true })
      .fill('synthetic-browser-provider-key');
    await dialog
      .getByLabel('HTTP(S) 代理地址', { exact: true })
      .fill('http://proxy.example:8080');
    await dialog.getByLabel('备注', { exact: true }).fill('自动化验收合成数据');
    await dialog.getByRole('button', { name: '确认保存', exact: true }).click();
    await expect(dialog.getByText('请确认后再保存。')).toBeVisible();
    await dialog
      .getByRole('checkbox', {
        name: '我确认保存此配置，后续调用将使用新的配置。',
      })
      .check();
    await dialog.getByRole('button', { name: '确认保存', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    const row = page.getByRole('row').filter({ hasText: '浏览器合成供应商' });
    await expect(row).toBeVisible();
    await expect(row.getByText('已配置', { exact: true })).toHaveCount(2);
    await expect(row.getByText('45', { exact: true })).toBeVisible();
    expect(await page.content()).not.toContain(
      'synthetic-browser-provider-key',
    );

    const readerContext = await browser.newContext({ baseURL: origin });
    try {
      const login = await readerContext.request.post(
        '/backend/api/v1/auth/admin/login',
        {
          headers: { Origin: origin },
          data: {
            username: 'AUDIT_READONLY',
            password: 'synthetic-rbac-password-1234',
          },
        },
      );
      expect(login.status()).toBe(200);
      const reader = await readerContext.newPage();
      await reader.goto('/admin/providers');
      await expect(
        reader.getByRole('cell', { name: '浏览器合成供应商', exact: true }),
      ).toBeVisible();
      await expect(
        reader.getByRole('button', { name: '新建供应商', exact: true }),
      ).toHaveCount(0);
      await expect(
        reader.getByRole('button', { name: /编\s*辑/, exact: true }),
      ).toHaveCount(0);
    } finally {
      await readerContext.close().catch(() => {});
    }

    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(`providers-${width}.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await page
        .getByRole('button', { name: '新建供应商', exact: true })
        .click();
      await expect(
        dialog.getByRole('button', { name: '确认保存', exact: true }),
      ).toBeVisible();
      await dialog.scrollIntoViewIfNeeded();
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(`provider-editor-${width}.png`),
        fullPage: true,
        animations: 'disabled',
      });
      await dialog
        .getByRole('button', { name: /取\s*消/, exact: true })
        .click();
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await row.getByRole('button', { name: /编\s*辑/, exact: true }).click();
    await expect(dialog.getByLabel('API Key', { exact: true })).toHaveValue('');
    await expect(
      dialog.getByLabel('HTTP(S) 代理地址', { exact: true }),
    ).toHaveValue('');
    await dialog.getByLabel('备注', { exact: true }).fill('备注已更新');
    await dialog
      .getByRole('checkbox', {
        name: '我确认保存此配置，后续调用将使用新的配置。',
      })
      .check();
    await dialog.getByRole('button', { name: '确认保存', exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(row.getByText('备注已更新', { exact: true })).toBeVisible();
    await row.getByRole('button', { name: /停\s*用/, exact: true }).click();
    await page.getByRole('button', { name: /确\s*认/, exact: true }).click();
    await expect(
      row.getByRole('button', { name: /启\s*用/, exact: true }),
    ).toBeVisible();

    await page.route('**/api/v1/admin/providers?**', (route) =>
      route.fulfill({ status: 503, json: {} }),
    );
    await page.getByRole('button', { name: /查\s*询/, exact: true }).click();
    await expect(page.getByText('供应商列表暂时无法加载。')).toBeVisible();
    await expect(row).toHaveCount(0);
    await page.unroute('**/api/v1/admin/providers?**');
    await page.getByRole('button', { name: /重\s*试/, exact: true }).click();
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: /删\s*除/, exact: true }).click();
    await page
      .getByRole('tooltip')
      .getByRole('button', { name: /删\s*除/, exact: true })
      .click();
    await expect(page.getByText('供应商已删除。')).toBeVisible();
    await expect(row).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    await context.close().catch(() => {});
  }
});
