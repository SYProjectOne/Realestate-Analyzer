/**
 * R11-MARKETOPS(D30, 목업 Market.dc.html) — G6 머리(지역 이름 질문형 h1 · 생활권 고르기 · 묶음 바꾸기 링크) · 한눈에 보기
 * 카드 4장(서버 값·줄 개수만 — 미분양 지역 합계는 계약 .22 `unsold_latest`, MK-1) · 질문형 구역 · 규제 8종(MK-8) ·
 * C5 구 고르기(N7) · 실거래 기간 열(MK-9) · 차트에 기준일(asof) · 편집하는 사람용 꼬리표 · 맨 아래 안내.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { Fact, Market } from '@/api/types';
import { t } from '@/i18n';
import { metaText } from '@/lib/meta';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import {
  areaPriceSummary,
  moveInByYear,
  REGULATION_KINDS,
  regulationGroups,
  sharedValue,
  unsoldScopes,
} from './summary';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

function patchMarket(fn: (m: Market) => Market) {
  server.use(
    http.get(mswPath('/snapshots/:sid/market'), async ({ request }) => {
      const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
      return HttpResponse.json(fn((await res?.json()) as Market));
    }),
  );
}

const fact = (v: string | number | null, unit: Fact['unit'] = 'text'): Fact => ({
  v,
  label: '확인됨',
  prov: 'fp_1',
  checked_at: '2026-10-07',
  unit,
});

describe('R11 G6 보조 함수(줄 세기·같은 값 보기만)', () => {
  it('moveInByYear: 입주 핀을 해마다 센다(연도 오름차순)', () => {
    expect(
      moveInByYear([
        { move_in_ym: '2029-08' },
        { move_in_ym: '2028-03' },
        { move_in_ym: '2028-12' },
      ]),
    ).toEqual([
      { year: '2028', count: 2 },
      { year: '2029', count: 1 },
    ]);
  });

  it('sharedValue: 모두 같을 때만 그 값', () => {
    expect(sharedValue(['a', 'a'])).toBe('a');
    expect(sharedValue(['a', 'b'])).toBeNull();
    expect(sharedValue(['a', null])).toBeNull();
    expect(sharedValue([])).toBeNull();
  });

  it('regulationGroups: 한 종류의 서버 값별 줄 수(처음 나온 순서, 빈 값 제외)', () => {
    const items = [
      { key: 'regulated_area', title: 'a', value: fact('비규제') },
      { key: 'regulated_area', title: 'b', value: fact('조정대상') },
      { key: 'regulated_area', title: 'c', value: fact('비규제') },
      { key: 'regulated_area', title: 'd', value: fact(null) },
      { key: 'price_cap', title: 'e', value: fact('적용') },
    ] as Market['regulation']['items'];
    expect(regulationGroups(items, 'regulated_area')).toEqual([
      { value: '비규제', count: 2 },
      { value: '조정대상', count: 1 },
    ]);
    expect(regulationGroups(items, 'price_cap')).toEqual([{ value: '적용', count: 1 }]);
  });

  it('unsoldScopes · areaPriceSummary', () => {
    const unsold = [
      {
        ym: '2026-07',
        scope_code: '1',
        scope_name: '가',
        total: fact(1),
        post_completion: fact(1),
      },
      {
        ym: '2026-08',
        scope_code: '1',
        scope_name: '가',
        total: fact(1),
        post_completion: fact(1),
      },
      {
        ym: '2026-08',
        scope_code: '2',
        scope_name: '나',
        total: fact(1),
        post_completion: fact(1),
      },
    ] as Market['unsold'];
    expect(unsoldScopes(unsold)).toEqual([
      { code: '1', name: '가' },
      { code: '2', name: '나' },
    ]);
    const rows = [
      { median_won: fact(1, 'won'), trade_window: 'w' },
      { median_won: fact(null, 'won'), trade_window: 'w' },
    ] as Market['living_area_prices'];
    expect(areaPriceSummary(rows)).toEqual({ withValue: 1, window: 'w' });
  });

  it('규제 종류는 계약 enum 8종 그대로', () => {
    expect(REGULATION_KINDS).toEqual([
      'regulated_area',
      'price_cap',
      'resale',
      'residency',
      'loan',
      'tax',
      'land_permit',
      'other',
    ]);
  });
});

describe('R11 G6 화면', () => {
  it('머리: "{지역} 시장, 지금 어때요?" + 생활권 질문 + 묶음 바꾸기 링크(G0-2) + 안내·출처 범례', async () => {
    renderRoute('/market');
    const h1 = await screen.findByRole('heading', {
      level: 1,
      name: new RegExp(t('page.G6.title')),
    });
    await waitFor(() => expect(h1.textContent).not.toBe(t('page.G6.headingNoRegion')));
    expect(screen.getByLabelText(t('page.G6.livingArea'))).toBeInTheDocument();
    expect(screen.getByText(t('page.G6.livingAreaHint'), { exact: false })).toBeInTheDocument();
    const edit = await screen.findByRole('link', { name: t('page.G6.livingAreaEdit') });
    expect(edit.getAttribute('href')).toMatch(/^\/regions\/\d+\/living-areas/);
    expect(screen.getByText(t('page.G6.intro'))).toBeInTheDocument();
    expect(screen.getByTestId('market-footnote')).toHaveTextContent(t('page.G6.footNote'));
  });

  it('한눈에 보기: 미분양 = 서버 unsold_latest 그대로(unsold[] 를 더하지 않는다)', async () => {
    patchMarket((m) => ({
      ...m,
      unsold_latest: {
        ym: '2026-08',
        total: { ...fact(4321, 'units'), reason: '지역 합계(시군구 4곳)' },
        post_completion: { ...fact(1234, 'units'), reason: '지역 합계(시군구 4곳)' },
        breakdown: [],
      },
    }));
    renderRoute('/market');
    const card = await screen.findByTestId('summary-unsold');
    expect(card).toHaveTextContent('4,321');
    expect(card).toHaveTextContent('1,234');
    expect(card).toHaveTextContent(t('page.G6.summary.unsoldYm', { ym: '2026-08' }));
  });

  it('한눈에 보기: unsold_latest 없음(.22 이전 저장본) → "확인 불가(이 수정본에는 합계가 없어요)"', async () => {
    patchMarket((m) => ({ ...m, unsold_latest: null }));
    renderRoute('/market');
    const card = await screen.findByTestId('summary-unsold');
    expect(card).toHaveTextContent(t('page.G6.summary.unsoldMissing'));
  });

  it('한눈에 보기: 입주 핀 줄 수 · 값 있는 생활권 줄 수 / 생활권 수 · 규제 값별 줄 수', async () => {
    patchMarket((m) => ({
      ...m,
      regulation: {
        items: [
          {
            key: 'regulated_area',
            title: '규제지역',
            scope: '가',
            value: fact('비규제'),
            note: null,
          },
          {
            key: 'regulated_area',
            title: '규제지역',
            scope: '나',
            value: fact('비규제'),
            note: null,
          },
          {
            key: 'price_cap',
            title: '분양가 상한제',
            scope: '가',
            value: fact('적용'),
            note: null,
          },
        ],
      },
    }));
    renderRoute('/market');
    const movein = await screen.findByTestId('summary-movein');
    expect(movein).toHaveTextContent(t('page.G6.summary.moveInHint'));
    const reg = await screen.findByTestId('summary-regulation');
    expect(reg).toHaveTextContent(metaText('page.G6.summary.regValue', { value: '비규제', n: 2 }));
    expect(reg).toHaveTextContent(metaText('page.G6.summary.regValue', { value: '적용', n: 1 }));
    const prices = await screen.findByTestId('summary-prices');
    expect(prices).toHaveTextContent(t('page.G6.summary.prices'));
  });

  it('규제 구역: 계약 항목 8종을 모두 보이고, 없는 종류는 "자료 없어요"', async () => {
    patchMarket((m) => ({
      ...m,
      regulation: {
        items: [
          { key: 'loan', title: '잔금대출', scope: null, value: fact('6억원'), note: '메모' },
        ],
      },
    }));
    renderRoute('/market');
    const section = await screen.findByRole('region', { name: t('page.G6.regulation') });
    expect(
      within(section).getByRole('heading', { level: 2, name: t('page.G6.regulationQ') }),
    ).toBeInTheDocument();
    for (const kind of REGULATION_KINDS) {
      const block = within(section).getByTestId(`regulation-${kind}`);
      expect(block).toHaveTextContent(t(`page.G6.regKind.${kind}`));
      if (kind === 'loan') {
        expect(block).toHaveTextContent('잔금대출');
        expect(block).toHaveTextContent('메모');
      } else {
        expect(block).toHaveTextContent(t('page.G6.regKindNone'));
      }
    }
  });

  it('질문형 구역 제목(h2)과 차트 공식 이름(구역 이름)', async () => {
    renderRoute('/market');
    for (const [name, title] of [
      ['chart.C03.title', 'page.G6.benchmark.title'],
      ['chart.C04.title', 'page.G6.supply.title'],
      ['chart.C05.title', 'page.G6.unsold.title'],
      ['chart.C09.title', 'page.G6.catalystBoard.title'],
      ['page.G6.prices', 'page.G6.pricesQ'],
      ['page.G6.loc.title', 'page.G6.loc.titleQ'],
      ['page.G6.catalyst.title', 'page.G6.catalyst.titleQ'],
    ] as const) {
      const region = await screen.findByRole('region', { name: t(name) });
      expect(within(region).getByRole('heading', { level: 2, name: t(title) })).toBeInTheDocument();
    }
    // 편집하는 사람용 꼬리표(위치 확인·URL 입력)
    expect(screen.getAllByText(t('page.G6.editor'))).toHaveLength(2);
  });

  it('차트에 기준일(asof)을 넘긴다 — 바닥줄 "기준일 …"', async () => {
    renderRoute('/market');
    const region = await screen.findByRole('region', { name: t('chart.C04.title') });
    await waitFor(() => expect(region).toHaveTextContent(/2026-\d\d-\d\d/));
  });

  it('C5 구 고르기: 범위 목록(서버 scope) → 고르면 부제가 그 범위', async () => {
    patchMarket((m) => ({
      ...m,
      unsold: [
        {
          ym: '2026-08',
          scope_code: 'A1',
          scope_name: '가구',
          total: fact(10, 'units'),
          post_completion: fact(1, 'units'),
        },
        {
          ym: '2026-08',
          scope_code: 'B2',
          scope_name: '나구',
          total: fact(20, 'units'),
          post_completion: fact(2, 'units'),
        },
      ] as Market['unsold'],
    }));
    renderRoute('/market');
    const select = await screen.findByLabelText(t('page.G6.unsold.scope'));
    expect(
      within(select).getByRole('option', { name: t('page.G6.unsold.scopeAuto') }),
    ).toBeInTheDocument();
    await userEvent.selectOptions(select, 'B2');
    const region = screen.getByRole('region', { name: t('chart.C05.title') });
    await waitFor(() =>
      expect(within(region).getByTestId('chart-subtitle')).toHaveTextContent('나구'),
    );
  });

  it('생활권 실거래: 거래 기간이 모두 같으면 위 한 줄, 다르면 "기간" 열', async () => {
    patchMarket((m) => ({
      ...m,
      living_area_prices: m.living_area_prices.map((r) => ({
        ...r,
        trade_window: '2026-04~2026-09',
      })),
    }));
    const { unmount } = renderRoute('/market');
    const table = await screen.findByRole('table', { name: t('page.G6.prices') });
    expect(screen.getByTestId('prices-window')).toHaveTextContent('2026-04~2026-09');
    expect(
      within(table).queryByRole('columnheader', { name: t('page.G6.priceCol.window') }),
    ).toBeNull();
    unmount();
    resetMockState();
    patchMarket((m) => ({
      ...m,
      living_area_prices: m.living_area_prices.map((r, i) => ({
        ...r,
        trade_window: i === 0 ? null : `2026-0${i}~2026-09`,
      })),
    }));
    renderRoute('/market');
    const table2 = await screen.findByRole('table', { name: t('page.G6.prices') });
    expect(
      within(table2).getByRole('columnheader', { name: t('page.G6.priceCol.window') }),
    ).toBeInTheDocument();
    expect(within(table2).getAllByText(t('empty.unknown')).length).toBeGreaterThan(0);
  });
});

describe('R11 G6 "구현할 때 지금 동작 그대로 유지"(MK-17)', () => {
  it('숨은 "차트" h2(제목 순서 h1 → h2 → h3)는 남는다', async () => {
    renderRoute('/market');
    const h2 = await screen.findByRole('heading', { level: 2, name: t('page.common.charts') });
    expect(h2).toHaveClass('sr-only');
  });

  it('위치 확인 폼은 한 줄만 열리고, 연결된 단지가 처음 선택돼 있다', async () => {
    renderRoute('/market');
    const panel = await screen.findByRole('region', { name: t('page.G6.loc.title') });
    const list = within(panel).getByRole('list', { name: t('page.G6.loc.title') });
    const items = within(list).getAllByRole('listitem');
    const linked = items.find((li) => li.getAttribute('data-catalyst-id') === '41') as HTMLElement;
    const other = items.find((li) => li.getAttribute('data-catalyst-id') === '44') as HTMLElement;
    await userEvent.click(within(linked).getByRole('button', { name: t('page.G6.loc.open') }));
    const select = within(linked).getByLabelText(t('page.G6.loc.complexes')) as HTMLSelectElement;
    await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
    expect([...select.selectedOptions].map((o) => o.value).sort()).toEqual(['2', '5', '6']);
    expect(within(linked).getByRole('button', { name: t('page.G6.loc.close') })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    await userEvent.click(within(other).getByRole('button', { name: t('page.G6.loc.open') }));
    expect(within(linked).queryByRole('form')).toBeNull();
    expect(within(other).getByRole('form')).toBeInTheDocument();
  });

  it('호재 URL 저장 뒤 입력 칸을 비운다', async () => {
    renderRoute('/market');
    const f = await screen.findByRole('form', { name: t('page.G6.catalyst.title') });
    const url = within(f).getByLabelText(t('page.G6.catalyst.url'));
    await userEvent.type(url, 'https://www.example-news.kr/a/1');
    await userEvent.type(within(f).getByLabelText(t('page.G6.catalyst.titleField')), '새 소식');
    await userEvent.click(within(f).getByRole('button', { name: t('page.G6.catalyst.submit') }));
    await screen.findByTestId('catalyst-created');
    expect(url).toHaveValue('');
    expect(within(f).getByLabelText(t('page.G6.catalyst.titleField'))).toHaveValue('');
  });
});
