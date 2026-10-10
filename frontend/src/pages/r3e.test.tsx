/**
 * R3e(5차 리뷰) FE4 화면 minor:
 *  - useJob: 조회 오류면 폴링을 멈춘다(무한 폴링).
 *  - jobWatch: 발행 대기 리비전 폴링 = 그 리비전을 진행할 잡이 끝날 때까지(30분 제한 대신), 실패 잡 리비전은 멈춤.
 *  - G5 '이후': 캐시에 남은 옛 대시보드로 잠깐 '변화 없음'이 보이지 않는다.
 *  - G6 시장: 상황 토글(?scenario=)을 서버에 보낸다(계약 .10).
 *  - G8: 발행 전(ready) 기준이면 생성 막음 + 안내, 409(conflict) 안내, 비교 선택은 발행 리비전만.
 *  - 계약 .10: 발행 뒤 만든 시나리오 404 → 시나리오 실행 안내, 사람 확인 이른 확인일 422 → 확인일 칸 오류.
 * (할인 discount_applied 는 complex/discount.test.tsx, safeHref 는 lib/safeHref.test.tsx,
 *  실거래 건수 n_trades Fact 는 r3c.test.tsx)
 */
import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ReactNode } from 'react';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { ApiError } from '@/api/client';
import { jobRefetchInterval, useJob, useSnapshots } from '@/api/hooks';
import {
  advancesRevision,
  isAwaitingPublish,
  PENDING_REVISION_POLL_MS,
  snapshotsRefetchInterval,
} from '@/api/jobWatch';
import type { Dashboard, JobRun, Snapshot } from '@/api/types';
import { snapshotText } from '@/components/SnapshotPicker';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { createTestQueryClient, renderRoute } from '@/test/render';
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ─── useJob 오류 → 폴링 멈춤 ───────────────────────────────

describe('useJob 오류면 폴링을 멈춘다 (5차 minor)', () => {
  it('jobRefetchInterval: error → false, done·failed → false, 진행 중 → 간격', () => {
    expect(jobRefetchInterval({ status: 'error' }, 100)).toBe(false);
    expect(jobRefetchInterval({ status: 'error', data: { status: 'running' } }, 100)).toBe(false);
    expect(jobRefetchInterval({ status: 'success', data: { status: 'done' } }, 100)).toBe(false);
    expect(jobRefetchInterval({ status: 'success', data: { status: 'failed' } }, 100)).toBe(false);
    expect(jobRefetchInterval({ status: 'success', data: { status: 'running' } }, 100)).toBe(100);
    expect(jobRefetchInterval({ status: 'pending' }, 100)).toBe(100);
  });

  it('GET /jobs/{id} 404 → 한 번 실패 뒤 다시 부르지 않는다', async () => {
    server.use(
      http.get(mswPath('/jobs/:id'), () =>
        HttpResponse.json({ code: 'not_found', detail: 'job 999' }, { status: 404 }),
      ),
    );
    const rec = recordRequests();
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useJob('999', 30), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const n = matching(rec.requests, 'GET', '/jobs/999').length;
    await sleep(200); // 폴링 간격(30ms)의 여러 배
    expect(matching(rec.requests, 'GET', '/jobs/999')).toHaveLength(n);
    expect(n).toBe(1);
    rec.stop();
  });
});

// ─── jobWatch: 잡 기준 발행 대기 폴링 ──────────────────────

