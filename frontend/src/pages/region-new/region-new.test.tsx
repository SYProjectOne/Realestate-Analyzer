import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('G0 지역 입력', () => {
  it('자동완성(디바운스) → 후보 다중 선택 칩 → 이름 → 분석 시작 → JobProgress', async () => {
    const rec = recordRequests();
    renderRoute('/regions/new');
    const search = await screen.findByRole('searchbox', { name: t('page.G0.search') });
    await userEvent.type(search, '검단');
    const list = await screen.findByRole('list', { name: t('page.G0.candidates') });
    // 디바운스: 글자마다가 아니라 멈춘 뒤 한 번(2자 미만은 호출 안 함)
    const resolves = matching(rec.requests, 'GET', '/regions/resolve');
    expect(resolves.length).toBe(1);
    expect(resolves[0]?.url.searchParams.get('q')).toBe('검단');

    const boxes = within(list).getAllByRole('checkbox');
    await userEvent.click(boxes[0] as HTMLElement);
    await userEvent.click(boxes[1] as HTMLElement);
    const chips = screen.getByRole('list', { name: t('page.G0.selected') });
    expect(within(chips).getAllByRole('button')).toHaveLength(2);

    const start = screen.getByRole('button', { name: t('page.G0.start') });
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText(t('page.G0.name')), '내 지역');
    expect(start).toBeEnabled();
    await userEvent.click(start);

    await waitFor(() => expect(matching(rec.requests, 'POST', '/regions')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/regions')[0]?.body) as {
      name: string;
      query_text: string;
      selections: { kind: string; code: string }[];
    };
    expect(body.name).toBe('내 지역');
    expect(body.query_text).toBe('검단');
    expect(body.selections).toHaveLength(2);
    expect(await screen.findByText(t('job.title'))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: t('page.G0.goLivingAreas') })).toBeInTheDocument();
    rec.stop();
  });

  it('칩의 × → 선택 해제', async () => {
    renderRoute('/regions/new');
    await userEvent.type(await screen.findByRole('searchbox', { name: t('page.G0.search') }), '검단');
    const list = await screen.findByRole('list', { name: t('page.G0.candidates') });
    await userEvent.click(within(list).getAllByRole('checkbox')[0] as HTMLElement);
    const chips = screen.getByRole('list', { name: t('page.G0.selected') });
    await userEvent.click(within(chips).getAllByRole('button')[0] as HTMLElement);
    expect(screen.getByText(t('page.G0.noneSelected'))).toBeInTheDocument();
  });
});
