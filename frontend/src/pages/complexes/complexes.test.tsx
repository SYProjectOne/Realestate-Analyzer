import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { MOCK_ROWS_KEY, resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { captureDownloads, matching, recordRequests } from '../_shared/testing';
import { COLUMN_STORAGE_KEY } from './ComplexTable';
import {
  FIRST_PAGE_SIZE,
  nextSort,
  PAGE_SIZE,
  readFilters,
  toApiFilter,
  toListParams,
} from './params';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G2 params', () => {
  it('가격(억) → 원, 입주연도 정수, 빈 값은 빠진다', () => {
    const values = readFilters(
      new URLSearchParams('price_max=7&move_in_year=2028&q=&land_type=공공택지'),
    );
    expect(toApiFilter(values)).toEqual({
      price_max: 700_000_000,
      move_in_year: 2028,
      land_type: '공공택지',
    });
    expect(toListParams(values, '-total', 'B')).toMatchObject({
      page: 1,
      size: PAGE_SIZE,
      sort: '-total',
      scenario: 'B',
    });
    expect(PAGE_SIZE).toBe(1000);
    expect(FIRST_PAGE_SIZE).toBeLessThanOrEqual(100);
  });
  it('정렬: 같은 키는 방향을 뒤집고 새 키는 내림차순부터', () => {
    expect(nextSort('-total', 'total')).toBe('total');
    expect(nextSort('total', 'total')).toBe('-total');
    expect(nextSort('-total', 'name')).toBe('-name');
  });
});

describe('G2 단지 리스트', () => {
  it('필터는 URL 쿼리 → API filter[...] 로 전달, CSV 도 같은 쿼리(Bearer fetch → 저장)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const saved = captureDownloads();
    const rec = recordRequests();
    const { router } = renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const filters = screen.getByRole('search', { name: t('page.G2.filters') });
    await userEvent.selectOptions(
      within(filters).getByLabelText(t('page.G2.filter.intake_status')),
      '가능',
    );
    await waitFor(() => expect(router.state.location.search).toContain('intake_status='));
    await waitFor(() => {
      const calls = matching(rec.requests, 'GET', /\/snapshots\/\d+\/complexes$/);
      expect(calls.some((c) => c.url.searchParams.get('filter[intake_status]') === '가능')).toBe(
        true,
      );
    });
    await userEvent.click(screen.getByRole('button', { name: t('page.G2.csv') }));
    await waitFor(() => expect(saved).toHaveLength(1));
    const csv = matching(rec.requests, 'GET', /\/complexes\.csv$/);
    expect(csv).toHaveLength(1);
    expect(csv[0]?.url.searchParams.get('filter[intake_status]')).toBe('가능');
    expect(csv[0]?.url.searchParams.has('page')).toBe(false);
    expect(csv[0]?.headers.get('authorization')).toBe('Bearer tok-write');
    expect(saved[0]?.filename).toMatch(/\.csv$/);
    expect(saved[0]?.href).toMatch(/^blob:/);
    rec.stop();
  });

  it('열 머리 클릭 → sort 쿼리(서버 정렬)', async () => {
    const { router } = renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await userEvent.click(within(table).getByRole('button', { name: t('page.G2.col.name') }));
    await waitFor(() => expect(router.state.location.search).toContain('sort=-name'));
  });

  it('체크 2개 → 비교 트레이 → /compare?ids=', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('checkbox').length).toBeGreaterThan(2));
    await userEvent.click(within(table).getAllByRole('checkbox')[0] as HTMLElement);
    const tray = screen.getByRole('complementary', { name: t('page.G2.tray') });
    expect(within(tray).getByRole('button', { name: t('page.G2.compare') })).toBeDisabled();
    await userEvent.click(within(table).getAllByRole('checkbox')[1] as HTMLElement);
    const link = within(tray).getByRole('link', { name: t('page.G2.compare') });
    expect(link.getAttribute('href')).toMatch(/\/compare\?.*ids=\d+,\d+/);
  });

  it('열 선택은 저장된다(localStorage)', async () => {
    renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    await userEvent.click(screen.getByText(t('page.G2.columns'), { selector: 'summary' }));
    await userEvent.click(screen.getByRole('checkbox', { name: t('page.G2.col.p10') }));
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem(COLUMN_STORAGE_KEY) ?? '{}')).toMatchObject({
        p10: true,
      }),
    );
    expect(
      screen.getByRole('columnheader', { name: (n) => n.includes(t('page.G2.col.p10')) }),
    ).toBeInTheDocument();
  });

  it('모바일(≤768px)은 읽기 전용 카드: 비교 체크·트레이·열 선택이 없다', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderRoute('/complexes');
      const list = await screen.findByRole('list', { name: t('page.G2.cards') });
      await waitFor(() => expect(within(list).getAllByRole('listitem').length).toBeGreaterThan(1));
      expect(screen.queryByRole('table', { name: t('page.G2.table') })).toBeNull();
      expect(within(list).queryAllByRole('checkbox')).toHaveLength(0);
      expect(screen.queryByRole('complementary', { name: t('page.G2.tray') })).toBeNull();
      expect(screen.queryByText(t('page.G2.columns'))).toBeNull();
    } finally {
      window.matchMedia = original;
    }
  });
});

