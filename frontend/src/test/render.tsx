import { QueryClient } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { AppProviders, PRODUCTION_QUERY_DEFAULTS } from '@/AppProviders';
import { appRoutes, preloadPages } from '@/routes';

// 이 도우미를 쓰는 테스트 파일은 화면 청크를 먼저 불러 둔다 — 첫 테스트의 findBy(5초)가 청크 변환·평가 시간을
// 함께 세지 않게(6차 리뷰: 부하에서 첫 화면 테스트 5017ms 실패). 모듈 평가 시 등록되는 파일 단위 훅이다.
beforeAll(() => preloadPages(), 60_000);

/**
 * 테스트용 QueryClient — 운영(`createQueryClient`)과 같은 기본값(staleTime 30초·포커스 재조회 없음)에 재시도만 끈다.
 * 6차 리뷰(부하 5017ms): staleTime 0 이던 때는 지연 로드 화면이 붙을 때마다 지역·리비전 목록을 다시 받아(운영에는
 * 없는 요청) 첫 findBy 창 안의 요청·렌더가 두 배였다.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { ...PRODUCTION_QUERY_DEFAULTS, retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

/** 앱 라우트 전체를 메모리 라우터로 렌더한다(MSW 핸들러 사용). */
export function renderRoute(
  path: string,
): RenderResult & { router: ReturnType<typeof createMemoryRouter> } {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  const result = render(
    <AppProviders queryClient={createTestQueryClient()}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...result, router };
}

/** 컴포넌트 하나를 Query·테마·출처 Provider로 감싸 렌더한다. */
export function renderWithProviders(ui: ReactElement): RenderResult {
  return render(<AppProviders queryClient={createTestQueryClient()}>{ui}</AppProviders>);
}
