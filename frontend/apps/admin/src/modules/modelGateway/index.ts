export { PROVIDER_PAGE } from './providerMeta';
export const ProviderManagement = lazy(async () => {
  const { ProviderManagement: Component } =
    await import('./ProviderManagement');
  return { default: Component };
});
import { lazy } from 'react';