describe('R9-UI P5 G2 모바일 카드 · 필터 시트(30-proposal §6)', () => {
  let original: typeof window.matchMedia;
  beforeEach(() => {
    original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
  });
  afterEach(() => {
    window.matchMedia = original;
  });

  it('카드마다 생활권 → 이름 → 접수·전매 종료 → 구매가 → 계약금·입주 → 종합 점수, 값마다 라벨', async () => {
    renderRoute('/complexes');
    const list = await screen.findByRole('list', { name: t('page.G2.cards') });
    const card = (await within(list).findAllByRole('listitem'))[0] as HTMLElement;
    const order = [...card.querySelectorAll('[data-field]')].map((el) =>
      el.getAttribute('data-field'),
    );
    expect(order).toEqual([
      'living_area',
      'name',
      'status',
      'price',
      'down_move_in',
      'total',
      'more',
    ]);
    expect(within(card).getByTestId('intake-badge')).toBeInTheDocument();
    // 구매가·전매 종료·계약금·입주·종합 = FactCell(값 + 라벨 또는 확인 불가)
    const cells = card.querySelectorAll(
      '[data-field="status"] [data-prov], [data-field="price"] [data-prov], [data-field="down_move_in"] [data-prov], [data-field="total"] [data-prov]',
    );
    expect(cells.length).toBeGreaterThanOrEqual(4);
    for (const cell of cells) {
      expect(
        cell.querySelector('[data-testid="label-badge"], [data-testid="empty-state"]'),
      ).not.toBeNull();
    }
  });

  it('가격 갭·+10% 상승 가능성은 카드 "더 보기"(1클릭)', async () => {
    renderRoute('/complexes');
    const list = await screen.findByRole('list', { name: t('page.G2.cards') });
    const card = (await within(list).findAllByRole('listitem'))[0] as HTMLElement;
    const more = within(card).getByText(t('page.G2.card.more'));
    const box = card.querySelector('[data-field="more"]') as HTMLElement;
    expect(box).not.toBeVisible();
    await userEvent.click(more);
    expect(box).toBeVisible();
    expect(within(box).getByText(t('page.G2.col.gap'))).toBeInTheDocument();
    expect(within(box).getByText(t('page.G2.col.p10'))).toBeInTheDocument();
  });

  it('필터는 시트(1클릭) — 시트 안에 필터 10칸', async () => {
    renderRoute('/complexes');
    await screen.findByRole('list', { name: t('page.G2.cards') });
    const open = screen.getByRole('button', { name: t('page.G2.card.filterSheet', { n: '0' }) });
    await userEvent.click(open);
    const sheet = screen.getByRole('dialog', { name: t('page.G2.filters') });
    for (const key of [
      'q',
      'intake_status',
      'living_area',
      'land_type',
      'resale_end_before',
      'price_min',
      'price_max',
      'move_in_year',
      'inclusion_class',
      'judge_scope',
    ] as const) {
      expect(within(sheet).getByLabelText(t(`page.G2.filter.${key}`))).toBeInTheDocument();
    }
    await userEvent.click(
      within(sheet).getByRole('button', { name: t('page.G2.card.filterApply') }),
    );
    expect(screen.queryByRole('dialog', { name: t('page.G2.filters') })).toBeNull();
  });
});

