import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { JOB_POLL_MS } from '@/api/hooks';
import type { CompareView, Weights } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { fromScenario, rebalance, toScenarioCreate, weightsSum } from './schema';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const W: Weights = { p10: 0.35, rerank: 0.2, gap: 0.15, benchmark: 0.1, supply: 0.1, liquidity: 0.1 };

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
  it('가중치 합 ≠ 1 이면 거부', () => {
    const r = toScenarioCreate(base, { ...W, p10: 0.9 }, null);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors.weights).toContain('1');
  });
  it('통과하면 억 → 원으로 바꾼 ScenarioCreate', () => {
    const r = toScenarioCreate({ ...base, equity_won: '2', loan_limit_won: '6', score: '20' }, W, null);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.body.params.equity_won).toBe(200_000_000);
      expect(r.body.params.loan_limit_won).toBe(600_000_000);
      expect(r.body.params.subscription).toEqual({ has_account: false, score: 20 });
      expect(r.body.weights).toEqual(W);
    }
  });
});

describe('G5 시나리오 화면', () => {
  it('잘못된 입력은 필드 오류를 보이고 POST 하지 않는다', async () => {
    const rec = recordRequests();
    renderRoute('/scenario');
    const form = await screen.findByRole('form', { name: t('page.G5.form') });
    await userEvent.type(within(form).getByLabelText(t('page.G5.field.score')), '{selectall}150');
    await userEvent.click(within(form).getByRole('button', { name: t('page.G5.save') }));
    expect(await within(form).findByText(t('page.G5.error.max', { max: 84 }))).toBeInTheDocument();
    expect(matching(rec.requests, 'POST', '/scenarios')).toHaveLength(0);
    rec.stop();
  });

  it('슬라이더를 움직여도 합은 1.00, 저장 → POST /scenarios', async () => {
    const rec = recordRequests();
    renderRoute('/scenario?scenario=B');
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
    rec.stop();
  });

  it('요건 사전 계산 표 + 캐시 히트 수', async () => {
    renderRoute('/scenario?scenario=B');
    expect(
      await screen.findByRole('table', { name: t('page.G5.requirements') }),
    ).toBeInTheDocument();
    expect(await screen.findByTestId('cache-hits')).toHaveTextContent(/18/);
  });

  it(`재판정 실행 → POST /jobs(rejudge) → ${JOB_POLL_MS}ms 폴링으로 완료 → 이전 대비 표`, async () => {
    const rec = recordRequests();
    renderRoute('/scenario?scenario=B');
    const run = await screen.findByRole('button', { name: t('page.G5.run') });
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
    const polls = matching(rec.requests, 'GET', /\/jobs\/\d+$/);
    expect(polls.length).toBeGreaterThanOrEqual(2);
    rec.stop();
  }, 15_000);

  it('escaped 봉투 → 상단 배너 "판정기가 질문을 남겼습니다" + 질문 텍스트', async () => {
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
    expect(within(banner as HTMLElement).getByText('자기자본 범위를 알려 주세요')).toBeInTheDocument();
  });
});
