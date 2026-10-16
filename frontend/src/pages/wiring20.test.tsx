/**
 * R9-UI × 계약 2026-10-09.20 연결(CHANGELOG .20 FE 차이 F1~F10, R9_TESTS_API §3, D29-4).
 * 화면은 서버가 준 Fact 를 그대로 그린다 — 곱하지·세지·고르지 않는다.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { Competition, ComplexDetail, Dashboard, Fact, Market } from '@/api/types';
import * as C04 from '@/charts/C04/buildOption';
import { t } from '@/i18n';
import ko from '@/i18n/ko.json';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

const fact = (v: number | null, extra: Partial<Fact> = {}): Fact => ({
  v,
  label: '확인됨',
  prov: `fp_w${String(v)}`,
  checked_at: '2026-10-07',
  unit: 'count',
  ...extra,
});

describe('F1 G3 내야 할 돈 — price.payment_amounts', () => {
  it('계약금·중도금·잔금 원 금액 = 서버 Fact(추정(산술(…)) 라벨·prov 그대로), 계산식은 title', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const amounts = detail.price.payment_amounts;
    expect(amounts).toBeTruthy();
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const money = within(head).getByRole('region', { name: t('page.G3.summary.money') });
    for (const f of [amounts!.down_payment_won, amounts!.interim_won, amounts!.balance_won]) {
      const text = `${f.label}(${f.reason ?? ''})`;
      expect(within(money).getAllByText(text).length).toBeGreaterThan(0);
    }
    expect(
      money.querySelector(`[data-prov="${amounts!.down_payment_first_won.prov}"]`),
    ).not.toBeNull();
    expect(within(money).getByTestId('payment-formula')).toHaveAttribute('title', amounts!.formula);
    expect(
      within(money).queryByText(t('page.G3.summary.downWonMissing'), { exact: false }),
    ).toBeNull();
  });

  it('옛 저장본(키 없음)은 "확인 불가(계산값 미제공)"', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const { payment_amounts: _drop, ...price } = detail.price;
    server.use(http.get(mswPath('/complexes/:id'), () => HttpResponse.json({ ...detail, price })));
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const money = within(head).getByRole('region', { name: t('page.G3.summary.money') });
    expect(
      within(money).getAllByText(
        t('empty.unknownWithReason', { reason: t('page.G3.summary.downWonMissing') }),
      ).length,
    ).toBeGreaterThan(0);
  });

  it('G2 계약금 금액 열(ComplexRow.down_payment_won — 열 선택으로 켬)', async () => {
    window.localStorage.setItem('sa.g2.columns', JSON.stringify({ v: 2, down_payment_won: true }));
    const page = await example<{ items: { complex_id: number; down_payment_won?: Fact | null }[] }>(
      '/snapshots/12/complexes',
    );
    const row = page.items.find((r) => r.down_payment_won?.prov);
    expect(row).toBeDefined();
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() =>
      expect(table.querySelector(`[data-testid="down-won-${row!.complex_id}"]`)).not.toBeNull(),
    );
  });
});

describe('F2 경쟁률 요약·당첨 가점(D29-4)', () => {
  const winning = (min: Fact, max: Fact, avg: Fact) => ({
    winning_score_min: min,
    winning_score_max: max,
    winning_score_avg: avg,
  });

  it('G3 경쟁률 탭: 요약(최고 경쟁률·미달 타입) — 기준 행이 없으면 확인 불가(사유)', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    renderRoute('/complexes/2#events');
    const section = await screen.findByRole('region', { name: t('page.G3.competition.title') });
    const summary = within(section).getByTestId('competition-summary');
    expect(summary).toHaveTextContent(t('page.G3.competition.maxRatio'));
    expect(summary).toHaveTextContent(detail.competition_summary?.max_ratio.reason ?? '');
  });

  it('가점 미수집이면 "제공하지 않음 — 청약홈" 안내 그대로', async () => {
    renderRoute('/complexes/2#events');
    const section = await screen.findByRole('region', { name: t('page.G3.competition.title') });
    expect(within(section).getByText(t('page.G3.competition.pointsMissing'))).toBeInTheDocument();
  });

  it('가점 값이 오면 행마다 최저·최고·평균 FactCell, 0/0/0 은 "가점제 당첨자 없음"', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    const [a, b, ...rest] = detail.competition as Competition[];
    const rows = [
      {
        ...a!,
        ...winning(
          fact(52, { unit: 'score' }),
          fact(69, { unit: 'score' }),
          fact(58.3, { unit: 'score' }),
        ),
      },
      { ...b!, ...winning(fact(0), fact(0, { prov: 'fp_z2' }), fact(0, { prov: 'fp_z3' })) },
      ...rest,
    ];
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({ ...detail, competition: rows }),
      ),
    );
    renderRoute('/complexes/2#events');
    const section = await screen.findByRole('region', { name: t('page.G3.competition.title') });
    expect(within(section).getByText(t('page.G3.competition.points'))).toBeInTheDocument();
    expect(section.querySelector('[data-prov="fp_w52"]')).not.toBeNull();
    expect(within(section).getByText(t('page.G3.competition.noPointWinners'))).toBeInTheDocument();
    expect(within(section).queryByText(t('page.G3.competition.pointsMissing'))).toBeNull();
  });

  it('G3 지금 상태에 경쟁률 요약 한 줄', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const status = within(head).getByRole('region', { name: t('page.G3.summary.status') });
    expect(within(status).getByTestId('competition-summary')).toBeInTheDocument();
  });
});

describe('F8 G1 TOP 카드 = ScoreRow 사실(목록 조인 없음)', () => {
  it('카드의 구매가·전매 종료·가격 갭 prov = top5 행 Fact, G1 은 목록 API 를 부르지 않는다', async () => {
    const rec = recordRequests();
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const card = within(top5).getAllByRole('listitem')[0] as HTMLElement;
    const row = dash.top5.find((r) => r.complex_id === Number(card.dataset.complexId));
    const facts = card.querySelector('[data-card="facts"]') as HTMLElement;
    for (const f of [row?.price_low, row?.price_high, row?.resale_end, row?.gap_pct]) {
      expect(facts.querySelector(`[data-prov="${f?.prov ?? 'none'}"]`)).not.toBeNull();
    }
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/dashboard').length).toBeGreaterThan(0),
    );
    // R11: 목록 API 는 '지금 접수 가능한 단지' 카드(filter[intake_status]=가능)만 부른다 — TOP 줄 사실을 목록에서 조인하지 않는다
    const lists = matching(rec.requests, 'GET', /\/snapshots\/\d+\/complexes$/);
    for (const r of lists) expect(r.url.searchParams.get('filter[intake_status]')).toBe('가능');
    rec.stop();
  });
});

describe('F5 변경 피드 summary·field_label·value_kind', () => {
  it('summary 한 줄, plain 은 펼침 없음, hash 는 "바뀐 값 보기" 안에 원값, field_label 은 title', async () => {
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    const plain = dash.changes.find((c) => c.value_kind === 'plain');
    const hash = dash.changes.find((c) => c.value_kind === 'hash');
    expect(plain && hash).toBeTruthy();
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    const plainItem = within(feed).getByText(plain!.summary!).closest('li') as HTMLElement;
    expect(within(plainItem).queryByText(t('page.G1.changeShowValue'))).toBeNull();
    expect(within(plainItem).getByText(plain!.summary!)).toHaveAttribute(
      'title',
      plain!.field_label,
    );
    const hashItem = within(feed).getByText(hash!.summary!).closest('li') as HTMLElement;
    const value = within(hashItem).getByTestId('change-value');
    expect(value).not.toBeVisible();
    expect(value).toHaveTextContent(hash!.new_text ?? '');
  });
});

describe('F4 G1 미분양 내역(breakdown)', () => {
  it('지역 현황 미분양 칸에 시군구별 내역(FactCell — 출처 1클릭)', async () => {
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    const parts = dash.kpis.unsold.breakdown ?? [];
    expect(parts.length).toBeGreaterThan(0);
    renderRoute('/');
    const region = await screen.findByRole('list', { name: t('page.G1.region') });
    const tile = region.querySelector('[data-kpi="unsold"]') as HTMLElement;
    const list = within(tile).getByTestId('unsold-breakdown');
    for (const p of parts) {
      expect(within(list).getByText(p.scope_name ?? '')).toBeInTheDocument();
      expect(list.querySelector(`[data-prov="${p.total.prov ?? ''}"]`)).not.toBeNull();
    }
  });
});

describe('F6 G6 범례 = 생활권 이름(living_area_name)', () => {
  it('C04 입주 물량 계열 이름은 living_area_name(내부 id 아님)', async () => {
    const market = await example<Market>('/snapshots/12/market');
    const supply = market.supply.map((s, i) => ({ ...s, living_area_name: `생활권이름${i % 3}` }));
    const option = C04.buildOption({ supply, markers: [], livingAreas: [] }) as {
      series: { name: string }[];
    };
    for (const s of option.series) expect(s.name).not.toMatch(/^la_\d+$/);
    expect(option.series.some((s) => s.name.startsWith('생활권이름'))).toBe(true);
  });
});

describe('F7 가격 갭 % 와 점수 분리', () => {
  it('퍼센트 칸 prov = gap_pct(.raw), 점수 칸 = gap_score', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    renderRoute('/complexes/2#gap');
    const panel = await screen.findByRole('tabpanel');
    expect(panel.querySelector(`[data-prov="${detail.gap.gap_pct.prov}"]`)).not.toBeNull();
    expect(detail.gap.gap_pct.prov).toMatch(/\.raw$/);
    const scoreRow = within(panel).getByText(t('page.G3.gap.score'))
      .nextElementSibling as HTMLElement;
    expect(
      scoreRow.querySelector(`[data-prov="${detail.gap.gap_score?.prov ?? ''}"]`),
    ).not.toBeNull();
  });
});

describe('F10 G2 접수 상태 정렬(sort=intake)', () => {
  it('접수 열 머리를 누르면 sort=intake(가능 먼저)', async () => {
    const { router } = renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await userEvent.click(within(table).getByRole('button', { name: t('page.G2.col.intake') }));
    await waitFor(() => expect(router.state.location.search).toContain('sort=intake'));
  });
});

describe('D29-4 "대표 층" → "최저가 층"', () => {
  it('ko.json 어디에도 "대표 층"·"대표층" 이 없고 가격표 열은 "최저가 층"', () => {
    expect(JSON.stringify(ko)).not.toMatch(/대표 ?층/);
    expect(t('page.G3.price.floorText')).toBe('최저가 층');
  });
});

describe('캘린더 종류는 데이터에서(계약 .21 새 종류 대비)', () => {
  it('모르는 종류도 그 글자로 보이고 범례에 나온다', async () => {
    server.use(
      http.get(mswPath('/ops/checklist'), () =>
        HttpResponse.json([
          {
            id: 9101,
            complex_id: 2,
            complex_name: '엘리프 검단 포레듀',
            kind: '청약 접수',
            title: '1순위 해당지역 청약 접수',
            due_date: '2026-11-03',
            status: 'open',
            note: null,
          },
        ]),
      ),
    );
    renderRoute('/ops');
    const calendar = await screen.findByRole('list', { name: t('page.G7.calendar') });
    expect(within(calendar).getByText('청약 접수')).toBeInTheDocument();
    expect(screen.getByTestId('calendar-legend')).toHaveTextContent('청약 접수');
  });
});
