/**
 * R9-UI P1(30-proposal §2, D28-1·D28-4): G3 머리를 3단으로 — 지금 상태 → 내야 할 돈 + 청약 전 꼭 볼 조건 → 점수·분류 → 탭.
 * 탭을 누르지 않고 돈·제한·일정이 보이고, 예전 머리의 값·라벨·출처가 하나도 사라지지 않는다.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexDetail } from '@/api/types';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleDetail(): Promise<ComplexDetail> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/complexes/2'),
  );
  return (await res?.json()) as ComplexDetail;
}

function useDetail(detail: ComplexDetail) {
  server.use(http.get(mswPath('/complexes/:id'), () => HttpResponse.json(detail)));
}

async function summary(name: string): Promise<HTMLElement> {
  return screen.findByRole('region', { name });
}

/** FactCell(출처 버튼)마다 라벨 글자 또는 확인 불가(사유)가 붙어 있다 */
function expectLabelled(root: HTMLElement, prov: string) {
  const cell = root.querySelector(`[data-prov="${prov}"]`);
  expect({ prov, found: cell !== null }).toEqual({ prov, found: true });
  const label = cell?.querySelector('[data-testid="label-badge"], [data-testid="empty-state"]');
  expect({ prov, label: (label?.textContent ?? '').trim().length > 0 }).toEqual({
    prov,
    label: true,
  });
}

describe('R9-UI P1 G3 머리 3단', () => {
  it('정보 계층 순서: 단지 → 지금 상태 → 내야 할 돈 → 청약 전 꼭 볼 조건 → 점수·분류, 그 뒤 탭', async () => {
    const detail = await exampleDetail();
    const { container } = renderRoute('/complexes/2');
    await summary(detail.header.name);
    const tiers = [...container.querySelectorAll('[data-tier]')].map((el) =>
      el.getAttribute('data-tier'),
    );
    expect(tiers).toEqual(['identity', 'status', 'money', 'conditions', 'score']);
    const scoreTier = container.querySelector('[data-tier="score"]') as HTMLElement;
    const tablist = screen.getByRole('tablist', { name: t('page.G3.tabs') });
    expect(
      scoreTier.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('탭을 누르지 않고: 거주의무·재당첨·규제지역·상한제·전매 종료·계약금·중도금·잔금·당첨 발표 값과 라벨', async () => {
    const detail = await exampleDetail();
    const current = detail.payment.find((p) => p.is_current);
    expect(current).toBeDefined();
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    const conditions = within(head).getByRole('region', { name: t('page.G3.summary.conditions') });
    for (const fact of [
      detail.header.residency_months,
      detail.header.rewin_restriction_years,
      detail.header.regulated,
      detail.header.price_cap,
      detail.header.resale_end,
    ]) {
      expectLabelled(conditions, fact?.prov ?? '');
    }
    const money = within(head).getByRole('region', { name: t('page.G3.summary.money') });
    for (const fact of [current?.down_payment_pct, current?.interim_pct, current?.balance_pct]) {
      expectLabelled(money, fact?.prov ?? '');
    }
    const status = within(head).getByRole('region', { name: t('page.G3.summary.status') });
    expectLabelled(status, detail.header.winner_date.prov ?? '');
    // 날짜는 기준일 대비 D±
    const winner = status.querySelector(`[data-prov="${detail.header.winner_date.prov}"]`);
    expect(winner?.textContent).toMatch(/\(D[+-]\d+\)|D-day/);
  });

  it('현재 적용 공고 = is_current 행의 notice_kind(값 그대로)', async () => {
    const detail = await exampleDetail();
    const kind = detail.payment.find((p) => p.is_current)?.notice_kind ?? '';
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    expect(
      within(head).getByText(t('page.G3.summary.currentNotice', { kind })),
    ).toBeInTheDocument();
  });

  it('접수 일정이 비면 "확인 불가(공고 일정 미수집)"', async () => {
    const detail = await exampleDetail();
    useDetail({ ...detail, header: { ...detail.header, apply_dates: [] } });
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    const status = within(head).getByRole('region', { name: t('page.G3.summary.status') });
    expect(
      within(status).getByText(
        t('empty.unknownWithReason', { reason: t('page.G3.summary.noScheduleReason') }),
      ),
    ).toBeInTheDocument();
  });

  it('머리의 계약금 값과 "내야 할 돈·일정" 탭의 값은 같은 출처(prov id)', async () => {
    const detail = await exampleDetail();
    const prov = detail.payment.find((p) => p.is_current)?.down_payment_pct.prov ?? '';
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    expect(head.querySelector(`[data-prov="${prov}"]`)).not.toBeNull();
    await userEvent.click(screen.getByRole('tab', { name: t('page.G3.tab.payment') }));
    const panel = await screen.findByRole('tabpanel');
    expect(panel.querySelector(`[data-prov="${prov}"]`)).not.toBeNull();
  });

  it('계약금 원 금액: 옛 저장본(price.payment_amounts 없음)은 "확인 불가(계산값 미제공)"', async () => {
    const detail = await exampleDetail();
    const { payment_amounts: _drop, ...price } = detail.price;
    useDetail({ ...detail, price });
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    const money = within(head).getByRole('region', { name: t('page.G3.summary.money') });
    expect(
      within(money).getAllByText(
        t('empty.unknownWithReason', { reason: t('page.G3.summary.downWonMissing') }),
      ).length,
    ).toBeGreaterThan(0);
  });

  it('예전 머리 값(가격·전매·입주·종합 점수·분류 확률·rerank 변화)이 모두 머리에 남는다', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    for (const fact of [
      detail.price.price_low,
      detail.price.price_high,
      detail.header.resale_end,
      detail.header.move_in_ym,
      detail.header.inclusion_prob,
      detail.score?.total,
      detail.score?.delta_rerank,
      detail.header.units_total,
    ]) {
      if (fact?.prov) expectLabelled(head, fact.prov);
    }
    expect(head).toHaveTextContent(detail.header.address ?? '');
    expect(within(head).getByText(t('page.G3.header.scopeReason'))).toBeInTheDocument();
  });

  it('"자격 판정 아님" 고지와 하단 고정 문구', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const head = await summary(detail.header.name);
    expect(within(head).getByText(t('page.G3.summary.notQualification'))).toBeInTheDocument();
    expect(screen.getByText(t('app.disclaimer'))).toBeInTheDocument();
  });
});

describe('R9-UI P1 G3 모바일(읽기 전용)', () => {
  it('탭 줄 대신 <select>, 고르면 해시가 바뀐다', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      const detail = await exampleDetail();
      const { router } = renderRoute('/complexes/2');
      await summary(detail.header.name);
      expect(screen.queryByRole('tablist')).toBeNull();
      const select = screen.getByRole('combobox', { name: t('page.G3.tabs') });
      await userEvent.selectOptions(select, 'payment');
      expect(router.state.location.hash).toBe('#payment');
      expect(screen.getByRole('main')).toHaveAttribute('data-readonly', 'true');
    } finally {
      window.matchMedia = original;
    }
  });
});
