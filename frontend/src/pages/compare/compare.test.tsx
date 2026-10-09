import { screen, within } from '@testing-library/react';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { parseIds } from './index';

vi.mock('echarts-for-react', () => ({ default: () => null }));
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
    expect(within(grid).getByText(t('page.G4.row.decision'))).toBeInTheDocument();
    expect(screen.getByRole('table', { name: t('page.G4.terms') })).toBeInTheDocument();
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
