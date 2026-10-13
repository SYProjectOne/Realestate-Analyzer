/**
 * `npm run lighthouse`(scripts/lighthouse.ts) 측정 대상·기준. 스크립트는 import 하면 바로 실행되므로 목록만 따로 둔다
 * (scripts/lighthouse-targets.test.ts 가 src/routes.tsx 화면 10개와 맞는지 본다).
 */
export const THRESHOLD = 80;
/**
 * R5-FE2: 화면당 측정 횟수 기본값. 판정은 횟수별 점수의 **중앙값**으로 한다 — 한 번 재면 CI 러너 소음(±3~4점)에
 * 기준 근처 점수가 뒤집혔다(CI run 38339589390: 모바일 75~78, 앞 실행·로컬은 82). `LH_RUNS` 로 바꾼다.
 */
export const DEFAULT_RUNS = 3;
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

/** `LH_RUNS` 값 → 측정 횟수. 비었거나 정수 ≥ 1 이 아니면 DEFAULT_RUNS */
export function runsFromEnv(value: string | undefined): number {
  if (value === undefined || value.trim() === '') return DEFAULT_RUNS;
  const n = Number(value);
  return Number.isInteger(n) && n >= 1 ? n : DEFAULT_RUNS;
}

/** 중앙값. 개수가 짝수면 가운데 둘 중 **낮은** 값(보수적 — 기준 판정이 좋은 쪽으로 기울지 않게) */
export function median(xs: readonly number[]): number {
  if (xs.length === 0) throw new Error('median: 빈 목록');
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor((s.length - 1) / 2)] as number;
}

/** 중앙값 성능 점수를 낸 실행의 번호(같은 값이 여럿이면 처음) — 지표(FCP·LCP·TBT)·감점 감사는 이 실행 것을 적는다 */
export function medianRunIndex(scores: readonly number[]): number {
  return scores.indexOf(median(scores));
}
