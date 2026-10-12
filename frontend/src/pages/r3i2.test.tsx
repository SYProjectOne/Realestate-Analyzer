/**
 * R3i FE8 2단계 — 계약 2026-10-09.14 FE 차이 표(`contracts/CHANGELOG.md` .14 F1–F12) 화면 맞춤.
 *  - F1(D17-2): `Snapshot.backfilled_at` → 그 리비전을 볼 때 "업그레이드 때 다시 계산한 값 포함" 안내(KST 날짜)
 *  - F2(D17-4): 사람 확인 할인 = 기준 타입 — 폼에 입력 전부터 기준 타입(단지 상세 price.basis_type_code), 응답
 *    `basis_type_code` 로 "기준 타입 X 할인으로 반영". G3 안내에도 기준 타입, 기준 타입 아닌 타입의 할인은 "표시만"
 *  - F3(m2): 할인 값 = 서버와 같은 엄격한 형식(폼 검사·MSW 목), 422 `discount_format`·`discount_not_below_price` → 값 칸
 *  - F4(m2): 다른 숫자 필드도 같은 엄격한 숫자(쉼표 세 자리마다, 숫자 사이 공백 없음, 단위 앞 공백 한 칸까지, 음수 거절)
 *  - F5(D17-5): PATCH /ops/checklist 202 + job_id → 발행 감시, 200 + null → 발행 없음 안내
 *  - F6(D17-5): PATCH /regions 이름만 → 202 + job_id(snapshot.publish) → 발행 감시
 *  - F7(m8·m14): PATCH /catalysts 좌표 소수 6자리 비교(목), 200 안내 문구에 '발행할 리비전 없음' 포함
 *  - F8(D17-3): snapshot.publish 예외 재시도(queued + requeue_reason publish_error, error_retries) = 진행 중
 *  - F9(D17-3): 미뤄진 잡(done + deferred_to)에 나중에 `redeferred_job_id` → 그 잡을 이어 감시
 *  - F10(m9): POST /reports compare 생략 503 → 준비 중 안내(회귀)
 *  - F11(m10): 422 field_errors — checked_at 먼저, 값 칸 오류도 함께(목·폼)
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { MemoryRouter } from 'react-router';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { ApiError } from '@/api/client';
import { jobRefetchInterval } from '@/api/hooks';
import { nextPublishJobId, publishPhase } from '@/api/jobWatch';
import type {
  ComplexDetail,
  HumanCheck,
  JobRun,
  Region,
  RegionPatched,
  Snapshot,
} from '@/api/types';
import { PublishJobProgress } from '@/components';
import { JobProgressView } from '@/components/JobProgress';
import { t } from '@/i18n';
import { handlers } from '@/mocks/handlers';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { RegionExpandPanel } from './living-areas/RegionExpandPanel';
import { humanCheckServerErrors, validateHumanValue } from './ops/HumanCheckForm';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const nowIso = () => new Date().toISOString();

function job(
  id: number,
  jobName: JobRun['job_name'],
  status: JobRun['status'],
  stats: Record<string, unknown> = {},
  payload: Record<string, unknown> = {},
  errorText: string | null = null,
  finishedAt: string | null = null,
): JobRun {
  return {
    id,
    job_name: jobName,
    kind: 'manual',
    payload,
    scheduled_at: nowIso(),
    started_at: nowIso(),
    finished_at: status === 'done' || status === 'failed' ? (finishedAt ?? nowIso()) : null,
    status,
    stats,
    error_text: errorText,
    progress: null,
  };
}

async function example<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`, init),
  );
  return (await res?.json()) as T;
}

/** 목 전체(보강 + 생성)로 요청 — 목 자체 동작 확인 */
async function viaMock(path: string, init: RequestInit): Promise<Response> {
  const res = await getResponse(
    handlers as RequestHandler[],
    new Request(`http://localhost/api${path}`, init),
  );
  if (!res) throw new Error(`목 응답 없음: ${path}`);
  return res;
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// ─── F1 backfilled_at ──────────────────────────────────────

describe('F1(D17-2) Snapshot.backfilled_at → "업그레이드 때 다시 계산한 값 포함" 안내', () => {
  async function serveSnapshots(backfilledAt: string | null) {
    const list = await example<Snapshot[]>('/regions/1/snapshots');
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(
          list.map((s, i) =>
            i === 0 && backfilledAt !== null ? { ...s, backfilled_at: backfilledAt } : s,
          ),
        ),
      ),
    );
    return list[0]!;
  }

  it('보고 있는 리비전에 backfilled_at → 안내(KST 날짜), 문구는 ko.json', async () => {
    // UTC 2026-10-11T16:30Z = KST 2026-10-12 01:30 → 날짜는 KST 로(D16-5)
    const first = await serveSnapshots('2026-10-11T16:30:00Z');
    renderRoute(`/?region=1&snapshot=${first.id}`);
    const banner = await screen.findByTestId('backfilled-banner');
    expect(banner).toHaveTextContent(t('app.backfilled', { date: '2026-10-12' }));
  });

  it('backfilled_at 키가 없으면 안내 없음', async () => {
    const first = await serveSnapshots(null);
    renderRoute(`/?region=1&snapshot=${first.id}`);
    await screen.findByRole('heading', { level: 1, name: t('page.G1.title') });
    await new Promise((r) => setTimeout(r, 200));
    expect(screen.queryByTestId('backfilled-banner')).toBeNull();
  });
});

