import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { captureDownloads, matching, recordRequests } from '../_shared/testing';
import { COLUMN_STORAGE_KEY } from './ComplexTable';
import { nextSort, readFilters, toApiFilter, toListParams } from './params';

vi.mock('echarts-for-react', () => ({ default: () => null }));
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
      size: 1000,
      sort: '-total',
      scenario: 'B',
    });
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
    await userEvent.click(
      within(table).getByRole('button', { name: new RegExp(t('page.G2.col.name')) }),
    );
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