describe('R9-UI P5 헤더(모바일·메뉴 정리 결정 12)', () => {
  it('데스크톱 메뉴: 홈·단지 리스트·비교·지역 시장·보고서 │ 시나리오·데이터·운영(옆) · 용어', async () => {
    renderRoute('/');
    const nav = await screen.findByRole('navigation');
    const names = within(nav)
      .getAllByRole('link')
      .map((a) => a.textContent);
    expect(names).toEqual([
      t('nav.G1'),
      t('nav.G2'),
      t('nav.G4'),
      t('nav.G6'),
      t('nav.G8'),
      t('nav.G5'),
      t('nav.G7'),
      t('glossary.nav'),
    ]);
  });

  it('모바일: 메뉴는 홈·단지 리스트(+용어), 상황은 전체 이름 select, 토큰·테마는 "설정" 안', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      const { router } = renderRoute('/');
      const nav = await screen.findByRole('navigation');
      expect(
        within(nav)
          .getAllByRole('link')
          .map((a) => a.textContent),
      ).toEqual([t('nav.G1'), t('nav.G2'), t('glossary.nav')]);
      const select = await screen.findByRole('combobox', { name: t('header.scenario') });
      const options = within(select).getAllByRole('option');
      expect(options.length).toBeGreaterThan(1);
      expect(options.some((o) => (o.textContent ?? '').length > 3)).toBe(true);
      await userEvent.selectOptions(select, options[1] as HTMLOptionElement);
      await waitFor(() => expect(router.state.location.search).toContain('scenario='));
      const settings = screen.getByText(t('header.settings'), { selector: 'summary' });
      expect(settings.closest('details')).not.toHaveAttribute('open');
      expect(settings.closest('details')).toContainElement(screen.getByTestId('token-button'));
    } finally {
      window.matchMedia = original;
    }
  });
});

describe('G2 첫 화면·전체 행 (W8·W9)', () => {
  const listCalls = (rec: ReturnType<typeof recordRequests>) =>
    matching(rec.requests, 'GET', /\/snapshots\/\d+\/complexes$/);

  it('W8: 첫 요청은 작은 페이지(size ≤ 100) — 첫 행을 먼저 그린다', async () => {
    window.localStorage.setItem(MOCK_ROWS_KEY, '1000');
    const rec = recordRequests();
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(1));
    const first = listCalls(rec)[0];
    expect(first?.url.searchParams.get('page')).toBe('1');
    expect(Number(first?.url.searchParams.get('size'))).toBeLessThanOrEqual(100);
    expect(Number(first?.url.searchParams.get('size'))).toBe(FIRST_PAGE_SIZE);
    rec.stop();
  });

  it('W9: total 이 1,000 을 넘어도 모든 행에 닿는다(페이지를 이어 받는다)', async () => {
    window.localStorage.setItem(MOCK_ROWS_KEY, '1500');
    const rec = recordRequests();
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    expect(table).toHaveAttribute('aria-rowcount', '1501');
    await waitFor(
      () =>
        expect(
          screen.getByText(t('page.G2.count', { shown: '1,500', total: '1,500' })),
        ).toBeInTheDocument(),
      { timeout: 10_000 },
    );
    const pages = listCalls(rec)
      .filter((r) => r.url.searchParams.get('size') === String(PAGE_SIZE))
      .map((r) => r.url.searchParams.get('page'));
    expect(pages).toEqual(['1', '2']);
    // 같은 페이지를 두 번 받지 않는다
    expect(new Set(pages).size).toBe(pages.length);
    // 마지막 행까지 스크롤해 보는 것은 실제 브라우저 e2e(e2e/pages 'G2 2,500행')가 본다(jsdom 은 레이아웃이 없다)
    rec.stop();
  });

  it('W9: total ≤ 첫 페이지면 추가 요청이 없다', async () => {
    const rec = recordRequests();
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(1));
    await new Promise((r) => setTimeout(r, 200));
    expect(listCalls(rec)).toHaveLength(1);
    rec.stop();
  });
});

