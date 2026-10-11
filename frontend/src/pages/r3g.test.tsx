/**
 * R3g FE6 1단계 — 7차 리뷰(`docs/design/wp/R3_REVIEW7.md`) FE 항목, 결정 D15-8.
 *  - M7: 503 materialize_pending 동안 **다른 리비전·시나리오의 이전 값**을 보이지 않는다(placeholder 는 같은 리비전·
 *    시나리오 키일 때만) + '준비 중'.
 *  - M8: G5 '이후' 열과 열린 서랍은 그 Fact 가 나온 리비전의 snapshot_id 로 조회한다.
 *  - minor 17–23.
 */
import { act, renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ReactNode } from 'react';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { useComplexesProgressive } from '@/api/hooks';
import type { Dashboard, JobRun, Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { createTestQueryClient, renderRoute } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const pending503 = (retryAfter = '600') =>
  HttpResponse.json(
    { code: 'materialize_pending', detail: '발행 리비전 저장본을 만드는 중' },
    { status: 503, headers: { 'Retry-After': retryAfter } },
  );

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString()),
  );
  return (await res!.json()) as T;
}

const nowIso = () => new Date().toISOString();

function job(
  id: number,
  jobName: JobRun['job_name'],
  status: JobRun['status'],
  payload: Record<string, unknown> = {},
  stats: Record<string, unknown> = {},
  errorText: string | null = null,
): JobRun {
  return {
    id,
    job_name: jobName,
    kind: jobName === 'rejudge' ? 'rejudge' : 'manual',
    payload,
    scheduled_at: nowIso(),
    started_at: nowIso(),
    finished_at: status === 'done' || status === 'failed' ? nowIso() : null,
    status,
    stats,
    error_text: errorText,
    progress: null,
  };
}

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

// ─── M8 · minor 17 ──────────────────────────────────────────

/** 출처 조회 요청의 snapshot_id 들 */
function provSnapshots(rec: ReturnType<typeof recordRequests>, from = 0): (string | null)[] {
  return matching(rec.requests.slice(from), 'GET', /\/provenance\//).map((r) =>
    r.url.searchParams.get('snapshot_id'),
  );
}

describe('M8 G5 이후 열·열린 서랍은 그 Fact 가 나온 리비전으로 조회한다', () => {
  it("G5 diff: '이후' 총점 셀 → snapshot_id=13(새 리비전), '이전' 총점 셀 → 12(기준 리비전)", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const rev2: Snapshot = {
      ...s12,
      id: 13,
      revision: 2,
      revision_of: s12.id,
      created_at: nowIso(),
    };
    let done = false;
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(done ? [rev2, ...snapshots] : snapshots),
      ),
      http.get(mswPath('/snapshots/:sid/dashboard'), async ({ request, params }) => {
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        const d = (await res!.json()) as Dashboard;
        if (params.sid !== '13') return HttpResponse.json(d);
        const [a, b, ...rest] = d.top5;
        return HttpResponse.json({
          ...d,
          snapshot_id: 13,
          top5: [{ ...b!, rank: 1 }, { ...a!, rank: 2 }, ...rest],
        });
      }),
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        done = true;
        return HttpResponse.json(
          job(Number(params.id), 'rejudge', 'done', { snapshot_id: 12 }, { snapshot_id: 13 }),
        );
      }),
    );
    const rec = recordRequests();
    renderRoute(`/scenario?scenario=B&snapshot=${s12.id}`);
    const run = await screen.findByRole('button', { name: t('page.G5.run') });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    const table = await screen.findByRole('table', { name: t('page.G5.diff') });
    const row = within(table).getAllByRole('row')[1] as HTMLElement;
    const cells = within(row).getAllByRole('cell');
    // 열: 순위 이전·이후, 총점 이전·이후, Δrerank (이름은 th)
    const afterCell = cells[3]!.querySelector<HTMLButtonElement>('button[data-prov]')!;
    const beforeCell = cells[2]!.querySelector<HTMLButtonElement>('button[data-prov]')!;
    let mark = rec.requests.length;
    await userEvent.click(afterCell);
    await screen.findByRole('dialog', { name: t('provenance.title') });
    await waitFor(() => expect(provSnapshots(rec, mark).length).toBeGreaterThan(0));
    expect(provSnapshots(rec, mark).every((sid) => sid === '13')).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: t('provenance.close') }));

    mark = rec.requests.length;
    await userEvent.click(beforeCell);
    await screen.findByRole('dialog', { name: t('provenance.title') });
    await waitFor(() => expect(provSnapshots(rec, mark).length).toBeGreaterThan(0));
    expect(provSnapshots(rec, mark).every((sid) => sid === String(s12.id))).toBe(true);
    // 헤더(보고 있는 리비전)는 그대로 12
    expect(screen.getByLabelText(t('header.snapshot'))).toHaveValue(String(s12.id));
    rec.stop();
  });

  it('minor 17: 서랍을 연 채 리비전이 바뀌어도 서랍은 연 Fact 의 리비전(12)으로 남는다(404 없음)', async () => {
    const rec = recordRequests();
    const { router } = renderRoute('/?snapshot=12');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    await userEvent.click(
      (within(top5).getAllByRole('listitem')[0] as HTMLElement).querySelector<HTMLButtonElement>(
        'button[data-prov]',
      )!,
    );
    const dialog = await screen.findByRole('dialog', { name: t('provenance.title') });
    await within(dialog).findByText(t('provenance.url'));
    const mark = rec.requests.length;
    await act(() => router.navigate('/?snapshot=11'));
    await screen.findByLabelText(t('header.snapshot'));
    await waitFor(() => expect(screen.getByLabelText(t('header.snapshot'))).toHaveValue('11'));
    expect(provSnapshots(rec, mark).filter((sid) => sid === '11')).toEqual([]);
    expect(within(dialog).getByText(t('provenance.url'))).toBeInTheDocument();
    rec.stop();
  });
});

export { within };
