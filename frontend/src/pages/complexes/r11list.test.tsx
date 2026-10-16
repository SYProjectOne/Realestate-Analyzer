/**
 * R11-HOME(D30, List·ListTable 보드) — G2 새 모양: h1 "{지역} 분양 단지 {n}곳" · 카드/표 전환(URL ?view= + 기억) ·
 * 데스크톱 카드 점수 줄(D30-10) · 정렬 상자(기본 -total, D28-4) · 개수 줄 정렬 이름 · 빈 결과 초기화 · 비교 바구니.
 * coverage-List.md `테스트` 열이 가리키는 테스트.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { sortLabel } from '.';
import { readSort, readView, SORT_PRESETS, toApiFilter, VIEW_STORAGE_KEY } from './params';

describe('지금 동작 그대로(LT-8 · LS-3 상자)', () => {
  it('readSort: 모르는 정렬 키 → -total, URL 전용 키 rank · price_low 는 그대로', () => {
    expect(readSort(new URLSearchParams('sort=-bogus'))).toBe('-total');
    expect(readSort(new URLSearchParams(''))).toBe('-total');
    expect(readSort(new URLSearchParams('sort=rank'))).toBe('rank');
    expect(readSort(new URLSearchParams('sort=price_low'))).toBe('price_low');
  });

  it('숫자 칸 잘못된 값은 조용히 무시(가격·입주 연도)', () => {
    expect(toApiFilter({ price_min: 'abc', price_max: '7.5', move_in_year: '2028.5' })).toEqual({
      price_max: 750_000_000,
    });
  });

  it('표: 고른 행 aria-selected, 정렬 머리 aria-sort + 다음 동작 title, 열 머리 용어 ?', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('checkbox').length).toBeGreaterThan(2));
    await userEvent.click(within(table).getAllByRole('checkbox')[0] as HTMLElement);
    expect(within(table).getAllByRole('checkbox')[0]?.closest('tr')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    const total = table.querySelector('th[data-col="total"]') as HTMLElement;
    expect(total).toHaveAttribute('aria-sort', 'descending');
    expect(within(total).getAllByRole('button')[0]).toHaveAttribute(
      'title',
      t('page.G2.sortAsc', { col: t('page.G2.col.total') }),
    );
    const terms = [...table.querySelectorAll('thead [data-testid="term"]')].map((el) =>
      el.getAttribute('data-term'),
    );
    expect(terms).toEqual(
      expect.arrayContaining(['intake_status', 'current_price', 'resale_end', 'gap', 'total']),
    );
  });

  it('CSV: 저장본 검증 실패(500)는 특수 문구(role=alert)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes.csv'), () =>
        HttpResponse.json(
          { code: 'stored_view_mismatch', message: 'x', detail: 'hash' },
          { status: 500 },
        ),
      ),
    );
    renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    await userEvent.click(screen.getByRole('button', { name: t('page.G2.csv') }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t('page.common.storedViewMismatch', { detail: 'hash' }),
    );
  });

  it('휴대폰 필터 시트는 Esc 로 닫힌다', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderRoute('/complexes');
      await screen.findByRole('list', { name: t('page.G2.cards') });
      await userEvent.click(
        screen.getByRole('button', { name: t('page.G2.card.filterSheet', { n: '0' }) }),
      );
      expect(screen.getByRole('dialog', { name: t('page.G2.filters') })).toBeInTheDocument();
      await userEvent.keyboard('{Escape}');
      expect(screen.queryByRole('dialog', { name: t('page.G2.filters') })).toBeNull();
    } finally {
      window.matchMedia = original;
    }
  });
});

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => {
  resetMockState();
  window.localStorage.removeItem(VIEW_STORAGE_KEY);
});

describe('보기 방식 카드 · 표(새로 더한 것 #1)', () => {
  it('readView: URL ?view= 가 먼저, 없으면 기억한 값, 없으면 표', () => {
    expect(readView(new URLSearchParams('view=cards'), 'table')).toBe('cards');
    expect(readView(new URLSearchParams(''), 'cards')).toBe('cards');
    expect(readView(new URLSearchParams('view=x'), 'y')).toBe('table');
  });

  it('카드를 누르면 ?view=cards(replace) + 이 브라우저에 기억, 다시 열면 카드', async () => {
    const { router, unmount } = renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const group = screen.getByRole('group', { name: t('page.G2.view.label') });
    const cardsBtn = within(group).getByRole('button', { name: t('page.G2.view.cards') });
    expect(cardsBtn).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(cardsBtn);
    await screen.findByRole('list', { name: t('page.G2.cards') });
    expect(router.state.location.search).toContain('view=cards');
    expect(router.state.historyAction).toBe('REPLACE');
    expect(window.localStorage.getItem(VIEW_STORAGE_KEY)).toBe('cards');
    // 카드 보기에는 비교 체크가 없어 비교 바구니도 없다
    expect(screen.queryByRole('complementary', { name: t('page.G2.tray') })).toBeNull();
    unmount();
    renderRoute('/complexes');
    expect(await screen.findByRole('list', { name: t('page.G2.cards') })).toBeInTheDocument();
  });
});

describe('데스크톱 카드(List 보드, D30-10)', () => {
  it('카드마다 접수·되팔기 → 생활권·세대 → 이름 → 현재 가격 → 종합 점수 줄 → 더 보기, 아래 계약금·입주·작년 경쟁률', async () => {
    renderRoute('/complexes?view=cards');
    const list = await screen.findByRole('list', { name: t('page.G2.cards') });
    const card = within(list).getAllByRole('listitem')[0] as HTMLElement;
    const order = [...card.querySelectorAll('[data-field]')].map((el) =>
      el.getAttribute('data-field'),
    );
    expect(order).toEqual([
      'status',
      'living_area',
      'name',
      'price',
      'total',
      'more',
      'down',
      'competition',
    ]);
    const total = card.querySelector('[data-field="total"]') as HTMLElement;
    expect(total.querySelector('[data-prov]')).not.toBeNull();
    expect(within(total).getByTestId('label-badge')).toBeInTheDocument();
  });

  it('정렬 상자: 기본 = 종합 점수 높은 순(-total), 접수 가능 먼저 → ?sort=intake, 표에서 고른 정렬은 "표에서 고른 정렬"', async () => {
    const { router } = renderRoute('/complexes?view=cards');
    await screen.findByRole('list', { name: t('page.G2.cards') });
    const select = screen.getByTestId('sort-select') as HTMLSelectElement;
    expect(select.value).toBe('-total');
    expect([...select.options].map((o) => o.value)).toEqual([...SORT_PRESETS]);
    await userEvent.selectOptions(select, 'intake');
    await waitFor(() => expect(router.state.location.search).toContain('sort=intake'));
    expect(screen.getByTestId('count-sort')).toHaveTextContent(t('page.G2.sort.intake'));
  });

  it('표 머리에서 고른 정렬이면 상자에 "표에서 고른 정렬"', async () => {
    renderRoute('/complexes?view=cards&sort=-gap_pct');
    await screen.findByRole('list', { name: t('page.G2.cards') });
    const select = screen.getByTestId('sort-select') as HTMLSelectElement;
    expect(select.value).toBe('-gap_pct');
    expect(select.selectedOptions[0]?.textContent).toBe(t('page.G2.sort.other'));
  });
});

describe('머리 · 개수 줄 · 빈 결과', () => {
  it('h1 = 화면 이름(스크린리더) + "{지역} 분양 단지 {n}곳"(n = 목록 total)', async () => {
    renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const h1 = await screen.findByRole('heading', { level: 1, name: /\d+/ });
    expect(h1).toHaveAccessibleName(new RegExp(`^${t('page.G2.title')} .+ \\d+`));
    expect(h1.querySelector('[data-meta="count"]')).not.toBeNull();
  });

  it('sortLabel: 상자 이름 · 열 이름 + 큰/작은 값부터 · 판정기 순위', () => {
    expect(sortLabel('-total')).toBe(t('page.G2.sort.-total'));
    expect(sortLabel('intake')).toBe(t('page.G2.sort.intake'));
    expect(sortLabel('-gap_pct')).toBe(t('page.G2.sortDesc', { col: t('page.G2.col.gap') }));
    expect(sortLabel('move_in_ym')).toBe(t('page.G2.sortAsc', { col: t('page.G2.col.move_in') }));
    expect(sortLabel('-rank')).toBe(t('page.G2.sort.rank'));
  });

  it('개수 줄 "{total}곳 중 {shown}곳을 보여요 · 정렬 이름"', async () => {
    renderRoute('/complexes');
    await screen.findByRole('table', { name: t('page.G2.table') });
    const sortName = screen.getByTestId('count-sort');
    expect(sortName).toHaveTextContent(t('page.G2.sort.-total'));
    const line = sortName.closest('p');
    expect(line?.querySelector('[data-meta="count"]')).not.toBeNull();
  });

  it('조건에 맞는 단지가 없으면 안내 + 필터 초기화 버튼(정렬도 지운다)', async () => {
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), () =>
        HttpResponse.json({ page: 1, size: 100, total: 0, asof_date: '2026-10-08', items: [] }),
      ),
    );
    const { router } = renderRoute('/complexes?q=없는단지&sort=-p10');
    expect(await screen.findByText(t('page.G2.empty'))).toBeInTheDocument();
    const buttons = screen.getAllByRole('button', { name: t('page.G2.clearFilters') });
    await userEvent.click(buttons[buttons.length - 1] as HTMLElement);
    await waitFor(() => {
      expect(router.state.location.search).not.toContain('q=');
      expect(router.state.location.search).not.toContain('sort=');
    });
  });
});

describe('비교 바구니(ListTable 보드)', () => {
  it('"{n}개 골랐어요" · 나란히 비교하기(2개 미만 잠김)', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('checkbox').length).toBeGreaterThan(2));
    const tray = screen.getByRole('complementary', { name: t('page.G2.tray') });
    expect(within(tray).getByRole('button', { name: t('page.G2.compare') })).toBeDisabled();
    // 고를 때마다 행이 다시 그려진다 — 매번 다시 찾는다
    await userEvent.click(within(table).getAllByRole('checkbox')[0] as HTMLElement);
    await userEvent.click(within(table).getAllByRole('checkbox')[1] as HTMLElement);
    expect(within(tray).getByText(t('page.G2.trayCount', { n: '2' }))).toBeInTheDocument();
    expect(
      within(tray).getByRole('link', { name: new RegExp(t('page.G2.compare')) }),
    ).toHaveAttribute('href', expect.stringMatching(/\/compare\?.*ids=\d+,\d+/));
  });
});
