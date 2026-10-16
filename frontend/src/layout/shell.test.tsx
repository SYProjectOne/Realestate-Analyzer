/**
 * R11-SHELL(D30-2·D30-4, 목업 Shell 보드): 머리줄·하단 메뉴·알림 띠·열쇠 버튼·화면 밝기·출처 서랍 머리.
 * 대응표 `docs/design/ui-benchmark/50-mockup/coverage/coverage-Shell.md` 의 '테스트' 칸이 이 파일의 테스트 이름을 가리킨다.
 */
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import {
  ROLE_STORAGE_KEY,
  TAB_REASON_KEY,
  TAB_ROLE_KEY,
  TAB_TOKEN_KEY,
  TOKEN_STORAGE_KEY,
} from '@/api/auth';
import type { Region, Snapshot } from '@/api/types';
import { t } from '@/i18n';
import ko from '@/i18n/ko.json';
import { THEME_STORAGE_KEY } from '@/lib/theme';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { MOCK_DEGRADED_KEY, resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const GLOBAL = 'region=1&scenario=B';

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

function mockMobile(): () => void {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    ...original(query),
    matches: query === MOBILE_QUERY,
  })) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

describe('R11 머리줄(D30-2)', () => {
  it('앱 이름 "청약 한눈에"는 표지와 함께 홈 링크이고 지역·상황 쿼리를 싣는다', async () => {
    renderRoute(`/complexes?${GLOBAL}`);
    await screen.findByRole('heading', { level: 1 });
    expect(t('app.name')).toBe('청약 한눈에');
    const home = screen.getByTestId('app-home');
    expect(home).toHaveTextContent(t('app.name'));
    expect(home.getAttribute('href')).toBe(`/?${GLOBAL}`);
    expect(home.querySelector('svg')).not.toBeNull();
    // 머리줄은 화면 꼭대기에 붙는다(데스크톱 sticky, 휴대폰은 하단 메뉴가 대신)
    expect(screen.getByTestId('app-header').className).toContain('sticky');
    // 주 메뉴와 작은 메뉴 사이 세로 구분선(장식)
    const nav = screen.getByRole('navigation', { name: t('nav.label') });
    expect(nav.querySelector('span[aria-hidden].w-px')).not.toBeNull();
  });

  it('메뉴 이름(D30-2): 홈·단지 찾기·비교하기·지역 시장·보고서 │ 내 조건(시나리오)·데이터·운영 · 용어 사전', async () => {
    renderRoute('/');
    const nav = await screen.findByRole('navigation', { name: t('nav.label') });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((a) => a.textContent),
    ).toEqual([
      '홈',
      '단지 찾기',
      '비교하기',
      '지역 시장',
      '보고서',
      '내 조건(시나리오)',
      '데이터·운영',
      '용어 사전',
    ]);
    // 라우트 경로는 그대로(D30-2)
    expect(
      within(nav)
        .getAllByRole('link')
        .map((a) => new URL(a.getAttribute('href') ?? '', 'http://x').pathname),
    ).toEqual([
      '/',
      '/complexes',
      '/compare',
      '/market',
      '/reports',
      '/scenario',
      '/ops',
      '/glossary',
    ]);
  });

  it('지금 화면 메뉴만 aria-current=page(강조)', async () => {
    renderRoute('/complexes');
    const nav = await screen.findByRole('navigation', { name: t('nav.label') });
    const current = within(nav)
      .getAllByRole('link')
      .filter((a) => a.getAttribute('aria-current') === 'page')
      .map((a) => a.textContent);
    expect(current).toEqual([t('nav.G2')]);
  });

  it('윗줄(표지·메뉴·접속 열쇠·화면) 다음 아랫줄(지역·기준일·상황)', async () => {
    renderRoute('/');
    const nav = await screen.findByRole('navigation', { name: t('nav.label') });
    const group = screen.getByTestId('header-selectors');
    expect(nav.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(group).getByLabelText(t('header.region'))).toBeInTheDocument();
    expect(within(group).getByLabelText(t('header.snapshot'))).toBeInTheDocument();
    expect(
      await within(group).findByRole('radiogroup', { name: t('header.scenario') }),
    ).toBeInTheDocument();
    // 데스크톱: 열쇠·화면은 윗줄 오른쪽 끝(아랫줄이 두 줄로 접히지 않게 — G2 첫 화면 행 수)
    const tools = screen.getByTestId('header-tools');
    expect(tools.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(tools).getByTestId('token-button')).toBeInTheDocument();
    expect(
      within(tools).getByRole('button', { name: new RegExp(`^${t('header.theme')}: `) }),
    ).toBeInTheDocument();
  });

  it('상황 토글 묶음 앞에 이름 "상황"이 보이고 → 키로 다음 상황(URL ?scenario=)', async () => {
    const { router } = renderRoute('/');
    const group = await screen.findByRole('radiogroup', { name: t('header.scenario') });
    expect(within(group).getByText(t('header.scenario'))).toBeInTheDocument();
    const radios = within(group).getAllByRole('radio');
    expect(radios.length).toBeGreaterThan(1);
    const first = radios.find((r) => r.getAttribute('aria-checked') === 'true') as HTMLElement;
    first.focus();
    await userEvent.keyboard('{ArrowRight}');
    await waitFor(() => expect(router.state.location.search).toContain('scenario='));
  });

  it('접속 열쇠 버튼 네 상태(SH-14): 없음·쓰기 가능·읽기 전용·설정됨', async () => {
    const cases: [string | null, string | null, string][] = [
      [null, null, t('auth.state.none')],
      ['tok-w', 'write', t('auth.state.write')],
      ['tok-r', 'read', t('auth.state.read')],
      ['tok-u', null, t('auth.state.unknown')],
    ];
    expect(cases.map((c) => c[2])).toEqual(['없음', '쓰기 가능', '읽기 전용', '설정됨']);
    for (const [token, role, text] of cases) {
      window.localStorage.clear();
      if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
      if (role) window.localStorage.setItem(ROLE_STORAGE_KEY, role);
      renderRoute('/glossary');
      const button = await screen.findByTestId('token-button');
      expect(button).toHaveTextContent(`${t('auth.button')} · ${text}`);
      expect(button).toHaveAttribute('aria-haspopup', 'dialog');
      cleanup();
    }
  });

  it('화면 밝기 버튼: "화면: 밝게" ↔ "화면: 어둡게"(aria-pressed) · html.dark · sa.theme 기억', async () => {
    renderRoute('/glossary');
    const button = await screen.findByRole('button', {
      name: `${t('header.theme')}: ${t('header.themeLight')}`,
    });
    expect(button).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(button);
    expect(
      screen.getByRole('button', { name: `${t('header.theme')}: ${t('header.themeDark')}` }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('스킵 링크는 main#main 을 가리키고, 본문은 main 랜드마크', async () => {
    renderRoute('/glossary');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('link', { name: t('app.skipToContent') })).toHaveAttribute(
      'href',
      '#main',
    );
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main');
  });

  it('바닥 문구는 D7 원문 그대로(투자 권유 아님 · 상대 비교)', async () => {
    renderRoute('/glossary');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('contentinfo')).toHaveTextContent('투자 권유 아님 · 상대 비교');
  });
});

describe('R11 선택칸(목업 §1, SH-10)', () => {
  it('지역이 없으면 "지역 없음" + 지역 추가, 기준일이 없으면 "기준일 없음"으로 칸이 꺼진다', async () => {
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([])),
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([])),
    );
    renderRoute('/glossary');
    const region = await screen.findByLabelText(t('header.region'));
    expect(
      within(region).getByRole('option', { name: t('header.regionNone') }),
    ).toBeInTheDocument();
    expect(within(region).getByRole('option', { name: t('header.regionAdd') })).toBeInTheDocument();
    const snapshot = screen.getByLabelText(t('header.snapshot'));
    expect(
      within(snapshot).getByRole('option', { name: t('header.snapshotNone') }),
    ).toBeInTheDocument();
    expect(snapshot).toBeDisabled();
    expect(t('header.snapshotNone')).toBe('기준일 없음');
  });

  it('지역을 바꾸면 ?region= 이 바뀌고 기준일은 그 지역 최신으로(?snapshot= 을 뺀다, #29)', async () => {
    const regions = await example<Region[]>('/regions');
    const first = regions[0] as Region;
    const second = { ...first, id: 999, name: `${first.name}-2` };
    server.use(http.get(mswPath('/regions'), () => HttpResponse.json([first, second])));
    const { router } = renderRoute(`/glossary?region=${String(first.id)}&snapshot=1`);
    const region = await screen.findByLabelText(t('header.region'));
    await within(region).findByRole('option', { name: second.name });
    await userEvent.selectOptions(region, String(second.id));
    await waitFor(() => expect(router.state.location.search).toContain('region=999'));
    expect(router.state.location.search).not.toContain('snapshot=');
  });

  it('상황 목록이 늦게 와도 자리를 미리 잡는다(CLS, #42)', async () => {
    let release: () => void = () => {};
    const scenarios = await example<unknown[]>('/scenarios');
    server.use(
      http.get(
        mswPath('/scenarios'),
        () =>
          new Promise<Response>((resolve) => {
            release = () => resolve(HttpResponse.json(scenarios));
          }),
      ),
    );
    renderRoute('/glossary');
    await screen.findByRole('heading', { level: 1 });
    const bar = screen.getByTestId('header-selectors');
    expect(within(bar).queryByRole('radiogroup')).toBeNull();
    expect(bar.querySelector('span[aria-hidden].bg-chip')).not.toBeNull();
    release();
    expect(
      await within(bar).findByRole('radiogroup', { name: t('header.scenario') }),
    ).toBeInTheDocument();
  });
});

