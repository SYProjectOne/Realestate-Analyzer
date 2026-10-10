/**
 * R3f(6차 리뷰 `R3_REVIEW6.md`) FE5 1단계 — 화면 minor 21–25(20 할인 기본값은 complex/discount.test.tsx):
 *  - 21 G8: 지역을 바꾸면 이전 지역 기준·비교 리비전을 보내지 않는다, 기준 = 비교 같은 리비전을 보내지 않는다.
 *  - 22 useJob: 일시 오류(5xx·네트워크)면 늦춰 가며 다시 조회한다(한 번 오류로 영구 중단 금지). 4xx 는 멈춘다.
 *  - 23 발행 대기 폴링: `/jobs` 를 size 최대로 읽고(기본 50건에 잘린 목록으로 멈추지 않음), `/jobs`·목록 5xx 동안은
 *    3초 고정 폴링이 아니라 늦춰 가며, 잡을 모르면 생성 후 30분 제한으로 돌아간다.
 *  - 24 시나리오 404 안내: code 가 not_found 이고 그 시나리오가 리비전 발행 **뒤에** 만들어졌을 때만(다른 404 는 일반 오류).
 *  - 25 G5 '이후' 조회 실패 → 오류 문구 + 다시 시도(받는 중 문구로 멈추지 않는다).
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ReactNode } from 'react';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { ApiError } from '@/api/client';
import {
  fetchActiveJobs,
  JOBS_SCAN_SIZE,
  jobRefetchInterval,
  useJob,
  useSnapshots,
} from '@/api/hooks';
import {
  failedRound,
  PENDING_REVISION_POLL_MS,
  POLL_BACKOFF_MAX_MS,
  POLL_ERROR_MAX_STREAK,
  snapshotsRefetchInterval,
} from '@/api/jobWatch';
import type { Dashboard, JobRun, Region, Scenario, Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { JobProgressView } from '@/components/JobProgress';
import { createTestQueryClient, renderRoute, renderWithProviders } from '@/test/render';
import { isScenarioMissing } from './_shared';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString()),
  );
  return (await res!.json()) as T;
}

const nowIso = () => new Date().toISOString();
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function job(
  id: number,
  jobName: JobRun['job_name'],
  status: JobRun['status'],
  payload: Record<string, unknown> = {},
  stats: Record<string, unknown> = {},
): JobRun {
  return {
    id,
    job_name: jobName,
    kind: jobName === 'rejudge' ? 'rejudge' : 'scheduled',
    payload,
    scheduled_at: nowIso(),
    started_at: nowIso(),
    finished_at: status === 'done' || status === 'failed' ? nowIso() : null,
    status,
    stats,
    error_text: status === 'failed' ? '실패' : null,
    progress: null,
  };
}

function wrapper() {
  const qc = createTestQueryClient();
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrapper };
}

// ─── 21 G8 지역 변경·같은 리비전 비교 ──────────────────────

describe('G8 기준·비교 리비전은 지금 지역의 것만, 서로 달라야 한다 (6차 minor 21)', () => {
  async function twoRegions() {
    const regions = await example<Region[]>('/regions');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const r1 = regions[0]!;
    const s12 = snapshots[0]!;
    const s22: Snapshot = { ...s12, id: 22, region_id: 2 };
    const s21: Snapshot = { ...s12, id: 21, region_id: 2, asof_date: '2026-10-07' };
    const r2: Region = { ...r1, id: 2, name: '테스트 지역 둘', latest_snapshot: s22 };
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([r1, r2])),
      http.get(mswPath('/regions/:id/snapshots'), ({ params }) =>
        HttpResponse.json(String(params.id) === '2' ? [s22, s21] : snapshots),
      ),
    );
    return { snapshots };
  }

  it('지역을 바꾸면 이전 지역에서 고른 기준·비교 리비전을 POST 하지 않는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    await twoRegions();
    const rec = recordRequests();
    renderRoute('/reports?region=1');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    const base = screen.getByLabelText(t('page.G8.snapshot'));
    await waitFor(() => expect(base.querySelector('option[value="12"]')).not.toBeNull());
    await userEvent.selectOptions(base, '12');
    const compare = screen.getByLabelText(t('page.G8.compareSnapshot'));
    await userEvent.selectOptions(compare, '11');

    await userEvent.selectOptions(screen.getByLabelText(t('header.region')), '2');
    await waitFor(() =>
      expect(
        screen.getByLabelText(t('page.G8.compareSnapshot')).querySelector('option[value="21"]'),
      ).not.toBeNull(),
    );
    expect(screen.getByLabelText(t('page.G8.snapshot'))).toHaveValue('22');
    expect(screen.getByLabelText(t('page.G8.compareSnapshot'))).toHaveValue('');
    await userEvent.click(screen.getByRole('button', { name: t('page.G8.generate') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/reports')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/reports')[0]!.body) as {
      snapshot_id: number;
      compare_snapshot_id: number | null;
    };
    expect(body.snapshot_id).toBe(22);
    expect(body.compare_snapshot_id).toBeNull();
    rec.stop();
  });

  it('비교로 고른 리비전을 기준으로 바꾸면 비교는 없음으로 — 같은 id 를 비교로 보내지 않는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    const compare = screen.getByLabelText(t('page.G8.compareSnapshot'));
    await waitFor(() => expect(compare.querySelector('option[value="11"]')).not.toBeNull());
    await userEvent.selectOptions(compare, '11');
    await userEvent.selectOptions(screen.getByLabelText(t('page.G8.snapshot')), '11');
    expect(compare).toHaveValue('');
    await userEvent.click(button);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/reports')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/reports')[0]!.body) as {
      snapshot_id: number;
      compare_snapshot_id: number | null;
    };
    expect(body).toMatchObject({ snapshot_id: 11, compare_snapshot_id: null });
    // 비교 diff 도 같은 id 로 부르지 않는다
    expect(
      matching(rec.requests, 'GET', '/changes').some(
        (r) =>
          r.url.searchParams.get('compare_snapshot') === '11' && r.url.pathname.includes('/11/'),
      ),
    ).toBe(false);
    rec.stop();
  });
});

// ─── 22 useJob 일시 오류 재시도 ────────────────────────────

describe('useJob: 일시 오류는 늦춰 가며 다시 조회, 4xx 는 멈춤 (6차 minor 22)', () => {
  it('jobRefetchInterval: 5xx·네트워크 → 늦춘 간격, 4xx → 멈춤, 연속 오류 상한 → 멈춤', () => {
    const e503 = new ApiError('internal', 'busy', 503);
    const eNet = new ApiError('network', 'offline', null);
    const e404 = new ApiError('not_found', 'job 9', 404);
    const e403 = new ApiError('forbidden', 'share', 403);
    expect(jobRefetchInterval({ status: 'error', error: e503 }, 100, 1)).toBe(200);
    expect(jobRefetchInterval({ status: 'error', error: eNet }, 100, 2)).toBe(400);
    expect(jobRefetchInterval({ status: 'error', error: e404 }, 100, 1)).toBe(false);
    expect(jobRefetchInterval({ status: 'error', error: e403 }, 100, 1)).toBe(false);
    expect(
      jobRefetchInterval({ status: 'error', error: e503 }, 100, POLL_ERROR_MAX_STREAK + 1),
    ).toBe(false);
    // 늦추기 상한
    expect(jobRefetchInterval({ status: 'error', error: e503 }, 10_000, 5)).toBe(
      POLL_BACKOFF_MAX_MS,
    );
    // 정상 상태는 그대로
    expect(jobRefetchInterval({ status: 'success', data: { status: 'running' } }, 100)).toBe(100);
    expect(jobRefetchInterval({ status: 'success', data: { status: 'done' } }, 100)).toBe(false);
  });

  it('GET /jobs/{id} 503 한 번 → 다시 조회해 running → done 까지 따라간다', async () => {
    let calls = 0;
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ code: 'internal', detail: 'busy' }, { status: 503 });
        }
        return HttpResponse.json(
          job(Number(params.id), 'rejudge', calls === 2 ? 'running' : 'done'),
        );
      }),
    );
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useJob('77', 30), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.data?.status).toBe('done'));
    expect(result.current.error).toBeNull();
    expect(calls).toBe(3);
  });

  it('JobProgressView: 받아 둔 잡이 있으면 일시 오류 동안 마지막 상태 + 다시 확인 중 줄', () => {
    const err = new ApiError('internal', 'busy', 503);
    renderWithProviders(<JobProgressView job={job(5, 'rejudge', 'running')} error={err} />);
    const box = screen.getByRole('status');
    expect(box).toHaveAttribute('data-status', 'running');
    expect(within(box).getByTestId('job-retrying')).toHaveTextContent(
      t('job.retrying', { detail: err.message }),
    );
  });
});

// ─── 23 /jobs size·5xx 늦추기 ──────────────────────────────

describe('발행 대기 폴링: /jobs 는 최대 size, 5xx 동안은 늦춘다 (6차 minor 23)', () => {
  async function revs() {
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const rev2: Snapshot = {
      ...s12,
      id: 13,
      revision: 2,
      revision_of: s12.id,
      status: 'ready',
      published_at: null,
      contradicted_claims: 0,
      created_at: '2026-01-01T00:00:00Z',
    };
    return { snapshots, rev2 };
  }

  it('fetchActiveJobs: queued·running 을 size=JOBS_SCAN_SIZE 로 읽는다', async () => {
    server.use(http.get(mswPath('/jobs'), () => HttpResponse.json([])));
    const rec = recordRequests();
    const got = await fetchActiveJobs(new AbortController().signal);
    expect(got).toEqual([]);
    const reqs = matching(rec.requests, 'GET', '/jobs');
    expect(reqs.map((r) => r.url.searchParams.get('status')).sort()).toEqual(['queued', 'running']);
    for (const r of reqs) expect(r.url.searchParams.get('size')).toBe(String(JOBS_SCAN_SIZE));
    rec.stop();
  });

  it('fetchActiveJobs: 목록이 size 에 꽉 차면(잘렸을 수 있음) truncated — 잘린 목록으로 멈추지 않되 생성 후 30분 상한', async () => {
    const many = Array.from({ length: JOBS_SCAN_SIZE }, (_, i) =>
      job(1000 + i, 'collect.daily', 'queued', { region_id: 99 }),
    );
    server.use(
      http.get(mswPath('/jobs'), ({ request }) =>
        HttpResponse.json(new URL(request.url).searchParams.get('status') === 'queued' ? many : []),
      ),
    );
    expect(await fetchActiveJobs(new AbortController().signal)).toBe('truncated');
    // 잘린 차례는 잡으로 멈추지 않지만 상한 없는 폴링도 아니다 — 생성 후 30분까지만(CEO 지시 a)
    const { snapshots, rev2 } = await revs();
    const now = Date.now();
    expect(
      snapshotsRefetchInterval([{ ...rev2, created_at: nowIso() }, ...snapshots], now, 'truncated'),
    ).toBe(PENDING_REVISION_POLL_MS);
    expect(snapshotsRefetchInterval([rev2, ...snapshots], now, 'truncated')).toBe(false);
  });

  it('snapshotsRefetchInterval: /jobs 실패 차례는 늦추고 30분 제한, 목록 자체 연속 오류도 늦추고 상한에서 멈춤', async () => {
    const { snapshots, rev2 } = await revs();
    const now = Date.now();
    const young = [{ ...rev2, created_at: nowIso() }, ...snapshots];
    const old = [rev2, ...snapshots];
    const publish = job(1, 'snapshot.publish', 'running', { snapshot_id: 13 });
    // 연속 실패 횟수: 이전 차례 기준 +1
    expect(failedRound('unread')).toEqual({ failed: 1 });
    expect(failedRound({ failed: 2 })).toEqual({ failed: 3 });
    expect(failedRound([publish])).toEqual({ failed: 1 });
    expect(snapshotsRefetchInterval(young, now, { failed: 1 })).toBe(PENDING_REVISION_POLL_MS * 2);
    expect(snapshotsRefetchInterval(young, now, { failed: 2 })).toBe(PENDING_REVISION_POLL_MS * 4);
    expect(snapshotsRefetchInterval(young, now, { failed: 20 })).toBe(POLL_BACKOFF_MAX_MS);
    // 잡을 모르는 채 오래된 리비전은 멈춘다(공유 링크와 같은 30분 제한)
    expect(snapshotsRefetchInterval(old, now, { failed: 1 })).toBe(false);
    // 목록 조회 자체가 연속 실패: 늦추고, 상한을 넘으면 멈춘다
    expect(snapshotsRefetchInterval(old, now, [publish], 1)).toBe(PENDING_REVISION_POLL_MS * 2);
    expect(snapshotsRefetchInterval(old, now, [publish], POLL_ERROR_MAX_STREAK + 1)).toBe(false);
    expect(snapshotsRefetchInterval(old, now, [publish], 0)).toBe(PENDING_REVISION_POLL_MS);
  });

  it('/jobs 가 5xx 를 계속 내면 3초마다 목록을 다시 부르지 않는다', async () => {
    const { snapshots, rev2 } = await revs();
    const fresh = { ...rev2, created_at: nowIso() };
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([fresh, ...snapshots])),
      http.get(mswPath('/jobs'), () =>
        HttpResponse.json({ code: 'internal', detail: 'down' }, { status: 500 }),
      ),
    );
    const rec = recordRequests();
    const { Wrapper } = wrapper();
    renderHook(() => useSnapshots(1), { wrapper: Wrapper });
    const lists = () => matching(rec.requests, 'GET', /\/regions\/1\/snapshots$/).length;
    // 첫 목록(잡 안 읽음) → 3초 뒤 두 번째(이때 /jobs 500) → 그다음은 6초 뒤
    await waitFor(() => expect(lists()).toBe(2), { timeout: PENDING_REVISION_POLL_MS * 2 });
    await sleep(PENDING_REVISION_POLL_MS + 1500);
    expect(lists()).toBe(2);
    rec.stop();
  }, 20_000);
});

// ─── 24 시나리오 404 안내는 code·생성 시각 확인 ─────────────

describe('시나리오 없음 안내는 그 시나리오가 발행 뒤에 만들어진 not_found 일 때만 (6차 minor 24)', () => {
  const published = { status: 'published', published_at: '2026-10-08T07:42:10+09:00' } as const;
  const scenario = (id: number, createdAt: string): Scenario =>
    ({
      id,
      code: null,
      name: `사용자 ${id}`,
      is_builtin: false,
      params: {},
      weights: {},
      requirements: {},
      policy: {},
      created_at: createdAt,
    }) as unknown as Scenario;
  const after = scenario(9, '2026-10-09T10:00:00+09:00');
  const before = scenario(8, '2026-10-01T10:00:00+09:00');

  it('isScenarioMissing: not_found + 발행 뒤 생성만 참', () => {
    const e404 = new ApiError('not_found', 'x', 404);
    expect(isScenarioMissing(e404, '9', published, [after])).toBe(true);
    // 발행 전에 만든 시나리오는 저장본이 있다 → 이 404 는 다른 것(단지·생활권 없음)
    expect(isScenarioMissing(e404, '8', published, [before])).toBe(false);
    // 목록에 없는 시나리오(삭제됨·없는 id) → 실행 안내가 아니다
    expect(isScenarioMissing(e404, '7', published, [after, before])).toBe(false);
    // 시나리오 목록을 아직 모르면 단정하지 않는다
    expect(isScenarioMissing(e404, '9', published, undefined)).toBe(false);
    // 계약 Error 본문이 없는 404(프록시 등 — code 'http')
    expect(isScenarioMissing(new ApiError('http', 'Not Found', 404), '9', published, [after])).toBe(
      false,
    );
    expect(isScenarioMissing(e404, '9', { status: 'ready', published_at: null }, [after])).toBe(
      false,
    );
  });

  it('G1 ?scenario=8(발행 전 생성) + 404 → 일반 오류, 시나리오 실행 안내 아님', async () => {
    const list = await example<Scenario[]>('/scenarios');
    server.use(
      http.get(mswPath('/scenarios'), () => HttpResponse.json([...list, before])),
      http.get(mswPath('/snapshots/:sid/dashboard'), () =>
        HttpResponse.json(
          { code: 'not_found', detail: 'complex 5 not in snapshot' },
          { status: 404 },
        ),
      ),
    );
    renderRoute('/?scenario=8');
    expect(await screen.findByText(/complex 5 not in snapshot/)).toBeInTheDocument();
    expect(screen.queryByTestId('scenario-missing')).toBeNull();
  });
});

// ─── 25 G5 '이후' 조회 실패 ────────────────────────────────

describe("G5 '이후' 조회 실패 → 오류 문구 + 다시 시도 (6차 minor 25)", () => {
  it('새 리비전 대시보드 500 → 받는 중 문구 대신 오류, 다시 시도하면 표', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    let fail = true;
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), async ({ params, request }) => {
        if (String(params.sid) === '13' && fail) {
          return HttpResponse.json({ code: 'internal', detail: 'boom' }, { status: 500 });
        }
        const url = new URL(request.url);
        url.pathname = url.pathname.replace(/\/snapshots\/\d+\//, `/snapshots/${s12.id}/`);
        const res = await getResponse(generatedHandlers as RequestHandler[], new Request(url));
        return HttpResponse.json((await res!.json()) as Dashboard);
      }),
      http.get(mswPath('/jobs/:id'), ({ params }) =>
        HttpResponse.json(job(Number(params.id), 'rejudge', 'done', {}, { snapshot_id: 13 })),
      ),
    );
    renderRoute(`/scenario?scenario=B&snapshot=${s12.id}`);
    const run = await screen.findByRole('button', { name: t('page.G5.run') });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    const err = await screen.findByTestId('g5-after-error');
    expect(err).toHaveAttribute('role', 'alert');
    expect(err).toHaveTextContent(t('page.G5.afterError', { detail: 'internal: boom' }));
    expect(screen.queryByTestId('g5-after-loading')).toBeNull();
    fail = false;
    await userEvent.click(within(err).getByRole('button', { name: t('app.retry') }));
    expect(await screen.findByRole('table', { name: t('page.G5.diff') })).toBeInTheDocument();
    expect(screen.queryByTestId('g5-after-error')).toBeNull();
  });
});
