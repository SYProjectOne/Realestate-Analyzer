import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from '../_shared/testing';

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