describe('R11 개발 전용 차트 갤러리(/__charts, #291·#292)', () => {
  it('머리줄 안에서 갤러리 제목을 그린다(목업에 그리지 않음 — 지금 그대로)', async () => {
    renderRoute('/__charts');
    expect(
      await screen.findByRole(
        'heading',
        { level: 1, name: t('chart.gallery.title') },
        { timeout: 15_000 },
      ),
    ).toBeInTheDocument();
  }, 30_000);
});

describe('R11 휴대폰 머리줄·하단 메뉴(D30-4, SH-19)', () => {
  it('머리줄에는 메뉴가 없고 하단 고정 바에 홈·단지 찾기·용어 사전(쿼리 유지)', async () => {
    const restore = mockMobile();
    try {
      renderRoute(`/?${GLOBAL}`);
      const bottom = await screen.findByTestId('bottom-nav');
      expect(screen.getAllByRole('navigation')).toEqual([bottom]);
      const links = within(bottom).getAllByRole('link');
      expect(links.map((a) => a.textContent)).toEqual(['홈', '단지 찾기', '용어 사전']);
      for (const link of links) {
        expect(new URL(link.getAttribute('href') ?? '', 'http://x').search).toBe(`?${GLOBAL}`);
      }
      expect(links[0]).toHaveAttribute('aria-current', 'page');
      expect(within(screen.getByTestId('app-header')).queryByRole('navigation')).toBeNull();
    } finally {
      restore();
    }
  });

  it("'설정'은 처음에 접혀 있고 안에 접속 열쇠·화면 버튼, 바닥 문구는 하단 바 위", async () => {
    const restore = mockMobile();
    try {
      renderRoute('/');
      const summary = await screen.findByText(t('header.settings'), { selector: 'summary' });
      const details = summary.closest('details') as HTMLElement;
      expect(details).not.toHaveAttribute('open');
      expect(details).toContainElement(screen.getByTestId('token-button'));
      expect(
        within(details).getByRole('button', { name: new RegExp(`^${t('header.theme')}: `) }),
      ).toBeInTheDocument();
      expect(screen.getByRole('contentinfo').className).toContain('mobile:bottom-');
    } finally {
      restore();
    }
  });

  it('휴대폰 칩 문구(SH-9): 보기만 / 컴퓨터에서 — 없는 주소도 보기만', async () => {
    expect(t('app.mobileReadOnly')).toBe('휴대폰에서는 보기만 할 수 있어요');
    expect(t('app.mobileUnsupported')).toBe('이 화면은 컴퓨터에서 써 주세요');
    const restore = mockMobile();
    try {
      renderRoute('/no-such-page');
      expect(await screen.findByText(t('app.mobileReadOnly'))).toBeInTheDocument();
      cleanup();
      renderRoute('/market');
      expect(await screen.findByText(t('app.mobileUnsupported'))).toBeInTheDocument();
    } finally {
      restore();
    }
  });
});

