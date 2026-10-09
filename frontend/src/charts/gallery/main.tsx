/** 테스트 전용 엔트리(gallery.html) — 라우터 없이 ChartGallery만. MSW 모드면 출처 패널 응답도 목으로. */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppProviders, createQueryClient } from '@/AppProviders';
import { ChartGallery } from './ChartGallery';
import '@/index.css';

const useMsw = import.meta.env.MODE === 'msw' || import.meta.env.VITE_MSW === 'true';

async function enableMocking(): Promise<void> {
  if (!useMsw) return;
  const { worker } = await import('@/mocks/browser');
  await worker.start({
    onUnhandledRequest: 'bypass',
    quiet: true,
    serviceWorker: { url: '/mockServiceWorker.js' },
  });
}

void enableMocking().then(() => {
  const root = document.getElementById('root');
  if (!root) throw new Error('#root 없음');
  createRoot(root).render(
    <StrictMode>
      <AppProviders queryClient={createQueryClient()}>
        <main className="min-h-screen bg-bg text-fg">
          <ChartGallery />
        </main>
      </AppProviders>
    </StrictMode>,
  );
});
