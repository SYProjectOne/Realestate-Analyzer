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
import { MemoryRouter } from 'react-router';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useComplexesProgressive } from '@/api/hooks';
import { MATERIALIZE_RETRY_MAX_DELAY_MS, queryRetry, queryRetryDelay } from '@/api/retryPolicy';
import type { Dashboard, JobRun, Region, Scenario, Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import {
  followPublish,
  PENDING_REVISION_MAX_AGE_MS,
  PUBLISH_FOLLOW_MAX_MS,
  publishPhase,
  publishTarget,
  snapshotsWatchExpired,
} from '@/api/jobWatch';
import { PublishJobProgress } from '@/components';
import { createTestQueryClient, renderRoute, renderWithProviders } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';
import { checkedAt422Kind } from './ops/HumanCheckForm';
import { revisionWithScenario } from './reports';

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

// ─── minor 19 · 21 ──────────────────────────────────────────

describe('minor 19: 발행 안내는 후속 snapshot.publish 잡이 끝날 때 닫고, publish_blocked 를 알린다', () => {
  const rejudge = job(900, 'rejudge', 'done', { snapshot_id: 12 }, { snapshot_id: 13 });

  it('publishTarget·followPublish: 그 리비전의 뒤 publish 잡 중 가장 새 것', () => {
    expect(publishTarget(rejudge)).toBe(13);
    expect(publishTarget(job(1, 'snapshot.publish', 'done', { snapshot_id: 14 }))).toBe(14);
    expect(publishTarget(job(2, 'rejudge', 'done', { snapshot_id: 12 }))).toBe(12);
    const list = [
      job(950, 'snapshot.publish', 'done', { snapshot_id: 13 }),
      job(951, 'snapshot.publish', 'queued', { snapshot_id: 13 }),
      job(952, 'snapshot.publish', 'queued', { snapshot_id: 99 }),
      job(800, 'snapshot.publish', 'done', { snapshot_id: 13 }),
    ];
    expect(followPublish(rejudge, list)?.id).toBe(951);
    expect(followPublish(rejudge, list.slice(2))).toBeNull();
    // 서버가 stats 로 알려 준 잡 id(있으면 그 잡도 후보)
    const told = job(901, 'rejudge', 'done', {}, { snapshot_id: 13, publish_job_id: 800 });
    expect(followPublish(told, [list[3]!])?.id).toBe(800);
  });

  it('publishPhase: 재판정 done 만으로는 닫지 않는다 → publish done 이면 발행, publish_blocked 면 막힘, 30분 넘으면 상한', () => {
    const t0 = 1_000_000;
    const base = {
      trigger: rejudge,
      follow: null,
      snapshot: undefined,
      listSettled: true,
      watchStart: t0,
      now: t0,
    };
    expect(publishPhase({ ...base, trigger: job(900, 'rejudge', 'running') }).kind).toBe('trigger');
    expect(publishPhase(base).kind).toBe('waiting');
    expect(
      publishPhase({
        ...base,
        follow: job(950, 'snapshot.publish', 'running', { snapshot_id: 13 }),
      }).kind,
    ).toBe('waiting');
    expect(
      publishPhase({ ...base, follow: job(950, 'snapshot.publish', 'done', { snapshot_id: 13 }) })
        .kind,
    ).toBe('published');
    const detail = 'publish_blocked: contradicted 2건';
    expect(
      publishPhase({
        ...base,
        follow: job(950, 'snapshot.publish', 'failed', { snapshot_id: 13 }, {}, detail),
      }),
    ).toEqual({ kind: 'blocked', detail });
    // done 이어도 stats.published=false 면 발행되지 않았다
    expect(
      publishPhase({
        ...base,
        follow: job(
          950,
          'snapshot.publish',
          'done',
          { snapshot_id: 13 },
          { published: false, contradicted: 2 },
        ),
      }).kind,
    ).toBe('blocked');
    expect(
      publishPhase({
        ...base,
        follow: job(950, 'snapshot.publish', 'failed', { snapshot_id: 13 }, {}, 'OperationalError'),
      }),
    ).toEqual({ kind: 'publishFailed', detail: 'OperationalError' });
    expect(publishPhase({ ...base, now: t0 + PUBLISH_FOLLOW_MAX_MS + 1 }).kind).toBe('expired');
    // 리비전 목록이 먼저 published 를 보여도 닫는다(잡 목록을 못 읽는 토큰)
    const snap = { id: 13, status: 'published' } as Snapshot;
    expect(publishPhase({ ...base, snapshot: snap }).kind).toBe('published');
    // 남은 모순 주장으로 ready 에 멈춘 리비전 = 막힘
    const stuck = { id: 13, status: 'ready', contradicted_claims: 2 } as Snapshot;
    expect(publishPhase({ ...base, snapshot: stuck }).kind).toBe('blocked');
    // 잡 자체가 publish 이고 뒤 잡이 없으면 그 잡으로 판단(목록을 받은 뒤)
    const pub = job(960, 'snapshot.publish', 'done', { snapshot_id: 14 }, { published: true });
    expect(publishPhase({ ...base, trigger: pub }).kind).toBe('published');
    expect(publishPhase({ ...base, trigger: pub, listSettled: false }).kind).toBe('waiting');
    // 발행을 같이 한 잡(stats.published, 계약 .11 region.expand) — 그 결과로 판단
    const expand = job(970, 'region.expand', 'done', {}, { snapshot_id: 13, published: true });
    expect(publishPhase({ ...base, trigger: expand }).kind).toBe('published');
    // 재판정 실패 = 발행 없음(잡 진행이 실패를 보인다)
    expect(publishPhase({ ...base, trigger: job(900, 'rejudge', 'failed') }).kind).toBe(
      'triggerFailed',
    );
  });

  it('화면: rejudge done 뒤에도 안내 유지 → 후속 publish done 이면 닫고 "발행됨"', async () => {
    let publishStatus: JobRun['status'] = 'running';
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) =>
        HttpResponse.json(
          job(Number(params.id), 'rejudge', 'done', { snapshot_id: 12 }, { snapshot_id: 13 }),
        ),
      ),
      http.get(mswPath('/jobs'), ({ request }) => {
        const q = new URL(request.url).searchParams;
        if (q.get('job_name') !== 'snapshot.publish') return HttpResponse.json([]);
        return HttpResponse.json([
          job(950, 'snapshot.publish', publishStatus, { snapshot_id: 13 }),
        ]);
      }),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={900} />
      </MemoryRouter>,
    );
    const box = await screen.findByTestId('publish-job');
    await within(box).findByText(t('job.status.done'));
    expect(within(box).getByTestId('publish-pending')).toHaveTextContent(t('job.publishPending'));
    expect(await within(box).findByText('snapshot.publish')).toBeInTheDocument();
    publishStatus = 'done';
    expect(await within(box).findByTestId('publish-done', {}, { timeout: 8000 })).toHaveTextContent(
      t('job.publishDone'),
    );
    expect(within(box).queryByTestId('publish-pending')).toBeNull();
  }, 15_000);

  it('화면: 후속 publish 가 publish_blocked 로 실패하면 막힘 안내', async () => {
    const detail = 'publish_blocked: contradicted 2건';
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) =>
        HttpResponse.json(
          job(Number(params.id), 'rejudge', 'done', { snapshot_id: 12 }, { snapshot_id: 13 }),
        ),
      ),
      http.get(mswPath('/jobs'), () =>
        HttpResponse.json([
          job(950, 'snapshot.publish', 'failed', { snapshot_id: 13 }, {}, detail),
        ]),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={900} />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('publish-blocked')).toHaveTextContent(
      t('job.publishBlocked', { detail }),
    );
    expect(screen.queryByTestId('publish-pending')).toBeNull();
  });
});

