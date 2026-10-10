import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { watchJobCompletion } from '@/api/jobWatch';
import { queryRetry, queryRetryDelay } from '@/api/retryPolicy';
import { ProvenanceProvider } from '@/components/ProvenancePanel';
import { ThemeProvider } from '@/lib/theme';

/**
 * 운영 쿼리 기본값 — 테스트 QueryClient(`test/render.tsx`)도 재시도 횟수만 바꿔 같은 값을 쓴다.
 * 재시도: 일반 오류 1번, 503 materialize_pending 은 Retry-After 간격으로 계속(계약 .11 F12 — `api/retryPolicy`).
 */
export const PRODUCTION_QUERY_DEFAULTS = {
  staleTime: 30_000,
  retry: queryRetry(1),
  retryDelay: queryRetryDelay,
  refetchOnWindowFocus: false,
} as const;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { ...PRODUCTION_QUERY_DEFAULTS } },
  });
}

/**
 * Query → 테마 → 출처 패널. 라우터는 바깥(main.tsx / test/render.tsx)에서 감싼다.
 * 잡 완료·리비전 발행 감시(`watchJobCompletion`, 4차 리뷰 M-15)를 QueryClient 에 한 번 건다.
 */
export function AppProviders({
  queryClient,
  children,
}: {
  queryClient: QueryClient;
  children: ReactNode;
}) {
  useEffect(() => watchJobCompletion(queryClient), [queryClient]);
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ProvenanceProvider>{children}</ProvenanceProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
