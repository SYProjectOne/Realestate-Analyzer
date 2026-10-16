/**
 * R11-SETUP(D30, 목업 Reports '다른 화면 · 공유 링크 받는 곳'): 카드 모양·쉬운 문구. 토큰 처리 동작은 share.test.tsx 가 지킨다.
 */
import { screen, within } from '@testing-library/react';
import { TOKEN_STORAGE_KEY, ROLE_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { resetMockState } from '@/mocks/handlers.extra';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

describe('R11 공유 링크 받는 곳', () => {
  it('주소가 잘렸을 때: 앱 이름 · 제목 · 경고 한 줄 · 홈으로 버튼', async () => {
    renderRoute('/share');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.share.title') }),
    ).toBeVisible();
    expect(screen.getByText(t('app.name'))).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(t('page.share.missing'));
    expect(screen.getByRole('link', { name: t('page.share.home') })).toHaveAttribute('href', '/');
  });

  it('쓰기 열쇠가 있을 때: 확인 창 아래 첫 선택·Esc 안내', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-mine');
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'write');
    renderRoute('/share#abc');
    const dialog = await screen.findByRole('alertdialog', { name: t('page.share.confirmTitle') });
    expect(within(dialog).getByText(t('page.share.confirmHint'))).toBeInTheDocument();
    expect(
      within(dialog)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual([t('page.share.tabOnly'), t('page.share.replace'), t('page.share.cancel')]);
  });
});
