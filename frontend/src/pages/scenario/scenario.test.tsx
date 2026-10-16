import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import { JOB_POLL_MS } from '@/api/hooks';
import type { CompareView, Region, Scenario, ScenarioPreview, Weights } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { presetFacts, REQ_FIRST_ROWS } from './index';
import { fromScenario, rebalance, toScenarioCreate, weightsSum } from './schema';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const W: Weights = {
  p10: 0.35,
  rerank: 0.2,
  gap: 0.15,
  benchmark: 0.1,
  supply: 0.1,
  liquidity: 0.1,
};

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(new URL(`/api${path}`, 'http://localhost').toString()),
  );
  return (await res!.json()) as T;
}

describe('G5 가중치 합 1 제약', () => {
  it('하나를 바꾸면 나머지가 비례로 맞춰져 합이 1', () => {
    const next = rebalance(W, 'p10', 0.5);
    expect(next.p10).toBe(0.5);
    expect(weightsSum(next)).toBeCloseTo(1, 6);
    // 나머지 비율 유지: rerank : gap = 0.2 : 0.15
    expect((next.rerank ?? 0) / (next.gap ?? 1)).toBeCloseTo(0.2 / 0.15, 2);
  });
  it('1로 올리면 나머지는 0, 0으로 내리면 나머지 비례', () => {
    const all = rebalance(W, 'gap', 1);
    expect(all.gap).toBe(1);
    expect(weightsSum(all)).toBeCloseTo(1, 6);
    expect(all.p10).toBe(0);
    const none = rebalance(all, 'gap', 0);
    expect(weightsSum(none)).toBeCloseTo(1, 6);
  });
});

describe('G5 zod 검증', () => {
  const base = { ...fromScenario(null, '내 조건') };
  it('가점 범위·입주 시기 형식·이름 필수', () => {
    const bad = toScenarioCreate(
      { ...base, name: ' ', score: '99', move_in_by: '2028/03' },
      W,
      null,
    );
    expect(bad.ok).toBe(false);
    if (!bad.ok) {
      expect(bad.errors.name).toBe(t('page.G5.error.required'));
      expect(bad.errors.score).toBe(t('page.G5.error.max', { max: 84 }));
      expect(bad.errors.move_in_by).toBe(t('page.G5.error.ym'));
    }
  });
  it('칸별 범위(SC-9): 가족 수 정수·대출 1000 이하·보유 50 이하·크기 10 이상·내 돈 0 이상·숫자 아님', () => {
    const bad = toScenarioCreate(
      {
        ...base,
        household_size: '2.5',
        loan_limit_won: '1200',
        holding_years: '60',
        preferred_area_m2: '5',
        equity_won: '-1',
      },
      W,
      null,
    );
    expect(bad.ok).toBe(false);
    if (!bad.ok) {
      expect(bad.errors.household_size).toBe(t('page.G5.error.number'));
      expect(bad.errors.loan_limit_won).toBe(t('page.G5.error.max', { max: '1,000' }));
      expect(bad.errors.holding_years).toBe(t('page.G5.error.max', { max: 50 }));
      expect(bad.errors.preferred_area_m2).toBe(t('page.G5.error.min', { min: 10 }));
      expect(bad.errors.equity_won).toBe(t('page.G5.error.min', { min: 0 }));
    }
    const nan = toScenarioCreate({ ...base, equity_won: 'abc' }, W, null);
    expect(!nan.ok && nan.errors.equity_won).toBe(t('page.G5.error.numberAny'));
  });
  it('가중치 합 ≠ 1 이면 거부(지금 합을 %로)', () => {
    const r = toScenarioCreate(base, { ...W, p10: 0.9 }, null);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors.weights).toBe(t('page.G5.error.weightsSum', { sum: '155%' }));
  });
  it('통과하면 억 → 원으로 바꾼 ScenarioCreate', () => {
    const r = toScenarioCreate(
      { ...base, equity_won: '2', loan_limit_won: '6', score: '20' },
      W,
      null,
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.body.params.equity_won).toBe(200_000_000);
      expect(r.body.params.loan_limit_won).toBe(600_000_000);
      expect(r.body.params.subscription).toEqual({ has_account: false, score: 20 });
      expect(r.body.weights).toEqual(W);
    }
  });
});

