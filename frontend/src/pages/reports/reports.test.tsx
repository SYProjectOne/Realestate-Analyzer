import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { Snapshot } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleSnapshots(): Promise<Snapshot[]> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/regions/1/snapshots'),
  );
  return (await res?.json()) as Snapshot[];
}

describe('G8 보고서', () => {
  it('생성 → POST /reports(html|pdf, 비교 스냅샷) → JobProgress', async () => {
    const rec = recordRequests();
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(screen.getByRole('radio', { name: t('page.G8.formats.pdf') }));
    const compare = screen.getByLabelText(t('page.G8.compareSnapshot'));
    const value = (compare.querySelectorAll('option')[1] as HTMLOptionElement).value;
    await userEvent.selectOptions(compare, value);
    await userEvent.click(button);
    await waitFor(() => expect(matching(rec.requests, 'POST', '/reports')).toHaveLength(1));
    const body = (await matching(rec.requests, 'POST', '/reports')[0]?.body) as {
      format: string;
      snapshot_id: number;
      compare_snapshot_id: number;
    };
    expect(body).toMatchObject({ format: 'pdf', compare_snapshot_id: Number(value) });
    expect(typeof body.snapshot_id).toBe('number');
    expect(await screen.findByText(t('job.title'))).toBeInTheDocument();
    // 비교 스냅샷을 고르면 diff 표(GET /changes?compare_snapshot=)
    expect(await screen.findByRole('table', { name: t('page.G8.diff') })).toBeInTheDocument();
    expect(
      matching(rec.requests, 'GET', '/changes').some(
        (r) => r.url.searchParams.get('compare_snapshot') === value,
      ),
    ).toBe(true);
    rec.stop();
  });

  it('contradicted claim이 있으면 생성 버튼 비활성 + 사유', async () => {
    const snapshots = await exampleSnapshots();
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(snapshots.map((s, i) => (i === 0 ? { ...s, contradicted_claims: 2 } : s))),
      ),
    );
    renderRoute('/reports');
    const button = await screen.findByRole('button', { name: t('page.G8.generate') });
    const reason = await screen.findByText(t('page.G8.blocked', { n: '2' }));
    expect(button).toBeDisabled();
    expect(reason).toHaveAttribute('role', 'alert');
  });

  it('보고서 목록: 완료된 것만 다운로드 링크', async () => {
    renderRoute('/reports');
    const table = await screen.findByRole('table', { name: t('page.G8.list') });
    const links = within(table).getAllByRole('link');
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link.getAttribute('href')).toMatch(/\/reports\/\d+$/);
  });
});