describe('R11 알림 띠(목업 §2, SH-2~SH-9)', () => {
  it('문구는 원래 뜻을 되살린다(미판정 모드·발행 순간 값·다른 탭·API_TOKEN)', () => {
    expect(t('app.degraded')).toContain('미판정 모드');
    expect(t('app.degraded')).toContain('이전에 저장한 판정 결과만');
    expect(t('app.degradedSnapshot')).toContain('미판정 모드');
    expect(t('app.degradedSnapshot')).not.toContain('못 모았');
    expect(t('app.backfilled', { date: '2026-10-13' })).toContain('발행 순간 값과 다를 수 있음');
    expect(t('app.backfilled', { date: '2026-10-13' })).toContain('2026-10-13');
    expect(t('auth.pinnedBanner')).toContain('다른 탭');
    expect(t('auth.pinnedBanner')).toContain('원래 열쇠를 그대로');
    expect(t('auth.readOnlyBanner')).toContain('API_TOKEN');
    expect(t('auth.readOnlyBanner')).not.toContain('공유받은');
    expect(t('job.watchExpired')).toContain('30분');
  });

  it('판정기 장애(/health degraded) → role=alert 주의 띠 + 경고 아이콘(SH-2)', async () => {
    window.localStorage.setItem(MOCK_DEGRADED_KEY, '1');
    renderRoute('/glossary');
    const banner = await screen.findByTestId('degraded-banner');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner).toHaveAttribute('data-banner-tone', 'warn');
    expect(banner).toHaveAttribute('data-degraded', 'judge');
    expect(banner).toHaveTextContent(t('app.degraded'));
    expect(banner.querySelector('svg[aria-hidden]')).not.toBeNull();
  });

  it('기준일 스냅샷 degraded 는 다른 문구·아이콘 없음(SH-3)', async () => {
    const list = await example<Snapshot[]>('/regions/1/snapshots');
    server.use(
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(list.map((s) => ({ ...s, degraded: true }))),
      ),
    );
    renderRoute('/glossary?region=1');
    const banner = await screen.findByTestId('degraded-banner');
    expect(banner).toHaveAttribute('data-degraded', 'snapshot');
    expect(banner).toHaveTextContent(t('app.degradedSnapshot'));
    expect(banner.querySelector('svg')).toBeNull();
  });

  it('지역 처음 분석 중/실패 띠: 굵은 한 줄 + 데이터·운영 링크(/ops?region=)', async () => {
    const regions = await example<Region[]>('/regions');
    const first = regions[0] as Region;
    server.use(
      http.get(mswPath('/regions'), () =>
        HttpResponse.json([{ ...first, status: 'bootstrapping' }]),
      ),
    );
    renderRoute('/glossary');
    let banner = await screen.findByTestId('region-loading-banner');
    expect(banner).toHaveAttribute('data-banner-tone', 'info');
    expect(within(banner).getByText(t('app.regionBootstrapping'))).toBeInTheDocument();
    expect(
      within(banner).getByRole('link', { name: t('app.regionBootstrappingLink') }),
    ).toHaveAttribute('href', `/ops?region=${String(first.id)}`);
    cleanup();
    server.use(
      http.get(mswPath('/regions'), () => HttpResponse.json([{ ...first, status: 'failed' }])),
    );
    renderRoute('/glossary');
    banner = await screen.findByTestId('region-loading-banner');
    expect(banner).toHaveAttribute('data-banner-tone', 'warn');
    expect(within(banner).getByText(t('app.regionFailed'))).toBeInTheDocument();
    expect(
      within(banner).getByRole('link', { name: t('app.regionFailedLink') }),
    ).toBeInTheDocument();
  });

  async function serveAllBanners() {
    window.localStorage.setItem(MOCK_DEGRADED_KEY, '1');
    const regions = await example<Region[]>('/regions');
    const list = await example<Snapshot[]>('/regions/1/snapshots');
    server.use(
      http.get(mswPath('/regions'), () =>
        HttpResponse.json(regions.map((r) => ({ ...r, status: 'bootstrapping' }))),
      ),
      http.get(mswPath('/regions/:id/snapshots'), () =>
        HttpResponse.json(list.map((s) => ({ ...s, backfilled_at: '2026-10-13T01:00:00Z' }))),
      ),
    );
  }

  const order = (ids: string[]) => {
    const stack = screen.getByTestId('banner-stack');
    return [...stack.children]
      .map((el) => el.getAttribute('data-testid') ?? el.getAttribute('role'))
      .filter((id): id is string => !!id && ids.includes(id));
  };

  it('띠 순서(#8): 판정기 장애 → 지역 처음 분석 → 다시 계산한 값 → 읽기 전용', async () => {
    await serveAllBanners();
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-r');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    renderRoute('/glossary?region=1');
    await screen.findByTestId('degraded-banner');
    await screen.findByTestId('region-loading-banner');
    await screen.findByTestId('backfilled-banner');
    await screen.findByTestId('readonly-banner');
    const ids = [
      'degraded-banner',
      'region-loading-banner',
      'backfilled-banner',
      'readonly-banner',
    ];
    expect(order(ids)).toEqual(ids);
  });

  it('띠 순서(#8): … 다시 계산한 값 → 탭 고정(SH-5) — 새 열쇠 사용 버튼', async () => {
    await serveAllBanners();
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-share');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    window.sessionStorage.setItem(TAB_TOKEN_KEY, 'tok-mine');
    window.sessionStorage.setItem(TAB_ROLE_KEY, 'write');
    window.sessionStorage.setItem(TAB_REASON_KEY, 'pinned');
    try {
      renderRoute('/glossary?region=1');
      const pinned = await screen.findByTestId('token-pinned-banner');
      await screen.findByTestId('backfilled-banner');
      const ids = [
        'degraded-banner',
        'region-loading-banner',
        'backfilled-banner',
        'token-pinned-banner',
      ];
      expect(order(ids)).toEqual(ids);
      expect(
        within(pinned).getByRole('button', { name: t('auth.useNewToken') }),
      ).toBeInTheDocument();
    } finally {
      window.sessionStorage.clear();
    }
  });

  it('읽기 전용 띠(SH-6): 열쇠 바꾸기 → 열쇠 창(머리줄 버튼으로 연 이유)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-r');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    renderRoute('/glossary');
    const banner = await screen.findByTestId('readonly-banner');
    expect(banner).toHaveTextContent(t('auth.readOnlyBanner'));
    await userEvent.click(within(banner).getByRole('button', { name: t('auth.change') }));
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    expect(within(dialog).getByText(t('auth.reason.manual'))).not.toHaveAttribute('role');
  });
});

