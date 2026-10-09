/**
 * D11-5(계약 .8 초안): 호재 위치 확인 UI — PATCH /catalysts/{id} → catalyst_link.
 * 좌표 없는 단지는 거리 '확인 불가(단지 좌표 없음…)'·가중치 1(비수치 메타), 위치 미확정이면 링크 없음.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { parseCoord } from './CatalystLocationPanel';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function panel() {
  return screen.findByRole('region', { name: t('page.G6.loc.title') });
}

async function row(name: string) {
  const list = within(await panel()).getByRole('list', { name: t('page.G6.loc.title') });
  return (await within(list).findByText(name)).closest('li') as HTMLElement;
}

describe('D11-5 호재 위치 확인', () => {
  it('좌표 검사: 범위·형식, 빈 값 허용', () => {
    expect(parseCoord('', 'lat')).toBeNull();
    expect(parseCoord('37.55', 'lat')).toBe(37.55);
    expect(parseCoord('91', 'lat')).toBe('invalid');
    expect(parseCoord('126.7', 'lon')).toBe(126.7);
    expect(parseCoord('abc', 'lon')).toBe('invalid');
  });

  it('위치 미확정 호재 → 단지 선택 → PATCH → 링크 표(거리 확인 불가·가중치) → 목록 "위치 확인됨"', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const item = await row('GTX-B');
    expect(within(item).getByTestId('loc-status')).toHaveTextContent(t('page.G6.loc.unconfirmed'));
    await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.open') }));
    const form = within(item).getByRole('form', {
      name: t('page.G6.loc.formFor', { name: 'GTX-B' }),
    });
    const select = within(form).getByLabelText(t('page.G6.loc.complexes'));
    await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1));
    const first = select.querySelectorAll('option')[0] as HTMLOptionElement;
    await userEvent.selectOptions(select, first.value);
    await userEvent.click(within(form).getByRole('button', { name: t('page.G6.loc.submit') }));

    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/catalysts/50')).toHaveLength(1));
    expect(await matching(rec.requests, 'PATCH', '/catalysts/50')[0]?.body).toEqual({
      location_confirmed: true,
      living_area_ids: [],
      complex_ids: [Number(first.value)],
    });
    const links = await within(await panel()).findByTestId('catalyst-links');
    const linkRow = within(links).getAllByRole('row')[1] as HTMLElement;
    expect(linkRow).toHaveTextContent(first.textContent ?? '');
    expect(linkRow).toHaveTextContent(t('page.G6.loc.noCoord'));
    expect(linkRow.querySelector('[data-meta="derived"]')).toHaveTextContent('1.00');
    // 시장 다시 읽기(사실 화면 무효화) → 위치 확인됨
    await waitFor(async () =>
      expect(within(await row('GTX-B')).getByTestId('loc-status')).toHaveTextContent(
        t('page.G6.loc.confirmed'),
      ),
    );
    rec.stop();
  });

  it('대상 없이 저장·위도만 입력·범위 밖 → 오류, PATCH 없음', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const item = await row('GTX-B');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.open') }));
    const form = within(item).getByRole('form');
    const submit = within(form).getByRole('button', { name: t('page.G6.loc.submit') });
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.needTarget'));
    await userEvent.type(within(form).getByLabelText(t('page.G6.loc.lat')), '37.5');
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.bothCoord'));
    await userEvent.type(within(form).getByLabelText(t('page.G6.loc.lon')), '200');
    await userEvent.click(submit);
    expect(within(form).getByRole('alert')).toHaveTextContent(t('page.G6.loc.badCoord'));
    expect(matching(rec.requests, 'PATCH', /\/catalysts\//)).toHaveLength(0);
    rec.stop();
  });

  it('위치 확인된 호재 → "위치 확인 취소" → PATCH location_confirmed=false → 링크 지움 안내', async () => {
    const rec = recordRequests();
    renderRoute('/market');
    const item = await row('검단구 신설');
    await userEvent.click(within(item).getByRole('button', { name: t('page.G6.loc.unconfirm') }));
    await waitFor(() => expect(matching(rec.requests, 'PATCH', '/catalysts/42')).toHaveLength(1));
    expect(await matching(rec.requests, 'PATCH', '/catalysts/42')[0]?.body).toEqual({
      location_confirmed: false,
    });
    expect(await within(await panel()).findByTestId('catalyst-links')).toHaveTextContent(
      t('page.G6.loc.cleared'),
    );
    rec.stop();
  });
});
