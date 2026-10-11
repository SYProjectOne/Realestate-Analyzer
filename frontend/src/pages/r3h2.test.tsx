/**
 * R3h FE7 2단계 — 계약 2026-10-09.13 FE 차이 표(`contracts/CHANGELOG.md` .13 F1–F10) 화면 맞춤.
 *  - F1(D16-1): 사람 확인 필드 `discount`(할인, 기준 타입, 원). 값 검사·오류는 서버 422 field_errors 기준.
 *  - F2(D16-1): 공고문 파서 할인은 늘 '추정' — 옆에 "공고문에서 찾은 할인(조건 확인 필요) — 사람 확인 시 구매가에 반영"
 *    안내 + G7 사람 확인 링크(단지·필드 discount 미리 채움, 전역 쿼리 유지). '확인됨'(사람 확인) 할인은 기존 차감 표시.
 *  - F3(D16-4): PATCH /catalysts 200(바뀐 것 없음, job_id null) → 진행 안내·다시 읽기 없음. 202 + job_id → 감시.
 *  - F4(D16-3): 발행 busy → 잡이 queued 로 돌아간다(requeue_reason) — 실패·막힘이 아니라 진행 중. 40회 넘김 failed → 실패.
 *  - F5·F6: publish_job_id 를 따라 잇는다(.12 F15 규칙 그대로 — 회귀 확인).
 *  - F8: POST /reports 503 materialize_pending(202 전) → 준비 중 안내(회귀 확인).
 *  - F9: 422 validation_error + field_errors 모든 칸(checked_at 먼저) → 칸마다(1단계 m17 과 같은 경로 — 회귀 확인).
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { MemoryRouter } from 'react-router';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { publishPhase } from '@/api/jobWatch';
import { HUMAN_CHECK_FIELDS, type ComplexDetail, type Fact, type JobRun } from '@/api/types';
import { PublishJobProgress } from '@/components';
import { JobProgressView } from '@/components/JobProgress';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';
import { humanCheckFieldOf } from './ops/humanCheckRules';

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

async function exampleDetail(): Promise<ComplexDetail> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/complexes/2'),
  );
  return (await res?.json()) as ComplexDetail;
}

// ─── F1 사람 확인 discount ─────────────────────────────────

describe('F1(D16-1) 사람 확인 필드 discount', () => {
  async function humanForm() {
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    const complex = within(form).getByLabelText(t('page.G7.hc.complex'));
    await waitFor(() => expect(complex.querySelector('option[value="2"]')).not.toBeNull());
    return form;
  }

  it('필드 목록·주장 대상 매핑: discount(discount_by_type.<타입> 포함)', () => {
    expect(HUMAN_CHECK_FIELDS).toContain('discount');
    expect(humanCheckFieldOf('discount')).toBe('discount');
    expect(humanCheckFieldOf('discount_by_type.84A')).toBe('discount');
  });

  it('폼: 할인 칸 선택 → 값(쉼표·원) 그대로 POST field=discount, 201 + job_id 감시', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await humanForm();
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.complex')), '2');
    const field = within(form).getByLabelText(t('page.G7.hc.field'));
    expect(
      within(field).getByRole('option', { name: t('page.G7.hcField.discount') }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(field, 'discount');
    const value = within(form).getByLabelText(t('page.G7.hc.value'));
    expect(value).toHaveAccessibleDescription(t('page.G7.hcHint.discount'));
    await userEvent.type(value, '3,000,000원');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() =>
      expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1),
    );
    expect(await matching(rec.requests, 'POST', '/ops/human-checks')[0]!.body).toMatchObject({
      complex_id: 2,
      field: 'discount',
      value_text: '3,000,000원',
    });
    expect(await within(form).findByTestId('human-check-job')).toBeInTheDocument();
    expect(within(form).getByTestId('publish-job')).toBeInTheDocument();
    rec.stop();
  });

  it('값 검사는 서버가 — 422 value_text 오류를 값 칸에(화면은 미리 거르지 않는다)', async () => {
    // R3i m2: 목은 할인 값을 검사하지 않는다 — 서버 422 응답 모양(계약 .13 F1)을 테스트가 직접 준다
    server.use(
      http.post(mswPath('/ops/human-checks'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail: 'discount 는 원 단위 정수여야 한다',
            field_errors: [
              { loc: ['body', 'value_text'], msg: 'discount 는 원 단위 정수여야 한다' },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/ops');
    const form = await humanForm();
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.complex')), '2');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.field')), 'discount');
    const value = within(form).getByLabelText(t('page.G7.hc.value'));
    await userEvent.type(value, '삼백만');
    await userEvent.selectOptions(within(form).getByLabelText(t('page.G7.hc.enteredBy')), '운영자');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G7.hc.submit') }));
    await waitFor(() => expect(value).toHaveAttribute('aria-invalid', 'true'));
    expect(matching(rec.requests, 'POST', '/ops/human-checks')).toHaveLength(1);
    expect(value).toHaveAccessibleDescription('discount 는 원 단위 정수여야 한다');
    rec.stop();
  });

  it('URL hc_field=discount 미리 채움', async () => {
    renderRoute('/ops?hc_complex=2&hc_field=discount');
    const form = await humanForm();
    expect(within(form).getByLabelText(t('page.G7.hc.field'))).toHaveValue('discount');
  });
});

// ─── F2 '추정' 할인 안내 ───────────────────────────────────

describe("F2(D16-1) 파서 할인은 '추정' — 안내 + G7 사람 확인 링크", () => {
  const discount = (label: Fact['label'], reason: string | null): Fact => ({
    v: 10_000_000,
    label,
    reason,
    prov: 'fp_9001',
    checked_at: '2026-10-08',
    unit: 'won',
  });

  function serve(patch: (d: ComplexDetail) => ComplexDetail) {
    server.use(
      http.get(mswPath('/complexes/:id'), async () =>
        HttpResponse.json(patch(await exampleDetail())),
      ),
    );
  }

  it("'추정' 할인(헤더·가격 표): 안내 문구 + /ops 사람 확인 링크(단지·discount, 전역 쿼리 유지)", async () => {
    serve((d) => ({
      ...d,
      price: {
        ...d.price,
        discount: discount('추정', '공고문 자동 추출 — 조건 확인 필요'),
        discount_applied: false,
      },
    }));
    const detail = await exampleDetail();
    const { router } = renderRoute('/complexes/2?region=1&snapshot=12&scenario=base#price');
    const header = await screen.findByTestId('header-discount');
    const headerLink = within(header).getByRole('link', {
      name: t('page.G3.price.discountHumanCheck'),
    });
    const href = new URL(headerLink.getAttribute('href') ?? '', 'http://x');
    expect(href.pathname).toBe('/ops');
    expect(href.searchParams.get('region')).toBe('1');
    expect(href.searchParams.get('snapshot')).toBe('12');
    expect(href.searchParams.get('scenario')).toBe('base');
    expect(href.searchParams.get('hc_complex')).toBe(String(detail.header.id));
    expect(href.searchParams.get('hc_field')).toBe('discount');
    expect(href.hash).toBe('#human-check');
    const row = await screen.findByTestId('price-discount');
    expect(row).toHaveTextContent(t('page.G3.price.discountEstimated'));
    expect(
      within(row).getByRole('link', { name: t('page.G3.price.discountHumanCheck') }),
    ).toBeInTheDocument();
    // 링크를 따라가면 G7 사람 확인 폼이 할인으로 미리 채워진다
    await userEvent.click(headerLink);
    await waitFor(() => expect(router.state.location.pathname).toBe('/ops'));
    const form = await screen.findByRole('form', { name: t('page.G7.human') });
    expect(within(form).getByLabelText(t('page.G7.hc.field'))).toHaveValue('discount');
  });

  it("타입별 '추정' 할인만 있어도 가격 표(기준 타입 줄)에 안내 + 링크", async () => {
    const basis = (await exampleDetail()).types.find((r) => r.is_basis)?.type_code ?? '84A';
    serve((d) => {
      return {
        ...d,
        price: { ...d.price, discount: null, discount_applied: false },
        payment: d.payment.map((p) =>
          p.is_current
            ? { ...p, discount_by_type: { [basis]: discount('추정', '공고문 자동 추출') } }
            : p,
        ),
      };
    });
    renderRoute('/complexes/2#price');
    // R3i m3: 표 아래 공통 한 줄이 아니라 기준 타입 줄에(기준 타입 아닌 줄은 r3i.test.tsx)
    const note = await screen.findByTestId(`type-discount-note-${basis}`);
    expect(note).toHaveTextContent(t('page.G3.price.discountEstimated'));
    expect(
      within(note).getByRole('link', { name: t('page.G3.price.discountHumanCheck') }),
    ).toBeInTheDocument();
  });

  it("'확인됨'(사람 확인) 할인: 기존 차감 표시, 추정 안내·링크 없음", async () => {
    serve((d) => ({
      ...d,
      price: {
        ...d.price,
        discount: discount('확인됨', '사람 확인(phone)'),
        discount_applied: true,
      },
    }));
    renderRoute('/complexes/2#price');
    const row = await screen.findByTestId('price-discount');
    expect(row).toHaveTextContent(t('page.G3.price.discountApplied'));
    expect(screen.queryByTestId('discount-estimated')).toBeNull();
    expect(screen.queryByRole('link', { name: t('page.G3.price.discountHumanCheck') })).toBeNull();
  });
});

// ─── F3 PATCH /catalysts 200 ───────────────────────────────

describe('F3(D16-4) 호재 PATCH: 200 바뀐 것 없음 → 감시·다시 읽기 없음, 202 → 감시', () => {
  async function saveGtx() {
    const panel = await screen.findByRole('region', { name: t('page.G6.loc.title') });
    const list = within(panel).getByRole('list', { name: t('page.G6.loc.title') });
    const item = (await within(list).findByText('GTX-B')).closest('li') as HTMLElement;
    await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.open') }));
    const form = within(item).getByRole('form', {
      name: t('page.G6.loc.formFor', { name: 'GTX-B' }),
    });
    const select = within(form).getByLabelText(t('page.G6.loc.complexes'));
    await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
    await userEvent.selectOptions(
      select,
      (select.querySelectorAll('option')[0] as HTMLOptionElement).value,
    );
    await userEvent.click(within(form).getByRole('button', { name: t('page.G6.loc.submit') }));
    return panel;
  }

  it('200 + job_id null → "바뀐 것 없음" 안내, 발행 진행·대기 안내 없음, 지역·사실 다시 읽지 않음', async () => {
    server.use(
      http.patch(mswPath('/catalysts/:id'), async () => {
        const res = await getResponse(
          generatedHandlers as RequestHandler[],
          new Request('http://localhost/api/catalysts/50', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
          }),
        );
        return HttpResponse.json(await res!.json(), { status: 200 });
      }),
    );
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/market');
    const panel = await saveGtx();
    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/catalysts/50')).toHaveLength(1));
    const regionsAfterPatch = () =>
      rec.requests.filter(
        (r, i) =>
          r.method === 'GET' &&
          r.url.pathname.endsWith('/regions') &&
          i > rec.requests.findIndex((x) => x.method === 'PATCH'),
      ).length;
    expect(await within(panel).findByTestId('catalyst-job-none')).toHaveTextContent(
      t('page.G6.loc.unchanged'),
    );
    expect(within(panel).queryByTestId('catalyst-job')).toBeNull();
    expect(within(panel).queryByTestId('publish-pending')).toBeNull();
    await new Promise((r) => setTimeout(r, 300));
    expect(regionsAfterPatch()).toBe(0);
    rec.stop();
  });

  it('목(계약 예시): 처음 저장 202 + 잡 감시, 같은 값 다시 저장 200 — 진행 안내 사라짐', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/market');
    const panel = await saveGtx();
    const jobBox = await within(panel).findByTestId('catalyst-job');
    expect(within(jobBox).getByText(t('page.G6.loc.jobHint'))).toBeInTheDocument();
    expect(await within(jobBox).findByText('snapshot.publish')).toBeInTheDocument();
    await saveGtx();
    expect(await within(panel).findByTestId('catalyst-job-none')).toHaveTextContent(
      t('page.G6.loc.unchanged'),
    );
    expect(within(panel).queryByTestId('catalyst-job')).toBeNull();
  });
});

// ─── F4 발행 busy 재큐잉 ───────────────────────────────────

describe('F4(D16-3) 발행 busy → queued 재큐잉은 진행 중(실패·막힘 아님)', () => {
  const requeued = job(
    950,
    'snapshot.publish',
    'queued',
    {
      requeue_count: 3,
      not_before: '2026-10-12T10:00:08+09:00',
      requeue_reason: 'publish_in_progress: 다른 발행(job:949)이 진행 중',
      publish_in_progress: 'job:949',
    },
    { snapshot_id: 13 },
  );

  it('JobProgressView: 대기 + "다른 발행이 끝나길 기다리는 중(재시도 3회)" — 오류 줄 없음', () => {
    renderWithProviders(<JobProgressView job={requeued} />);
    const box = screen.getByRole('status');
    expect(box).toHaveAttribute('data-status', 'queued');
    expect(within(box).getByTestId('job-requeued')).toHaveTextContent(
      t('job.requeued', { n: '3' }),
    );
    expect(box.textContent).not.toMatch(/publish_in_progress/);
    expect(within(box).queryByText(/오류/)).toBeNull();
  });

  it('publishPhase: queued 재큐잉 = waiting · 40회 넘어 failed = 발행 실패', () => {
    const trigger = job(900, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 950 });
    const base = { trigger, snapshot: undefined, watchStart: 0, now: 0 };
    expect(publishPhase({ ...base, last: requeued }).kind).toBe('waiting');
    const exhausted = job(
      950,
      'snapshot.publish',
      'failed',
      { requeue_count: 40, publish_in_progress: 'job:949' },
      { snapshot_id: 13 },
      'publish_in_progress: 다른 발행(job:949)이 진행 중',
    );
    expect(publishPhase({ ...base, last: exhausted }).kind).toBe('publishFailed');
  });

  it('화면: rejudge done → 발행 잡 queued(재큐잉) → 대기 안내 유지, 막힘·실패 안내 없음', async () => {
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) =>
        Number(params.id) === 900
          ? HttpResponse.json(job(900, 'rejudge', 'done', { snapshot_id: 13, publish_job_id: 950 }))
          : HttpResponse.json(requeued),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={900} />
      </MemoryRouter>,
    );
    const box = await screen.findByTestId('publish-job');
    expect(await within(box).findByTestId('job-requeued')).toBeInTheDocument();
    expect(box).toHaveAttribute('data-phase', 'waiting');
    expect(within(box).getByTestId('publish-pending')).toBeInTheDocument();
    expect(within(box).queryByTestId('publish-failed')).toBeNull();
    expect(within(box).queryByTestId('publish-blocked')).toBeNull();
  });
});

// ─── F5·F6 publish_job_id 사슬(회귀) ───────────────────────

describe('F5·F6 publish_job_id 를 이어 감시(회귀)', () => {
  it('F5 그 자리 발행 busy → publish_job_id(다른 잡)를 이어 그 잡 done 이면 발행됨', async () => {
    server.use(
      http.get(mswPath('/jobs/:id'), ({ params }) =>
        Number(params.id) === 970
          ? HttpResponse.json(
              job(970, 'region.expand', 'done', {
                published: false,
                publish_in_progress: 'job:949',
                publish_job_id: 971,
                publish_retry_job_id: 971,
                snapshot_id: 13,
              }),
            )
          : HttpResponse.json(
              job(971, 'snapshot.publish', 'done', { publish_job_id: 971, published: true }),
            ),
      ),
    );
    renderWithProviders(
      <MemoryRouter>
        <PublishJobProgress jobId={970} />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('publish-done', {}, { timeout: 8000 })).toBeInTheDocument();
  }, 15_000);

  it('F6 포함돼 닫힌 후속 잡 → publish_job_id(정수)를 이어 감시', () => {
    const included = job(
      960,
      'snapshot.publish',
      'done',
      { included_in_snapshot_id: 13, publish_job_id: 955 },
      { snapshot_id: 13, follow_up: true },
    );
    const base = { trigger: included, snapshot: undefined, watchStart: 0, now: 0 };
    expect(publishPhase({ ...base, last: included }).kind).toBe('waiting');
    expect(
      publishPhase({
        ...base,
        last: job(955, 'region.expand', 'done', { publish_job_id: 955, published: true }),
      }).kind,
    ).toBe('published');
  });
});

// ─── F8 보고서 503(회귀) ───────────────────────────────────

describe('F8 POST /reports 비교 리비전 미완 → 503 materialize_pending 안내(회귀)', () => {
  it('생성 버튼 → 503 → 준비 중 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    server.use(
      http.post(mswPath('/reports'), () =>
        HttpResponse.json(
          { code: 'materialize_pending', detail: 'report_diff 미완', pending_count: 1 },
          { status: 503, headers: { 'Retry-After': '5' } },
        ),
      ),
    );
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    const compare = screen.getByLabelText(t('page.G8.compareSnapshot'));
    await waitFor(() => expect(compare.querySelector('option[value="11"]')).not.toBeNull());
    await userEvent.selectOptions(compare, '11');
    await userEvent.click(button);
    expect(await screen.findByText(t('page.G8.pending'))).toBeInTheDocument();
  });
});