describe('minor 21: 발행 대기 감시가 30분 상한에 닿으면 조용히 멈추지 않고 알린다', () => {
  const ready = (createdAgoMs: number, now: number): Snapshot =>
    ({
      id: 13,
      region_id: 1,
      asof_date: '2026-10-08',
      revision: 2,
      status: 'ready',
      degraded: false,
      contradicted_claims: 0,
      created_at: new Date(now - createdAgoMs).toISOString(),
    }) as Snapshot;

  it('snapshotsWatchExpired: 잡을 모르는(forbidden·truncated·failed) 채 생성 30분이 지나면 true', () => {
    const now = Date.parse('2026-10-11T00:00:00Z');
    const old = [ready(PENDING_REVISION_MAX_AGE_MS + 60_000, now)];
    const young = [ready(60_000, now)];
    expect(snapshotsWatchExpired(old, now, 'forbidden')).toBe(true);
    expect(snapshotsWatchExpired(old, now, 'truncated')).toBe(true);
    expect(snapshotsWatchExpired(old, now, { failed: 2 })).toBe(true);
    expect(snapshotsWatchExpired(young, now, 'forbidden')).toBe(false);
    // 잡을 알면 상한이 아니라 잡 기준(진행 잡 없음 = 끝남)
    expect(snapshotsWatchExpired(old, now, [])).toBe(false);
    expect(snapshotsWatchExpired(old, now, 'unread')).toBe(false);
    expect(snapshotsWatchExpired([], now, 'forbidden')).toBe(false);
  });

  it('헤더: 30분 넘은 발행 대기 리비전 + /jobs 403 → 상한 안내와 다시 확인 버튼', async () => {
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const stale: Snapshot = {
      ...snapshots[0]!,
      id: 13,
      revision: 2,
      status: 'ready',
      published_at: null,
      contradicted_claims: 0,
      degraded: false,
      created_at: new Date(Date.now() - PENDING_REVISION_MAX_AGE_MS - 60_000).toISOString(),
    };
    let listCalls = 0;
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => {
        listCalls += 1;
        return HttpResponse.json([stale, ...snapshots]);
      }),
      http.get(mswPath('/jobs'), () =>
        HttpResponse.json({ code: 'forbidden', detail: '공유 링크' }, { status: 403 }),
      ),
    );
    renderRoute('/');
    const notice = await screen.findByTestId('publish-watch-expired', {}, { timeout: 8000 });
    expect(notice).toHaveTextContent(t('job.watchExpired'));
    const before = listCalls;
    await userEvent.click(within(notice).getByRole('button', { name: t('job.watchRecheck') }));
    await waitFor(() => expect(listCalls).toBeGreaterThan(before));
  }, 15_000);
});

