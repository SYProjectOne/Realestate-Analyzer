import { lazy, type ComponentType, type ReactElement } from 'react';
import type { RouteObject } from 'react-router';
import { ChartGalleryPage } from '@/app/ChartGalleryPage';
import type { MobilePolicy, RouteHandle } from '@/hooks/useMobileLayout';
import type { TKey } from '@/i18n';
import { AppLayout } from '@/layout/AppLayout';
import { NotFoundPage } from '@/pages/not-found';
import { SharePage } from '@/pages/share';

/** 화면 청크 불러오기 함수들(`preloadPages`) */
const pageLoaders: (() => Promise<unknown>)[] = [];

/** 화면마다 별도 청크(첫 화면 번들을 줄인다 — Lighthouse 성능). AppLayout의 Suspense가 받는다. */
function page<K extends string>(
  load: () => Promise<Record<K, ComponentType>>,
  name: K,
): ComponentType {
  pageLoaders.push(load);
  return lazy(async (): Promise<{ default: ComponentType }> => ({ default: (await load())[name] }));
}

/**
 * 화면 청크를 모두 미리 불러온다. 테스트(`test/render.tsx`)가 파일마다 한 번 — 첫 화면 렌더의 findBy 창 안에서
 * 청크 변환·평가를 기다리지 않게 한다(6차 리뷰: 부하에서 첫 테스트가 5초를 넘음).
 */
export async function preloadPages(): Promise<void> {
  await Promise.all(pageLoaders.map((load) => load()));
}

const RegionNewPage = page(() => import('@/pages/region-new'), 'RegionNewPage');
const LivingAreasPage = page(() => import('@/pages/living-areas'), 'LivingAreasPage');
const DashboardPage = page(() => import('@/pages/dashboard'), 'DashboardPage');
const ComplexesPage = page(() => import('@/pages/complexes'), 'ComplexesPage');
const ComplexPage = page(() => import('@/pages/complex'), 'ComplexPage');
const ComparePage = page(() => import('@/pages/compare'), 'ComparePage');
const ScenarioPage = page(() => import('@/pages/scenario'), 'ScenarioPage');
const MarketPage = page(() => import('@/pages/market'), 'MarketPage');
const OpsPage = page(() => import('@/pages/ops'), 'OpsPage');
const ReportsPage = page(() => import('@/pages/reports'), 'ReportsPage');

export interface RouteDef {
  /** 화면 id (RA §7-1, D2-5) */
  id: 'G0' | 'G0-2' | 'G1' | 'G2' | 'G3' | 'G4' | 'G5' | 'G6' | 'G7' | 'G8';
  path: string;
  titleKey: TKey;
  element: ReactElement;
  /** D7: 모바일은 G1·G2·G3만 읽기 전용 */
  mobile: MobilePolicy;
}

/** 화면 10개 — 순서는 G0, G0-2, G1~G8 */
export const routeDefs: RouteDef[] = [
  {
    id: 'G0',
    path: '/regions/new',
    titleKey: 'page.G0.title',
    element: <RegionNewPage />,
    mobile: 'unsupported',
  },
  {
    id: 'G0-2',
    path: '/regions/:id/living-areas',
    titleKey: 'page.G0_2.title',
    element: <LivingAreasPage />,
    mobile: 'unsupported',
  },
  {
    id: 'G1',
    path: '/',
    titleKey: 'page.G1.title',
    element: <DashboardPage />,
    mobile: 'readonly',
  },
  {
    id: 'G2',
    path: '/complexes',
    titleKey: 'page.G2.title',
    element: <ComplexesPage />,
    mobile: 'readonly',
  },
  {
    id: 'G3',
    path: '/complexes/:id',
    titleKey: 'page.G3.title',
    element: <ComplexPage />,
    mobile: 'readonly',
  },
  {
    id: 'G4',
    path: '/compare',
    titleKey: 'page.G4.title',
    element: <ComparePage />,
    mobile: 'unsupported',
  },
  {
    id: 'G5',
    path: '/scenario',
    titleKey: 'page.G5.title',
    element: <ScenarioPage />,
    mobile: 'unsupported',
  },
  {
    id: 'G6',
    path: '/market',
    titleKey: 'page.G6.title',
    element: <MarketPage />,
    mobile: 'unsupported',
  },
  {
    id: 'G7',
    path: '/ops',
    titleKey: 'page.G7.title',
    element: <OpsPage />,
    mobile: 'unsupported',
  },
  {
    id: 'G8',
    path: '/reports',
    titleKey: 'page.G8.title',
    element: <ReportsPage />,
    mobile: 'unsupported',
  },
];

/** dev(또는 MSW 모드)에서만 여는 차트 갤러리 — 프로덕션 번들에는 라우트가 없다 */
const DEV_ROUTES: RouteObject[] =
  import.meta.env.DEV || import.meta.env.MODE === 'msw'
    ? [
        {
          path: '/__charts',
          element: <ChartGalleryPage />,
          handle: { screen: 'charts', mobile: 'unsupported' } satisfies RouteHandle,
        },
      ]
    : [];

export const appRoutes: RouteObject[] = [
  /**
   * 공유 링크 착지(`/share#<token>`, M9) — AppLayout 밖: 토큰을 저장하기 전에 API 를 부르지 않는다.
   * 화면 10개(routeDefs)가 아니라 진입 도우미다.
   */
  {
    path: '/share',
    element: <SharePage />,
    handle: { screen: 'share', mobile: 'readonly' } satisfies RouteHandle,
  },
  {
    element: <AppLayout />,
    children: [
      ...routeDefs.map((def): RouteObject => ({
        path: def.path,
        element: def.element,
        handle: { screen: def.id, mobile: def.mobile } satisfies RouteHandle,
      })),
      ...DEV_ROUTES,
      {
        path: '*',
        element: <NotFoundPage />,
        handle: { screen: '404', mobile: 'readonly' } satisfies RouteHandle,
      },
    ],
  },
];