describe('발행 대기 리비전 폴링 = 잡이 끝날 때까지 (5차 minor)', () => {
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
      created_at: '2026-01-01T00:00:00Z', // 30분보다 오래됨 — 잡이 남았으면 그래도 폴링
    };
    return { snapshots, s12, rev2 };
  }

  it('advancesRevision: 대기·진행 중이고 이 지역(스냅샷) 잡만, 보고서·백업은 아니다', async () => {
    const { snapshots, rev2 } = await revs();
    const list = [rev2, ...snapshots];
    expect(advancesRevision(job(1, 'snapshot.publish', 'queued', { snapshot_id: 13 }), list)).toBe(
      true,
    );
    expect(advancesRevision(job(2, 'rejudge', 'running', { snapshot_id: 12 }), list)).toBe(true);
    expect(advancesRevision(job(3, 'region.expand', 'running', { region_id: 1 }), list)).toBe(true);
    expect(advancesRevision(job(4, 'collect.daily', 'queued', { region_id: 2 }), list)).toBe(false);
    expect(advancesRevision(job(5, 'rejudge', 'queued', { snapshot_id: 99 }), list)).toBe(false);
    expect(advancesRevision(job(6, 'report', 'running', { snapshot_id: 13 }), list)).toBe(false);
    expect(advancesRevision(job(7, 'backup', 'running'), list)).toBe(false);
    expect(advancesRevision(job(8, 'snapshot.publish', 'failed', { snapshot_id: 13 }), list)).toBe(
      false,
    );
  });

  it('snapshotsRefetchInterval: 잡이 남으면 30분이 지나도 폴링, 잡이 없으면 멈춤, 못 읽었으면 한 번 더', async () => {
    const { snapshots, rev2 } = await revs();
    const list = [rev2, ...snapshots];
    const now = Date.now();
    const publish = job(1, 'snapshot.publish', 'running', { snapshot_id: 13 });
    // 잡을 읽을 수 없으면(공유 링크) 생성 후 30분 제한 — 이 리비전은 오래됐다
    expect(snapshotsRefetchInterval(list, now, 'forbidden')).toBe(false);
    expect(snapshotsRefetchInterval([{ ...rev2, created_at: nowIso() }, ...snapshots], now)).toBe(
      PENDING_REVISION_POLL_MS,
    );
    // 진행 중 잡이 있으면 시간과 무관하게 폴링
    expect(snapshotsRefetchInterval(list, now, [publish])).toBe(PENDING_REVISION_POLL_MS);
    // 이번 차례에 잡을 못 읽었으면(첫 조회) 한 번 더 — 다음 차례에 잡을 읽는다
    expect(snapshotsRefetchInterval(list, now, 'unread')).toBe(PENDING_REVISION_POLL_MS);
    // 목록 직전에 읽은 잡이 없다(발행 실패) → 멈춤
    expect(snapshotsRefetchInterval(list, now, [])).toBe(false);
    // 관계없는 잡(다른 지역·보고서)만 남았으면 멈춤
    const other = [
      job(2, 'collect.daily', 'running', { region_id: 2 }),
      job(3, 'report', 'queued'),
    ];
    expect(snapshotsRefetchInterval(list, now, other)).toBe(false);
    // 발행 대기 리비전이 없으면 잡과 무관하게 멈춤
    expect(snapshotsRefetchInterval(snapshots, now, [publish])).toBe(false);
  });

  it('더 뒤 발행 리비전에 밀려난 ready 리비전은 기다리지 않는다', async () => {
    const { snapshots } = await revs();
    const old = snapshots.find((s) => s.status === 'ready')!; // 예시: 2026-10-06 ready
    expect(isAwaitingPublish(old)).toBe(true);
    expect(isAwaitingPublish(old, snapshots)).toBe(false);
    expect(snapshotsRefetchInterval(snapshots, Date.parse(old.created_at))).toBe(false);
  });

  it('잡이 실패해 building 으로 남은 리비전: 진행 중 잡이 없으면 목록 폴링을 멈춘다', async () => {
    const { snapshots, rev2 } = await revs();
    const building = { ...rev2, status: 'building' as const, created_at: nowIso() };
    let activeCalls = 0;
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json([building, ...snapshots]),
      ),
      http.get(mswPath('/jobs'), ({ request }) => {
        const status = new URL(request.url).searchParams.get('status');
        activeCalls += 1;
        // 첫 조회: rejudge 가 아직 돌고 있다 → 다음부터: 실패로 끝나 진행 중 잡 없음
        if (activeCalls <= 2 && status === 'running') {
          return HttpResponse.json([job(905, 'rejudge', 'running', { snapshot_id: 12 })]);
        }
        return HttpResponse.json([]);
      }),
    );
    const rec = recordRequests();
    const { Wrapper } = wrapper();
    renderHook(() => useSnapshots(1), { wrapper: Wrapper });
    const lists = () => matching(rec.requests, 'GET', /\/regions\/1\/snapshots$/).length;
    // 진행 중 잡이 있는 동안은 폴링한다
    await waitFor(() => expect(lists()).toBeGreaterThan(1), {
      timeout: PENDING_REVISION_POLL_MS * 2,
    });
    // 잡이 끝난(목록 []) 뒤 목록을 한 번 더 받고 멈춘다
    await waitFor(() => expect(activeCalls).toBeGreaterThan(2), {
      timeout: PENDING_REVISION_POLL_MS * 2,
    });
    await sleep(PENDING_REVISION_POLL_MS + 500);
    const settled = lists();
    await sleep(PENDING_REVISION_POLL_MS + 500);
    expect(lists()).toBe(settled);
    rec.stop();
  }, 30_000);

  it('/jobs 를 읽지 못하면(공유 토큰 403) 잡 조회를 반복하지 않고 30분 제한으로 돌아간다', async () => {
    const { snapshots, rev2 } = await revs();
    const fresh = { ...rev2, created_at: nowIso() };
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([fresh, ...snapshots])),
      http.get(mswPath('/jobs'), () =>
        HttpResponse.json({ code: 'forbidden', detail: 'share' }, { status: 403 }),
      ),
    );
    const rec = recordRequests();
    const { Wrapper } = wrapper();
    renderHook(() => useSnapshots(1), { wrapper: Wrapper });
    const lists = () => matching(rec.requests, 'GET', /\/regions\/1\/snapshots$/).length;
    await waitFor(() => expect(lists()).toBeGreaterThan(1), {
      timeout: PENDING_REVISION_POLL_MS * 2,
    });
    // 403 뒤 /jobs 는 다시 부르지 않는다(queued·running 두 번 = 1회 조회)
    expect(matching(rec.requests, 'GET', '/jobs').length).toBeLessThanOrEqual(2);
    rec.stop();
  }, 20_000);
});

