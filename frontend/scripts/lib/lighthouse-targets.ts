/**
 * `npm run lighthouse`(scripts/lighthouse.ts) 측정 대상·기준. 스크립트는 import 하면 바로 실행되므로 목록만 따로 둔다
 * (scripts/lighthouse-targets.test.ts 가 src/routes.tsx 화면 10개와 맞는지 본다).
 */
export const THRESHOLD = 80;
export const CATEGORIES = ['performance', 'accessibility', 'best-practices'] as const;
export type Category = (typeof CATEGORIES)[number];
export type FormFactor = 'desktop' | 'mobile';

export interface Target {
  path: string;
  formFactor: FormFactor;
}

/**
 * 화면 id ↔ 경로(MSW 계약 예시로 열리는 값). 데스크톱은 화면 10개 전부(G0·G0-2·G1~G8),
 * 모바일은 D7 이 지원하는 G1·G2·G3 만.
 */
export const TARGETS: Target[] = [
  // R5-FE(D25-1): G0 지역 입력 · G0-2 생활권 편집(계약 예시 지역 id 1)
  { path: '/regions/new', formFactor: 'desktop' },
  { path: '/regions/1/living-areas', formFactor: 'desktop' },
  { path: '/', formFactor: 'desktop' },
  { path: '/complexes', formFactor: 'desktop' },
  { path: '/complexes/2', formFactor: 'desktop' },
  { path: '/compare?ids=2,7,4', formFactor: 'desktop' },
  { path: '/scenario', formFactor: 'desktop' },
  { path: '/market', formFactor: 'desktop' },
  { path: '/ops', formFactor: 'desktop' },
  { path: '/reports', formFactor: 'desktop' },
  { path: '/', formFactor: 'mobile' },
  { path: '/complexes', formFactor: 'mobile' },
  { path: '/complexes/2', formFactor: 'mobile' },
];
