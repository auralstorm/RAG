import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ConnectedApp } from './app/ConnectedApp';
import { createBrowserRouter } from 'react-router';
import { createChatRoutes } from './routes/routes';
import './styles/global.css';

const container = document.getElementById('root');
if (container === null) throw new Error('Application root is missing');

const router = createBrowserRouter(createChatRoutes());

createRoot(container).render(
  <StrictMode>
    <ConnectedApp router={router} />
  </StrictMode>,
);
