import { QueryClient } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { AppProviders } from '@/AppProviders';
import { appRoutes } from '@/routes';

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
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
