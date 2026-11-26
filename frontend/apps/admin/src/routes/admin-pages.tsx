import type { ComponentType, ReactNode } from 'react';
import { DASHBOARD_PAGE } from '@admin/modules/dashboard';
import { PROVIDER_PAGE } from '@admin/modules/modelGateway';

interface AdminPage {
  readonly path: string;
  readonly name: string;
  readonly title: string;
  readonly description: string;
  readonly requiredPermission: string;
  readonly icon: ReactNode;
  readonly load: () => Promise<{ Component: ComponentType }>;
}

// This registry owns route loading; display metadata belongs to its module.
const DASHBOARD_ROUTE: AdminPage = {
  ...DASHBOARD_PAGE,
  load: async () => {
    const { DashboardPage } =
      await import('@admin/pages/dashboard/DashboardPage');
    return { Component: DashboardPage };
  },
};

const PROVIDER_ROUTE: AdminPage = {
  ...PROVIDER_PAGE,
  load: async () => {
    const { ProviderPage } =
      await import('@admin/pages/providers/ProviderPage');
    return { Component: ProviderPage };
  },
};

export const ADMIN_PAGES: readonly AdminPage[] = [
  DASHBOARD_ROUTE,
  PROVIDER_ROUTE,
];
