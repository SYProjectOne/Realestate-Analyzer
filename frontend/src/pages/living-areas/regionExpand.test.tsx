/**
 * D11-7(계약 .8): 지역 선택 확장 UI — PATCH /regions/{id} {selections, name?}
 * → RegionPatched {region, change_event, job_id(region.expand), added, removed}.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { RegionSelection } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { selectionDiff } from './RegionExpandPanel';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const sel = (code: string, kind: RegionSelection['kind'] = 'sigungu'): RegionSelection => ({
  kind,
  code,
  full_name: `지역 ${code}`,
});

describe('D11-7 지역 범위 확장', () => {
  it('selectionDiff: 추가·제거만 센다(종류+코드 기준)', () => {
    const before = [sel('1'), sel('2')];
    const after = [sel('2'), sel('3'), sel('1', 'legal_dong')];
    const diff = selectionDiff(before, after);
    expect(diff.added.map((s) => `${s.kind}:${s.code}`)).toEqual(['sigungu:3', 'legal_dong:1']);
    expect(diff.removed.map((s) => s.code)).toEqual(['1']);
  });

  it('후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 응답 added·change_event·job_id 잡 진행', async () => {
    const rec = recordRequests();
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    const current = within(panel).getByRole('list', { name: t('page.G0_2.expand.current') });
    const before = within(current).getAllByRole('listitem').length;
    const submit = within(panel).getByRole('button', { name: t('page.G0_2.expand.submit') });
    expect(submit).toBeDisabled();

    await userEvent.type(within(panel).getByLabelText(t('page.G0_2.expand.search')), '검단');
    const list = await within(panel).findByRole('list', {
      name: t('page.G0_2.expand.candidates'),
    });
    const addable = within(list)
      .getAllByRole('button', { name: t('page.G0_2.expand.add') })
      .find((b) => !(b as HTMLButtonElement).disabled);
    expect(addable).toBeDefined();
    await userEvent.click(addable!);
    expect(within(current).getAllByRole('listitem')).toHaveLength(before + 1);
    expect(within(panel).getByTestId('expand-diff')).toHaveTextContent(
      t('page.G0_2.expand.diff', { added: '1', removed: '0' }),
    );

    await userEvent.click(submit);
    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/regions/1')).toHaveLength(1));
    const body = (await matching(rec.requests, 'PATCH', '/regions/1')[0]?.body) as {
      selections: RegionSelection[];
    };
    expect(body.selections).toHaveLength(before + 1);
    expect(body).not.toHaveProperty('name');
    const job = await within(panel).findByTestId('expand-job');
    // 계약 예시 region_patched.json: 추가 1(경기도 김포시)·제거 0, change_event critical, job_id 961
    expect(within(job).getByTestId('expand-result')).toHaveTextContent(
      t('page.G0_2.expand.result', { added: '1', removed: '0' }),
    );
    expect(within(job).getByTestId('expand-result')).toHaveTextContent('경기도 김포시');
    expect(job).toHaveTextContent('선택 4개(추가: 경기도 김포시)');
    expect(await within(job).findByText('region.expand')).toBeInTheDocument();
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/jobs\/961$/).length).toBeGreaterThan(0),
    );
    rec.stop();
  });

  it('이름만 바꿔도 저장할 수 있고 본문에 name 이 실린다', async () => {
    const rec = recordRequests();
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    const submit = within(panel).getByRole('button', { name: t('page.G0_2.expand.submit') });
    const name = within(panel).getByLabelText(t('page.G0_2.expand.name'));
    await userEvent.clear(name);
    await userEvent.type(name, '새 이름');
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/regions/1')).toHaveLength(1));
    expect(await matching(rec.requests, 'PATCH', '/regions/1')[0]?.body).toMatchObject({
      name: '새 이름',
    });
    rec.stop();
  });

  it('서버 409(선택이 그대로) → detail 을 보인다', async () => {
    server.use(
      http.patch(mswPath('/regions/:id'), () =>
        HttpResponse.json({ code: 'conflict', detail: '선택이 바뀌지 않았다' }, { status: 409 }),
      ),
    );
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    const name = within(panel).getByLabelText(t('page.G0_2.expand.name'));
    await userEvent.type(name, ' 2');
    await userEvent.click(
      within(panel).getByRole('button', { name: t('page.G0_2.expand.submit') }),
    );
    expect(await within(panel).findByRole('alert')).toHaveTextContent('선택이 바뀌지 않았다');
  });

  it('서버 409 뒤 지역을 다시 받는다(화면이 본 선택이 낡았다 — 4차 minor)', async () => {
    server.use(
      http.patch(mswPath('/regions/:id'), () =>
        HttpResponse.json({ code: 'conflict', detail: '선택이 바뀌지 않았다' }, { status: 409 }),
      ),
    );
    const rec = recordRequests();
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    const regionGets = () => matching(rec.requests, 'GET', /\/regions(\/1)?$/).length;
    await waitFor(() => expect(regionGets()).toBeGreaterThan(0));
    const before = regionGets();
    await userEvent.type(within(panel).getByLabelText(t('page.G0_2.expand.name')), ' 2');
    await userEvent.click(
      within(panel).getByRole('button', { name: t('page.G0_2.expand.submit') }),
    );
    await within(panel).findByRole('alert');
    await waitFor(() => expect(regionGets()).toBeGreaterThan(before));
    rec.stop();
  });

  it('선택이 하나뿐이면 뺄 수 없다', async () => {
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    const current = within(panel).getByRole('list', { name: t('page.G0_2.expand.current') });
    let items = within(current).getAllByRole('listitem');
    // 하나만 남을 때까지 뺀다
    while (items.length > 1) {
      await userEvent.click(within(items[0] as HTMLElement).getByRole('button'));
      items = within(current).getAllByRole('listitem');
    }
    expect(within(items[0] as HTMLElement).getByRole('button')).toBeDisabled();
  });
});