describe('R11 열쇠 창(SH-13·SH-15)', () => {
  it('뒤 화면 어둡게(aria-modal) · 안내(API_TOKEN·READONLY_TOKEN·이 브라우저에만) · 입력칸 포커스 · Esc 로 닫힘', async () => {
    renderRoute('/glossary');
    await userEvent.click(await screen.findByTestId('token-button'));
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    expect(t('auth.title')).toBe('접속 열쇠 넣기');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByTestId('token-backdrop')).toContainElement(dialog);
    for (const word of ['API_TOKEN', 'READONLY_TOKEN', '이 브라우저에만']) {
      expect(t('auth.intro')).toContain(word);
    }
    expect(within(dialog).getByText(t('auth.intro'))).toBeInTheDocument();
    expect(within(dialog).getByLabelText(t('auth.label'))).toHaveFocus();
    // 저장된 열쇠가 없으면 '지우기' 없음
    expect(within(dialog).queryByRole('button', { name: t('auth.clear') })).toBeNull();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: t('auth.title') })).toBeNull();
  });

  it('비어 있으면 "열쇠를 넣어 주세요"(role=alert), 확인 중에는 버튼이 꺼지고 "열쇠 확인 중…"', async () => {
    let release: () => void = () => {};
    server.use(
      http.get(
        mswPath('/regions'),
        () =>
          new Promise<Response>((resolve) => {
            release = () => resolve(HttpResponse.json([]));
          }),
      ),
    );
    renderRoute('/glossary');
    await userEvent.click(await screen.findByTestId('token-button'));
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    await userEvent.click(within(dialog).getByRole('button', { name: t('auth.save') }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent(t('auth.empty'));
    await userEvent.type(within(dialog).getByLabelText(t('auth.label')), 'tok-x');
    await userEvent.click(within(dialog).getByRole('button', { name: t('auth.save') }));
    const checking = await within(dialog).findByRole('button', { name: t('auth.checking') });
    expect(checking).toBeDisabled();
    release();
  });

  it('열쇠 저장·지움 알림 문구(SH-15)는 해요체', () => {
    expect(t('auth.savedWrite')).toBe('쓰기 열쇠를 저장했어요');
    expect(t('auth.savedRead')).toContain('저장·실행 버튼은 꺼져요');
    expect(t('auth.cleared')).toBe('저장한 열쇠를 지웠어요');
    expect(t('auth.notPersisted')).toContain('이 탭에서만');
  });
});

