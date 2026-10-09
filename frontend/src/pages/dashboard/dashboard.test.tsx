import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G1 홈 대시보드', () => {
  it('KPI 5개: 판정 대상·접수 가능·미분양·입주 피크·데이터 신선도', async () => {
    renderRoute('/');
    const kpis = await screen.findByRole('list', { name: t('page.G1.kpis') });
    for (const key of ['judged', 'intakeOpen', 'unsold', 'movePeak', 'freshness'] as const) {
      expect(within(kpis).getByText(t(`page.G1.kpi.${key}`))).toBeInTheDocument();
    }
  });

  it('TOP 5 카드: 종합·+10% 확률·접수 배지, 카드 클릭 → G3', async () => {
    const { router } = renderRoute('/');
    const top5 = await screen.findByRole('list', { name: t('page.G1.top5') });
    const cards = within(top5).getAllByRole('listitem');
    const first = cards[0] as HTMLElement;
    expect(within(first).getByText(t('page.G1.total'))).toBeInTheDocument();
    expect(within(first).getByText(t('page.G1.p10'))).toBeInTheDocument();
    expect(within(first).getByTestId('intake-badge')).toBeInTheDocument();
    await userEvent.click(within(first).getByText(t('page.G1.p10')));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/complexes/${first.dataset.complexId}`),
    );
  });

  it('변경 피드 항목 → G3 해당 탭(URL 해시)', async () => {
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    const links = within(feed).getAllByRole('link');
    expect(links[0]).toHaveAttribute('href', expect.stringMatching(/^\/complexes\/7.*#payment$/));
  });

  it('상황 토글 → ?scenario= 로 dashboard 재조회', async () => {
    const rec = recordRequests();
    renderRoute('/');
    await screen.findByRole('list', { name: t('page.G1.top5') });
    await userEvent.click(await screen.findByRole('radio', { name: /^B / }));
    await waitFor(() => {
      const calls = matching(rec.requests, 'GET', '/dashboard');
      expect(calls.some((c) => c.url.searchParams.get('scenario') === 'B')).toBe(true);
    });
    rec.stop();
  });
});
