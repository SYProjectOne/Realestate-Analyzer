import { screen, waitFor, within } from '@testing-library/react';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { parseIds } from './index';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G4 parseIds', () => {
  it('정수만, 중복 제거', () => {
    expect(parseIds('2,7,4')).toEqual([2, 7, 4]);
    expect(parseIds('2, 2, x, 0, -1, 3.5, 9')).toEqual([2, 9]);
    expect(parseIds(null)).toEqual([]);
  });
});

describe('G4 비교', () => {
  it.each([
    ['/compare?ids=2', 1],
    ['/compare?ids=1,2,3,4,5,6,7', 7],
    ['/compare', 0],
  ])('%s → ids 2~6 검사 안내, API 호출 없음', async (path, n) => {
    const rec = recordRequests();
    renderRoute(path);
    expect(await screen.findByText(t('page.G4.invalidIds', { n: String(n) }))).toBeInTheDocument();
    expect(matching(rec.requests, 'GET', '/compare')).toHaveLength(0);
    rec.stop();
  });

  it('비교 표(열 = 단지) · 조건 표 · 상황별 판정(C7) · 동률 배지', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const grid = await screen.findByRole('table', { name: t('page.G4.grid') });
    expect(within(grid).getAllByRole('columnheader')).toHaveLength(4);
    expect(within(grid).getByText(/^판정기 선택 확률\(상황 /)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: t('page.G4.termsFirst') })).toBeInTheDocument();
    expect(screen.getByText(t('chart.C07.title'))).toBeInTheDocument();
    // 상황 B 예시: confidence 0.48 → 동률
    expect(screen.getAllByTestId('tie-badge').length).toBeGreaterThan(0);
  });

  it('가상 후보 wait_new(complex_id null, 계약 .5) → 상황별 판정에 "가상 후보: <label>" + 선택 확률', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=B');
    const panel = await screen.findByRole('region', { name: t('page.G4.decision') });
    const list = await within(panel).findByRole('list', { name: t('page.G4.virtual') });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(1);
    const item = items[0] as HTMLElement;
    expect(item).toHaveAttribute('data-option', 'wait_new');
    expect(item).toHaveTextContent(
      t('page.G4.virtualCandidate', { label: '모집공고 대기 후 1순위 청약' }),
    );
    expect(item).toHaveTextContent(t('page.G4.row.prob'));
    expect(item).toHaveTextContent('0%');
    // 요건 표에서도 가상 후보임을 표시
    const req = within(panel).getByRole('table', { name: t('page.G4.requirements') });
    const row = within(req).getByRole('row', { name: /모집공고 대기 후 1순위 청약/ });
    expect(within(row).getByText(t('chart.C07.virtual'))).toBeInTheDocument();
  });

  it('wait_new 가 없는 상황(base) → 가상 후보 목록 없음', async () => {
    renderRoute('/compare?ids=2,7,4&scenario=base');
    const panel = await screen.findByRole('region', { name: t('page.G4.decision') });
    expect(within(panel).queryByRole('list', { name: t('page.G4.virtual') })).toBeNull();
  });
});

describe('R9-UI P9 G4 사실 비교를 먼저(30-proposal §10)', () => {
  it('블록 순서: 조건 비교 → 점수·판정기 → 가격 갭 → 점수 분해 → 가격 전망 → 상황별 판정 → 민감도', async () => {
    const { container } = renderRoute('/compare?ids=2,7,4&scenario=B');
    await screen.findByRole('table', { name: t('page.G4.grid') });
    await waitFor(() => expect(container.querySelector('[data-block="C10"]')).not.toBeNull());
    const order = [...container.querySelectorAll('[data-block]')].map((el) =>
      el.getAttribute('data-block'),
    );
    expect(order).toEqual(['terms', 'grid', 'C02', 'C06', 'ladder', 'decision', 'C10']);
  });

  it('점수 순위와 판정기 선택 확률의 차이를 한 문장으로 설명한다', async () => {
    renderRoute('/compare?ids=2,7,4');
    const scores = await screen.findByRole('region', { name: t('page.G4.scores') });
    expect(within(scores).getByText(t('page.G4.rankVsDecide'))).toBeInTheDocument();
  });

  it('조건 비교 표: 접수·현재 구매가(가격 갭 응답의 Fact 그대로)·전매·계약금 — 라벨·출처 유지', async () => {
    renderRoute('/compare?ids=2,7,4');
    const terms = await screen.findByRole('table', { name: t('page.G4.termsFirst') });
    const rowOf = (name: string) =>
      within(terms).getByRole('row', { name: new RegExp(`^${name}`) });
    expect(within(rowOf(t('page.G4.row.intake'))).getAllByTestId('intake-badge')).toHaveLength(3);
    const price = rowOf(t('page.G4.term.price'));
    const provs = [...price.querySelectorAll('[data-prov]')];
    expect(provs.length).toBeGreaterThan(0);
    for (const cell of provs) {
      expect(
        cell.querySelector('[data-testid="label-badge"], [data-testid="empty-state"]'),
      ).not.toBeNull();
    }
    expect(rowOf(t('page.G4.term.resale_end'))).toBeInTheDocument();
    expect(rowOf(t('page.G4.term.down_payment_pct'))).toBeInTheDocument();
  });
});