// ─── F2 기준 타입 표시 ─────────────────────────────────────

describe('F2(D17-4) 사람 확인 할인 = 기준 타입 — 폼·응답·G3 안내에 기준 타입', () => {
  async function humanForm() {
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    return form;
  }

  it('폼: 단지·할인 칸 선택 → 입력 전부터 "기준 타입 84A 할인" 안내(단지 상세 price.basis_type_code)', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const basis = detail.price.basis_type_code as string;
    renderRoute('/ops?hc_complex=2&hc_field=discount');
    const form = await humanForm();
    const value = within(form).getByLabelText(t('page.G7.hc.value'));
    await waitFor(() =>
      expect(value).toHaveAccessibleDescription(t('page.G7.hcHint.discountBasis', { type: basis })),
    );
  });

  it('저장 응답 basis_type_code → "기준 타입 X 할인으로 반영"', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/ops?hc_complex=2&hc_field=discount');
    const form = await humanForm();
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.value')), '1,000,000원');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    expect(await within(form).findByTestId('human-check-basis')).toHaveTextContent(
      t('page.G7.hc.discountBasisSaved', { type: '84A' }),
    );
  });

  it('목: discount 201 응답에 basis_type_code(예시 상세 기준 타입), 다른 필드는 null', async () => {
    const ok = await viaMock(
      '/ops/human-checks',
      jsonInit('POST', {
        complex_id: 2,
        field: 'discount',
        value_text: '1,000,000원',
        kind: 'phone',
        entered_by: '운영자',
        checked_at: '2026-10-08T10:00:00+09:00',
      }),
    );
    expect(ok.status).toBe(201);
    expect(((await ok.json()) as HumanCheck).basis_type_code).toBe('84A');
    const other = await viaMock(
      '/ops/human-checks',
      jsonInit('POST', {
        complex_id: 2,
        field: 'resale_months',
        value_text: '12',
        kind: 'phone',
        entered_by: '운영자',
        checked_at: '2026-10-08T10:00:00+09:00',
      }),
    );
    expect(((await other.json()) as HumanCheck).basis_type_code ?? null).toBeNull();
  });

  function serveDetail(patch: (d: ComplexDetail) => ComplexDetail) {
    server.use(
      http.get(mswPath('/complexes/:id'), async () =>
        HttpResponse.json(patch(await example<ComplexDetail>('/complexes/2'))),
      ),
    );
  }

  it("G3: 기준 타입 '추정' 할인 안내에 기준 타입, 다른 타입의 '확인됨' 할인은 '표시만(기준 타입 아님)'", async () => {
    const fact = (label: '추정' | '확인됨') => ({
      v: 5_000_000,
      label,
      reason: label === '추정' ? '공고문 자동 추출 — 조건 확인 필요' : '사람 확인(phone)',
      prov: 'fp_1',
      checked_at: '2026-10-08',
      unit: 'won' as const,
    });
    serveDetail((d) => ({
      ...d,
      price: { ...d.price, discount: fact('추정'), discount_applied: false },
      payment: d.payment.map((p) =>
        p.is_current
          ? { ...p, discount_by_type: { '84A': fact('추정'), '84B': fact('확인됨') } }
          : p,
      ),
    }));
    renderRoute('/complexes/2#price');
    expect(await screen.findByTestId('price-discount')).toHaveTextContent(
      t('page.G3.price.discountEstimatedBasis', { type: '84A' }),
    );
    expect(await screen.findByTestId('type-discount-note-84B')).toHaveTextContent(
      t('page.G3.price.discountNonBasis', { type: '84A' }),
    );
    expect(screen.getByTestId('type-discount-note-84A')).toHaveTextContent(
      t('page.G3.price.discountEstimatedBasis', { type: '84A' }),
    );
  });
});

