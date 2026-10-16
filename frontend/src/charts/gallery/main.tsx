/**
 * 테스트 전용 엔트리(gallery.html) — 라우터 없이 ChartGallery만. MSW 모드면 출처 패널 응답도 목으로.
 *
 * 렌더는 MSW 를 기다리지 않는다(R3i, 9차 리뷰 m19 `charts-gallery C05` 부하 시간 초과): 갤러리는 처음 그릴 때 API 를
 * 부르지 않고(출처 패널을 열 때만), MSW 시작은 목 핸들러 동적 import + 서비스 워커 등록·활성이라 새 브라우저 컨텍스트마다
 * 부하에 따라 수 초가 걸린다. 그래서 렌더와 MSW 시작을 따로 하고, 준비되면 `<html data-msw="ready">`(실패 `failed`)를
 * 단다 — 출처 패널을 여는 e2e 는 이 표지를 기다린다.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AppProviders, createQueryClient } from '@/AppProviders';
import { loadAllNamespaces } from '@/i18n';
import { ChartGallery } from './ChartGallery';
import '@/index.css';

const useMsw = import.meta.env.MODE === 'msw' || import.meta.env.VITE_MSW === 'true';

async function enableMocking(): Promise<void> {
  const { worker } = await import('@/mocks/browser');
  await worker.start({
    onUnhandledRequest: 'bypass',
    quiet: true,
    serviceWorker: { url: '/mockServiceWorker.js' },
  });
}

const root = document.getElementById('root');
if (!root) throw new Error('#root 없음');
// R11-I18N: 차트·용어·화면 문자열은 이름공간 청크 — 테스트 전용 엔트리라 전부 받은 뒤 그린다
void loadAllNamespaces().then(() =>
  createRoot(root).render(
    <StrictMode>
      <AppProviders queryClient={createQueryClient()}>
        <main className="min-h-screen bg-bg text-fg">
          <ChartGallery />
        </main>
      </AppProviders>
    </StrictMode>,
  ),
);

if (useMsw) {
  enableMocking().then(
    () => {
      document.documentElement.dataset.msw = 'ready';
    },
    (error: unknown) => {
      document.documentElement.dataset.msw = 'failed';
      console.error('MSW 시작 실패(갤러리 렌더는 그대로)', error);
    },
  );
}