// ─── G5 '이후' 캐시 ─────────────────────────────────────────

describe("G5 '이후' 값은 잡 뒤에 받은 응답만 (5차 minor)", () => {
  it('잡이 리비전을 알려 주지 않아 같은 리비전을 다시 읽어도 캐시 값으로 "변화 없음"을 보이지 않는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    let done = false;
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), async ({ request }) => {
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        const d = (await res!.json()) as Dashboard;
        if (!done) return HttpResponse.json(d);
        await sleep(50);
        const [a, b, ...rest] = d.top5;
        return HttpResponse.json({ ...d, top5: [{ ...b!, rank: 1 }, { ...a!, rank: 2 }, ...rest] });
      }),
      // 잡은 바로 done, stats 에 snapshot_id 없음 → '이후' = 기준 리비전(같은 쿼리 키)
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        done = true;
        return HttpResponse.json(job(Number(params.id), 'rejudge', 'done', {}, {}));
      }),
    );
    renderRoute(`/scenario?scenario=B&snapshot=${s12.id}`);
    const run = await screen.findByRole('button', { name: t('page.G5.run') });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    // 처음 나타나는 순간부터 새 값이다 — 옛 캐시로 '순위 변동 없음'이 먼저 뜨지 않는다
    const table = await screen.findByRole('table', { name: t('page.G5.diff') });
    expect(screen.queryByText(t('page.G5.noDiff'))).toBeNull();
    expect(within(table).getAllByRole('row').length).toBeGreaterThan(1);
    expect(screen.queryByTestId('g5-after-loading')).toBeNull();
  });
});

// ─── G6 시장 시나리오 ───────────────────────────────────────

describe('G6 시장: 상황 토글을 서버에 보낸다 (계약 .10)', () => {
  it('?scenario=B → GET /snapshots/{sid}/market?scenario=B', async () => {
    const rec = recordRequests();
    renderRoute('/market?scenario=B');
    await screen.findByRole('heading', { name: t('page.G6.title') });
    await waitFor(() =>
      expect(
        matching(rec.requests, 'GET', /\/snapshots\/\d+\/market$/).some(
          (r) => r.url.searchParams.get('scenario') === 'B',
        ),
      ).toBe(true),
    );
    rec.stop();
  });
});

// ─── G8: 발행 전 기준·409 안내 ─────────────────────────────