// ─── F3·F4 엄격한 숫자 ─────────────────────────────────────

describe('F3·F4(m2) 사람 확인 숫자 = 서버와 같은 엄격한 형식', () => {
  it.each([
    '1,0',
    ',,5,,',
    ' 1 0 0 0 ',
    '10,00,000',
    '٣٠٠٠',
    '９９',
    '-0',
    '1000 원',
    '1.5',
    '100,000,000,001',
    '삼백만',
  ])('할인 %s → 폼 검사 오류(서버 discount_format 과 같은 판정)', (raw) => {
    expect(validateHumanValue('discount', raw)).not.toBeNull();
  });

  it.each(['3,000,000원', '0', '1000', '  1000  ', '100,000,000,000'])('할인 %s → 통과', (raw) => {
    expect(validateHumanValue('discount', raw)).toBeNull();
  });

  it('다른 숫자 필드(F4): 쉼표 세 자리마다·숫자 사이 공백 없음·단위 앞 공백 한 칸·음수 거절', () => {
    expect(validateHumanValue('max_price_won', '605,000,000')).toBeNull();
    expect(validateHumanValue('max_price_won', '605,000,000원')).toBeNull();
    expect(validateHumanValue('max_price_won', '6050,00,000')).not.toBeNull();
    expect(validateHumanValue('max_price_won', '605 000 000')).not.toBeNull();
    expect(validateHumanValue('max_price_won', '６０５000000')).not.toBeNull();
    expect(validateHumanValue('resale_months', '3 년')).toBeNull();
    expect(validateHumanValue('resale_months', '3  년')).not.toBeNull();
    expect(validateHumanValue('resale_months', '1 2')).not.toBeNull();
    expect(validateHumanValue('resale_months', '-0')).not.toBeNull();
    expect(validateHumanValue('resale_months', '12개월')).toBeNull();
    expect(validateHumanValue('resale_months', '12%')).not.toBeNull();
    expect(validateHumanValue('down_payment_pct', '10 %')).toBeNull();
    expect(validateHumanValue('down_payment_pct', '10.123')).not.toBeNull();
  });

  it('값은 고쳐 쓰지 않고 그대로(앞뒤 공백만 떼고) 보낸다 — 서버가 같은 규칙으로 읽는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/ops?hc_complex=2&hc_field=max_price_won');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    await waitFor(() =>
      expect(
        within(form).getByLabelText(t('page.G7.hc.complex')).querySelector('option[value="2"]'),
      ).not.toBeNull(),
    );
    await userEvent.type(within(form).getByLabelText(t('page.G7.hc.value')), ' 605,000,000원 ');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() =>
      expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1),
    );
    expect(await matching(rec.requests, 'POST', '/ops/human-checks')[0]!.body).toMatchObject({
      value_text: '605,000,000원',
    });
    rec.stop();
  });

  it('422 discount_format·discount_not_below_price → 값 칸에 code 별 안내', () => {
    const err = (code: 'discount_format' | 'discount_not_below_price', detail: string) =>
      new ApiError(code, detail, 422, [{ loc: ['body', 'value_text'], msg: detail }]);
    expect(humanCheckServerErrors(err('discount_format', 'x')).fields.value).toBe(
      t('page.G7.hc.discountFormat', { detail: 'x' }),
    );
    expect(humanCheckServerErrors(err('discount_not_below_price', 'y')).fields.value).toBe(
      t('page.G7.hc.discountNotBelowPrice', { detail: 'y' }),
    );
  });

  it('화면: 서버 422 discount_not_below_price → 값 칸 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/ops?hc_complex=2&hc_field=discount');
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    await waitFor(() =>
      expect(
        within(form).getByLabelText(t('page.G7.hc.complex')).querySelector('option[value="2"]'),
      ).not.toBeNull(),
    );
    const value = within(form).getByLabelText(t('page.G7.hc.value'));
    // 예시 상세 기준 타입 84A: min(대표층가 5.75억, 최고가 6.05억) = 5.75억 이상은 목이 거절(서버와 같은 규칙)
    await userEvent.type(value, '575,000,000원');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() => expect(value).toHaveAttribute('aria-invalid', 'true'));
    expect(value.getAttribute('aria-describedby')).toBeTruthy();
    expect(
      document.getElementById(value.getAttribute('aria-describedby') as string)?.textContent,
    ).toMatch(new RegExp(`^${t('page.G7.hc.discountNotBelowPrice', { detail: '' }).slice(0, 10)}`));
  });

  const hcBody = (value: string, checkedAt = '2026-10-08T10:00:00+09:00') =>
    jsonInit('POST', {
      complex_id: 2,
      field: 'discount',
      value_text: value,
      kind: 'phone',
      entered_by: '운영자',
      checked_at: checkedAt,
    });

  it.each([
    ['1,0', 'discount_format'],
    ['٣٠٠٠', 'discount_format'],
    ['1000 원', 'discount_format'],
    ['575,000,000', 'discount_not_below_price'],
  ])('목: 할인 %s → 422 %s(loc body.value_text)', async (value, code) => {
    const res = await viaMock('/ops/human-checks', hcBody(value));
    expect(res.status).toBe(422);
    const body = (await res.json()) as {
      code: string;
      detail: string;
      field_errors: { loc: string[]; msg: string }[];
    };
    expect(body.code).toBe(code);
    expect(body.field_errors).toEqual([{ loc: ['body', 'value_text'], msg: body.detail }]);
  });

  it('목: 0(할인 없음 확인)·574,999,999 → 201', async () => {
    expect((await viaMock('/ops/human-checks', hcBody('0'))).status).toBe(201);
    expect((await viaMock('/ops/human-checks', hcBody('574,999,999'))).status).toBe(201);
  });

  it('F11 목: checked_at·값 둘 다 틀리면 validation_error + 모든 칸(checked_at 먼저)', async () => {
    const res = await viaMock('/ops/human-checks', hcBody('1,0', '2026-10-08'));
    expect(res.status).toBe(422);
    const body = (await res.json()) as { code: string; field_errors: { loc: string[] }[] };
    expect(body.code).toBe('validation_error');
    expect(body.field_errors.map((f) => f.loc[1])).toEqual(['checked_at', 'value_text']);
  });

  it('F11 화면: checked_at·값 칸 오류를 함께 보인다', () => {
    const e = new ApiError('validation_error', 'bad', 422, [
      { loc: ['body', 'checked_at'], msg: 'checked bad' },
      { loc: ['body', 'value_text'], msg: 'value bad' },
    ]);
    const { fields } = humanCheckServerErrors(e);
    expect(fields.checkedAt).toBeTruthy();
    expect(fields.value).toBe('value bad');
  });
});