describe('R11 열쇠 창 덧붙임(SH-13)', () => {
  it('"열쇠 보이기"를 켜면 입력칸이 글자로 보인다', async () => {
    renderRoute('/glossary');
    await userEvent.click(await screen.findByTestId('token-button'));
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    const input = within(dialog).getByLabelText(t('auth.label'));
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('autocomplete', 'off');
    await userEvent.click(within(dialog).getByRole('checkbox', { name: t('auth.show') }));
    expect(input).toHaveAttribute('type', 'text');
  });

  it('확인 요청이 실패하면 "열쇠를 확인하지 못했어요: …"(role=alert)', async () => {
    server.use(http.get(mswPath('/regions'), () => HttpResponse.error()));
    renderRoute('/glossary');
    await userEvent.click(await screen.findByTestId('token-button'));
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    await userEvent.type(within(dialog).getByLabelText(t('auth.label')), 'tok-x');
    await userEvent.click(within(dialog).getByRole('button', { name: t('auth.save') }));
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent ?? '').toContain(t('auth.checkError', { detail: '' }));
  });
});

describe('R11 기준일 없음(§7)', () => {
  it('발행 기준일이 없으면 "아직 기준일이 없어요"', async () => {
    const regions = await example<Region[]>('/regions');
    server.use(
      http.get(mswPath('/regions'), () =>
        HttpResponse.json(regions.map((r) => ({ ...r, status: 'ready', latest_snapshot: null }))),
      ),
      http.get(mswPath('/regions/:id/snapshots'), () => HttpResponse.json([])),
    );
    renderRoute('/');
    expect(await screen.findByText(t('app.noSnapshot'))).toBeInTheDocument();
    expect(t('app.noSnapshot')).toContain('아직 기준일이 없어요');
  });
});

describe('R11 없는 주소(§9)', () => {
  it('"찾는 화면이 없어요" + 홈으로(쿼리 유지)', async () => {
    renderRoute(`/no-such-page?${GLOBAL}`);
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.notFound.title') }),
    ).toBeInTheDocument();
    expect(t('page.notFound.title')).toBe('찾는 화면이 없어요');
    expect(screen.getByTestId('not-found-home')).toHaveTextContent(t('page.notFound.home'));
    expect(screen.getByTestId('not-found-home').getAttribute('href')).toBe(`/?${GLOBAL}`);
  });
});

describe('R11 ko 이름 표(D30-2·D30-9)', () => {
  it('메뉴·용어 사전·접수 미정·공식 홈페이지 안내문 이름', () => {
    expect(ko.nav).toMatchObject({
      G1: '홈',
      G2: '단지 찾기',
      G4: '비교하기',
      G5: '내 조건(시나리오)',
      G6: '지역 시장',
      G7: '데이터·운영',
      G8: '보고서',
    });
    expect(ko.glossary.nav).toBe('용어 사전');
    expect(ko.intake.status.미정).toBe('접수 미정');
    expect(ko.page.common.changeField.official_popup_hash).toBe('공식 홈페이지 안내문');
  });
});
