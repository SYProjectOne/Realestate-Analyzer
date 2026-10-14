/**
 * R9-UI 완료 조건(ui-benchmark-rea §5): 단순화 뒤에도 출처·확인일·라벨이 하나도 사라지지 않는다.
 *  - G1·G2(데스크톱·모바일 카드)·G3·G4 의 모든 출처 버튼(FactCell·이름 출처)에 비어 있지 않은 라벨 글자 또는 '확인 불가(사유)'
 *  - 조용한 글자로 낮춘 '확인됨' 값도 한 번 클릭으로 출처 패널(원문 주소·확인일·라벨)에 닿는다
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { provenanceConflict } from '@/charts/gallery/fixtures';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

function expectEveryProvLabelled(root: HTMLElement) {
  const cells = [...root.querySelectorAll('button[data-prov]')].filter(
    // 이름 출처 버튼(NameWithProvenance 등)은 라벨이 없을 수 있다 — FactCell(값 + 라벨)만
    (el) => el.querySelector('.tabular-nums, [data-testid="empty-state"]') !== null,
  );
  expect(cells.length).toBeGreaterThan(0);
  const bad = cells.filter((cell) => {
    const label = cell.querySelector('[data-testid="label-badge"], [data-testid="empty-state"]');
    return !label || (label.textContent ?? '').trim().length === 0;
  });
  expect(bad.map((b) => b.getAttribute('data-prov'))).toEqual([]);
}

describe('라벨·출처가 사라지지 않는다(R9-UI 전 화면)', () => {
  it.each([
    ['G1', '/', () => screen.findByRole('list', { name: t('page.G1.top5') })],
    ['G2', '/complexes', () => screen.findByRole('table', { name: t('page.G2.table') })],
    ['G3', '/complexes/2', () => screen.findByRole('region', { name: '엘리프 검단 포레듀' })],
    ['G4', '/compare?ids=2,7,4', () => screen.findByRole('table', { name: t('page.G4.grid') })],
  ])('%s 모든 값 칸에 라벨', async (_id, path, ready) => {
    renderRoute(path);
    await ready();
    await waitFor(() => expectEveryProvLabelled(document.body));
  });

  it('G2 모바일 카드도 값마다 라벨', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderRoute('/complexes');
      await screen.findByRole('list', { name: t('page.G2.cards') });
      await waitFor(() => expectEveryProvLabelled(document.body));
    } finally {
      window.matchMedia = original;
    }
  });

  it("조용한 '확인됨' 값 → 1클릭 출처 패널(원문 주소·확인일·라벨)", async () => {
    server.use(
      http.get(mswPath('/provenance/:prov_id'), () => HttpResponse.json(provenanceConflict())),
    );
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: '엘리프 검단 포레듀' });
    const quiet = head.querySelector('[data-testid="label-badge"][data-tone="quiet"]');
    expect(quiet).not.toBeNull();
    const button = quiet?.closest('button[data-prov]') as HTMLElement;
    await userEvent.click(button);
    const panel = await screen.findByRole('dialog', { name: t('provenance.title') });
    expect(await within(panel).findByText(t('provenance.url'))).toBeInTheDocument();
    expect(within(panel).getByText(t('provenance.checkedAt'))).toBeInTheDocument();
    expect(within(panel).getByText(t('provenance.label'))).toBeInTheDocument();
  });
});