// ─── F5 체크리스트 PATCH 202 ───────────────────────────────

describe('F5(D17-5) PATCH /ops/checklist 202 + job_id → 발행 감시', () => {
  async function changeStatus(to: string) {
    const table = await screen.findByRole('table', { name: t('page.G7.checklist') });
    const select = within(table).getAllByRole('combobox')[0] as HTMLSelectElement;
    await waitFor(() => expect(select).toBeEnabled());
    await userEvent.selectOptions(select, to);
  }

  it('목: 상태가 바뀌면 202 + job_id(snapshot.publish 상태 있는 잡), 같은 값이면 200 + null', async () => {
    const first = await viaMock('/ops/checklist/51', jsonInit('PATCH', { status: 'done' }));
    expect(first.status).toBe(202);
    const item = (await first.json()) as { job_id: number | null; status: string };
    expect(item.status).toBe('done');
    expect(item.job_id).not.toBeNull();
    const jobRes = await viaMock(`/jobs/${item.job_id}`, { method: 'GET' });
    expect(((await jobRes.json()) as JobRun).job_name).toBe('snapshot.publish');
    const again = await viaMock('/ops/checklist/51', jsonInit('PATCH', { status: 'done' }));
    expect(again.status).toBe(200);
    expect(((await again.json()) as { job_id: number | null }).job_id).toBeNull();
  });

  it('화면: 202 → 발행 진행(publish-job), 200 → "발행 작업 없음" 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/ops');
    await changeStatus('done');
    const box = await screen.findByTestId('checklist-job');
    expect(within(box).getByText(t('page.G7.check.jobHint'))).toBeInTheDocument();
    expect(await within(box).findByTestId('publish-job')).toBeInTheDocument();
    server.use(
      http.patch(mswPath('/ops/checklist/:id'), async () =>
        HttpResponse.json({
          ...(await example<Record<string, unknown>>('/ops/checklist/51', jsonInit('PATCH', {}))),
          job_id: null,
        }),
      ),
    );
    await changeStatus('na');
    expect(await screen.findByTestId('checklist-job-none')).toHaveTextContent(
      t('page.G7.check.unchanged'),
    );
    expect(screen.queryByTestId('checklist-job')).toBeNull();
  });
});

