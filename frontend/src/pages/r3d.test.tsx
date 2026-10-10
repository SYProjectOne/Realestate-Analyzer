/**
 * R3d(4차 리뷰) FE3 화면:
 *  - Critical 5: G5 실행 뒤 '이후' 값은 잡이 쓴 새 리비전(stats.snapshot_id)에서 읽는다(옛 리비전 아님).
 *  - Major 15: 잡 완료 → 지역·리비전 목록 무효화, 발행 대기 리비전 폴링 → 새로 고침 없이 새 리비전이 기본.
 *  - Major 16: 보고서 기준·비교 선택이 리비전을 구별하고 생성 중(building) 리비전은 고를 수 없다.
 *  - minor: 409 뒤 재조회(PATCH /regions·POST /reports), 체크리스트 closed_by 표시.
 */
import { QueryClient } from '@tanstack/react-query';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import {
  invalidateAfterJob,
  isAwaitingPublish,
  PENDING_REVISION_POLL_MS,
  snapshotsRefetchInterval,
  watchJobCompletion,
} from '@/api/jobWatch';
import type { ChecklistItem, Dashboard, JobRun, Region, Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { resultSnapshotId } from '@/lib/contract';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { snapshotText } from '@/components/SnapshotPicker';
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

function snap(base: Snapshot, patch: Partial<Snapshot>): Snapshot {
  return { ...base, ...patch };
}

function doneJob(id: number, jobName: JobRun['job_name'], stats: Record<string, unknown>): JobRun {
  return {
    id,
    job_name: jobName,
    kind: jobName === 'rejudge' ? 'rejudge' : 'manual',
    payload: {},
    scheduled_at: nowIso(),
    started_at: nowIso(),
    finished_at: nowIso(),
    status: 'done',
    stats,
    error_text: null,
    progress: null,
  };
}

// ─── jobWatch 단위 ─────────────────────────────────────────

describe('jobWatch (M-15)', () => {
  function client() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    const stop = watchJobCompletion(qc);
    const seed = () => {
      qc.setQueryData(['regions'], [{ id: 1 }]);
      qc.setQueryData(['regions', '1'], { id: 1 });
      qc.setQueryData(['snapshots', '12', 'dashboard', null], { x: 1 });
      qc.setQueryData(['complexes', '5', '12', null], { x: 1 });
      qc.setQueryData(['reports', ''], []);
      qc.setQueryData(['scenarios'], []);
    };
    const inv = (key: readonly unknown[]) => qc.getQueryState(key)?.isInvalidated ?? false;
    return { qc, stop, seed, inv };
  }

  it('잡 상세가 running → done 이면 지역·리비전·사실 화면 무효화(시나리오는 그대로)', () => {
    const { qc, stop, seed, inv } = client();
    seed();
    qc.setQueryData(['jobs', '7'], { ...doneJob(7, 'rejudge', {}), status: 'running' });
    expect(inv(['regions'])).toBe(false);
    qc.setQueryData(['jobs', '7'], doneJob(7, 'rejudge', { snapshot_id: 13 }));
    expect(inv(['regions'])).toBe(true);
    expect(inv(['regions', '1'])).toBe(true);
    expect(inv(['snapshots', '12', 'dashboard', null])).toBe(true);
    expect(inv(['complexes', '5', '12', null])).toBe(true);
    expect(inv(['scenarios'])).toBe(false);
    stop();
  });

  it('잡 목록에서 처음 본 done(옛 잡)은 완료로 치지 않고, queued → done 전환만', () => {
    const { qc, stop, seed, inv } = client();
    seed();
    qc.setQueryData(['jobs', 'list', {}], [doneJob(1, 'rejudge', {})]);
    expect(inv(['regions'])).toBe(false);
    qc.setQueryData(
      ['jobs', 'list', {}],
      [doneJob(1, 'rejudge', {}), { ...doneJob(2, 'collect.daily', {}), status: 'queued' }],
    );
    expect(inv(['regions'])).toBe(false);
    qc.setQueryData(
      ['jobs', 'list', {}],
      [doneJob(1, 'rejudge', {}), doneJob(2, 'collect.daily', {})],
    );
    expect(inv(['regions'])).toBe(true);
    stop();
  });

  it('report 잡 완료는 보고서 목록만', () => {
    const { qc, seed, inv } = client();
    seed();
    invalidateAfterJob(qc, { job_name: 'report' });
    expect(inv(['reports', ''])).toBe(true);
    expect(inv(['regions'])).toBe(false);
  });

  it('리비전 목록에서 ready → published 전환이면 지역(latest_snapshot)·사실 화면 무효화', async () => {
    const { qc, stop, seed, inv } = client();
    const [s12] = await example<Snapshot[]>('/regions/1/snapshots');
    const rev2 = snap(s12!, { id: 13, revision: 2, status: 'ready', created_at: nowIso() });
    seed();
    qc.setQueryData(['regions', '1', 'snapshots'], [rev2, s12]);
    expect(inv(['regions'])).toBe(false);
    qc.setQueryData(['regions', '1', 'snapshots'], [{ ...rev2, status: 'published' }, s12]);
    expect(inv(['regions'])).toBe(true);
    expect(inv(['snapshots', '12', 'dashboard', null])).toBe(true);
    // 리비전 목록 자신은 방금 받은 값 — 다시 무효화하지 않는다
    expect(inv(['regions', '1', 'snapshots'])).toBe(false);
    stop();
  });

  it('발행 대기 리비전(building·ready·모순 0·최근)만 폴링', async () => {
    const [s12] = await example<Snapshot[]>('/regions/1/snapshots');
    const now = Date.now();
    const fresh = new Date(now - 1000).toISOString();
    const ready = snap(s12!, { status: 'ready', created_at: fresh, contradicted_claims: 0 });
    expect(isAwaitingPublish(ready, now)).toBe(true);
    expect(isAwaitingPublish({ ...ready, status: 'building' }, now)).toBe(true);
    expect(isAwaitingPublish({ ...ready, contradicted_claims: 2 }, now)).toBe(false);
    expect(isAwaitingPublish({ ...ready, degraded: true }, now)).toBe(false);
    expect(isAwaitingPublish({ ...ready, status: 'published' }, now)).toBe(false);
    expect(isAwaitingPublish({ ...ready, created_at: '2026-01-01T00:00:00Z' }, now)).toBe(false);
    expect(snapshotsRefetchInterval([s12!, ready], now)).toBe(PENDING_REVISION_POLL_MS);
    expect(snapshotsRefetchInterval([s12!], now)).toBe(false);
  });

  it('resultSnapshotId: stats.snapshot_id(정수·숫자 문자열)만', () => {
    expect(resultSnapshotId({ stats: { snapshot_id: 13 } })).toBe('13');
    expect(resultSnapshotId({ stats: { snapshot_id: '14' } })).toBe('14');
    expect(resultSnapshotId({ stats: { snapshot_id: 1.5 } })).toBeNull();
    expect(resultSnapshotId({ stats: {} })).toBeNull();
    expect(resultSnapshotId(null)).toBeNull();
  });
});

