import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router';
import { AppProviders, createQueryClient } from './AppProviders';
import { loadAllNamespaces } from './i18n';
import { appRoutes } from './routes';
import './index.css';

/** `npm run dev:msw`(mode=msw) 또는 VITE_MSW=true면 API 대신 MSW 핸들러가 응답한다. */
const useMsw = import.meta.env.MODE === 'msw' || import.meta.env.VITE_MSW === 'true';

async function enableMocking(): Promise<void> {
  if (!useMsw) return;
  // R11-I18N: MSW 모드(dev:msw·e2e/pages)는 문자열 이름공간을 처음부터 전부 등록한다(운영은 화면 청크가 자기 문자열을 싣는다 — i18n/namespaces.ts)
  const [{ worker }] = await Promise.all([import('./mocks/browser'), loadAllNamespaces()]);
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