describe('G8 보고서: 발행 전 리비전·409 안내 (5차 minor)', () => {
  async function withReadyRevision() {
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const ready: Snapshot = {
      ...s12,
      id: 13,
      revision: 2,
      revision_of: s12.id,
      status: 'ready',
      published_at: null,
      contradicted_claims: 0,
      created_at: nowIso(),
    };
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([ready, ...snapshots])),
    );
    return { snapshots, s12, ready };
  }

  it('ready(발행 전) 기준이면 생성 버튼 비활성 + 안내, 요청을 보내지 않는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    await withReadyRevision();
    const rec = recordRequests();
    renderRoute('/reports?snapshot=13');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    expect(await screen.findByText(t('page.G8.unpublished'))).toHaveAttribute('role', 'alert');
    expect(button).toBeDisabled();
    expect(matching(rec.requests, 'POST', '/reports')).toHaveLength(0);
    rec.stop();
  });

  it('비교 선택은 발행 리비전만(ready·building 제외)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const { snapshots, s12, ready } = await withReadyRevision();
    renderRoute(`/reports?snapshot=${s12.id}`);
    const compare = await screen.findByLabelText(t('page.G8.compareSnapshot'));
    await waitFor(() => expect(compare.querySelectorAll('option').length).toBeGreaterThan(1));
    const values = [...compare.querySelectorAll('option')].map((o) => o.value).filter(Boolean);
    const published = snapshots.filter((s) => s.status === 'published' && s.id !== s12.id);
    expect(values.sort()).toEqual(published.map((s) => String(s.id)).sort());
    expect(values).not.toContain(String(ready.id));
    const base = screen.getByLabelText(t('page.G8.snapshot'));
    expect([...base.querySelectorAll('option')].map((o) => o.textContent)).not.toContain(
      snapshotText(ready),
    );
  });

  it('POST /reports 409 conflict(발행 전 등) → 안내 문구(조용히 묻히지 않는다)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    server.use(
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          { code: 'conflict', detail: 'snapshot 12 는 발행 전(ready)이라 보고서를 만들 수 없다' },
          { status: 409 },
        ),
      ),
    );
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    const alert = await screen.findByText(
      t('page.G8.conflict', {
        detail: 'snapshot 12 는 발행 전(ready)이라 보고서를 만들 수 없다',
      }),
    );
    expect(alert).toHaveAttribute('role', 'alert');
  });
});

// ─── 계약 .10: 발행 뒤 만든 시나리오 404 ──────────────────────

describe('발행 리비전 + 발행 뒤 만든 시나리오 = 404 → 시나리오 실행 안내 (계약 .10 S2)', () => {
  it('isScenarioMissing: 사용자 시나리오·발행 리비전·404 일 때만', () => {
    const e404 = new ApiError('not_found', 'scenario 9', 404);
    expect(isScenarioMissing(e404, '9', 'published')).toBe(true);
    expect(isScenarioMissing(e404, 'B', 'published')).toBe(false); // 내장 시나리오는 늘 저장본이 있다
    expect(isScenarioMissing(e404, null, 'published')).toBe(false);
    expect(isScenarioMissing(e404, '9', 'ready')).toBe(false); // 발행 전은 실시간 계산
    expect(isScenarioMissing(new ApiError('internal', 'x', 500), '9', 'published')).toBe(false);
  });

  it('G1 ?scenario=9(발행 뒤 생성) → 404 → 안내 + 시나리오 실행 링크(전역 쿼리 유지)', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () =>
        HttpResponse.json(
          { code: 'not_found', detail: 'scenario 9 not in snapshot' },
          { status: 404 },
        ),
      ),
    );
    renderRoute('/?scenario=9');
    const box = await screen.findByTestId('scenario-missing');
    expect(box).toHaveTextContent(t('page.common.scenarioMissing', { scenario: '9' }));
    const link = within(box).getByRole('link', { name: t('page.common.scenarioMissingRun') });
    expect(link.getAttribute('href')).toMatch(/^\/scenario\?.*scenario=9/);
  });
});

// ─── 계약 .10: 사람 확인 이른 확인일 422 ───────────────────────

describe('사람 확인 이른 확인일 → 422 checked_at → 확인일 칸 오류 (계약 .10 S6)', () => {
  it('field_errors loc [body, checked_at] 를 확인 시각 칸 경고로 보인다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const detail = '이 필드에 2026-10-08 관측된 공식 공고가 있다';
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
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.field')), 'move_in_ym');
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.value')), '2028-03');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '검토자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    const checkedAt = within(form).getByLabelText(t('page.G7.hc.checkedAt'));
    await waitFor(() => expect(checkedAt).toHaveAttribute('aria-invalid', 'true'));
    const msg = t('page.G7.hc.checkedAtTooEarly', { detail });
    expect(within(form).getByText(msg)).toHaveAttribute('role', 'alert');
    expect(checkedAt).toHaveAccessibleDescription(msg);
    expect(within(form).queryByTestId('human-check-result')).toBeNull();
  });
});