// ─── 새로 고침 없는 리비전 전환 (M-15) ─────────────────────

describe('잡 완료 → 새 리비전이 새로 고침 없이 기본이 된다 (M-15)', () => {
  it('G1 재판정 잡 done → 리비전 목록 갱신 → ready 폴링 → published → 헤더·대시보드가 리비전 2', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const regions = await example<Region[]>('/regions');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const rev2 = snap(s12, {
      id: 13,
      revision: 2,
      revision_of: s12.id,
      revision_reason: '재판정',
      status: 'ready',
      published_at: null,
      created_at: nowIso(),
    });
    let stage: 'before' | 'ready' | 'published' = 'before';
    let readyServed = 0;
    const list = () => {
      if (stage === 'before') return snapshots;
      if (stage === 'ready' && readyServed++ >= 1) stage = 'published';
      return [
        stage === 'published' ? { ...rev2, status: 'published' as const } : rev2,
        ...snapshots,
      ];
    };
    const region = (r: Region): Region =>
      stage === 'published' ? { ...r, latest_snapshot: { ...rev2, status: 'published' } } : r;
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json(regions.map(region))),
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json(list())),
      http.get(mswPath('/snapshots/:sid/dashboard'), async ({ request }) => {
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        const d = (await res!.json()) as Dashboard;
        return HttpResponse.json({ ...d, rejudge_needed: true });
      }),
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        stage = stage === 'before' ? 'ready' : stage;
        return HttpResponse.json(doneJob(Number(params.id), 'rejudge', { snapshot_id: 13 }));
      }),
    );
    const rec = recordRequests();
    renderRoute('/');
    const notice = await screen.findByTestId('rejudge-notice');
    const picker = await screen.findByLabelText(t('header.snapshot'));
    await waitFor(() => expect(picker).toHaveValue(String(s12.id)));
    await userEvent.click(within(notice).getByRole('button', { name: t('page.G1.rejudgeRun') }));
    // 잡 done → 리비전 목록 다시 받기(ready) → 폴링 → published → latest_snapshot = 13
    await waitFor(() => expect(picker).toHaveValue('13'), {
      timeout: PENDING_REVISION_POLL_MS * 3,
    });
    expect(
      within(picker).getByRole('option', { name: snapshotText({ ...rev2, status: 'published' }) }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/snapshots/13/dashboard').length).toBeGreaterThan(0),
    );
    rec.stop();
  }, 20_000);
});

