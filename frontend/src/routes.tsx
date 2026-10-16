import { lazy, type ComponentType, type ReactElement } from 'react';
import type { RouteObject } from 'react-router';
import type { MobilePolicy, RouteHandle } from '@/hooks/useMobileLayout';
import { loadAllNamespaces, loadNamespaces, type KoNamespace, type TKey } from '@/i18n';
import { AppLayout } from '@/layout/AppLayout';
import { NotFoundPage } from '@/pages/not-found';
import { SharePage } from '@/pages/share';

/** 화면 청크 불러오기 함수들(`preloadPages`) */
const pageLoaders: (() => Promise<unknown>)[] = [];

/**
 * 화면마다 별도 청크(첫 화면 번들을 줄인다 — Lighthouse 성능). AppLayout의 Suspense가 받는다.
 *
 * R11-I18N: `ns` = 그 화면이 쓰는 문자열 이름공간(src/i18n/namespaces.ts). 화면 청크와 **동시에** 받아 둘 다 끝난 뒤
 * 렌더한다 — 첫 렌더에 문자열이 이미 있다(키 노출·깜빡임·CLS 없음). 어떤 이름공간이 필요한지는
 * `src/i18n/routeNamespaces.test.ts`(화면 폴더에서 닿는 모듈의 키를 정적으로 훑는다)가 검사하고, 빠진 것을 이름으로 알려 준다.
 * 화면 모듈 최상위(렌더 밖)에서 이름공간 키로 t() 를 부르지 않는다 — 두 청크의 평가 순서는 정해져 있지 않다(같은 테스트가 본다).
 */
function page<K extends string>(
  load: () => Promise<Record<K, ComponentType>>,
  name: K,
  ns: readonly KoNamespace[] | 'all',
): ComponentType {
  const loadWithStrings = async () => {
    const [mod] = await Promise.all([
      load(),
      ns === 'all' ? loadAllNamespaces() : loadNamespaces(ns),
    ]);
    return mod;
  };
  pageLoaders.push(loadWithStrings);
  return lazy(async (): Promise<{ default: ComponentType }> => ({
    default: (await loadWithStrings())[name],
  }));
}

/**
 * 화면 청크를 모두 미리 불러온다. 테스트(`test/render.tsx`)가 파일마다 한 번 — 첫 화면 렌더의 findBy 창 안에서
 * 청크 변환·평가를 기다리지 않게 한다(6차 리뷰: 부하에서 첫 테스트가 5초를 넘음).
 */
export async function preloadPages(): Promise<void> {
  await Promise.all(pageLoaders.map((load) => load()));
}

const RegionNewPage = page(() => import('@/pages/region-new'), 'RegionNewPage', [
  'page/G0',
  'glossary',
]);
const LivingAreasPage = page(() => import('@/pages/living-areas'), 'LivingAreasPage', [
  'page/G0_2',
  'page/G0',
  'glossary',
]);
const DashboardPage = page(() => import('@/pages/dashboard'), 'DashboardPage', [
  'page/G1',
  'chart',
  'glossary',
]);
const ComplexesPage = page(() => import('@/pages/complexes'), 'ComplexesPage', [
  'page/G2',
  'glossary',
]);
const ComplexPage = page(() => import('@/pages/complex'), 'ComplexPage', [
  'page/G3',
  'page/G2',
  'chart',
  'glossary',
]);
const ComparePage = page(() => import('@/pages/compare'), 'ComparePage', [
  'page/G4',
  'page/G3',
  'page/G5',
  'chart',
  'glossary',
]);
const ScenarioPage = page(() => import('@/pages/scenario'), 'ScenarioPage', [
  'page/G5',
  'chart',
  'glossary',
]);
const MarketPage = page(() => import('@/pages/market'), 'MarketPage', [
  'page/G6',
  'chart',
  'glossary',
]);
const OpsPage = page(() => import('@/pages/ops'), 'OpsPage', ['page/G7', 'page/G3', 'glossary']);
const ReportsPage = page(() => import('@/pages/reports'), 'ReportsPage', ['page/G8', 'glossary']);
const GlossaryPage = page(() => import('@/pages/glossary'), 'GlossaryPage', ['glossary']);

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

/** dev(또는 MSW 모드)에서만 여는 차트 갤러리 — 프로덕션 번들에는 라우트가 없다(지연 청크도 없다) */
const DEV_ROUTES: RouteObject[] =
  import.meta.env.DEV || import.meta.env.MODE === 'msw'
    ? [
        {
          path: '/__charts',
          element: (() => {
            // 개발 화면 — 이름공간을 전부 받는다(갤러리 예시가 화면 문구도 쓴다)
            const ChartGalleryPage = page(
              () => import('@/app/ChartGalleryPage'),
              'ChartGalleryPage',
              'all',
            );
            return <ChartGalleryPage />;
          })(),
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
      /**
       * 용어 모음(R9-UI P6, 30-proposal §7) — 화면 10개(routeDefs)가 아니라 도움 페이지. 모바일도 읽기 전용으로 연다.
       */
      {
        path: '/glossary',
        element: <GlossaryPage />,
        handle: { screen: 'glossary', mobile: 'readonly' } satisfies RouteHandle,
      },
      ...DEV_ROUTES,
      {
        path: '*',
        element: <NotFoundPage />,
        handle: { screen: '404', mobile: 'readonly' } satisfies RouteHandle,
      },
    ],
  },
];
