import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G6 지역 시장', () => {
  it('생활권 필터 → URL ?living_area= → GET /market?living_area=', async () => {
    const rec = recordRequests();
    const { router } = renderRoute('/market');
    await screen.findByText(t('chart.C03.title'));
    const select = screen.getByLabelText(t('page.G6.livingArea'));
    await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
    const value = (select.querySelectorAll('option')[1] as HTMLOptionElement).value;
    await userEvent.selectOptions(select, value);
    await waitFor(() => expect(router.state.location.search).toContain(`living_area=${value}`));
    await waitFor(() =>
      expect(
        matching(rec.requests, 'GET', '/market').some(
          (r) => r.url.searchParams.get('living_area') === value,
        ),
      ).toBe(true),
    );
    rec.stop();
  });

  it('규제 요약 카드와 생활권별 실거래 시세 표', async () => {
    renderRoute('/market');
    expect(await screen.findByRole('heading', { name: t('page.G6.regulation') })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: t('page.G6.prices') })).toBeInTheDocument();
  });
});
