/**
 * R11-SETUP(D30, 목업 LivingAreas): G0-2 '생활권이 뭐예요?' 한 줄 답 · 옮기기 도구줄 · 카드(5개 + 더 보기) · 화면 아래 저장 줄 ·
 * 지역 범위(#range). 지금 동작(규칙·저장·422·범위 확장)은 living-areas.test.tsx · regionExpand.test.tsx 가 지킨다.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import type { Region } from '@/api/types';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { DONG_PREVIEW } from './index';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function region1(): Promise<Region> {
  const res = await fetch('http://localhost/api/regions/1');
  return (await res.json()) as Region;
}

/** 지역 1 + 생활권 하나에 법정동을 여럿(접기 시험용) */
function withBigArea(region: Region, extra: string[]): Region {
  const [first, ...rest] = region.living_areas;
  return {
    ...region,
    legal_dong_codes: [...region.legal_dong_codes, ...extra],
    living_areas: [
      { ...first!, legal_dong_codes: [...first!.legal_dong_codes, ...extra] },
      ...rest,
    ],
  };
}

function cards(): HTMLElement[] {
  return within(screen.getByRole('region', { name: t('page.G0_2.cards') })).getAllByRole('region');
}

describe('R11 G0-2 생활권 — 목업 LivingAreas', () => {
  it("머리: '생활권이 뭐예요?' 한 줄 답이 맨 위(지역을 받기 전부터) · 현재 위치 줄 · 생활권·법정동 개수 · #range 링크", async () => {
    renderRoute('/regions/1/living-areas');
    const answer = await screen.findByTestId('living-area-answer');
    expect(answer).toHaveTextContent(t('page.G0_2.whatIs'));
    expect(answer).toHaveTextContent(t('page.G0_2.answer'));
    const region = await region1();
    expect(
      await screen.findByText(
        t('page.G0_2.summary', {
          areas: String(region.living_areas.length),
          dongs: String(region.legal_dong_codes.length),
        }),
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: t('page.G0.crumbLabel') })).toHaveTextContent(
      region.name,
    );
    expect(screen.getByRole('link', { name: t('page.G0_2.toRange') })).toHaveAttribute(
      'href',
      '#range',
    );
    expect(screen.getByRole('region', { name: t('page.G0_2.expand.title') })).toHaveAttribute(
      'id',
      'range',
    );
    expect(screen.getByText(t('page.G0_2.footnote'))).toBeInTheDocument();
  });

  it('카드: 법정동은 처음 5개 + "나머지 n개 더 보기"(누르면 모두 · 접기)', async () => {
    const region = await region1();
    const extra = Array.from({ length: 6 }, (_, i) => `99999${String(i).padStart(5, '0')}`);
    server.use(
      http.get(mswPath('/regions/:id'), () => HttpResponse.json(withBigArea(region, extra))),
    );
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    const big = cards()[0] as HTMLElement;
    const total = (region.living_areas[0]?.legal_dong_codes.length ?? 0) + extra.length;
    expect(within(big).getAllByRole('checkbox')).toHaveLength(DONG_PREVIEW);
    const more = within(big).getByRole('button', {
      name: t('page.G0_2.more', { n: String(total - DONG_PREVIEW) }),
    });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(more);
    expect(within(big).getAllByRole('checkbox')).toHaveLength(total);
    // 이름을 모르는 동(지역 선택에 없는 코드)은 코드만, 고르기 이름도 '코드 고르기'(LA-2)
    const codeOnly = within(big).getByRole('checkbox', {
      name: t('page.G0_2.selectDong', { name: extra[0]! }),
    });
    expect((codeOnly.closest('label') as HTMLElement).textContent).toBe(extra[0]);
    await userEvent.click(within(big).getByRole('button', { name: t('page.G0_2.less') }));
    expect(within(big).getAllByRole('checkbox')).toHaveLength(DONG_PREVIEW);
  });

  it('도구줄: 고른 동 수 · 고른 동이 없으면 "이리로 옮기기" 꺼짐 · 고른 동이 있는 카드는 강조', async () => {
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    const toolbar = screen.getByTestId('move-toolbar');
    expect(toolbar).toHaveTextContent(t('page.G0_2.selectedCount', { n: '0' }));
    expect(within(toolbar).getByRole('button', { name: t('page.G0_2.move') })).toBeDisabled();
    expect(toolbar).toHaveTextContent(t('page.G0_2.dropHint'));
    const first = cards()[0] as HTMLElement;
    await userEvent.click(within(first).getAllByRole('checkbox')[0] as HTMLElement);
    expect(toolbar).toHaveTextContent(t('page.G0_2.selectedCount', { n: '1' }));
    expect(within(toolbar).getByRole('button', { name: t('page.G0_2.move') })).toBeEnabled();
    expect(first).toHaveAttribute('data-active', 'true');
  });

  it('끌어다 놓기: 고르지 않은 동은 그 동만, 고른 동을 끌면 고른 동 전부 옮기고 고른 표시를 지운다(#26~#28)', async () => {
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    await userEvent.click(screen.getByRole('button', { name: t('page.G0_2.add') }));
    const target = () => cards()[cards().length - 1] as HTMLElement;
    expect(target()).toHaveAttribute('data-new', 'true');
    expect(within(target()).getByText(t('page.G0_2.dropEmpty'))).toBeInTheDocument();
    // 지우기는 빈 새 생활권만 켜진다
    expect(within(target()).getByRole('button', { name: t('page.G0_2.delete') })).toBeEnabled();
    const dongCode = (box: HTMLElement) =>
      (box.closest('li') as HTMLElement).textContent?.match(/\d{10}/)?.[0] ??
      box.getAttribute('aria-label') ??
      '';
    const drop = (code: string) =>
      fireEvent.drop(target(), { dataTransfer: { getData: () => code } });

    // 1) 고르지 않은 동 하나
    const second = cards()[1] as HTMLElement;
    const one = within(second).getAllByRole('checkbox')[0] as HTMLElement;
    const oneCode = dongCode(one);
    drop(oneCode);
    expect(within(target()).getAllByRole('checkbox')).toHaveLength(1);
    expect(screen.getByText(t('page.G0_2.dirty'))).toBeInTheDocument();

    // 2) 고른 동 둘 중 하나를 끌면 둘 다
    const first = cards()[0] as HTMLElement;
    const boxes = within(first).getAllByRole('checkbox');
    const pickedBoxes = boxes.slice(0, Math.min(2, boxes.length));
    for (const b of pickedBoxes) await userEvent.click(b);
    drop(dongCode(pickedBoxes[0] as HTMLElement));
    expect(within(target()).getAllByRole('checkbox')).toHaveLength(1 + pickedBoxes.length);
    expect(screen.getByTestId('move-toolbar')).toHaveTextContent(
      t('page.G0_2.selectedCount', { n: '0' }),
    );
  });

  it('저장 줄: 생활권 저장 · 안내 · 변경 표시, 읽기 전용이면 꺼지고 이유를 보인다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem('sa.token.role', 'read');
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    const bar = screen.getByTestId('save-bar');
    const save = within(bar).getByRole('button', { name: t('page.G0_2.save') });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute('title', t('auth.readOnlyHint'));
    expect(bar).toHaveTextContent(t('auth.readOnlyHint'));
    // 동이 남은 카드의 지우기는 꺼지고 이유가 title
    const del = within(cards()[0] as HTMLElement).getByRole('button', {
      name: t('page.G0_2.delete'),
    });
    expect(del).toBeDisabled();
    expect(del).toHaveAttribute('title', t('page.G0_2.deleteDisabled'));
  });

  it('저장 → 저장 줄 아래 발행 진행(쓰기 토큰)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    const rec = recordRequests();
    renderRoute('/regions/1/living-areas');
    await screen.findAllByRole('textbox', { name: t('page.G0_2.areaName') });
    const bar = screen.getByTestId('save-bar');
    expect(bar).toHaveTextContent(t('page.G0_2.saveNote'));
    const first = cards()[0] as HTMLElement;
    const name = within(first).getByRole('textbox', { name: t('page.G0_2.areaName') });
    await userEvent.type(name, ' 2');
    expect(within(bar).getByText(t('page.G0_2.dirty'))).toBeInTheDocument();
    await userEvent.click(within(bar).getByRole('button', { name: t('page.G0_2.save') }));
    await waitFor(() => expect(matching(rec.requests, 'PUT', '/living-areas')).toHaveLength(1));
    expect(await screen.findByTestId('publish-job')).toBeInTheDocument();
    expect(await screen.findByText(t('page.G0_2.saved'))).toBeInTheDocument();
    expect(within(bar).queryByText(t('page.G0_2.dirty'))).toBeNull();
    rec.stop();
  });

  it('지역 범위: ? 설명 · 마지막 하나는 뺄 수 없다는 title · 후보 없음 문구', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    await userEvent.click(within(panel).getByRole('button', { name: t('page.G0_2.expand.help') }));
    expect(within(panel).getByRole('note')).toHaveTextContent(t('page.G0_2.expand.helpBody'));
    const current = within(panel).getByRole('list', { name: t('page.G0_2.expand.current') });
    let items = within(current).getAllByRole('listitem');
    while (items.length > 1) {
      await userEvent.click(within(items[0] as HTMLElement).getByRole('button'));
      items = within(current).getAllByRole('listitem');
    }
    expect(within(items[0] as HTMLElement).getByRole('button')).toHaveAttribute(
      'title',
      t('page.G0_2.expand.removeLast'),
    );
    server.use(http.get(mswPath('/regions/resolve'), () => HttpResponse.json([])));
    await userEvent.type(within(panel).getByLabelText(t('page.G0_2.expand.search')), '없는곳');
    expect(await within(panel).findByText(t('page.G0_2.expand.noCandidates'))).toBeInTheDocument();
  });

  it('지역 범위 저장 → 토스트 · 새로 추가 표시 · 잡 안내 · 끝나면 다시 읽는다는 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    renderRoute('/regions/1/living-areas');
    const panel = await screen.findByRole('region', { name: t('page.G0_2.expand.title') });
    await userEvent.type(within(panel).getByLabelText(t('page.G0_2.expand.search')), '검단');
    const list = await within(panel).findByRole('list', {
      name: t('page.G0_2.expand.candidates'),
    });
    const addable = within(list)
      .getAllByRole('button', { name: t('page.G0_2.expand.add') })
      .find((b) => !(b as HTMLButtonElement).disabled)!;
    await userEvent.click(addable);
    const current = within(panel).getByRole('list', { name: t('page.G0_2.expand.current') });
    const added = current.querySelector('[data-added]') as HTMLElement;
    expect(added).toHaveTextContent(t('page.G0_2.expand.added'));
    await userEvent.click(
      within(panel).getByRole('button', { name: t('page.G0_2.expand.submit') }),
    );
    expect(await screen.findByText(t('page.G0_2.expand.saved'))).toBeInTheDocument();
    const job = await within(panel).findByTestId('expand-job');
    expect(job).toHaveTextContent(t('page.G0_2.expand.jobHint'));
    expect(job).toHaveTextContent(t('page.G0_2.expand.jobDoneHint'));
  });
});
