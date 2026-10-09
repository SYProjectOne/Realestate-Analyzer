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
});