describe('G5 조각 함수', () => {
  it('presetFacts: 서버 params·policy 를 이어 붙인 입력 값(가점·내 돈·대출·목적·보유·크기·의무·목표 시점)', async () => {
    const scenarios = await example<Scenario[]>('/scenarios');
    const a = scenarios.find((s) => s.code === 'A')!;
    const text = presetFacts(a);
    expect(text).toContain(t('page.G5.fact.homeless'));
    expect(text).toContain(t('page.G5.fact.score', { n: '60' }));
    expect(text).toContain(t('page.G5.fact.equity', { won: '' }).trim());
    expect(text).toContain(t('page.G5.purpose.실거주'));
    expect(text).toContain(t('page.G5.fact.area', { n: '84' }));
    expect(text).toContain(
      t('page.G5.fact.horizon', { target: t('chart.C01.horizon.move_in_plus_1y') }),
    );
    const c = scenarios.find((s) => s.code === 'C')!;
    expect(presetFacts(c)).toContain(
      t('page.G5.fact.horizon', { target: t('chart.C01.horizon.asof_plus_5y') }),
    );
  });
});

describe('G5 시나리오 화면', () => {
  it('머리: h1(내 조건(시나리오)) · 단계 번호가 붙은 질문형 구역 1~4', async () => {
    renderRoute('/scenario?scenario=B');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G5.title') }),
    ).toBeInTheDocument();
    for (const q of ['startQ', 'formQ', 'runQ', 'requirementsQ'] as const) {
      expect(await screen.findByRole('region', { name: t(`page.G5.${q}`) })).toBeInTheDocument();
    }
  });

  it('조건 목록을 불러오는 중 → 뼈대 + "불러오는 중…"', async () => {
    server.use(http.get(mswPath('/scenarios'), () => new Promise(() => {})));
    renderRoute('/scenario');
    const box = await screen.findByTestId('skeleton');
    expect(box).toHaveTextContent(t('app.loading'));
  });

  it('출발 조건: 기본 제공 카드 5개(이름·누구에게·주요 값) · 지금 보는 조건 = ?scenario= → 없으면 기본', async () => {
    const { router } = renderRoute('/scenario');
    const group = await screen.findByRole('radiogroup', { name: t('page.G5.presets') });
    const cards = within(group).getAllByRole('radio');
    expect(cards).toHaveLength(5);
    const on = cards.filter((c) => c.getAttribute('aria-checked') === 'true');
    expect(on).toHaveLength(1);
    expect(on[0]).toHaveTextContent('기본');
    expect(on[0]).toHaveTextContent(t('page.G5.current'));
    expect(on[0]).toHaveTextContent(t('page.G5.presetCodeBase'));
    expect(screen.getByText(t('page.G5.readOnlyBuiltin'))).toBeInTheDocument();
    // 카드를 누르면 전역 ?scenario= 가 바뀐다
    await userEvent.click(cards.find((c) => c.textContent?.includes('A 가점 높음'))!);
    await waitFor(() => expect(router.state.location.search).toContain('scenario=A'));
    const again = await screen.findByRole('radiogroup', { name: t('page.G5.presets') });
    expect(
      within(again)
        .getAllByRole('radio')
        .find((c) => c.getAttribute('aria-checked') === 'true'),
    ).toHaveTextContent('A 가점 높음');
  });

  it('출발 조건 select: 옵션 = 시나리오 이름 전부, 바꾸면 ?scenario=', async () => {
    const { router } = renderRoute('/scenario?scenario=B');
    const select = await screen.findByLabelText(t('page.G5.base'));
    expect(select).toHaveValue('B');
    expect(within(select).getAllByRole('option').length).toBeGreaterThanOrEqual(5);
    await userEvent.selectOptions(select, 'C');
    await waitFor(() => expect(router.state.location.search).toContain('scenario=C'));
  });

  it('폼: 칸 이름 = 쉬운 말 · 단위 · 숫자 칸 inputMode=decimal · 기본 제공이면 이름 비움 + 새 이름 안내', async () => {
    renderRoute('/scenario?scenario=A');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    expect(within(form).getByLabelText(t('page.G5.field.name'))).toHaveValue('');
    expect(screen.getByText(t('page.G5.readOnlyBuiltin'))).toBeInTheDocument();
    const equity = within(form).getByLabelText(t('page.G5.field.equity_won'));
    expect(equity).toHaveValue('3');
    expect(equity).toHaveAttribute('inputmode', 'decimal');
    expect(form.querySelectorAll('input[inputmode="decimal"]')).toHaveLength(6);
    expect(within(form).getAllByText(t('page.G5.unit.equity_won')).length).toBeGreaterThan(0);
    expect(within(form).getByText(t('page.G5.unit.score'))).toBeInTheDocument();
    expect(within(form).getByLabelText(t('page.G5.field.homeless'))).toBeChecked();
    expect(within(form).getByLabelText(t('page.G5.field.move_in_by'))).toHaveAttribute(
      'placeholder',
      t('page.G5.placeholderYm'),
    );
    const purpose = within(form).getByLabelText(t('page.G5.field.purpose'));
    expect(
      within(purpose)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual([
      t('page.G5.purpose.'),
      t('page.G5.purpose.실거주'),
      t('page.G5.purpose.시세차익'),
      t('page.G5.purpose.병행'),
    ]);
    // 청약 가점 용어 '?'
    expect(form.querySelector('[data-term="points"]')).not.toBeNull();
    for (const g of ['household', 'money', 'plan'] as const) {
      expect(
        within(form).getByRole('group', { name: t(`page.G5.group.${g}`) }),
      ).toBeInTheDocument();
    }
  });

  it('잘못된 입력은 필드 오류(aria-invalid·describedby)를 보이고 POST 하지 않는다', async () => {
    const rec = recordRequests();
    renderRoute('/scenario');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    const score = within(form).getByLabelText(t('page.G5.field.score'));
    await userEvent.type(score, '{selectall}150');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G5.save') }));
    expect(await within(form).findByText(t('page.G5.error.max', { max: 84 }))).toBeInTheDocument();
    expect(score).toHaveAttribute('aria-invalid', 'true');
    const described = score.getAttribute('aria-describedby');
    expect(described && document.getElementById(described)).toHaveTextContent(
      t('page.G5.error.max', { max: 84 }),
    );
    expect(within(form).getByText(t('page.G5.error.required'))).toBeInTheDocument();
    expect(matching(rec.requests, 'POST', '/scenarios')).toHaveLength(0);
    rec.stop();
  });

  it('비중: 쉬운 이름 슬라이더 6개 · 값 "35% (0.35)" · 오를 가능성 설명에 목표 시점·당첨 확률 아님 · 합계', async () => {
    renderRoute('/scenario?scenario=A');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    const group = within(form).getByRole('group', { name: t('page.G5.weights') });
    expect(within(group).getByText(t('page.G5.weightsHint'))).toBeInTheDocument();
    const sliders = within(group).getAllByRole('slider');
    expect(sliders.map((s) => s.getAttribute('aria-label'))).toEqual([
      t('chart.C06.component.p10'),
      t('chart.C06.component.rerank'),
      t('chart.C06.component.gap'),
      t('chart.C06.component.benchmark'),
      t('chart.C06.component.supply'),
      t('chart.C06.component.move_in'),
    ]);
    expect(sliders[0]).toHaveAttribute('aria-valuetext', '35%');
    const p10 = group.querySelector('[data-weight="p10"]') as HTMLElement;
    expect(p10).toHaveTextContent(t('page.G5.weightValue', { pct: '35%', dec: '0.35' }));
    expect(p10).toHaveTextContent(
      t('page.G4.row.p10Target', {
        target: t('chart.C01.horizon.move_in_plus_1y'),
        name: 'A 가점 높음(실거주)',
      }),
    );
    expect(p10).toHaveTextContent(t('chart.C10.why.p10'));
    expect(t('chart.C10.why.p10')).toContain('당첨 확률 아님');
    expect(within(group).getByTestId('weights-sum')).toHaveTextContent(
      t('page.G5.weightsSum', { pct: '100%', sum: '1.00' }),
    );
  });

  it('슬라이더를 움직여도 합은 1.00, 저장 → POST /scenarios → 토스트 + 저장한 조건으로 전환', async () => {
    const rec = recordRequests();
    const { router } = renderRoute('/scenario?scenario=B');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    const group = within(form).getByRole('group', { name: t('page.G5.weights') });
    const slider = within(group).getByRole('slider', { name: t('chart.C06.component.p10') });
    fireEvent.change(slider, { target: { value: '0.6' } });
    expect(within(group).getByTestId('weights-sum')).toHaveTextContent('1.00');
    await userEvent.type(within(form).getByLabelText(t('page.G5.field.name')), '내 조건');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G5.save') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/scenarios')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/scenarios')[0]?.body) as {
      weights: Weights;
      name: string;
    };
    expect(body.name).toBe('내 조건');
    expect(body.weights.p10).toBe(0.6);
    expect(weightsSum(body.weights)).toBeCloseTo(1, 3);
    expect(await screen.findByText(t('page.G5.saved'))).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).not.toContain('scenario=B'));
    rec.stop();
  });

  it('저장 실패 → role=alert "저장하지 못했어요: …"', async () => {
    server.use(
      http.post(mswPath('/scenarios'), () =>
        HttpResponse.json({ code: 'internal', detail: 'boom' }, { status: 500 }),
      ),
    );
    renderRoute('/scenario?scenario=B');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    await userEvent.type(within(form).getByLabelText(t('page.G5.field.name')), '내 조건');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G5.save') }));
    const alert = await within(form).findByRole('alert');
    expect(alert.textContent).toMatch(new RegExp(`^${t('page.G5.saveError', { detail: '' })}`));
  });

  it('저장 요청을 보내는 동안 [이 조건 저장] 꺼짐(#49)', async () => {
    server.use(http.post(mswPath('/scenarios'), () => new Promise(() => {})));
    renderRoute('/scenario?scenario=B');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    await userEvent.type(within(form).getByLabelText(t('page.G5.field.name')), '내 조건');
    const save = within(form).getByRole('button', { name: t('page.G5.save') });
    await userEvent.click(save);
    await waitFor(() => expect(save).toBeDisabled());
  });

  it('기준일이 없으면 [다시 판정하기] 꺼짐(#53)', async () => {
    const regions = await example<Region[]>('/regions');
    server.use(
      http.get(mswPath('/regions'), () =>
        HttpResponse.json([{ ...regions[0]!, latest_snapshot: null }]),
      ),
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([])),
    );
    renderRoute('/scenario?scenario=B');
    const run = await screen.findByRole('button', { name: t('page.G5.run') });
    await new Promise((r) => setTimeout(r, 300));
    expect(run).toBeDisabled();
  });

  it('읽기 전용 열쇠 → 저장·다시 판정 버튼 꺼짐 + 안내 title', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    renderRoute('/scenario?scenario=B');
    const save = await screen.findByRole('button', { name: t('page.G5.save') });
    const run = screen.getByRole('button', { name: t('page.G5.run') });
    for (const b of [save, run]) {
      await waitFor(() => expect(b).toBeDisabled());
      expect(b).toHaveAttribute('title', t('auth.readOnlyHint'));
    }
  });

  it('요건 사전 계산: 쉬운 열 이름 + 요건 문장 · 상태 배지·근거 · 단지 링크 · 캐시 줄', async () => {
    renderRoute('/scenario?scenario=B');
    const region = await screen.findByRole('region', { name: t('page.G5.requirementsQ') });
    const table = await within(region).findByRole('table', { name: t('page.G5.requirements') });
    expect(region).toHaveTextContent(t('page.G5.requirementsHint'));
    const heads = within(table).getAllByRole('columnheader');
    expect(heads[0]).toHaveTextContent(t('page.G5.req.complexCount', { total: '5', shown: '5' }));
    expect(heads[1]).toHaveTextContent(
      `${t('page.G5.req.access')} (${t('page.G5.reqTerm.access')})`,
    );
    expect(within(table).getAllByTestId('req-status')).toHaveLength(15);
    // 열 머리 아래 요건 문장 · 칸 아래 근거 = 서버 문장 그대로
    const preview = await example<ScenarioPreview>('/scenarios/3/preview');
    expect(heads[1]).toHaveTextContent(preview.requirements.access.text);
    expect(
      within(table).getAllByText(preview.requirements_pre[0]!.funds.evidence).length,
    ).toBeGreaterThan(0);
    const link = within(table).getByRole('link', { name: '엘리프 검단 포레듀' });
    expect(link.getAttribute('href')).toMatch(/^\/complexes\/2\?scenario=B/);
    expect(await within(region).findByTestId('cache-hits')).toHaveTextContent(/18/);
    expect(region).toHaveTextContent(t('page.G5.reqDisclaimer'));
  });

  it(`요건 표: 처음 ${REQ_FIRST_ROWS}곳 → [나머지 n곳 더 보기] · 제외 단지 회색 + 제외 배지`, async () => {
    const preview = await example<ScenarioPreview>('/scenarios/3/preview');
    const many = Array.from({ length: 11 }, (_, i) => ({
      ...preview.requirements_pre[0]!,
      complex_id: 100 + i,
      name: `단지${i}`,
      excluded: i === 0,
    }));
    server.use(
      http.get(mswPath('/scenarios/:id/preview'), () =>
        HttpResponse.json({ ...preview, requirements_pre: many }),
      ),
    );
    renderRoute('/scenario?scenario=B');
    const table = await screen.findByRole('table', { name: t('page.G5.requirements') });
    expect(within(table).getAllByRole('row')).toHaveLength(REQ_FIRST_ROWS + 1);
    const excluded = table.querySelector('[data-excluded="true"]') as HTMLElement;
    expect(excluded).toHaveClass('text-grayed');
    expect(within(excluded).getByText(t('page.G5.req.excluded'))).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole('button', {
        name: t('page.G5.reqMore', { n: String(11 - REQ_FIRST_ROWS) }),
      }),
    );
    expect(within(table).getAllByRole('row')).toHaveLength(12);
  });

  it('요건 표를 못 불러오면 오류 문구', async () => {
    server.use(
      http.get(mswPath('/scenarios/:id/preview'), () =>
        HttpResponse.json({ code: 'internal', detail: 'boom' }, { status: 500 }),
      ),
    );
    renderRoute('/scenario?scenario=B');
    const region = await screen.findByRole('region', { name: t('page.G5.requirementsQ') });
    expect(await within(region).findByText(/boom/, {}, { timeout: 10_000 })).toBeInTheDocument();
  }, 20_000);

  it(`재판정 실행 → POST /jobs(rejudge) → ${JOB_POLL_MS}ms 폴링으로 완료 → 이전 대비 표`, async () => {
    const rec = recordRequests();
    renderRoute('/scenario?scenario=B');
    const region = await screen.findByRole('region', { name: t('page.G5.runQ') });
    expect(region).toHaveTextContent(t('page.G5.runHint'));
    expect(await within(region).findByTestId('run-cache')).toHaveTextContent(
      t('page.G5.cache', { hits: '18', misses: '1' }),
    );
    const run = within(region).getByRole('button', { name: t('page.G5.run') });
    await waitFor(() => expect(run).toBeEnabled());
    await userEvent.click(run);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/jobs')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/jobs')[0]?.body) as {
      job_name: string;
      payload: { snapshot_id: number; scenario_id: number };
    };
    expect(body.job_name).toBe('rejudge');
    expect(body.payload.scenario_id).toBe(3);
    expect(await screen.findByText(t('page.G5.running'))).toBeInTheDocument();
    // 목 잡은 두 번째 폴링에서 done → 2초 간격 폴링을 실제로 기다린다
    expect(
      await screen.findByRole('table', { name: t('page.G5.diff') }, { timeout: JOB_POLL_MS * 3 }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('g5-done')).toHaveTextContent(t('page.G5.runDone'));
    expect(screen.getByRole('heading', { name: t('page.G5.diff') })).toBeInTheDocument();
    const polls = matching(rec.requests, 'GET', /\/jobs\/\d+$/);
    expect(polls.length).toBeGreaterThanOrEqual(2);
    rec.stop();
  }, 15_000);

  it('escaped 봉투 → 맨 위 띠 "판정기가 질문을 남겼어요" + 질문 텍스트', async () => {
    const res = await getResponse(
      generatedHandlers as RequestHandler[],
      new Request('http://localhost/api/snapshots/12/compare?ids=1,2'),
    );
    const view = (await res?.json()) as CompareView;
    const b = view.decisions.B;
    if (!b) throw new Error('예시에 상황 B 판정 없음');
    server.use(
      http.get(mswPath('/snapshots/:sid/compare'), () =>
        HttpResponse.json({
          ...view,
          decisions: {
            ...view.decisions,
            B: { ...b, status: 'escaped', escaped: true, question: '자기자본 범위를 알려 주세요' },
          },
        }),
      ),
    );
    renderRoute('/scenario?scenario=B');
    const title = await screen.findByText(t('page.G5.escaped'));
    const banner = title.closest('[role="alert"]');
    expect(banner).not.toBeNull();
    expect(
      within(banner as HTMLElement).getByText('자기자본 범위를 알려 주세요'),
    ).toBeInTheDocument();
  });

  it('판정기 결과·민감도: 머리글(조건 이름) + 질문형 h2 + C07·C10, 차트 바닥줄에 기준일', async () => {
    renderRoute('/scenario?scenario=B');
    const judge = await screen.findByRole('region', { name: t('page.G5.judgeQ') });
    expect(judge).toHaveTextContent(
      t('page.G5.sensEyebrow', { title: t('chart.C07.title'), name: 'B 가점 낮음·소액 자기자본' }),
    );
    expect(within(judge).getByRole('heading', { name: t('chart.C07.title') })).toBeInTheDocument();
    const sens = screen.getByRole('region', { name: t('chart.C10.question') });
    expect(sens).toHaveTextContent(
      t('page.G5.sensEyebrow', { title: t('chart.C10.title'), name: 'B 가점 낮음·소액 자기자본' }),
    );
    expect(within(sens).getByRole('heading', { name: t('chart.C10.title') })).toBeInTheDocument();
    await waitFor(() => {
      for (const f of document.querySelectorAll('figure'))
        expect(f).toHaveTextContent('2026-10-08');
    });
  });

  it('화면 글자에 내부 키(p10·rerank·move_in …)가 없고, 같은 용어 ? 는 한 번만', async () => {
    renderRoute('/scenario?scenario=A');
    await screen.findByRole('table', { name: t('page.G5.requirements') });
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: t('chart.C10.title') })).toBeInTheDocument(),
    );
    expect(document.body.textContent ?? '').not.toMatch(
      /\b(p10|rerank|benchmark|liquidity|move_in|supported|contradicted)\b/,
    );
    const terms = [...document.querySelectorAll('[data-testid="term"]')].map((el) =>
      el.getAttribute('data-term'),
    );
    expect(new Set(terms).size).toBe(terms.length);
  });
});
