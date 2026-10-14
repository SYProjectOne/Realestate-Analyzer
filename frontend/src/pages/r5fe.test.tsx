/**
 * R5-FE(D25-1) — RA §7 공통 규칙 "상황 토글은 `?scenario=`로 전 화면 공유, 기준일은 `?snapshot=`"이 화면 이동에서 유지되는가,
 * G2 비교 트레이 6개 상한(RA §7-1 `CompareTray`(체크 2~6)).
 *
 * 이동 경로: 헤더 네비 링크(G1~G8) · G1 TOP 5 카드(이름 링크·카드 빈 곳 클릭) · G2 표 행(단지 이름 링크) · G2 비교 트레이
 * → G4 · G4 열 머리(단지 링크) → G3 · G3 "목록으로" → G2.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { MOCK_ROWS_KEY, resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

/** 기본값이 아닌 기준일(목록 12·11·10 중 최신이 아닌 11)과 내장 시나리오 B */
const SNAPSHOT = '11';
const SCENARIO = 'B';
const GLOBAL = `region=1&snapshot=${SNAPSHOT}&scenario=${SCENARIO}`;

type Loc = { pathname: string; search: string };

function expectGlobal(search: string): void {
  const p = new URLSearchParams(search);
  expect(p.get('scenario')).toBe(SCENARIO);
  expect(p.get('snapshot')).toBe(SNAPSHOT);
}

function expectHrefGlobal(el: HTMLElement): void {
  const href = el.getAttribute('href') ?? '';
  expectGlobal(new URL(href, 'http://x').search);
}

async function waitPath(router: { state: { location: Loc } }, pathname: string | RegExp) {
  await waitFor(() => {
    const now = router.state.location.pathname;
    if (typeof pathname === 'string') expect(now).toBe(pathname);
    else expect(now).toMatch(pathname);
  });
  return router.state.location;
}

describe('R5-FE 1: ?scenario=·?snapshot= 가 화면 이동에서 유지된다', () => {
  it('헤더 네비 링크 8개(화면 7 + 용어 모음, R9-UI P6)가 모두 scenario·snapshot 을 싣고, 클릭하면 그대로 이동한다', async () => {
    const { router } = renderRoute(`/?${GLOBAL}`);
    await screen.findByRole('heading', { level: 1, name: t('page.G1.title') });
    const nav = screen.getByRole('navigation');
    const links = within(nav).getAllByRole('link');
    expect(links.length).toBe(8);
    for (const link of links) expectHrefGlobal(link);

    // G1 → G2 → G6 → G1 차례로 눌러도 유지
    for (const [key, path] of [
      ['nav.G2', '/complexes'],
      ['nav.G6', '/market'],
      ['nav.G5', '/scenario'],
      ['nav.G1', '/'],
    ] as const) {
      await userEvent.click(within(nav).getByRole('link', { name: t(key) }));
      const loc = await waitPath(router, path);
      expectGlobal(loc.search);
    }
    // 토글도 그 값을 보인다
    expect(screen.getByRole('radio', { name: /^B / })).toHaveAttribute('aria-checked', 'true');
  });

  it('G1 TOP 5 카드: 이름 링크 href 와 카드 빈 곳 클릭 이동 모두 유지', async () => {
    const { router } = renderRoute(`/?${GLOBAL}`);
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cards = within(top5).getAllByRole('listitem');
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) {
      const id = card.dataset.complexId;
      const link = within(card).getAllByRole('link')[0] as HTMLElement;
      expect(link.getAttribute('href')).toMatch(new RegExp(`^/complexes/${id}\\?`));
      expectHrefGlobal(link);
    }
    // 변경 피드 항목 → G3 해당 탭도 같은 쿼리
    const feed = screen.getByRole('list', { name: t('page.G1.changes') });
    for (const a of within(feed).getAllByRole('link')) expectHrefGlobal(a);
    const first = cards[0] as HTMLElement;
    await userEvent.click(within(first).getByText(t('page.G1.p10')));
    const loc = await waitPath(router, `/complexes/${first.dataset.complexId}`);
    expectGlobal(loc.search);
  });

  it('G1 TOP 5 카드 이름 링크 클릭 → G3 에서도 유지', async () => {
    const { router } = renderRoute(`/?${GLOBAL}`);
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const first = within(top5).getAllByRole('listitem')[0] as HTMLElement;
    await userEvent.click(within(first).getAllByRole('link')[0] as HTMLElement);
    const loc = await waitPath(router, `/complexes/${first.dataset.complexId}`);
    expectGlobal(loc.search);
    // G3 의 "목록으로" 링크도 유지
    await screen.findByRole('heading', { level: 1, name: t('page.G3.title') });
    const back = await screen.findByRole('link', { name: t('page.common.backToList') });
    expectHrefGlobal(back);
  });

  it('G2 표 행(단지 이름 링크) → G3, 필터 쿼리는 G3 로 넘기지 않는다', async () => {
    const { router } = renderRoute(
      `/complexes?${GLOBAL}&intake_status=${encodeURIComponent('가능')}`,
    );
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(1));
    const rowLinks = within(table)
      .getAllByRole('link')
      .filter((a) => /^\/complexes\/\d+/.test(a.getAttribute('href') ?? ''));
    expect(rowLinks.length).toBeGreaterThan(0);
    for (const a of rowLinks) expectHrefGlobal(a);
    await userEvent.click(rowLinks[0] as HTMLElement);
    const loc = await waitPath(router, /^\/complexes\/\d+$/);
    expectGlobal(loc.search);
    expect(new URLSearchParams(loc.search).has('intake_status')).toBe(false);
  });

  it('G2 비교 트레이 → G4, G4 열 머리 단지 링크 → G3 까지 유지', async () => {
    const { router } = renderRoute(`/complexes?${GLOBAL}`);
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('checkbox').length).toBeGreaterThan(2));
    await userEvent.click(within(table).getAllByRole('checkbox')[0] as HTMLElement);
    await userEvent.click(within(table).getAllByRole('checkbox')[1] as HTMLElement);
    const tray = screen.getByRole('complementary', { name: t('page.G2.tray') });
    await userEvent.click(within(tray).getByRole('link', { name: t('page.G2.compare') }));
    let loc = await waitPath(router, '/compare');
    expectGlobal(loc.search);
    expect(new URLSearchParams(loc.search).get('ids')).toMatch(/^\d+,\d+$/);

    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    const head = within(grid)
      .getAllByRole('link')
      .find((a) => /^\/complexes\/\d+/.test(a.getAttribute('href') ?? '')) as HTMLElement;
    expectHrefGlobal(head);
    await userEvent.click(head);
    loc = await waitPath(router, /^\/complexes\/\d+$/);
    expectGlobal(loc.search);
  });
});