// ─── minor 20 ───────────────────────────────────────────────

describe('minor 20: 사람 확인 checked_at 422 는 서버 code/detail 로 가른다(클라이언트 시계 아님)', () => {
  const futureDetail =
    '확인 시각 2026-10-11T12:00:00+09:00 은 지금(2026-10-11T11:00:00+09:00)보다 10분 넘게 미래다 — 실제로 확인한 시각을 적는다';
  const earlyDetail =
    '확인일 2026-10-01(KST) 은 이미 수집된 공식 공고(관측 2026-10-05, 다른 값)보다 이르다 — 그 공고 뒤에 다시 확인한 날짜를 적는다';
  const formatDetail = "확인 시각 'x' 은 시간대가 붙은 RFC3339 날짜·시각이 아니다";
  const err = (detail: string, code: 'validation_error' = 'validation_error') =>
    new ApiError(code, detail, 422, [{ loc: ['body', 'checked_at'], msg: detail }]);

  it('checkedAt422Kind: 서버 문구로 미래·이른 확인일·그 밖', () => {
    expect(checkedAt422Kind(err(futureDetail))).toBe('future');
    expect(checkedAt422Kind(err(earlyDetail))).toBe('early');
    expect(checkedAt422Kind(err(formatDetail))).toBe('other');
    expect(checkedAt422Kind(new ApiError('validation_error', 'x', 422))).toBeNull();
    expect(checkedAt422Kind(new ApiError('internal', 'x', 500))).toBeNull();
  });

  async function fillAndSubmit() {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    // 확인 시각 = 기본값(지금) — 브라우저 시계로는 미래가 아니다
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    return form;
  }

  it('보낸 시각이 브라우저 시계로 과거여도 서버가 "미래" 422 면 미래 안내(이른 확인일 아님)', async () => {
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail: futureDetail,
            field_errors: [{ loc: ['body', 'checked_at'], msg: futureDetail }],
          },
          { status: 422 },
        ),
      ),
    );
    const form = await fillAndSubmit();
    expect(
      await within(form).findByText(t('page.G7.hc.checkedAtFuture', { detail: futureDetail })),
    ).toBeInTheDocument();
  });

  it('서버가 이른 확인일 422 면 이른 확인일 안내, 그 밖의 checked_at 422 는 서버 문구 그대로', async () => {
    let detail = earlyDetail;
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail,
            field_errors: [{ loc: ['body', 'checked_at'], msg: detail }],
          },
          { status: 422 },
        ),
      ),
    );
    const form = await fillAndSubmit();
    expect(
      await within(form).findByText(t('page.G7.hc.checkedAtTooEarly', { detail: earlyDetail })),
    ).toBeInTheDocument();
    detail = formatDetail;
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    expect(
      await within(form).findByText(t('page.G7.hc.checkedAtServer', { detail: formatDetail })),
    ).toBeInTheDocument();
  });
});

// ─── minor 22 ───────────────────────────────────────────────

