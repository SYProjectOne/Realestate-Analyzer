import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { watchJobCompletion } from '@/api/jobWatch';
import { ProvenanceProvider } from '@/components/ProvenancePanel';
import { ThemeProvider } from '@/lib/theme';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
    },
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
