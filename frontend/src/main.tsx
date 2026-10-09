import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { AppProviders, createQueryClient } from './AppProviders';
import { appRoutes } from './routes';
import './index.css';

/** `npm run dev:msw`(mode=msw) 또는 VITE_MSW=true면 API 대신 MSW 핸들러가 응답한다. */
const useMsw = import.meta.env.MODE === 'msw' || import.meta.env.VITE_MSW === 'true';

async function enableMocking(): Promise<void> {
  if (!useMsw) return;
  const { worker } = await import('./mocks/browser');
  await worker.start({ onUnhandledRequest: 'bypass', quiet: true });
}

const router = createBrowserRouter(appRoutes);
const queryClient = createQueryClient();

void enableMocking().then(() => {
  const root = document.getElementById('root');
  if (!root) throw new Error('#root 없음');
  createRoot(root).render(
    <StrictMode>
      <AppProviders queryClient={queryClient}>
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>,
  );
});
