/**
 * R3g FE6 1단계 — 7차 리뷰(`docs/design/wp/R3_REVIEW7.md`) FE 항목, 결정 D15-8.
 *  - M7: 503 materialize_pending 동안 **다른 리비전·시나리오의 이전 값**을 보이지 않는다(placeholder 는 같은 리비전·
 *    시나리오 키일 때만) + '준비 중'.
 *  - M8: G5 '이후' 열과 열린 서랍은 그 Fact 가 나온 리비전의 snapshot_id 로 조회한다.
 *  - minor 17–23.
 */
import { act, renderHook, screen, waitFor, within } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ReactNode } from 'react';
import { useComplexesProgressive } from '@/api/hooks';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { createTestQueryClient, renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const pending503 = (retryAfter = '600') =>
  HttpResponse.json(
    { code: 'materialize_pending', detail: '발행 리비전 저장본을 만드는 중' },
    { status: 503, headers: { 'Retry-After': retryAfter } },
  );

/** 생성 예시 응답 그대로(경로·쿼리 유지) */
async function passthrough(request: Request): Promise<Response> {
  const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
  return HttpResponse.json(await res!.json());
}

// ─── M7 ────────────────────────────────────────────────────

describe('M7 503 materialize_pending 동안 다른 리비전·시나리오의 이전 값을 보이지 않는다', () => {
  it('G1: 리비전을 바꿔 새 리비전이 503 이면 이전 리비전 TOP 5 대신 "준비 중"', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), ({ params, request }) =>
        params.sid === '11' ? pending503() : passthrough(request),
      ),
    );
    const { router } = renderRoute('/?snapshot=12');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    await act(() => router.navigate('/?snapshot=11'));
    expect(await screen.findByTestId('materialize-pending')).toHaveTextContent(
      t('page.common.materializePending'),
    );
    expect(screen.queryByRole('list', { name: t('page.G1.top5') })).toBeNull();
  });

  it('G1: 시나리오를 바꿔 그 시나리오가 503 이면 기본 시나리오 TOP 5 를 보이지 않는다', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), ({ request }) =>
        new URL(request.url).searchParams.get('scenario') === 'A'
          ? pending503()
          : passthrough(request),
      ),
    );
    const { router } = renderRoute('/?snapshot=12');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    await act(() => router.navigate('/?snapshot=12&scenario=A'));
    expect(await screen.findByTestId('materialize-pending')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: t('page.G1.top5') })).toBeNull();
  });

  it('G2: 리비전을 바꿔 503 이면 이전 리비전 행 대신 "준비 중"(minor 18)', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), ({ params, request }) =>
        params.sid === '11' ? pending503() : passthrough(request),
      ),
    );
    const { router } = renderRoute('/complexes?snapshot=12');
    await screen.findByRole('table', { name: t('page.G2.table') });
    await act(() => router.navigate('/complexes?snapshot=11'));
    expect(await screen.findByTestId('materialize-pending')).toHaveTextContent(
      t('page.common.materializePending'),
    );
    expect(screen.queryByRole('table', { name: t('page.G2.table') })).toBeNull();
  });

  it('G2: 같은 리비전·시나리오에서 필터만 바꾸면 이전 행을 잠깐 둔다(placeholder 유지)', async () => {
    let hold: (() => void) | null = null;
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), async ({ request }) => {
        if (new URL(request.url).searchParams.get('sort') === 'name') {
          await new Promise<void>((resolve) => {
            hold = resolve;
          });
        }
        return passthrough(request);
      }),
    );
    const { router } = renderRoute('/complexes?snapshot=12');
    await screen.findByRole('table', { name: t('page.G2.table') });
    await act(() => router.navigate('/complexes?snapshot=12&sort=name'));
    await waitFor(() => expect(hold).not.toBeNull());
    expect(screen.getByRole('table', { name: t('page.G2.table') })).toBeInTheDocument();
    act(() => hold!());
  });

  it('G6: 리비전을 바꿔 503 이면 이전 리비전 시장 자료 대신 "준비 중"', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/market'), ({ params, request }) =>
        params.sid === '11' ? pending503() : passthrough(request),
      ),
    );
    const { router } = renderRoute('/market?snapshot=12');
    await screen.findByRole('region', { name: t('page.G6.regulation') });
    await act(() => router.navigate('/market?snapshot=11'));
    expect(await screen.findByTestId('materialize-pending')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: t('page.G6.regulation') })).toBeNull();
  });

  it('minor 18: G2 목록 결과가 재시도 중 실패 사유와 다시 시도(refetch)를 넘긴다', async () => {
    server.use(http.get(mswPath('/snapshots/:sid/complexes'), () => pending503()));
    const qc = createTestQueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useComplexesProgressive('12', {}, 50), { wrapper });
    await waitFor(() =>
      expect((result.current.failureReason as { code?: string } | null)?.code).toBe(
        'materialize_pending',
      ),
    );
    expect(typeof result.current.refetch).toBe('function');
  });
});

export { within };
