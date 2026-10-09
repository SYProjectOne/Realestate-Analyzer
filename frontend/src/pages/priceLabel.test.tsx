/**
 * R3 minor 27 — price_low 의 라벨을 숨기지 않는다(showLabel={false} 제거). 가격 범위 하단·상단 모두 라벨 배지.
 */
import { screen, waitFor, within } from '@testing-library/react';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('가격 범위 하단(price_low) 라벨이 보인다', () => {
  it('G3 헤더·가격 탭: 현재 구매가 범위 = 하단·상단 각각 라벨 배지', async () => {
    renderRoute('/complexes/2#price');
    await screen.findByRole('tabpanel');
    const terms = await screen.findAllByText(t('page.G3.header.price'), { selector: 'dt' });
    // 헤더 + 가격 탭
    expect(terms.length).toBe(2);
    for (const term of terms) {
      const dd = term.nextElementSibling as HTMLElement;
      expect(dd.tagName).toBe('DD');
      expect(within(dd).getAllByTestId('label-badge')).toHaveLength(2);
    }
  });

  it('G2 표: 가격 칸 = 하단·상단 각각 라벨 배지', async () => {
    renderRoute('/complexes');
    const table = await screen.findByRole('table', { name: t('page.G2.table') });
    await waitFor(() => expect(within(table).getAllByRole('row').length).toBeGreaterThan(1));
    const row = within(table).getAllByRole('row')[1] as HTMLElement;
    const priceCell = Array.from(row.querySelectorAll('td')).find(
      (td) => td.querySelector('[aria-hidden]')?.textContent === '~',
    ) as HTMLElement;
    expect(priceCell).toBeTruthy();
    expect(within(priceCell).getAllByTestId('label-badge')).toHaveLength(2);
  });
});
