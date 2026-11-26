import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter } from 'react-router';

import { ConnectedApp } from './app/ConnectedApp';
import { createAdminRoutes } from './routes/routes';
import './styles/global.css';

const container = document.getElementById('root');
if (container === null) throw new Error('Application root is missing');

const router = createBrowserRouter(createAdminRoutes());

createRoot(container).render(
  <StrictMode>
    <ConnectedApp router={router} />
  </StrictMode>,
);