// ─── F6 지역 이름만 → 202 ─────────────────────────────────

describe('F6(D17-5) PATCH /regions 이름만 → 202 + snapshot.publish 잡', () => {
  it('목: 선택 그대로 + 이름만 → 202, change_event null, job = snapshot.publish', async () => {
    const region = await example<Region>('/regions/1');
    const res = await viaMock(
      '/regions/1',
      jsonInit('PATCH', { selections: region.selections, name: `${region.name} 2` }),
    );
    expect(res.status).toBe(202);
    const body = (await res.json()) as RegionPatched;
    expect(body.change_event).toBeNull();
    expect(body.added).toEqual([]);
    expect(body.region.name).toBe(`${region.name} 2`);
    expect(body.job_id).not.toBeNull();
    const jobRes = await viaMock(`/jobs/${body.job_id}`, { method: 'GET' });
    expect(((await jobRes.json()) as JobRun).job_name).toBe('snapshot.publish');
  });

  it('화면: 이름만 202 → 이름만 안내 + 발행 진행(재판정 안내 아님)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const region = await example<Region>('/regions/1');
    const { container } = renderWithProviders(
      <MemoryRouter>
        <RegionExpandPanel region={region} />
      </MemoryRouter>,
    );
    const panel = within(container);
    await userEvent.type(panel.getByLabelText(t('page.G0_2.expand.name')), ' 2');
    await userEvent.click(panel.getByText(t('page.G0_2.expand.submit')));
    expect(await panel.findByTestId('expand-name-publish')).toHaveTextContent(
      t('page.G0_2.expand.nameOnlyPublish'),
    );
    expect(await panel.findByTestId('publish-job')).toBeInTheDocument();
    expect(panel.queryByText(t('page.G0_2.expand.jobHint'))).toBeNull();
    expect(panel.queryByTestId('expand-name-only')).toBeNull();
  });
});

// ─── F7 호재 좌표 6자리 ────────────────────────────────────

describe('F7(m8·m14) PATCH /catalysts 좌표 소수 6자리 비교 · 200 안내', () => {
  it('목: 소수 7자리가 6자리 반올림으로 같으면 200 + null', async () => {
    const body = (lat: number) => ({
      location_confirmed: true,
      complex_ids: [2],
      lat,
      lon: 126.6543214,
    });
    expect((await viaMock('/catalysts/50', jsonInit('PATCH', body(37.1234567)))).status).toBe(202);
    const again = await viaMock('/catalysts/50', jsonInit('PATCH', body(37.12345671)));
    expect(again.status).toBe(200);
  });

  it("200 안내 문구는 '발행할 리비전 없음'도 말한다(m14)", () => {
    expect(t('page.G6.loc.unchanged')).toMatch(/발행할 리비전/);
  });
});

// ─── F8·F9 발행 재시도·재등록 ──────────────────────────────

describe('F8(D17-3) 발행 예외 재시도 = 진행 중', () => {
  const retrying = job(
    980,
    'snapshot.publish',
    'queued',
    {
      error_retries: 2,
      publish_error: 'OperationalError',
      requeue_reason: 'publish_error: OperationalError: database is locked',
      not_before: '2026-10-12T10:00:08+09:00',
    },
    { snapshot_id: 13 },
  );

  it('JobProgressView: "발행 오류 — 다시 시도하는 중(2/5회)", 영문 코드·오류 줄 없음', () => {
    renderWithProviders(<JobProgressView job={retrying} />);
    const box = screen.getByRole('status');
    expect(within(box).getByTestId('job-requeued')).toHaveTextContent(
      t('job.requeuedError', { n: '2', max: '5' }),
    );
    expect(box.textContent).not.toMatch(/publish_error/);
    expect(within(box).queryByText(/오류: /)).toBeNull();
  });

  it('publishPhase: 재시도 queued = waiting, 5회 넘어 failed(재등록 없음) = 실패(코드 접두 없이)', () => {
    const trigger = job(979, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 980 });
    const base = { trigger, snapshot: undefined, watchStart: 0, now: 0 };
    expect(publishPhase({ ...base, last: retrying }).kind).toBe('waiting');
    const failed = job(
      980,
      'snapshot.publish',
      'failed',
      { error_retries: 5, publish_error: 'OperationalError' },
      { snapshot_id: 13 },
      'publish_error: OperationalError: database is locked',
    );
    const phase = publishPhase({ ...base, last: failed });
    expect(phase).toEqual({
      kind: 'publishFailed',
      detail: 'OperationalError: database is locked',
    });
  });
});

