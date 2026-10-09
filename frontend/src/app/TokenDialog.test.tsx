import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import { ROLE_STORAGE_KEY, TOKEN_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import '@/pages/_shared/testing';
import { renderRoute } from '@/test/render';

vi.mock('echarts-for-react', () => ({ default: () => null }));
beforeEach(() => resetMockState());

const TOKENS = { 'tok-write': 'write', 'tok-read': 'read' } as const;
const tokenOf = (request: Request) =>
  request.headers.get('authorization')?.replace(/^Bearer /, '') ?? '';

/** 토큰을 요구하는 서버: /regions 는 토큰이 맞아야 하고, POST /jobs 는 읽기 전용이면 403 */
function requireToken() {
  server.use(
    http.get(mswPath('/regions'), async ({ request }) => {
      if (!(tokenOf(request) in TOKENS)) {
        return HttpResponse.json(
          { code: 'unauthorized', detail: 'Bearer 토큰이 필요하다' },
          { status: 401 },
        );
      }
      const res = await getResponse(generatedHandlers as RequestHandler[], request);
      return res ?? HttpResponse.json([]);
    }),
    http.post(mswPath('/jobs'), ({ request }) =>
      TOKENS[tokenOf(request) as keyof typeof TOKENS] === 'read'
        ? HttpResponse.json({ code: 'forbidden', detail: 'GET 만' }, { status: 403 })
        : HttpResponse.json({ code: 'validation_error', detail: 'body' }, { status: 422 }),
    ),
  );
}

async function enterToken(token: string) {
  const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
  await userEvent.type(within(dialog).getByLabelText(t('auth.label')), token);
  await userEvent.click(within(dialog).getByRole('button', { name: t('auth.save') }));
  return dialog;
}

describe('토큰 다이얼로그', () => {
  it('토큰 없이 401 → 다이얼로그(토큰 필요) → 틀린 토큰은 거절', async () => {
    requireToken();
    renderRoute('/reports');
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    expect(within(dialog).getByText(t('auth.reason.missing'))).toBeInTheDocument();
    expect(within(dialog).getByLabelText(t('auth.label'))).toHaveAttribute('type', 'password');
    await enterToken('tok-nope');
    expect(await within(dialog).findByText(t('auth.invalid'))).toBeInTheDocument();
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it('읽기 전용 토큰 → 저장(role=read) · 안내 배너 · 쓰기 버튼 비활성', async () => {
    requireToken();
    renderRoute('/reports');
    await enterToken('tok-read');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: t('auth.title') })).toBeNull());
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-read');
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('read');
    expect(await screen.findByTestId('readonly-banner')).toBeInTheDocument();
    expect(screen.getByTestId('token-button')).toHaveTextContent(t('auth.state.read'));
    // 다시 불러온 지역 → 스냅샷 → 생성 버튼(읽기 전용이라 꺼짐)
    const generate = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(screen.getByLabelText(t('page.G8.snapshot'))).toHaveValue());
    expect(generate).toBeDisabled();
    expect(generate).toHaveAttribute('title', t('auth.readOnlyHint'));
  });

  it('쓰기 토큰 → 저장(role=write) · 배너 없음 · 생성 버튼 켜짐', async () => {
    requireToken();
    renderRoute('/reports');
    await enterToken('tok-write');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: t('auth.title') })).toBeNull());
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('write');
    expect(screen.queryByTestId('readonly-banner')).toBeNull();
    const generate = await screen.findByRole('button', { name: t('page.G8.generate') });
    await waitFor(() => expect(generate).toBeEnabled());
  });

  it('헤더 버튼으로 열고, 저장한 토큰을 지울 수 있다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-write');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'write');
    renderRoute('/');
    await userEvent.click(await screen.findByTestId('token-button'));
    const dialog = await screen.findByRole('dialog', { name: t('auth.title') });
    expect(within(dialog).getByTestId('token-current')).toHaveTextContent(t('auth.state.write'));
    await userEvent.click(within(dialog).getByRole('button', { name: t('auth.clear') }));
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    await userEvent.click(within(dialog).getByRole('button', { name: t('auth.close') }));
    expect(screen.queryByRole('dialog', { name: t('auth.title') })).toBeNull();
  });

  it('저장소 쓰기가 막혀도 이 탭에서는 동작하고 안내한다', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'QuotaExceededError');
    });
    requireToken();
    renderRoute('/reports');
    await enterToken('tok-write');
    expect(
      await screen.findByText(`${t('auth.savedWrite')} · ${t('auth.notPersisted')}`),
    ).toBeInTheDocument();
    expect(screen.getByTestId('token-button')).toHaveTextContent(t('auth.state.write'));
  });
});
