import type { ReactElement } from 'react';
import type { RouteObject } from 'react-router';
import type { MobilePolicy, RouteHandle } from '@/hooks/useMobileLayout';
import type { TKey } from '@/i18n';
import { AppLayout } from '@/layout/AppLayout';
import { ComparePage } from '@/pages/compare';
import { ComplexPage } from '@/pages/complex';
import { ComplexesPage } from '@/pages/complexes';
import { DashboardPage } from '@/pages/dashboard';
import { LivingAreasPage } from '@/pages/living-areas';
import { MarketPage } from '@/pages/market';
import { NotFoundPage } from '@/pages/not-found';
import { OpsPage } from '@/pages/ops';
import { RegionNewPage } from '@/pages/region-new';
import { ReportsPage } from '@/pages/reports';
import { ScenarioPage } from '@/pages/scenario';

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

export const appRoutes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      ...routeDefs.map((def): RouteObject => ({
        path: def.path,
        element: def.element,
        handle: { screen: def.id, mobile: def.mobile } satisfies RouteHandle,
      })),
      {
        path: '*',
        element: <NotFoundPage />,
        handle: { screen: '404', mobile: 'readonly' } satisfies RouteHandle,
      },
    ],
  },
];
