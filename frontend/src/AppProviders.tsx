import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { ProvenanceProvider } from '@/components/ProvenancePanel';
import { ThemeProvider } from '@/lib/theme';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
    },
  });
}

/** Query → 테마 → 출처 패널. 라우터는 바깥(main.tsx / test/render.tsx)에서 감싼다. */
export function AppProviders({
  queryClient,
  children,
}: {
  queryClient: QueryClient;
  children: ReactNode;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ProvenanceProvider>{children}</ProvenanceProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
