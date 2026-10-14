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

  it('모바일(≤768px)은 읽기 전용: 비교 체크·트레이·열 선택이 없다', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderRoute('/complexes');
      const table = await screen.findByRole('table', { name: t('page.G2.table') });
      await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(2));
      expect(within(table).queryAllByRole('checkbox')).toHaveLength(0);
      expect(screen.queryByRole('complementary', { name: t('page.G2.tray') })).toBeNull();
      expect(screen.queryByText(t('page.G2.columns'))).toBeNull();
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
