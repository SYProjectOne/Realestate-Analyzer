/**
 * R11-SETUP(D30, 목업 RegionNew): G0 '1 찾기 → 2 확인·이름 → 3 분석 시작 → 4 진행' 흐름의 새 모양과 문구.
 * 지금 동작(디바운스·고급 조회 기간·검사·잡 진행)은 region-new.test.tsx · r4fe9.test.tsx 가 지킨다.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function pick(text = '검단') {
  renderRoute('/regions/new');
  await userEvent.type(await screen.findByRole('searchbox', { name: t('page.G0.search') }), text);
  return screen.findByRole('list', { name: t('page.G0.candidates') });
}

describe('R11 G0 지역 입력 — 목업 RegionNew', () => {
  it('머리: 현재 위치 줄 · 질문형 h1 · 안내 · 진행 순서 4단계(첫 단계가 지금 단계)', async () => {
    renderRoute('/regions/new');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G0.title') }),
    ).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: t('page.G0.crumbLabel') })).toHaveTextContent(
      t('page.G0.crumb'),
    );
    expect(screen.getByText(t('page.G0.intro'))).toBeInTheDocument();
    const steps = within(screen.getByRole('list', { name: t('page.G0.stepsLabel') })).getAllByRole(
      'listitem',
    );
    expect(steps.map((s) => s.querySelector('b')?.textContent)).toEqual([
      t('page.G0.steps.find'),
      t('page.G0.steps.confirm'),
      t('page.G0.steps.start'),
      t('page.G0.steps.progress'),
    ]);
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    expect(steps[1]).toHaveTextContent(t('page.G0.steps.confirmNone'));
    // 고르기 전: 2단계 칸은 '고른 곳이 없어요'
    expect(screen.getByText(t('page.G0.noneSelected'))).toBeInTheDocument();
  });

  it('후보: 개수 · 쉬운 일치 정도 · 종류·일치 범례 · 법정동/행정동 설명(?) — 고르면 강조와 2단계 "n곳 골랐어요"', async () => {
    const list = await pick();
    const rows = within(list).getAllByRole('listitem');
    expect(screen.getByText(t('page.G0.candidateCount', { n: String(rows.length) }))).toBeVisible();
    expect(screen.getByText(t('page.G0.legend'))).toBeInTheDocument();
    expect(screen.getByText(t('page.G0.pickTitle'))).toBeInTheDocument();
    // 일치 정도는 목업 문구(정확 일치 → 이름이 같아요 …)
    const matches = list.querySelectorAll('[data-match]');
    for (const m of matches) {
      expect(m.textContent).toBe(t(`page.G0.match.${m.getAttribute('data-match')}` as never));
    }
    // ? 설명
    const help = screen.getByRole('button', { name: t('page.G0.dongHelp.button') });
    expect(help).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(help);
    expect(screen.getByRole('note')).toHaveTextContent(t('page.G0.dongHelp.body'));
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('note')).toBeNull();

    await userEvent.click(within(list).getAllByRole('checkbox')[0] as HTMLElement);
    expect(within(list).getAllByRole('listitem')[0]?.querySelector('label')).toHaveAttribute(
      'data-checked',
      'true',
    );
    const steps = within(screen.getByRole('list', { name: t('page.G0.stepsLabel') })).getAllByRole(
      'listitem',
    );
    expect(steps[1]).toHaveTextContent(t('page.G0.steps.confirmHint', { n: '1' }));
    expect(screen.getByText(t('page.G0.chipHint'))).toBeInTheDocument();
  });

  it("시작 버튼에 이름이 들어간다('{이름}' 분석 시작) · 꺼진 이유 · 공개 자료 안내", async () => {
    const list = await pick();
    await userEvent.click(within(list).getAllByRole('checkbox')[0] as HTMLElement);
    const start = screen.getByRole('button', { name: t('page.G0.start') });
    expect(start).toBeDisabled();
    expect(screen.getByTestId('g0-start-disabled')).toHaveTextContent(t('page.G0.startDisabled'));
    expect(screen.getByText(t('page.G0.startNote'))).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(t('page.G0.name')), '내 지역');
    expect(start).toHaveAccessibleName(t('page.G0.startNamed', { name: '내 지역' }));
    expect(start).toBeEnabled();
    expect(screen.queryByTestId('g0-start-disabled')).toBeNull();
    expect(screen.getByText(t('page.G0.nameHint'))).toBeInTheDocument();
  });

  it('4 진행 상황: 서버 지역 이름으로 머리말 · 끝나기 전 안내, 끝나면 "홈으로" 링크(?region=) · 생활권 링크는 시작 직후부터', async () => {
    const list = await pick();
    await userEvent.click(within(list).getAllByRole('checkbox')[0] as HTMLElement);
    await userEvent.type(screen.getByLabelText(t('page.G0.name')), '내 지역');
    await userEvent.click(
      screen.getByRole('button', { name: t('page.G0.startNamed', { name: '내 지역' }) }),
    );
    const progress = await screen.findByTestId('g0-progress');
    // 잠깐 뜨는 알림: 시작
    expect(await screen.findByText(t('page.G0.started'))).toBeInTheDocument();
    expect(within(progress).getByRole('heading', { level: 2 })).toHaveTextContent(
      t('page.G0.progressTitle'),
    );
    const living = within(progress).getByRole('link', { name: t('page.G0.goLivingAreas') });
    expect(living.getAttribute('href')).toMatch(/^\/regions\/[^/]+\/living-areas$/);
    // 잡이 끝나면 머리말이 '분석이 끝났어요'로, 홈 링크가 나온다(목 잡은 곧 done)
    const home = await within(progress).findByRole('link', { name: t('page.G0.goDashboard') });
    expect(home.getAttribute('href')).toMatch(/^\/\?region=/);
    expect(within(progress).getByTestId('g0-progress-head')).toHaveTextContent(t('page.G0.done'));
    // 잠깐 뜨는 알림: 끝(머리말 + 토스트)
    await waitFor(() => expect(screen.getAllByText(t('page.G0.done')).length).toBeGreaterThan(1));
    const steps = within(screen.getByRole('list', { name: t('page.G0.stepsLabel') })).getAllByRole(
      'listitem',
    );
    await waitFor(() => expect(steps[3]).toHaveAttribute('data-step-state', 'done'));
  });

  it('검색 실패는 role=alert 오류 줄, 후보가 없으면 다른 이름을 넣어 보라는 안내', async () => {
    server.use(
      http.get(mswPath('/regions/resolve'), () =>
        HttpResponse.json({ code: 'internal', detail: '검색 서버 오류' }, { status: 500 }),
      ),
    );
    renderRoute('/regions/new');
    await userEvent.type(
      await screen.findByRole('searchbox', { name: t('page.G0.search') }),
      '검단',
    );
    expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent(
      /검색 서버 오류|500/,
    );
    server.resetHandlers();
    server.use(http.get(mswPath('/regions/resolve'), () => HttpResponse.json([])));
    await userEvent.clear(screen.getByRole('searchbox', { name: t('page.G0.search') }));
    await userEvent.type(screen.getByRole('searchbox', { name: t('page.G0.search') }), '없는곳');
    expect(await screen.findByText(t('page.G0.noCandidates'))).toBeInTheDocument();
  });

  it("찾는 동안 '찾는 중…'(role=status)", async () => {
    server.use(
      http.get(mswPath('/regions/resolve'), async () => {
        await delay(400);
        return HttpResponse.json([]);
      }),
    );
    renderRoute('/regions/new');
    await userEvent.type(
      await screen.findByRole('searchbox', { name: t('page.G0.search') }),
      '검단',
    );
    expect(await screen.findByRole('status')).toHaveTextContent(t('page.G0.searching'));
    expect(await screen.findByText(t('page.G0.noCandidates'))).toBeInTheDocument();
  });

  it('읽기 전용 토큰이면 시작 버튼이 꺼지고 그 이유를 보인다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem('sa.token.role', 'read');
    const list = await pick();
    await userEvent.click(within(list).getAllByRole('checkbox')[0] as HTMLElement);
    await userEvent.type(screen.getByLabelText(t('page.G0.name')), '내 지역');
    const start = screen.getByRole('button', {
      name: t('page.G0.startNamed', { name: '내 지역' }),
    });
    expect(start).toBeDisabled();
    expect(start).toHaveAttribute('title', t('auth.readOnlyHint'));
    expect(screen.getByTestId('g0-start-disabled')).toHaveTextContent(t('auth.readOnlyHint'));
  });
});
