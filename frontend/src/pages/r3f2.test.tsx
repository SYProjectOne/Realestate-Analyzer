/**
 * R3f FE5 2단계 — 계약 2026-10-09.11 FE 차이 표(F1–F15) 화면 맞춤:
 *  - F1 출처 서랍·G3 출처 탭: `GET /provenance/{id}?snapshot_id=<보고 있는 리비전>`(충돌 출처 클릭 포함), 404·503 표시.
 *  - F3–F6 발행 유발 쓰기: 202(호재 위치·생활권·지역 선택) / 201 + job_id(사람 확인) → 잡 감시 + '발행까지 이전 리비전' 안내.
 *    (호재 위치는 market/catalystLocation.test.tsx)
 *  - F7·F8 사람 확인 checked_at: 시간대 붙은 RFC3339 로 보낸다, 10분 넘는 미래는 보내지 않는다, 서버 422 미래·이른 확인일 구분.
 *  - F10 보고서: 사용자 시나리오 대상 리비전 검사(생성 전 차단 + 리비전 바꾸기), 422 scenario_not_in_revision 안내,
 *    비교 후보 = 대상보다 앞선 발행 리비전, 503 준비 중.
 *  - F12·F15 새 오류 code: materialize_pending(503 + Retry-After) = '준비 중' + 자동 재시도, stored_view_mismatch = 서버 오류.
 * (F2 주장 목록·F9 체크리스트 자동 done·F11 보고서 HTML·F13 할인 값·F14 예시는 화면 규칙 변화 없음 — 보고서 표 참고)
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { ApiError, parseRetryAfter, toApiError } from '@/api/client';
import { humanCheckJobId, provenanceSnapshot } from '@/api/hooks';
import { queryRetry, queryRetryDelay } from '@/api/retryPolicy';
import {
  API_ERROR_CODES,
  type Dashboard,
  type Provenance,
  type Scenario,
  type Snapshot,
} from '@/api/types';
import { snapshotText } from '@/components/SnapshotPicker';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { checkedAtProblem, offsetText, toRfc3339 } from './ops/HumanCheckForm';
import {
  compareCandidates,
  createErrorText,
  isOlderRevision,
  revisionWithScenario,
} from './reports';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string, method = 'GET'): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString(), {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: method === 'GET' ? undefined : '{}',
    }),
  );
  return (await res!.json()) as T;
}

const pending503 = (retryAfter = '0') =>
  HttpResponse.json(
    { code: 'materialize_pending', detail: '발행 리비전 12 저장본을 만드는 중' },
    { status: 503, headers: { 'Retry-After': retryAfter } },
  );

// ─── F12 오류 code·재시도 규칙 ─────────────────────────────

describe('F12 새 오류 code · materialize_pending 재시도 규칙', () => {
  it('계약 Error code 3개를 파싱한다(목록에 없으면 http 로 떨어진다)', async () => {
    for (const code of [
      'scenario_not_in_revision',
      'stored_view_mismatch',
      'materialize_pending',
    ] as const) {
      expect(API_ERROR_CODES).toContain(code);
      const err = await toApiError(
        new Response(JSON.stringify({ code, detail: 'x' }), {
          status: 503,
          headers: { 'Retry-After': '7' },
        }),
      );
      expect(err.code).toBe(code);
      expect(err.retryAfterMs).toBe(7000);
    }
  });

  it('Retry-After: 초·HTTP 날짜·없음', () => {
    expect(parseRetryAfter('3')).toBe(3000);
    expect(parseRetryAfter(null)).toBeNull();
    const now = Date.parse('2026-10-10T00:00:00Z');
    expect(parseRetryAfter('Sat, 10 Oct 2026 00:00:05 GMT', now)).toBe(5000);
  });

  it('queryRetry: materialize_pending 만 계속 재시도(Retry-After 간격, 0.5~30초), 그 밖은 base 번', () => {
    const pending = new ApiError('materialize_pending', 'x', 503, [], null, 2000);
    const other = new ApiError('internal', 'x', 500);
    expect(queryRetry(0)(0, pending)).toBe(true);
    expect(queryRetry(0)(39, pending)).toBe(true);
    expect(queryRetry(0)(40, pending)).toBe(false);
    expect(queryRetry(0)(0, other)).toBe(false);
    expect(queryRetry(1)(0, other)).toBe(true);
    expect(queryRetryDelay(0, pending)).toBe(2000);
    expect(queryRetryDelay(0, new ApiError('materialize_pending', 'x', 503, [], null, 0))).toBe(
      500,
    );
    expect(
      queryRetryDelay(0, new ApiError('materialize_pending', 'x', 503, [], null, 600_000)),
    ).toBe(30_000);
  });
});

// ─── F15 발행 리비전 GET 503 → 준비 중 → 자동 재시도 ───────────

describe('F15 발행 리비전 저장본 생성 전(503 materialize_pending) → 준비 중 → 자동 재시도', () => {
  it('G1 대시보드: 503 동안 "준비 중", Retry-After 뒤 다시 불러 화면이 뜬다', async () => {
    let calls = 0;
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), async ({ request }) => {
        calls += 1;
        if (calls === 1) return pending503('0');
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        return HttpResponse.json((await res!.json()) as Dashboard);
      }),
    );
    renderRoute('/');
    expect(await screen.findByTestId('materialize-pending')).toHaveTextContent(
      t('page.common.materializePending'),
    );
    expect(await screen.findByRole('list', { name: t('page.G1.top5') })).toBeInTheDocument();
    expect(screen.queryByTestId('materialize-pending')).toBeNull();
    expect(calls).toBe(2);
  });

  it('stored_view_mismatch(500) → 서버 오류(저장본 검증 실패) 문구, 재시도 없음', async () => {
    let calls = 0;
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () => {
        calls += 1;
        return HttpResponse.json(
          { code: 'stored_view_mismatch', detail: 'sha256 불일치' },
          { status: 500 },
        );
      }),
    );
    renderRoute('/');
    expect(
      await screen.findByText(t('page.common.storedViewMismatch', { detail: 'sha256 불일치' })),
    ).toBeInTheDocument();
    expect(calls).toBe(1);
  });
});

// ─── F1 출처 서랍 snapshot_id ─────────────────────────────

describe('F1 출처 조회는 보고 있는 리비전(snapshot_id)을 늘 넘긴다', () => {
  async function provenanceWithConflict(): Promise<Provenance> {
    const base = await example<Provenance>('/provenance/fp_1');
    return {
      ...base,
      conflicts: [
        {
          id: 'fp_99001',
          value_text: '다른 값',
          label: '추정',
          reason: '출처 상충',
          url: null,
          checked_at: '2026-10-07',
          source_kind: null,
          source_rank: 3,
          chosen: false,
          excerpt: null,
        },
      ],
    };
  }

  it('G1 숫자 셀 → 출처 서랍 GET /provenance/{id}?snapshot_id=12, 충돌 출처 열기도 같은 snapshot_id', async () => {
    const prov = await provenanceWithConflict();
    server.use(
      http.get(mswPath('/provenance/:prov_id'), ({ params }) =>
        HttpResponse.json({ ...prov, id: String(params.prov_id) }),
      ),
    );
    const rec = recordRequests();
    renderRoute('/?snapshot=12');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cell = (
      within(top5).getAllByRole('listitem')[0] as HTMLElement
    ).querySelector<HTMLButtonElement>('button[data-prov]')!;
    await userEvent.click(cell);
    const dialog = await screen.findByRole('dialog', { name: t('provenance.title') });
    await within(dialog).findByText(t('provenance.url'));
    const first = matching(rec.requests, 'GET', /\/provenance\//);
    expect(first.length).toBeGreaterThan(0);
    expect(first.every((r) => r.url.searchParams.get('snapshot_id') === '12')).toBe(true);

    await userEvent.click(
      within(dialog).getByRole('button', { name: t('provenance.openConflict') }),
    );
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/provenance/fp_99001')).toHaveLength(1),
    );
    expect(
      matching(rec.requests, 'GET', '/provenance/fp_99001')[0]!.url.searchParams.get('snapshot_id'),
    ).toBe('12');
    rec.stop();
  });

  it('provenanceSnapshot: 응답 prov 는 리비전을 넘기고, 화면이 만든 접수 근거 rd_ 는 리비전 없이(저장본에 없음)', () => {
    expect(provenanceSnapshot('fp_11', '12')).toBe('12');
    expect(provenanceSnapshot('cs_1', 12)).toBe(12);
    expect(provenanceSnapshot('rd_9062', '12')).toBeNull();
    expect(provenanceSnapshot('fp_11', null)).toBeNull();
    expect(provenanceSnapshot(null, '12')).toBeNull();
  });

  it('헤더에서 다른 리비전을 고르면 서랍도 그 리비전으로 조회한다', async () => {
    const rec = recordRequests();
    renderRoute('/?snapshot=11');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cell = (
      within(top5).getAllByRole('listitem')[0] as HTMLElement
    ).querySelector<HTMLButtonElement>('button[data-prov]')!;
    await userEvent.click(cell);
    await screen.findByRole('dialog', { name: t('provenance.title') });
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/provenance\//).length).toBeGreaterThan(0),
    );
    for (const r of matching(rec.requests, 'GET', /\/provenance\//)) {
      expect(r.url.searchParams.get('snapshot_id')).toBe('11');
    }
    rec.stop();
  });

  it('G3 출처 탭: 상세의 snapshot_id 로 조회, 404(그 리비전에 없던 출처)는 오류 문구', async () => {
    const rec = recordRequests();
    server.use(
      http.get(mswPath('/provenance/:prov_id'), () =>
        HttpResponse.json(
          { code: 'not_found', detail: '발행 리비전 12 에 없던 출처' },
          { status: 404 },
        ),
      ),
    );
    renderRoute('/complexes/2?snapshot=12');
    await screen.findByRole('tablist', { name: t('page.G3.tabs') });
    await userEvent.click(screen.getByRole('tab', { name: t('page.G3.tab.provenance') }));
    expect(await screen.findByText(/발행 리비전 12 에 없던 출처/)).toBeInTheDocument();
    const reqs = matching(rec.requests, 'GET', /\/provenance\//);
    expect(reqs.length).toBeGreaterThan(0);
    expect(reqs.every((r) => r.url.searchParams.get('snapshot_id') === '12')).toBe(true);
    rec.stop();
  });

  it('출처 서랍 503 → 준비 중 → 자동 재시도 뒤 내용', async () => {
    let calls = 0;
    server.use(
      http.get(mswPath('/provenance/:prov_id'), async ({ request }) => {
        calls += 1;
        if (calls === 1) return pending503('0');
        const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
        return HttpResponse.json(await res!.json());
      }),
    );
    renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    await userEvent.click(
      (within(top5).getAllByRole('listitem')[0] as HTMLElement).querySelector<HTMLButtonElement>(
        'button[data-prov]',
      )!,
    );
    const dialog = await screen.findByRole('dialog', { name: t('provenance.title') });
    expect(
      await within(dialog).findByText(t('page.common.materializePending')),
    ).toBeInTheDocument();
    expect(await within(dialog).findByText(t('provenance.url'))).toBeInTheDocument();
  });
});

// ─── F4·F5·F6 발행 유발 쓰기 → 잡 감시 ──────────────────────

describe('F4·F5·F6 발행 유발 쓰기는 job_id 를 감시하고 발행까지 이전 리비전이라고 알린다', () => {
  it('F4 생활권 PUT 202 → 발행 대기 안내 + 잡 진행', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.add') }));
    const names = screen.getAllByRole('textbox', { name: t('page.G0_2.areaName') });
    await userEvent.type(names[names.length - 1] as HTMLElement, '새');
    const firstDong = screen.getAllByRole('checkbox')[0] as HTMLElement;
    await userEvent.click(firstDong);
    const target = screen.getByLabelText(t('page.G0_2.moveTo'));
    const options = target.querySelectorAll('option');
    await userEvent.selectOptions(target, (options[options.length - 1] as HTMLOptionElement).value);
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.move') }));
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.save') }));
    const job = await screen.findByTestId('publish-job');
    expect(within(job).getByTestId('publish-pending')).toHaveTextContent(t('job.publishPending'));
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/jobs\/912$/).length).toBeGreaterThan(0),
    );
    rec.stop();
  });

  it('F5 지역 선택 PATCH 202 → 발행 대기 안내 + region.expand 진행', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    await userEvent.type(within(panel).getByLabelText(t('page.G0_2.expand.search')), '검단');
    const list = await within(panel).findByRole('list', {
      name: t('page.G0_2.expand.candidates'),
    });
    const addable = within(list)
      .getAllByRole('button', { name: t('page.G0_2.expand.add') })
      .find((b) => !(b as HTMLButtonElement).disabled)!;
    await userEvent.click(addable);
    await userEvent.click(
      within(panel).getByRole('button', { name: t('page.G0_2.expand.submit') }),
    );
    const job = await within(panel).findByTestId('publish-job');
    expect(within(job).getByTestId('publish-pending')).toHaveTextContent(t('job.publishPending'));
    expect(await within(job).findByText('region.expand')).toBeInTheDocument();
  });

  it('F6 humanCheckJobId: job_id 우선, 옛 응답은 rejudge_job_id', () => {
    expect(humanCheckJobId({ rejudge_job_id: 3, job_id: 4 })).toBe(4);
    expect(humanCheckJobId({ rejudge_job_id: 3 })).toBe(3);
    expect(humanCheckJobId({ rejudge_job_id: null, job_id: null })).toBeNull();
  });

  it('F6·F7 사람 확인: RFC3339(시간대) 로 보내고 201 + job_id 잡을 발행 대기 안내와 함께 감시', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() =>
      expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1),
    );
    const body = (await matching(rec.requests, 'POST', '/ops/human-checks')[0]!.body) as {
      checked_at: string;
    };
    expect(body.checked_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/);
    const job = await within(form).findByTestId('human-check-job');
    expect(within(job).getByTestId('publish-pending')).toHaveTextContent(t('job.publishPending'));
    expect(await within(job).findByText('rejudge')).toBeInTheDocument();
    rec.stop();
  });
});

// ─── F7·F8 checked_at ──────────────────────────────────────

describe('F7·F8 사람 확인 checked_at: 시간대 RFC3339 · 미래 422 · 이른 확인일 422 구분', () => {
  it('toRfc3339: datetime-local → 브라우저 오프셋을 붙인 RFC3339, 형식 오류·없는 날짜는 null', () => {
    const off = offsetText(-new Date(2026, 9, 9, 10, 20).getTimezoneOffset());
    expect(toRfc3339('2026-10-09T10:20')).toBe(`2026-10-09T10:20:00${off}`);
    expect(toRfc3339('2026-10-09T10:20:30')).toBe(`2026-10-09T10:20:30${off}`);
    expect(toRfc3339('')).toBeNull();
    expect(toRfc3339('2026-10-09')).toBeNull();
    expect(toRfc3339('2026-02-30T10:00')).toBeNull();
    expect(offsetText(540)).toBe('+09:00');
    expect(offsetText(-330)).toBe('-05:30');
    expect(offsetText(0)).toBe('+00:00');
  });

  it('checkedAtProblem: 비었으면 입력 안내, 10분 넘게 미래면 미래 안내, 그 안은 통과', () => {
    const now = new Date(2026, 9, 10, 12, 0).getTime();
    expect(checkedAtProblem('', now)).toBe(t('page.G7.hc.checkedAtRequired'));
    expect(checkedAtProblem('2026-10-10T12:09', now)).toBeNull();
    expect(checkedAtProblem('2026-10-10T12:11', now)).toBe(t('page.G7.hc.checkedAtFutureLocal'));
    expect(checkedAtProblem('2026-10-09T08:00', now)).toBeNull();
  });

  async function fillForm() {
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    await userEvent.selectOptions(complex, '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.value')), '가능');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    return form;
  }

  it('10분 넘게 미래인 확인 시각은 보내지 않고 확인 시각 칸에 미래 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await fillForm();
    const checkedAt = within(form).getByLabelText(t('page.G7.hc.checkedAt'));
    const future = new Date(Date.now() + 2 * 3600_000);
    future.setMinutes(future.getMinutes() - future.getTimezoneOffset());
    await userEvent.clear(checkedAt);
    await userEvent.type(checkedAt, future.toISOString().slice(0, 16));
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() => expect(checkedAt).toHaveAttribute('aria-invalid', 'true'));
    expect(within(form).getByText(t('page.G7.hc.checkedAtFutureLocal'))).toHaveAttribute(
      'role',
      'alert',
    );
    expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(0);
    rec.stop();
  });

  it('서버 422 미래(서버 시계 기준) → 확인 시각 칸에 미래 안내(이른 확인일 문구 아님)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const detail = '확인 시각 … 은 지금보다 10분 넘게 미래다';
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
    const form = await fillForm();
    const checkedAt = within(form).getByLabelText(t('page.G7.hc.checkedAt'));
    // 클라이언트 기준 5분 뒤(10분 여유 안) — 서버 시계가 늦으면 서버가 422
    const soon = new Date(Date.now() + 5 * 60_000);
    soon.setMinutes(soon.getMinutes() - soon.getTimezoneOffset());
    await userEvent.clear(checkedAt);
    await userEvent.type(checkedAt, soon.toISOString().slice(0, 16));
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() => expect(checkedAt).toHaveAttribute('aria-invalid', 'true'));
    expect(within(form).getByText(t('page.G7.hc.checkedAtFuture', { detail }))).toBeInTheDocument();
  });
});

// ─── F10 보고서 ─────────────────────────────────────────────

describe('F10 보고서: 사용자 시나리오 대상 리비전 검사 · 비교는 앞선 리비전만 · 422·503 안내', () => {
  async function fixtures() {
    const snapshots = await example<Snapshot[]>('/regions/1/snapshots');
    const s12 = snapshots[0]!; // 2026-10-08 r1, 발행 2026-10-08T07:42
    const s11 = snapshots[1]!; // 2026-10-07 r1
    const s13: Snapshot = {
      ...s12,
      id: 13,
      revision: 2,
      revision_of: 12,
      revision_reason: '시나리오 실행',
      published_at: '2026-10-09T12:00:00+09:00',
      created_at: '2026-10-09T11:50:00+09:00',
    };
    const scenarios = await example<Scenario[]>('/scenarios');
    const base = scenarios.find((s) => s.code === 'base')!;
    const mine: Scenario = {
      ...base,
      id: 9,
      code: null,
      name: '내 조건 9',
      is_builtin: false,
      created_at: '2026-10-09T10:00:00+09:00', // s12 발행 뒤, s13 발행 전
    };
    return { snapshots, s11, s12, s13, scenarios, mine };
  }

  it('isOlderRevision·compareCandidates: (기준일, 리비전, id) 순 — 자기 자신·더 새 리비전 제외', async () => {
    const { s11, s12, s13 } = await fixtures();
    expect(isOlderRevision(s11, s12)).toBe(true);
    expect(isOlderRevision(s12, s13)).toBe(true);
    expect(isOlderRevision(s13, s12)).toBe(false);
    expect(isOlderRevision(s12, s12)).toBe(false);
    expect(compareCandidates([s13, s12, s11], s12).map((s) => s.id)).toEqual([11]);
    expect(compareCandidates([s13, s12, s11], s13).map((s) => s.id)).toEqual([12, 11]);
    expect(compareCandidates([s13, s12, s11], null)).toEqual([]);
  });

  it('revisionWithScenario: 그 시나리오를 만든 뒤 발행된 가장 새 리비전', async () => {
    const { s11, s12, s13, mine } = await fixtures();
    expect(revisionWithScenario([s13, s12, s11], mine)?.id).toBe(13);
    expect(revisionWithScenario([s12, s11], mine)).toBeNull();
  });

  it('createErrorText: 422 scenario_not_in_revision·503 materialize_pending 안내', () => {
    expect(
      createErrorText(new ApiError('scenario_not_in_revision', '리비전 12 에 없다', 422)),
    ).toBe(t('page.G8.scenarioNotInRevisionServer', { detail: '리비전 12 에 없다' }));
    expect(createErrorText(new ApiError('materialize_pending', 'x', 503))).toBe(
      t('page.G8.pending'),
    );
  });

  it('?scenario=<발행 뒤 만든 시나리오> + 대상 12 → 생성 막고 안내, "리비전 13 으로" → 대상 바꿔 scenario_id 와 POST', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const { snapshots, s13, scenarios, mine } = await fixtures();
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([s13, ...snapshots])),
      http.get(mswPath('/scenarios'), () => HttpResponse.json([...scenarios, mine])),
    );
    const rec = recordRequests();
    renderRoute('/reports?snapshot=12&scenario=9');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    const msg = t('page.G8.scenarioNotInRevision', { name: mine.name });
    expect(await screen.findByText(msg)).toHaveAttribute('role', 'alert');
    expect(button).toBeDisabled();
    expect(screen.getByLabelText(t('page.G8.scenario'))).toHaveValue('9');

    await userEvent.click(screen.getByTestId('g8-pick-scenario-revision'));
    expect(screen.getByLabelText(t('page.G8.snapshot'))).toHaveValue('13');
    await waitFor(() => expect(button).toBeEnabled());
    expect(screen.queryByText(msg)).toBeNull();
    // 비교 후보: 13 보다 앞선 12·11
    const compare = screen.getByLabelText(t('page.G8.compareSnapshot'));
    expect([...compare.querySelectorAll('option')].map((o) => o.value)).toEqual(['', '12', '11']);
    await userEvent.selectOptions(compare, '12');
    await userEvent.click(button);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/reports')).toHaveLength(1));
    expect(await matching(rec.requests, 'POST', '/reports')[0]!.body).toMatchObject({
      snapshot_id: 13,
      compare_snapshot_id: 12,
      scenario_id: 9,
    });
    expect(snapshotText(s13)).toBeTruthy();
    rec.stop();
  });

  it('서버 422 scenario_not_in_revision → 안내 + 대상 다시 고르기 버튼', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const { snapshots, s13, scenarios, mine } = await fixtures();
    // 시각을 모르는 시나리오(created_at null) — 화면은 판단하지 않고 서버가 거절
    const unknown: Scenario = { ...mine, created_at: null };
    const detail = '시나리오 9 는 리비전 12 에 없다(발행 뒤 만든 시나리오)';
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([s13, ...snapshots])),
      http.get(mswPath('/scenarios'), () => HttpResponse.json([...scenarios, unknown])),
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
    renderRoute('/reports?snapshot=12');
    await screen.findByRole('button', { name: t('page.G8.generate') });
    const select = screen.getByLabelText(t('page.G8.scenario'));
    await waitFor(() => expect(select.querySelector('option[value="9"]')).not.toBeNull());
    await userEvent.selectOptions(select, '9');
    await userEvent.click(screen.getByRole('button', { name: t('page.G8.generate') }));
    expect(
      await screen.findByText(t('page.G8.scenarioNotInRevisionServer', { detail })),
    ).toHaveAttribute('role', 'alert');
  });

  it('내장 시나리오는 대상 리비전 검사 없이 scenario_id 로 보낸다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/reports?scenario=B');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await waitFor(() => expect(screen.getByLabelText(t('page.G8.scenario'))).toHaveValue('3'));
    await userEvent.click(button);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/reports')).toHaveLength(1));
    expect(await matching(rec.requests, 'POST', '/reports')[0]!.body).toMatchObject({
      scenario_id: 3,
    });
    rec.stop();
  });
});