describe('R5-FE 3: G2 비교 트레이 6개 상한', () => {
  it('6개를 고르면 나머지 체크가 막히고, 7번째는 들어가지 않으며, 비교 링크는 6개 id', async () => {
    window.localStorage.setItem(MOCK_ROWS_KEY, '10');
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() =>
      expect(within(table).getAllByRole('checkbox').length).toBeGreaterThanOrEqual(7),
    );
    const boxes = () => within(table).getAllByRole('checkbox') as HTMLInputElement[];
    for (let i = 0; i < 6; i += 1) await userEvent.click(boxes()[i] as HTMLElement);

    const tray = screen.getByRole('complementary', { name: t('page.G2.tray') });
    expect(within(tray).getByText(t('page.G2.trayMax'))).toBeInTheDocument();
    expect(within(tray).queryByText(t('page.G2.trayHint'))).toBeNull();
    // 고른 6개는 그대로 켜져 있고(해제 가능), 나머지는 모두 비활성
    const checked = boxes().filter((b) => b.checked);
    const unchecked = boxes().filter((b) => !b.checked);
    expect(checked).toHaveLength(6);
    expect(checked.every((b) => !b.disabled)).toBe(true);
    expect(unchecked.length).toBeGreaterThan(0);
    expect(unchecked.every((b) => b.disabled)).toBe(true);

    // 7번째 클릭은 무시된다(비활성)
    await userEvent.click(unchecked[0] as HTMLElement);
    expect(boxes().filter((b) => b.checked)).toHaveLength(6);
    // 트레이 칩(제거 버튼) 6개, 비교 링크 ids 6개
    const chips = within(tray)
      .getAllByRole('button')
      .filter((b) => b.textContent?.endsWith('×'));
    expect(chips).toHaveLength(6);
    const href = within(tray)
      .getByRole('link', { name: t('page.G2.compare') })
      .getAttribute('href');
    const ids = new URL(href ?? '', 'http://x').searchParams.get('ids')?.split(',') ?? [];
    expect(ids).toHaveLength(6);
    expect(new Set(ids).size).toBe(6);

    // 하나를 빼면 다시 고를 수 있다
    await userEvent.click(chips[0] as HTMLElement);
    await waitFor(() => expect(boxes().filter((b) => b.checked)).toHaveLength(5));
    expect(boxes().every((b) => !b.disabled)).toBe(true);
    expect(within(tray).getByText(t('page.G2.trayHint'))).toBeInTheDocument();
  });
});
