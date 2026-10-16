/**
 * R11-DETAIL(D30, 보드 Detail · DetailTabs · Mobile): G3 질문형 구역 · 사실 줄(D30-7) · 납부 띠 + 카드 3 · 조건 칸 ·
 * 일정 진행 줄 · 경쟁률 요약(가점 범위 = 서버 competition_summary) · 점수 성분(쉬운 이름 · 비중 · 목표 시점 · 보장 아님) ·
 * 가격 갭 비교군 전체 중앙값(계약 .22 comps_median) · 차트 asof · 탭 해시·키보드 · 모바일 고르기 상자.
 * 화면은 계산하지 않고 판단 문장을 짓지 않는다(규칙 3·5) — 값은 FactCell(라벨·출처) 그대로인지 본다.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
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
import { G3_VISIBLE_TABS } from './index';

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

async function head(detail: ComplexDetail): Promise<HTMLElement> {
  return screen.findByRole('region', { name: detail.header.name });
}

function prov(root: HTMLElement, id: string | null | undefined): Element | null {
  return id ? root.querySelector(`[data-prov="${id}"]`) : null;
}

function withMobile<T>(fn: () => Promise<T>): Promise<T> {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    ...original(query),
    matches: query === MOBILE_QUERY,
  })) as typeof window.matchMedia;
  return fn().finally(() => {
    window.matchMedia = original;
  });
}

describe('R11 G3 머리 — 사실 줄(D30-7)', () => {
  it('현재 적용 공고 · 적용 시작(FactCell) · 접수 상태 · 확인 경로 · 확인일만 — 판단 문장 없음', async () => {
    const detail = await exampleDetail();
    const current = detail.payment.find((p) => p.is_current)!;
    const intake = detail.intake_current!;
    renderRoute('/complexes/2');
    const h = await head(detail);
    const status = within(h).getByRole('region', { name: t('page.G3.summary.status') });
    expect(within(status).getByTestId('current-notice')).toHaveTextContent(
      t('page.G3.summary.currentNotice', { kind: current.notice_kind ?? '' }),
    );
    expect(prov(status, current.effective_from.prov)).not.toBeNull();
    const line = within(status).getByTestId('status-intake');
    expect(line).toHaveTextContent(t(`intake.status.${intake.status}` as 'intake.status.가능'));
    expect(line).toHaveTextContent(t(`intake.path.${intake.path}` as 'intake.path.official_popup'));
    expect(line).toHaveTextContent(/\d{4}-\d{2}-\d{2}/);
    // 사실 줄은 서버 값 이음뿐 — 머리 카드에 쉬운 말 요약 문장(…했고, 지금은 …) 이 없다
    expect(status.textContent ?? '').not.toMatch(/끝났고|지금은 남은/);
  });

  it('현재 위치 줄(단지 찾기 › 이름) · 단지 목록으로 링크 — 전역 쿼리 유지', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2?region=1&snapshot=12');
    await head(detail);
    const crumb = screen.getByRole('navigation', { name: t('page.G3.crumb.label') });
    expect(crumb).toHaveTextContent(detail.header.name);
    const list = within(crumb).getByRole('link', { name: t('page.G3.crumb.list') });
    expect(list.getAttribute('href')).toContain('snapshot=12');
    const back = screen.getByRole('link', { name: t('page.G3.backToList') });
    expect(back.getAttribute('href')).toContain('region=1');
    expect(screen.getByRole('heading', { level: 1, name: t('page.G3.title') })).toBeInTheDocument();
  });

  it('생활권 이름 · 일반/특별공급 세대(용어 ?) · 주소', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const h = await head(detail);
    const identity = h.querySelector('[data-tier="identity"]') as HTMLElement;
    expect(identity).toHaveTextContent(detail.header.living_area_name ?? '');
    for (const f of [detail.header.units_general, detail.header.units_special]) {
      if (f.prov) expect(prov(identity, f.prov)).not.toBeNull();
    }
    expect(
      within(identity).getByRole('button', {
        name: new RegExp(t('glossary.items.special_supply.term').replace(/[()]/g, '.')),
      }),
    ).toBeInTheDocument();
  });
});

describe('R11 G3 언제, 얼마를 내야 하나요?', () => {
  it('납부 띠(장식) + 카드 3: 비율 Fact · 원 금액 = payment_amounts(추정(산술)) · 1차 계약금 · 입주 연월', async () => {
    const detail = await exampleDetail();
    const current = detail.payment.find((p) => p.is_current)!;
    const amounts = detail.price.payment_amounts!;
    renderRoute('/complexes/2');
    const h = await head(detail);
    const money = within(h).getByRole('region', { name: t('page.G3.summary.money') });
    expect(within(money).getByTestId('payment-band')).toHaveAttribute('aria-hidden', 'true');
    const cards = within(money).getAllByRole('listitem');
    expect(cards).toHaveLength(3);
    const [down, interim, balance] = cards as [HTMLElement, HTMLElement, HTMLElement];
    expect(prov(down, current.down_payment_pct.prov)).not.toBeNull();
    expect(within(down).getByText(t('page.G3.summary.downWhen'))).toBeInTheDocument();
    expect(prov(interim, current.interim_pct.prov)).not.toBeNull();
    expect(prov(balance, current.balance_pct.prov)).not.toBeNull();
    expect(prov(balance, detail.header.move_in_ym.prov)).not.toBeNull();
    for (const [card, fact] of [
      [down, amounts.down_payment_won],
      [interim, amounts.interim_won],
      [balance, amounts.balance_won],
    ] as const) {
      expect(within(card).getAllByText(`${fact.label}(${fact.reason ?? ''})`).length).toBe(1);
    }
    expect(within(money).getByText(t('page.G3.summary.moneyLabel'))).toBeInTheDocument();
    // 용어 ? 3개(계약금·중도금·잔금)
    expect(
      within(money).getAllByRole('button', { name: /\?|뜻|설명/ }).length,
    ).toBeGreaterThanOrEqual(3);
  });

  it('납부 조건이 없으면 카드 대신 "확인 불가(납부 조건을 아직 못 모음)"', async () => {
    const detail = await exampleDetail();
    useDetail({ ...detail, payment: [] });
    renderRoute('/complexes/2');
    const h = await head(detail);
    const money = within(h).getByRole('region', { name: t('page.G3.summary.money') });
    expect(
      within(money).getByText(
        t('empty.unknownWithReason', { reason: t('page.G3.summary.noPayment') }),
      ),
    ).toBeInTheDocument();
    expect(within(money).queryByTestId('payment-band')).toBeNull();
  });
});

describe('R11 G3 청약 전에 꼭 확인할 조건', () => {
  it('칸 5개(용어 ?) — 실거주 0개월은 "의무 없음" + 근거 FactCell, 전매는 D± + "팔 수 있게 되는 날"', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const h = await head(detail);
    const cond = within(h).getByRole('region', { name: t('page.G3.summary.conditions') });
    for (const id of [
      'cond-resale',
      'cond-residency',
      'cond-rewin',
      'cond-regulated',
      'cond-price-cap',
    ]) {
      expect(within(cond).getByTestId(id)).toBeInTheDocument();
    }
    const residency = within(cond).getByTestId('cond-residency');
    expect(Number(detail.header.residency_months.v)).toBe(0);
    expect(residency).toHaveTextContent(t('page.G3.summary.residencyNone'));
    expect(prov(residency, detail.header.residency_months.prov)).not.toBeNull();
    const resale = within(cond).getByTestId('cond-resale');
    expect(resale).toHaveTextContent(/\(D[-+]\d+\)|D-day/);
    expect(resale).toHaveTextContent(t('page.G3.summary.resaleEndPlain'));
    const rewin = within(cond).getByTestId('cond-rewin');
    expect(rewin).not.toHaveTextContent(t('page.G3.summary.rewinNone'));
  });
});

describe('R11 G3 일정은 어디쯤 왔나요?', () => {
  it('순서: 접수 일정 → 당첨자 발표 → 계약 → 되팔기 가능 → 입주, 기준일 전 날은 past', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const h = await head(detail);
    const steps = within(h).getByTestId('schedule-steps');
    const items = within(steps).getAllByRole('listitem');
    const n = detail.header.apply_dates.length + 1 + detail.header.contract_dates.length + 2;
    expect(items).toHaveLength(n);
    expect(items[0]).toHaveTextContent(detail.header.apply_dates[0]?.kind ?? '');
    expect(items[detail.header.apply_dates.length]).toHaveTextContent(
      t('page.G3.summary.winnerDate'),
    );
    expect(items.at(-2)).toHaveTextContent(t('page.G3.schedule.resale'));
    expect(items.at(-1)).toHaveTextContent(t('page.G3.schedule.moveIn'));
    // 당첨 발표(2025-09-10) < 기준일(2026-10-08) → 지난 일정
    const winner = items[detail.header.apply_dates.length] as HTMLElement;
    expect(winner.dataset.stepState).toBe('past');
    expect(prov(winner, detail.header.winner_date.prov)).not.toBeNull();
    // 되팔기 가능(2028-09-10)은 아직
    expect((items.at(-2) as HTMLElement).dataset.stepState).not.toBe('past');
  });
});

describe('R11 G3 청약 때 얼마나 몰렸나요?', () => {
  it('요약 3칸(최고 경쟁률 · 모자랐던 타입 · 가점 최저~최고 = competition_summary) + 기준 부제 + 경쟁률 전체 링크', async () => {
    const detail = await exampleDetail();
    const summary = detail.competition_summary!;
    useDetail({
      ...detail,
      competition_summary: {
        ...summary,
        winning_score_min: {
          v: 30,
          label: '확인됨',
          prov: 'fp_ws_min',
          checked_at: '2026-10-07',
          unit: 'score',
        },
        winning_score_max: {
          v: 63,
          label: '확인됨',
          prov: 'fp_ws_max',
          checked_at: '2026-10-07',
          unit: 'score',
        },
      },
    });
    const { router } = renderRoute('/complexes/2');
    const h = await head(detail);
    const card = within(h).getByRole('region', { name: t('page.G3.compSummary.title') });
    expect(card).toHaveTextContent(t('page.G3.compSummary.basis', { basis: summary.basis }));
    expect(prov(card, 'fp_ws_min')).not.toBeNull();
    expect(prov(card, 'fp_ws_max')).not.toBeNull();
    await userEvent.click(within(card).getByRole('link', { name: t('page.G3.compSummary.more') }));
    await waitFor(() => expect(router.state.location.hash).toBe('#events'));
  });

  it('요약 키가 없는 옛 저장본은 "확인 불가(경쟁률 요약이 없어요 …)"', async () => {
    const detail = await exampleDetail();
    const { competition_summary: _drop, ...rest } = detail;
    useDetail(rest as ComplexDetail);
    renderRoute('/complexes/2');
    const h = await head(detail);
    const card = within(h).getByRole('region', { name: t('page.G3.compSummary.title') });
    expect(
      within(card).getByText(
        t('empty.unknownWithReason', { reason: t('page.G3.compSummary.none') }),
      ),
    ).toBeInTheDocument();
  });
});

describe('R11 G3 점수는 왜 이렇게 나왔나요?', () => {
  it('성분마다 쉬운 이름 · 비중 · 성분 점수 Fact, +10% 성분에 목표 시점과 "보장 아님"', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const h = await head(detail);
    const card = within(h).getByRole('region', { name: t('page.G3.summary.score') });
    const list = within(card).getByRole('list', { name: t('page.G3.scoreWhy.list') });
    const rows = within(list).getAllByRole('listitem');
    const keys = Object.keys(detail.score!.components);
    expect(rows).toHaveLength(keys.length);
    const p10 = rows.find((r) => r.dataset.component === 'p10')!;
    expect(p10).toHaveTextContent(t('page.G3.scoreWhy.component.p10'));
    expect(p10).toHaveTextContent(t('page.G3.scoreWhy.weight', { w: '35%' }));
    expect(prov(p10, detail.score!.components.p10.score.prov)).not.toBeNull();
    expect(p10).toHaveAttribute('title', detail.score!.components.p10.formula_text);
    const note = await within(p10).findByTestId('score-p10-note');
    expect(note).toHaveTextContent(t('page.G3.scoreWhy.p10Note'));
    const row = detail.ladder.find((r) => r.horizon === 'move_in_plus_1y');
    await waitFor(() => expect(note).toHaveTextContent(row?.target_label ?? ''));
    expect(prov(card, detail.score!.total.prov)).not.toBeNull();
  });

  it('점수가 없으면 종합 점수 "확인 불가(점수 계산 전)", 성분 목록 없음', async () => {
    const detail = await exampleDetail();
    useDetail({ ...detail, score: null });
    renderRoute('/complexes/2');
    const h = await head(detail);
    const card = within(h).getByRole('region', { name: t('page.G3.summary.score') });
    expect(
      within(card).getByText(t('empty.unknownWithReason', { reason: t('page.G3.scoreWhy.none') })),
    ).toBeInTheDocument();
    expect(within(card).queryByRole('list', { name: t('page.G3.scoreWhy.list') })).toBeNull();
  });

  it('판정 범위 사유는 서버 문자열 그대로(D30-6 한국어 분류명)', async () => {
    const detail = await exampleDetail();
    const reason = '포함/제외 classify 제외 클래스(공공분양)';
    useDetail({ ...detail, header: { ...detail.header, judge_scope_reason: reason } });
    renderRoute('/complexes/2');
    const h = await head(detail);
    expect(within(h).getByTestId('scope-reason')).toHaveTextContent(reason);
  });
});

describe('R11 G3 가격 카드 — 주변 거래 비교(계약 .22 comps_median)', () => {
  it('가격 갭 % · 이 단지 가운데값 · 비교 단지 전체 가운데값(서버 Fact) · 비교 단지 수', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2');
    const h = await head(detail);
    const card = h.querySelector('[data-tier="price"]') as HTMLElement;
    expect(prov(card, detail.gap.gap_pct.prov)).not.toBeNull();
    expect(prov(card, detail.price.price_mid.prov)).not.toBeNull();
    const median = within(card).getByTestId('gap-mini-comps-median');
    expect(median.querySelector('[data-testid="label-badge"]')).toHaveTextContent(
      detail.gap.comps_median?.label ?? '',
    );
    expect(card).toHaveTextContent(
      t('page.G3.gapMini.compsCount', { n: String(detail.gap.comps.length) }),
    );
  });

  it('.22 전 저장본(키 없음)은 "확인 불가(예전 저장본이라 값 없음)"', async () => {
    const detail = await exampleDetail();
    const { comps_median: _a, comps_median_unadjusted: _b, ...gap } = detail.gap;
    useDetail({ ...detail, gap });
    renderRoute('/complexes/2');
    const h = await head(detail);
    expect(within(h).getByTestId('gap-mini-comps-median')).toHaveTextContent(
      t('empty.unknownWithReason', { reason: t('page.G3.gapMini.compsMedianOld') }),
    );
  });

  it('주변 시세 비교 탭에도 비교군 전체 가운데값', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2#gap');
    const panel = await screen.findByRole('tabpanel');
    const box = within(panel).getByTestId('gap-comps-median');
    expect(box).toHaveTextContent(t('page.G3.gap.compsMedian'));
    expect(prov(box, detail.gap.comps_median?.prov)).not.toBeNull();
  });
});

describe('R11 G3 탭', () => {
  it('차트 4개(C01·C02·C08·C09)에 기준일(asof) 바닥줄', async () => {
    const detail = await exampleDetail();
    for (const hash of ['events', 'gap', 'ladder', 'catalysts']) {
      const { unmount } = renderRoute(`/complexes/2#${hash}`);
      const panel = await screen.findByRole('tabpanel');
      await waitFor(() => expect(panel).toHaveTextContent(detail.asof_date));
      unmount();
    }
  });

  it('납부 일정 전체: 공고마다 열 하나(지금 적용 배지) — 같은 행에 두 공고 계약금 Fact', async () => {
    const detail = await exampleDetail();
    renderRoute('/complexes/2#payment');
    const panel = await screen.findByRole('tabpanel');
    const table = within(panel).getByTestId('payment-compare');
    const headers = within(table).getAllByRole('columnheader');
    expect(headers).toHaveLength(detail.payment.length + 1);
    expect(within(table).getByText(t('page.G3.payment.current'))).toBeInTheDocument();
    const downRow = within(table).getByRole('rowheader', { name: t('page.G3.payment.down') })
      .parentElement as HTMLElement;
    for (const term of detail.payment) {
      expect(prov(downRow, term.down_payment_pct.prov)).not.toBeNull();
    }
  });

  it('납부 조건이 없으면 탭에 "없음"', async () => {
    const detail = await exampleDetail();
    useDetail({ ...detail, payment: [] });
    renderRoute('/complexes/2#payment');
    const panel = await screen.findByRole('tabpanel');
    expect(
      within(panel).getByText(t('empty.unknownWithReason', { reason: t('page.common.none') })),
    ).toBeInTheDocument();
  });

  it('키보드 ←→ 로 탭 이동(끝에서 돌아감, 포커스 이동) · 해시 replace', async () => {
    const { router } = renderRoute('/complexes/2#price');
    const first = await screen.findByRole('tab', { name: t('page.G3.tab.price') });
    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    const last = G3_VISIBLE_TABS[G3_VISIBLE_TABS.length - 1];
    await waitFor(() => expect(router.state.location.hash).toBe(`#${last}`));
    const lastTab = screen.getByRole('tab', { name: t('page.G3.tab.provenance') });
    expect(lastTab).toHaveFocus();
    fireEvent.keyDown(lastTab, { key: 'ArrowRight' });
    await waitFor(() => expect(router.state.location.hash).toBe('#price'));
    expect(screen.getByRole('tab', { name: t('page.G3.tab.price') })).toHaveFocus();
  });

  it('모르는 해시면 첫 탭(평형별 가격) · 탭 패널은 tabpanel + aria-labelledby', async () => {
    renderRoute('/complexes/2#nope');
    const tab = await screen.findByRole('tab', { name: t('page.G3.tab.price') });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });

  it('탭 안 질문형 제목(평형별 가격 · 출처·원문)', async () => {
    renderRoute('/complexes/2#price');
    expect(
      await screen.findByRole('heading', { level: 3, name: t('page.G3.price.title') }),
    ).toBeInTheDocument();
    renderRoute('/complexes/2#provenance');
    expect(
      await screen.findByRole('heading', { level: 3, name: t('page.G3.provenance.title') }),
    ).toBeInTheDocument();
  });

  it('개발 소식이 없으면 목록에 "이 단지에 연결된 개발 소식이 없어요"', async () => {
    const detail = await exampleDetail();
    useDetail({ ...detail, catalysts: [] });
    renderRoute('/complexes/2#catalysts');
    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getByText(t('page.G3.catalyst.empty'))).toBeInTheDocument();
  });
});

describe('R11 G3 모바일(D7 읽기 전용)', () => {
  it('"더 자세히" 고르기 상자 + 주소 접힘, 화면이 자기 아래 메뉴를 그리지 않는다', async () => {
    await withMobile(async () => {
      const detail = await exampleDetail();
      renderRoute('/complexes/2');
      const h = await head(detail);
      expect(screen.getByText(t('page.G3.tabSelect'))).toBeInTheDocument();
      const select = screen.getByRole('combobox', { name: t('page.G3.tabs') });
      expect(within(select).getAllByRole('option')).toHaveLength(G3_VISIBLE_TABS.length);
      const info = within(h).getByText(t('page.G3.summary.info'));
      expect(info.tagName).toBe('SUMMARY');
      // 아래 주 메뉴는 공통 틀(R11-SHELL) 하나뿐 — G3 안에는 nav 가 현재 위치 줄 하나
      const main = screen.getByRole('main');
      expect(within(main).getAllByRole('navigation')).toHaveLength(1);
    });
  });
});