// ─── C-5: G5 '이후' = 새 리비전 ─────────────────────────────

describe('G5 실행 뒤 이후 값은 새 리비전에서 (C-5)', () => {
  it('rejudge 잡 stats.snapshot_id 의 대시보드를 읽어 diff — 옛 리비전 값이 아니다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const rev2 = snap(s12, { id: 13, revision: 2, revision_of: s12.id, created_at: nowIso() });
    let done = false;
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(done ? [rev2, ...snapshots] : snapshots),
      ),
      http.get(mswPath('/snapshots/:sid/dashboard'), async ({ request, params }) => {
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        const d = (await res!.json()) as Dashboard;
        if (params.sid !== '13') return HttpResponse.json(d);
        // 새 리비전: 1위·2위가 바뀌었다
        const [a, b, ...rest] = d.top5;
        return HttpResponse.json({
          ...d,
          snapshot_id: 13,
          top5: [{ ...b!, rank: 1 }, { ...a!, rank: 2 }, ...rest],
        });
      }),
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        done = true;
        return HttpResponse.json(doneJob(Number(params.id), 'rejudge', { snapshot_id: 13 }));
      }),
    );
    const rec = recordRequests();
    renderRoute(`/scenario?scenario=B&snapshot=${s12.id}`);
    const run = await screen.findByRole('button', { name: t('page.G5.run') });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    const table = await screen.findByRole('table', { name: t('page.G5.diff') });
    expect(screen.queryByText(t('page.G5.noDiff'))).toBeNull();
    expect(table).toBeInTheDocument();
    expect(
      matching(rec.requests, 'GET', '/snapshots/13/dashboard').some(
        (r) => r.url.searchParams.get('scenario') === 'B',
      ),
    ).toBe(true);
    // 이후 값이 어느 리비전인지 보이고, 그 리비전으로 화면을 옮길 수 있다
    const after = screen.getByTestId('g5-after');
    await waitFor(() => expect(after).toHaveTextContent(snapshotText(rev2)));
    await userEvent.click(within(after).getByRole('button', { name: t('page.G5.openRevision') }));
    await waitFor(() => expect(screen.getByLabelText(t('header.snapshot'))).toHaveValue('13'));
    rec.stop();
  });
});

// ─── M-16: 보고서 리비전 선택 ───────────────────────────────