describe('R9-UI P4 G2 필터 접기 · 접수 가능 칩 · 목록 안내(30-proposal §5)', () => {
  const MORE = [
    'land_type',
    'resale_end_before',
    'price_min',
    'price_max',
    'move_in_year',
    'inclusion_class',
    'judge_scope',
  ] as const;

  it('기본: 핵심 필터 3칸(단지명·접수·생활권)만 보이고 나머지 7칸은 "필터 더 보기"(1클릭)', async () => {
    renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const filters = screen.getByRole('search', { name: t('page.G2.filters') });
    for (const key of ['q', 'intake_status', 'living_area'] as const) {
      expect(within(filters).getByLabelText(t(`page.G2.filter.${key}`))).toBeInTheDocument();
    }
    for (const key of MORE) {
      expect(within(filters).queryByLabelText(t(`page.G2.filter.${key}`))).toBeNull();
    }
    const more = within(filters).getByRole('button', {
      name: t('page.G2.filtersMore', { n: '0' }),
    });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(more);
    for (const key of MORE) {
      expect(within(filters).getByLabelText(t(`page.G2.filter.${key}`))).toBeInTheDocument();
    }
    expect(within(filters).getByRole('button', { name: t('page.G2.filtersLess') })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('URL 에 숨은 필터 값이 있으면 펼친 채로 열고, 버튼에 적용 개수', async () => {
    renderRoute('/complexes?land_type=공공택지&move_in_year=2028');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const filters = screen.getByRole('search', { name: t('page.G2.filters') });
    expect(within(filters).getByLabelText(t('page.G2.filter.land_type'))).toHaveValue('공공택지');
    await userEvent.click(within(filters).getByRole('button', { name: t('page.G2.filtersLess') }));
    expect(
      within(filters).getByRole('button', { name: t('page.G2.filtersMore', { n: '2' }) }),
    ).toBeInTheDocument();
  });

  it('"지금 접수 가능만 보기" 칩 = intake_status=가능 쿼리, 다시 누르면 전체', async () => {
    const { router } = renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const chip = screen.getByRole('button', { name: t('page.G2.openNowChip') });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(chip);
    await waitFor(() =>
      expect(router.state.location.search).toContain('intake_status=%EA%B0%80%EB%8A%A5'),
    );
    const off = screen.getByRole('button', { name: t('page.G2.openNowChipOff') });
    expect(off).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(off);
    await waitFor(() => expect(router.state.location.search).not.toContain('intake_status='));
  });

  it('목록 안내 한 줄', async () => {
    renderRoute('/complexes');
    expect(await screen.findByText(t('page.G2.intro'))).toBeInTheDocument();
  });
});

describe('R9-UI P4 G2 기본 열 8개(D28-4)', () => {
  const headers = async () => {
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(2));
    return within(table)
      .getAllByRole('columnheader')
      .map((th) => th.getAttribute('data-col'))
      .filter((id) => id !== 'select');
  };

  it('기본: 단지 → 접수 → 현재 구매가 → 계약금 비율 → 전매 종료 → 입주 → 가격 갭 → 종합 점수', async () => {
    renderRoute('/complexes');
    expect(await headers()).toEqual([
      'name',
      'intake',
      'price',
      'down_payment',
      'resale_end',
      'move_in',
      'gap',
      'total',
    ]);
  });

  it('생활권은 단지 이름 아래 줄(같은 행)', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    const cell = (await within(table).findAllByTestId('name-living-area'))[0] as HTMLElement;
    expect(cell.textContent?.length ?? 0).toBeGreaterThan(0);
  });

  it('예전 저장값(버전 없음)은 사용자가 바꾼 열만 남기고 새 기본을 따른다', async () => {
    // 예전 기본(p10·land_type·units_total·down_payment 숨김) 그대로 + 사용자가 p10 을 켬
    window.localStorage.setItem(
      COLUMN_STORAGE_KEY,
      JSON.stringify({
        p10: true,
        land_type: false,
        units_total: false,
        down_payment: false,
        inclusion: true,
        last_change: true,
        living_area: true,
      }),
    );
    renderRoute('/complexes');
    expect(await headers()).toEqual([
      'name',
      'intake',
      'price',
      'down_payment',
      'resale_end',
      'move_in',
      'gap',
      'total',
      'p10',
    ]);
    await waitFor(() =>
      expect(JSON.parse(window.localStorage.getItem(COLUMN_STORAGE_KEY) ?? '{}')).toMatchObject({
        v: 2,
        p10: true,
      }),
    );
  });

  it('숨긴 열(생활권·+10%·단지 분류·택지·총 세대·마지막 변경)은 열 선택 1클릭', async () => {
    renderRoute('/complexes');
    await headers();
    await userEvent.click(screen.getByText(t('page.G2.columns'), { selector: 'summary' }));
    for (const key of [
      'living_area',
      'p10',
      'inclusion',
      'land_type',
      'units_total',
      'last_change',
    ] as const) {
      expect(screen.getByRole('checkbox', { name: t(`page.G2.col.${key}`) })).not.toBeChecked();
    }
    await userEvent.click(screen.getByRole('checkbox', { name: t('page.G2.col.inclusion') }));
    expect(await headers()).toContain('inclusion');
  });

  it('접수 칸: 상태 배지 + 아래 작은 사유(쉬운 말, 원 사유 title)', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(2));
    const reasons = within(table).queryAllByTestId('intake-reason');
    for (const r of reasons) expect(r.textContent?.length ?? 0).toBeGreaterThan(0);
  });
});
