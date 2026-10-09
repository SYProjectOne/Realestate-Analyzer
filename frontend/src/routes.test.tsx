import { cleanup, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { t } from '@/i18n';
import { MOBILE_QUERY } from '@/lib/useMediaQuery';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { routeDefs } from './routes';
import { renderRoute } from './test/render';

const CASES = [
  ['G0', '/regions/new', 'page.G0.title'],
  ['G0-2', '/regions/rg_1/living-areas', 'page.G0_2.title'],
  ['G1', '/', 'page.G1.title'],
  ['G2', '/complexes', 'page.G2.title'],
  ['G3', '/complexes/cx_1', 'page.G3.title'],
  ['G4', '/compare?ids=cx_1,cx_2', 'page.G4.title'],
  ['G5', '/scenario', 'page.G5.title'],
  ['G6', '/market', 'page.G6.title'],
  ['G7', '/ops', 'page.G7.title'],
  ['G8', '/reports', 'page.G8.title'],
] as const;

describe('라우트 10개', () => {
  it('routeDefs에 화면 10개가 정의돼 있다', () => {
    expect(routeDefs.map((r) => r.id)).toEqual(CASES.map(([id]) => id));
  });

  it.each(CASES)('%s %s → 제목을 렌더한다', async (_id, path, titleKey) => {
    renderRoute(path);
    expect(await screen.findByRole('heading', { level: 1, name: t(titleKey) })).toBeInTheDocument();
  });

  it('모든 화면 하단에 "투자 권유 아님 · 상대 비교" 고정 문구', async () => {
    renderRoute('/complexes');
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText(t('app.disclaimer'))).toBeInTheDocument();
  });

  it('지역이 하나도 없으면 / → /regions/new', async () => {
    server.use(http.get(mswPath('/regions'), () => HttpResponse.json([])));
    renderRoute('/');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.G0.title') }),
    ).toBeInTheDocument();
  });

  it('헤더에 RegionPicker(+지역 추가)·SnapshotPicker·ScenarioToggle·테마 토글이 있다', async () => {
    renderRoute('/');
    expect(await screen.findByRole('option', { name: t('header.regionAdd') })).toBeInTheDocument();
    expect(await screen.findByLabelText(t('header.snapshot'))).toBeInTheDocument();
    expect(
      await screen.findByRole('radiogroup', { name: t('header.scenario') }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: new RegExp(t('header.theme')) })).toBeInTheDocument();
  });

  it('모바일(≤768px): G1은 읽기 전용 안내, G7은 데스크톱 안내', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      ...original(query),
      matches: query === MOBILE_QUERY,
    })) as typeof window.matchMedia;
    try {
      renderRoute('/');
      expect(await screen.findByText(t('app.mobileReadOnly'))).toBeInTheDocument();
      expect(screen.getByRole('main')).toHaveAttribute('data-readonly', 'true');
      cleanup();
      renderRoute('/ops');
      expect(await screen.findByText(t('app.mobileUnsupported'))).toBeInTheDocument();
    } finally {
      window.matchMedia = original;
    }
  });

  it('없는 경로는 404 제목', async () => {
    renderRoute('/no-such-page');
    expect(
      await screen.findByRole('heading', { level: 1, name: t('page.notFound.title') }),
    ).toBeInTheDocument();
  });
});
