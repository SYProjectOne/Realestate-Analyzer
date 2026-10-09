/**
 * D11-7(계약 .8 초안): 지역 선택 확장 UI — PATCH /regions/{id} {selections} → Region + region.expand 잡.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { RegionSelection } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
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

  it('후보 검색 → 추가 → 변경 요약 → 저장 = PATCH selections → 새 리비전 잡 진행', async () => {
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
    const job = await within(panel).findByTestId('expand-job');
    expect(await within(job).findByText('region.expand')).toBeInTheDocument();
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
