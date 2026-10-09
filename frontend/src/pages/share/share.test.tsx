import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import {
  ROLE_STORAGE_KEY,
  TAB_REASON_KEY,
  TAB_ROLE_KEY,
  TAB_TOKEN_KEY,
  TOKEN_STORAGE_KEY,
} from '@/api/auth';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';
import { shareTokenFromHash } from './index';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const SHARE_TOKEN = 'q3Zt0w9mK1xR7bY2cV8nH4sL6dF5gJ0aP3eU1iO9tQw';

describe('M9 /share 라우트 — 공유 링크로 들어오기', () => {
  it('#<토큰> → 읽기 전용 토큰으로 저장 · 주소의 # 제거 · / 로 이동', async () => {
    const replace = vi.spyOn(window.history, 'replaceState');
    const { router } = renderRoute(`/share#${SHARE_TOKEN}`);
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(router.state.location.hash).toBe('');
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe(SHARE_TOKEN);
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('read');
    expect(replace).toHaveBeenCalled();
    const url = String(replace.mock.calls[0]?.[2] ?? '');
    expect(url).not.toContain('#');
    expect(url).not.toContain(SHARE_TOKEN);
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G1.title') }),
    ).toBeInTheDocument();
    // 읽기 전용 안내 배너
    expect(await screen.findByTestId('readonly-banner')).toBeInTheDocument();
  });

  it('토큰 없이 /share → 오류 안내, 저장하지 않는다', async () => {
    const { router } = renderRoute('/share');
    expect(await screen.findByRole('alert')).toHaveTextContent(t('page.share.missing'));
    expect(router.state.location.pathname).toBe('/share');
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});

describe('N-M7 공유 링크 — 잘못된 인코딩 · 저장된 쓰기 토큰 덮어쓰기 확인', () => {
  it('shareTokenFromHash: 잘못된 퍼센트 인코딩(URIError)은 throw 하지 않고 null', () => {
    expect(shareTokenFromHash('#%E0%A4%A')).toBeNull();
    expect(shareTokenFromHash('#%')).toBeNull();
    expect(shareTokenFromHash('#abc%20')).toBe('abc');
    expect(shareTokenFromHash('#')).toBeNull();
  });

  it('잘못된 인코딩의 /share#… → 토큰 없음 안내, 저장하지 않는다', async () => {
    const { router } = renderRoute('/share#%E0%A4%A');
    expect(await screen.findByRole('alert')).toHaveTextContent(t('page.share.missing'));
    expect(router.state.location.pathname).toBe('/share');
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  function storeWrite(role: 'write' | null = 'write') {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-mine');
    if (role) window.localStorage.setItem(ROLE_STORAGE_KEY, role);
  }

  async function confirmDialog() {
    return screen.findByRole('alertdialog', { name: t('page.share.confirmTitle') });
  }

  it('저장된 쓰기 토큰이 있으면 덮어쓰지 않고 확인 다이얼로그(기본 = 이 탭에서만)', async () => {
    storeWrite();
    const { router } = renderRoute(`/share#${SHARE_TOKEN}`);
    const dialog = await confirmDialog();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription(t('page.share.confirmBody'));
    const tabOnly = within(dialog).getByRole('button', { name: t('page.share.tabOnly') });
    expect(within(dialog).getByRole('button', { name: t('page.share.replace') })).toBeVisible();
    expect(within(dialog).getByRole('button', { name: t('page.share.cancel') })).toBeVisible();
    await waitFor(() => expect(tabOnly).toHaveFocus());
    // 아직 아무것도 바꾸지 않았다
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-mine');
    expect(router.state.location.pathname).toBe('/share');
  });

  it('"이 탭에서만 읽기 전용으로 보기" → sessionStorage 에만, 저장된 쓰기 토큰은 그대로', async () => {
    storeWrite();
    const { router } = renderRoute(`/share#${SHARE_TOKEN}`);
    const dialog = await confirmDialog();
    await userEvent.click(within(dialog).getByRole('button', { name: t('page.share.tabOnly') }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBe(SHARE_TOKEN);
    expect(window.sessionStorage.getItem(TAB_ROLE_KEY)).toBe('read');
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-mine');
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('write');
    expect(await screen.findByTestId('readonly-banner')).toBeInTheDocument();
  });

  it('"저장된 토큰을 공유 토큰으로 바꾸기" → localStorage 를 읽기 전용 공유 토큰으로', async () => {
    storeWrite();
    const { router } = renderRoute(`/share#${SHARE_TOKEN}`);
    const dialog = await confirmDialog();
    await userEvent.click(within(dialog).getByRole('button', { name: t('page.share.replace') }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe(SHARE_TOKEN);
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('read');
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
  });

  it('"취소" → 아무것도 적용하지 않고 홈으로', async () => {
    storeWrite();
    const replace = vi.spyOn(window.history, 'replaceState');
    const { router } = renderRoute(`/share#${SHARE_TOKEN}`);
    const dialog = await confirmDialog();
    await userEvent.click(within(dialog).getByRole('button', { name: t('page.share.cancel') }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-mine');
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('write');
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
    // 토큰이 주소창에 남지 않는다
    const urls = replace.mock.calls.map((c) => String(c[2] ?? ''));
    expect(urls.some((u) => u.includes(SHARE_TOKEN))).toBe(false);
    expect(replace).toHaveBeenCalled();
  });

  it('권한을 모르는 저장 토큰(role 없음)도 확인한다', async () => {
    storeWrite(null);
    renderRoute(`/share#${SHARE_TOKEN}`);
    expect(await confirmDialog()).toBeInTheDocument();
  });

  it('저장된 토큰이 읽기 전용이면 확인 없이 바로 적용(지금처럼 localStorage)', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-old-read');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    const { router } = renderRoute(`/share#${SHARE_TOKEN}`);
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe(SHARE_TOKEN);
  });
});

describe('N-M7 다른 탭 토큰 변경 배너', () => {
  it('다른 탭 변경으로 고정된 토큰이면 배너 + "새 토큰 사용" → 고정 해제', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-share');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    window.sessionStorage.setItem(TAB_TOKEN_KEY, 'tok-mine');
    window.sessionStorage.setItem(TAB_ROLE_KEY, 'write');
    window.sessionStorage.setItem(TAB_REASON_KEY, 'pinned');
    renderRoute('/');
    const banner = await screen.findByTestId('token-pinned-banner');
    expect(banner).toHaveTextContent(t('auth.pinnedBanner'));
    expect(screen.queryByTestId('readonly-banner')).toBeNull();
    await userEvent.click(within(banner).getByRole('button', { name: t('auth.useNewToken') }));
    await waitFor(() => expect(screen.queryByTestId('token-pinned-banner')).toBeNull());
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
    // 이제 저장소의 읽기 전용 토큰
    expect(await screen.findByTestId('readonly-banner')).toBeInTheDocument();
  });

  it('공유 링크를 이 탭에만 연 경우(reason share)는 배너가 없다', async () => {
    window.sessionStorage.setItem(TAB_TOKEN_KEY, 'tok-share');
    window.sessionStorage.setItem(TAB_ROLE_KEY, 'read');
    window.sessionStorage.setItem(TAB_REASON_KEY, 'share');
    renderRoute('/');
    expect(await screen.findByTestId('readonly-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('token-pinned-banner')).toBeNull();
  });
});

describe('M9 G7 공유 링크 패널', () => {
  async function panel() {
    return screen.findByRole('region', { name: t('page.G7.share.title') });
  }

  it('목록: 상태(활성·만료·회수)와 만료일', async () => {
    renderRoute('/ops');
    const section = await panel();
    const table = await within(section).findByRole('table', { name: t('page.G7.share.list') });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('가족 공유');
    expect(rows[0]).toHaveTextContent(t('page.G7.share.status.active'));
    expect(rows[0]).toHaveTextContent('2026-11-08');
    expect(rows[1]).toHaveTextContent(t('page.G7.share.status.expired'));
    // 만료된 링크는 회수 버튼이 없다
    expect(within(rows[1] as HTMLElement).queryByRole('button')).toBeNull();
  });

  it('발급 → POST /share-links {label} → 링크(<origin>/share#토큰)를 한 번만 보이고 복사', async () => {
    const rec = recordRequests();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    renderRoute('/ops');
    const section = await panel();
    await userEvent.type(within(section).getByLabelText(t('page.G7.share.label')), '검토 요청');
    await userEvent.click(within(section).getByRole('button', { name: t('page.G7.share.create') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/share-links')).toHaveLength(1));
    expect(await matching(rec.requests, 'POST', '/share-links')[0]?.body).toEqual({
      label: '검토 요청',
    });
    const created = await within(section).findByTestId('share-created');
    const url = `${window.location.origin}/share#${SHARE_TOKEN}`;
    expect(within(created).getByRole('textbox')).toHaveValue(url);
    expect(created).toHaveTextContent(t('page.G7.share.once'));
    expect(created).toHaveTextContent(t('page.G7.share.expires', { date: '2026-11-08' }));
    await userEvent.click(within(created).getByRole('button', { name: t('page.G7.share.copy') }));
    expect(writeText).toHaveBeenCalledWith(url);
    expect(await within(created).findByText(t('page.G7.share.copied'))).toBeInTheDocument();
    // 닫으면 토큰은 다시 볼 수 없다
    await userEvent.click(within(created).getByRole('button', { name: t('page.G7.share.done') }));
    expect(within(section).queryByTestId('share-created')).toBeNull();
    expect(section).not.toHaveTextContent(SHARE_TOKEN);
    rec.stop();
  });

  it('label 은 64자까지', async () => {
    renderRoute('/ops');
    const input = within(await panel()).getByLabelText(t('page.G7.share.label'));
    expect(input).toHaveAttribute('maxLength', '64');
  });

  it('label 이 비면 본문 label 없이(null) 보낸다', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const section = await panel();
    await userEvent.click(within(section).getByRole('button', { name: t('page.G7.share.create') }));
    await waitFor(() => expect(matching(rec.requests, 'POST', '/share-links')).toHaveLength(1));
    expect(await matching(rec.requests, 'POST', '/share-links')[0]?.body).toEqual({ label: null });
    rec.stop();
  });

  it('회수 → DELETE /share-links/{id}', async () => {
    const rec = recordRequests();
    renderRoute('/ops');
    const table = await within(await panel()).findByRole('table', {
      name: t('page.G7.share.list'),
    });
    await userEvent.click(within(table).getByRole('button', { name: t('page.G7.share.revoke') }));
    await waitFor(() => expect(matching(rec.requests, 'DELETE', '/share-links/3')).toHaveLength(1));
    rec.stop();
  });

  it('읽기 전용(공유) 토큰이면 패널이 없고 GET /share-links 도 부르지 않는다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-read');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    const rec = recordRequests();
    server.use(
      http.get(mswPath('/share-links'), () =>
        HttpResponse.json({ code: 'forbidden', detail: 'write token only' }, { status: 403 }),
      ),
    );
    renderRoute('/ops');
    await screen.findByRole('heading', { level: 1, name: t('page.G7.title') });
    await screen.findByRole('region', { name: t('page.G7.claims.title') });
    expect(screen.queryByRole('region', { name: t('page.G7.share.title') })).toBeNull();
    expect(matching(rec.requests, 'GET', '/share-links')).toHaveLength(0);
    rec.stop();
  });
});