describe('minor 22: G8 지역을 바꾸면 이전 지역의 생성 오류·잡 진행을 지운다', () => {
  it('409 오류가 난 뒤 지역을 바꾸면 오류 문구가 사라진다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const regions = await example<Region[]>('/regions');
    const other: Region = { ...regions[0]!, id: 2, name: '다른 지역', latest_snapshot: null };
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([...regions, other])),
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          { code: 'publish_blocked', detail: '남은 모순 주장 2건' },
          { status: 409 },
        ),
      ),
    );
    const { router } = renderRoute('/reports?region=1');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const msg = t('page.G8.conflict', { detail: '남은 모순 주장 2건' });
    expect(await screen.findByText(msg)).toBeInTheDocument();
    await act(() => router.navigate('/reports?region=2'));
    await waitFor(() => expect(screen.queryByText(msg)).toBeNull());
  });

  it('잡을 등록한 뒤 지역을 바꾸면 그 잡 진행을 내린다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const regions = await example<Region[]>('/regions');
    const other: Region = { ...regions[0]!, id: 2, name: '다른 지역', latest_snapshot: null };
    server.use(http.get(mswPath('/regions'), () => HttpResponse.json([...regions, other])));
    const { router } = renderRoute('/reports?region=1');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByText(t('job.title'))).toBeInTheDocument();
    await act(() => router.navigate('/reports?region=2'));
    await waitFor(() => expect(screen.queryByText(t('job.title'))).toBeNull());
  });
});

// ─── minor 23 ───────────────────────────────────────────────

describe('minor 23: 재시도 규칙·추천 리비전 버튼', () => {
  it('stored_view_mismatch(500) 는 운영 기본(base 1)에서도 다시 부르지 않는다', () => {
    const mismatch = new ApiError('stored_view_mismatch', 'sha256', 500);
    expect(queryRetry(1)(0, mismatch)).toBe(false);
    expect(queryRetry(1)(0, new ApiError('internal', 'x', 500))).toBe(true);
  });

  it('Retry-After 를 30초로 자르지 않는다(서버가 준 간격 그대로, 비정상 값만 상한)', () => {
    const after = (ms: number) => new ApiError('materialize_pending', 'x', 503, [], null, ms);
    expect(queryRetryDelay(0, after(120_000))).toBe(120_000);
    expect(queryRetryDelay(0, after(0))).toBe(500);
    expect(queryRetryDelay(0, after(10 * 3600_000))).toBe(MATERIALIZE_RETRY_MAX_DELAY_MS);
  });

  it('G8: 서버가 422 scenario_not_in_revision 인데 화면이 맞다고 본 리비전이 가장 새 것이면 — 같은 리비전을 추천(숨김)하지 않고 다른 리비전 또는 시나리오 실행 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const s13: Snapshot = {
      ...s12,
      id: 13,
      revision: 2,
      revision_of: 12,
      published_at: '2026-10-09T12:00:00+09:00',
      created_at: '2026-10-09T11:50:00+09:00',
    };
    const scenarios = await example<Scenario[]>('/scenarios');
    const base = scenarios.find((s) => s.code === 'base')!;
    // 화면 기준으로는 리비전 13 발행 전에 만든 시나리오(13 에 있다고 본다) — 서버는 13 에 없다고 거절
    const mine: Scenario = {
      ...base,
      id: 9,
      code: null,
      name: '내 조건 9',
      is_builtin: false,
      created_at: '2026-10-09T10:00:00+09:00',
    };
    const detail = '시나리오 9 는 리비전 13 에 없다';
    const list: Snapshot[] = [s13, ...snapshots];
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json(list)),
      http.get(mswPath('/scenarios'), () => HttpResponse.json([...scenarios, mine])),
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          {
            code: 'scenario_not_in_revision',
            detail,
            field_errors: [{ loc: ['body', 'scenario_id'], msg: detail }],
          },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/reports?snapshot=13&scenario=9');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(
      await screen.findByText(t('page.G8.scenarioNotInRevisionServer', { detail })),
    ).toBeInTheDocument();
    // 거절된 13 말고 결과가 있을 리비전이 없다 → 시나리오 실행으로 안내(버튼을 숨긴 채 두지 않는다)
    const run = await screen.findByTestId('g8-run-scenario');
    expect(run).toHaveTextContent(t('page.common.scenarioMissingRun'));
    expect(screen.queryByTestId('g8-pick-scenario-revision')).toBeNull();
  });

  it('revisionWithScenario: 서버가 거절한 리비전은 후보에서 뺀다', async () => {
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const s13: Snapshot = {
      ...s12,
      id: 13,
      revision: 2,
      published_at: '2026-10-09T12:00:00+09:00',
    };
    const s14: Snapshot = {
      ...s12,
      id: 14,
      revision: 3,
      published_at: '2026-10-09T13:00:00+09:00',
    };
    const scenarios = await example<Scenario[]>('/scenarios');
    const mine: Scenario = {
      ...scenarios[0]!,
      id: 9,
      code: null,
      is_builtin: false,
      created_at: '2026-10-09T10:00:00+09:00',
    };
    expect(revisionWithScenario([s14, s13], mine)?.id).toBe(14);
    expect(revisionWithScenario([s14, s13], mine, 14)?.id).toBe(13);
    expect(revisionWithScenario([s13], mine, 13)).toBeNull();
  });
});

export { within };
