import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { moveCodes, validate, type DraftArea } from './index';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const A: DraftArea = { key: 'a', id: 'la_1', name: '가', codes: ['1', '2'] };
const B: DraftArea = { key: 'b', id: 'la_2', name: '나', codes: ['3'] };

describe('G0-2 규칙', () => {
  it('모든 법정동은 정확히 한 생활권에', () => {
    expect(validate(['1', '2', '3'], [A, B]).ok).toBe(true);
    expect(validate(['1', '2', '3', '4'], [A, B]).unassigned).toEqual(['4']);
    expect(validate(['1', '2', '3'], [A, { ...B, codes: ['3', '1'] }]).duplicated).toEqual(['1']);
    expect(validate(['1', '2', '3'], [A, { ...B, name: ' ' }]).emptyName).toBe(true);
  });
  it('moveCodes: 옮기면 원래 생활권에서 빠진다', () => {
    const next = moveCodes([A, B], ['2'], 'b');
    expect(next[0]?.codes).toEqual(['1']);
    expect(next[1]?.codes).toEqual(['3', '2']);
  });
});

describe('G0-2 생활권 편집', () => {
  it('세대수(Fact) 표시 · 법정동이 있으면 삭제 불가', async () => {
    renderRoute('/regions/1/living-areas');
    const names = await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    expect(names.length).toBeGreaterThanOrEqual(2);
    for (const button of screen.getAllByRole('button', { name: t('page.G0_2.delete') })) {
      expect(button).toBeDisabled();
    }
    expect(screen.getAllByText(t('page.G0_2.households')).length).toBe(names.length);
  });

  it('생활권 추가 → 법정동 선택 후 이동 → 이름 변경 → 저장(PUT) → 잡 진행', async () => {
    const rec = recordRequests();
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.add') }));
    const names = screen.getAllByRole('textbox', { name: t('page.G0_2.areaName') });
    const newName = names[names.length - 1] as HTMLInputElement;
    await userEvent.clear(newName);
    await userEvent.type(newName, '새 묶음');
    // 새 생활권은 비어 있어 삭제 가능
    const deletes = screen.getAllByRole('button', { name: t('page.G0_2.delete') });
    expect(deletes[deletes.length - 1]).toBeEnabled();

    const firstDong = screen.getAllByRole('checkbox')[0] as HTMLElement;
    await userEvent.click(firstDong);
    const target = screen.getByLabelText(t('page.G0_2.moveTo'));
    const options = target.querySelectorAll('option');
    await userEvent.selectOptions(target, (options[options.length - 1] as HTMLOptionElement).value);
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.move') }));
    expect(screen.getByText(t('page.G0_2.dirty'))).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.save') }));
    await waitFor(() => expect(matching(rec.requests, 'PUT', '/living-areas')).toHaveLength(1));
    const body = (await matching(rec.requests, 'PUT', '/living-areas')[0]?.body) as {
      living_areas: { id: string | null; name: string; legal_dong_codes: string[] }[];
    };
    const added = body.living_areas[body.living_areas.length - 1];
    expect(added).toMatchObject({ id: null, name: '새 묶음' });
    expect(added?.legal_dong_codes).toHaveLength(1);
    const all = body.living_areas.flatMap((a) => a.legal_dong_codes);
    expect(new Set(all).size).toBe(all.length);
    expect(await screen.findByText(t('job.title'))).toBeInTheDocument();
    rec.stop();
  });

  it('422 → 필드 오류 표시', async () => {
    server.use(
      http.put(mswPath('/regions/:id/living-areas'), () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            detail: '법정동 배정 오류',
            field_errors: [{ loc: ['living_areas', 0], msg: '중복' }],
          },
          { status: 422 },
        ),
      ),
    );
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.save') }));
    const alert = await screen.findByText(t('page.G0_2.saveError', { detail: '법정동 배정 오류' }));
    expect(
      within(alert.parentElement as HTMLElement).getByText('living_areas.0: 중복'),
    ).toBeInTheDocument();
  });
});