describe('G8 보고서 기준·비교 = 리비전 (M-16)', () => {
  it('비교 선택에 리비전 표기, 생성 중 리비전은 빠진다; 생성 중 기준이면 생성 막음', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!;
    const rev2 = snap(s12, {
      id: 13,
      revision: 2,
      revision_of: s12.id,
      revision_reason: '사람 확인',
    });
    const building = snap(s12, {
      id: 14,
      revision: 3,
      status: 'building',
      created_at: '2026-10-08T09:00:00+09:00',
    });
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json([building, rev2, ...snapshots]),
      ),
    );
    renderRoute(`/reports?snapshot=${s12.id}`);
    const compare = await screen.findByLabelText(t('page.G8.compareSnapshot'));
    await waitFor(() => expect(compare.querySelectorAll('option').length).toBeGreaterThan(1));
    const labels = [...compare.querySelectorAll('option')].map((o) => o.textContent);
    expect(labels).toContain(snapshotText(rev2));
    expect(labels).not.toContain(snapshotText(building));
    expect(labels.filter((l) => l === snapshotText(s12))).toHaveLength(0); // 기준 자신 제외
    const base = screen.getByLabelText(t('page.G8.snapshot'));
    expect([...base.querySelectorAll('option')].map((o) => o.value)).not.toContain('14');

    // 헤더가 생성 중 리비전을 가리키면 생성 버튼 비활성 + 사유
    await userEvent.selectOptions(screen.getByLabelText(t('header.snapshot')), '14');
    const button = screen.getByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeDisabled());
    expect(screen.getByText(t('page.G8.building'))).toHaveAttribute('role', 'alert');
  });
});

// ─── minor: 409 뒤 재조회 ──────────────────────────────────

describe('409 뒤 재조회 (4차 minor)', () => {
  it('POST /reports 409 → 리비전 목록·보고서 목록을 다시 받는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    server.use(
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          { code: 'publish_blocked', detail: '모순 주장이 남았다' },
          { status: 409 },
        ),
      ),
    );
    const rec = recordRequests();
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/regions\/\d+\/snapshots$/).length).toBeGreaterThan(0),
    );
    const before = matching(rec.requests, 'GET', /\/regions\/\d+\/snapshots$/).length;
    const reportsBefore = matching(rec.requests, 'GET', '/reports').length;
    await userEvent.click(button);
    expect(await screen.findByText('모순 주장이 남았다')).toBeInTheDocument();
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/regions\/\d+\/snapshots$/).length).toBeGreaterThan(
        before,
      ),
    );
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/reports').length).toBeGreaterThan(reportsBefore),
    );
    rec.stop();
  });
});

// ─── minor: 체크리스트 closed_by ─────────────────────────────

describe('체크리스트 closed_by 표시 (4차 minor)', () => {
  it('닫힌 항목에 자동 닫힘·사람이 닫음 배지, 열린 항목엔 없다', async () => {
    const items = await example<ChecklistItem[]>('/ops/checklist');
    const first = items[0]!;
    server.use(
      http.get(mswPath('/ops/checklist'), () =>
        HttpResponse.json([
          { ...first, id: 901, title: '자동 닫힌 항목', status: 'na', closed_by: 'auto' },
          { ...first, id: 902, title: '사람이 닫은 항목', status: 'done', closed_by: 'human' },
          { ...first, id: 903, title: '열린 항목', status: 'open', closed_by: null },
        ] satisfies ChecklistItem[]),
      ),
    );
    renderRoute('/ops');
    const table = await screen.findByRole('table', { name: t('page.G7.checklist') });
    const rowOf = (title: string) =>
      within(table).getByRole('rowheader', { name: title }).closest('tr') as HTMLElement;
    await waitFor(() => expect(within(table).getAllByTestId('closed-by')).toHaveLength(2));
    expect(within(rowOf('자동 닫힌 항목')).getByTestId('closed-by')).toHaveTextContent(
      t('page.G7.check.closedBy.auto'),
    );
    expect(within(rowOf('사람이 닫은 항목')).getByTestId('closed-by')).toHaveTextContent(
      t('page.G7.check.closedBy.human'),
    );
    expect(within(rowOf('열린 항목')).queryByTestId('closed-by')).toBeNull();
  });
});

// act 경고 방지용(폴링 타이머가 남은 채 끝나는 테스트)
afterEach(async () => {
  await act(async () => {});
});
