// @vitest-environment node
/**
 * R5-FE 3(D25-1): Lighthouse(`npm run lighthouse`, 기준 80)가 화면 10개(G0·G0-2·G1~G8) 전부를 잰다.
 * 화면 목록은 src/routes.tsx 의 routeDefs 경로에서 읽는다 — 화면이 늘면 TARGETS 도 늘려야 이 테스트가 통과한다.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_RUNS,
  median,
  medianRunIndex,
  runsFromEnv,
  TARGETS,
  THRESHOLD,
} from './lib/lighthouse-targets';
import { FRONTEND_ROOT } from './lib/openapi-source';

/** routeDefs 블록의 화면 경로(`/regions/:id/living-areas` …) */
function screenRoutePaths(): string[] {
  const src = readFileSync(resolve(FRONTEND_ROOT, 'src/routes.tsx'), 'utf8');
  const start = src.indexOf('export const routeDefs');
  const end = src.indexOf('];', start);
  expect(start).toBeGreaterThan(0);
  return [...src.slice(start, end).matchAll(/\bpath: '([^']+)'/g)].map((m) => m[1] as string);
}

function matches(pattern: string, path: string): boolean {
  const pathname = path.split('?')[0] ?? path;
  const re = new RegExp(`^${pattern.replace(/:[^/]+/g, '[^/]+')}$`);
  return re.test(pathname);
}

describe('Lighthouse TARGETS', () => {
  it('기준 80', () => {
    expect(THRESHOLD).toBe(80);
  });

  it('routeDefs 화면 10개 모두 데스크톱 측정 대상이 있다(G0 /regions/new · G0-2 생활권 편집 포함)', () => {
    const routes = screenRoutePaths();
    expect(routes).toHaveLength(10);
    const desktop = TARGETS.filter((t) => t.formFactor === 'desktop').map((t) => t.path);
    const missing = routes.filter((r) => !desktop.some((p) => matches(r, p)));
    expect(missing).toEqual([]);
    expect(desktop).toContain('/regions/new');
    expect(desktop.some((p) => matches('/regions/:id/living-areas', p))).toBe(true);
  });

  it('모바일은 D7 이 지원하는 G1·G2·G3 만', () => {
    const mobile = TARGETS.filter((t) => t.formFactor === 'mobile').map((t) => t.path);
    expect(mobile.sort()).toEqual(['/', '/complexes', '/complexes/2'].sort());
  });

  it('같은 (경로, 폼 팩터)는 한 번만', () => {
    const keys = TARGETS.map((t) => `${t.formFactor} ${t.path}`);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe('R5-FE2: 여러 번 재고 중앙값으로 판정', () => {
  it('기본 3회, LH_RUNS 로 바꾼다(잘못된 값은 기본값)', () => {
    expect(DEFAULT_RUNS).toBe(3);
    expect(runsFromEnv(undefined)).toBe(3);
    expect(runsFromEnv('')).toBe(3);
    expect(runsFromEnv('5')).toBe(5);
    expect(runsFromEnv('1')).toBe(1);
    for (const bad of ['0', '-2', '2.5', 'abc']) expect(runsFromEnv(bad)).toBe(3);
  });

  it('중앙값: 홀수는 가운데, 짝수는 가운데 둘 중 낮은 값, 빈 목록은 오류', () => {
    expect(median([78, 91, 88])).toBe(88);
    expect(median([75])).toBe(75);
    expect(median([90, 70, 80, 85])).toBe(80);
    expect(() => median([])).toThrow();
  });

  it('한 번 튄 낮은 점수는 판정을 뒤집지 않는다(중앙값 ≥ 기준)', () => {
    expect(median([88, 76, 90])).toBeGreaterThanOrEqual(THRESHOLD);
    expect(median([79, 76, 90])).toBeLessThan(THRESHOLD);
  });

  it('지표는 중앙값 점수를 낸 실행 것', () => {
    expect(medianRunIndex([78, 91, 88])).toBe(2);
    expect(medianRunIndex([88, 88, 70])).toBe(0);
  });
});
