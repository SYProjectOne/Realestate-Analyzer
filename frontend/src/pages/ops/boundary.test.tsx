/** R3 minor 35 — D2-6 '범위 경계' 단지 목록을 G7 에서 본다(G2 필터로만 보이던 것). */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexRowPage } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

/** 예시 행 2개를 '범위 경계'로 바꾸고 서버처럼 filter[inclusion_class] 로 거른다 */
function boundaryRows() {
  server.use(
    http.get(mswPath('/snapshots/:sid/complexes'), async ({ request }) => {
      const res = await getResponse(generatedHandlers as RequestHandler[], request.clone());
      const page = (await res?.json()) as ComplexRowPage;
      const rows = page.items.map((row, i) =>
        i < 2 ? { ...row, inclusion_class: '범위 경계' as const } : row,
      );
      const want = new URL(request.url).searchParams.get('filter[inclusion_class]');
      const items = want ? rows.filter((r) => r.inclusion_class === want) : rows;
      return HttpResponse.json({ ...page, items, total: items.length });
    }),
  );
}

describe('G7 범위 경계 목록', () => {
  it('GET complexes?filter[inclusion_class]=범위 경계 → 이름 + 단지 화면 링크', async () => {
    boundaryRows();
    const rec = recordRequests();
    const { router } = renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.boundary.title') });
    const list = await within(section).findByRole('list', { name: t('page.G7.boundary.title') });
    const links = within(list).getAllByRole('link');
    expect(links).toHaveLength(2);
    await waitFor(() =>
      expect(
        matching(rec.requests, 'GET', /\/snapshots\/\d+\/complexes$/).some(
          (r) => r.url.searchParams.get('filter[inclusion_class]') === '범위 경계',
        ),
      ).toBe(true),
    );
    const href = links[0]?.getAttribute('href') ?? '';
    expect(href).toMatch(/^\/complexes\/\d+/);
    await userEvent.click(links[0] as HTMLElement);
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/complexes\/\d+$/));
    rec.stop();
  });

  it('범위 경계 단지가 없으면 빈 안내', async () => {
    renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.boundary.title') });
    expect(await within(section).findByText(t('page.G7.boundary.none'))).toBeInTheDocument();
  });
});