describe('F9(D17-3) 미뤄진 쓰기 재등록(redeferred_job_id)을 이어 감시', () => {
  it('nextPublishJobId: deferred + redeferred_job_id → 그 잡, 실패 + redeferred → 그 잡, deferred + rejudge_job_id → 재판정', () => {
    expect(
      nextPublishJobId(
        job(990, 'snapshot.publish', 'done', {
          deferred_to: 13,
          publish_job_id: null,
          redeferred_job_id: 995,
        }),
      ),
    ).toBe(995);
    expect(
      nextPublishJobId(
        job(980, 'snapshot.publish', 'failed', { error_retries: 5, redeferred_job_id: 996 }),
      ),
    ).toBe(996);
    expect(
      nextPublishJobId(
        job(991, 'snapshot.publish', 'done', {
          deferred_to: 13,
          publish_job_id: null,
          rejudge_job_id: 997,
        }),
      ),
    ).toBe(997);
  });

  it('jobRefetchInterval: done + deferred_to(재등록 전, 30분 안) → 계속 느리게 폴링, 재등록·오래됨 → 멈춤', () => {
    const deferred = job(990, 'snapshot.publish', 'done', { deferred_to: 13 });
    expect(jobRefetchInterval({ status: 'success', data: deferred })).toBeGreaterThan(0);
    expect(
      jobRefetchInterval({
        status: 'success',
        data: { ...deferred, stats: { deferred_to: 13, redeferred_job_id: 995 } },
      }),
    ).toBe(false);
    const old = job(
      990,
      'snapshot.publish',
      'done',
      { deferred_to: 13 },
      {},
      null,
      new Date(Date.now() - 31 * 60_000).toISOString(),
    );
    expect(jobRefetchInterval({ status: 'success', data: old })).toBe(false);
    expect(jobRefetchInterval({ status: 'success', data: job(1, 'rejudge', 'done') })).toBe(false);
  });

  it('화면: rejudge → 발행 잡 미룸(deferred) → 나중에 redeferred_job_id → 새 잡 done = 발행됨, 재등록 안내', async () => {
    let deferredReads = 0;
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) => {
        const id = Number(params.id);
        if (id === 900)
          return HttpResponse.json(
            job(900, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 990 }),
          );
        if (id === 990) {
          deferredReads += 1;
          return HttpResponse.json(
            job(
              990,
              'snapshot.publish',
              'done',
              deferredReads < 2
                ? { deferred_to: 13, publish_job_id: null, published: false }
                : {
                    deferred_to: 13,
                    publish_job_id: null,
                    published: false,
                    redeferred_job_id: 995,
                  },
              { snapshot_id: 13, follow_up: true },
            ),
          );
        }
        return HttpResponse.json(
          job(
            995,
            'snapshot.publish',
            'done',
            { published: true, resumed_snapshot_id: 13, snapshot_id: 13 },
            { snapshot_id: 13, follow_up: true },
          ),
        );
      }),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={900} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByTestId('publish-deferred', {}, { timeout: 8000 }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId('publish-done', {}, { timeout: 15_000 })).toBeInTheDocument();
    expect(screen.getByTestId('publish-redeferred')).toHaveTextContent(t('job.publishRedeferred'));
  }, 25_000);
});

// ─── F10 보고서 compare 생략 503(회귀) ────────────────────

describe('F10(m9) POST /reports compare 생략 → 503 materialize_pending → 준비 중(회귀)', () => {
  it('비교 리비전을 고르지 않고 생성 → 503 → 준비 중 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    server.use(
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          { code: 'materialize_pending', detail: '기본 비교 report_diff 미완', pending_count: 1 },
          { status: 503, headers: { 'Retry-After': '5' } },
        ),
      ),
    );
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByText(t('page.G8.pending'))).toBeInTheDocument();
    const posted = (await matching(rec.requests, 'POST', '/reports')[0]!.body) as Record<
      string,
      unknown
    >;
    expect(posted.compare_snapshot_id ?? null).toBeNull();
    rec.stop();
  });
});
