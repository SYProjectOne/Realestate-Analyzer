/**
 * T16 "60fps 스크롤"(R3 minor 37 → 재리뷰 m37) — DOM 행 수 대리 지표 대신 실제 프레임 간격을 잰다.
 *
 * 기준 = `docs/design/DECISIONS.md` **D10-8**: 가상 스크롤 **p50 프레임 간격 ≤ 17ms(60fps)** + **p95 ≤ 34ms**.
 * RA 의 "60fps" 는 p50 으로 해석해 기록한다(RA 60fps = p50, D10-8). p95 34ms = 60Hz 프레임 2개(33.3ms, rAF 타임스탬프
 * 양자화로 33.4ms 로 찍힌다) — 95% 의 프레임이 '최대 한 번 놓침' 안에 있어야 한다.
 *
 * 프로덕션 빌드(MSW 모드, `vite build --mode msw` + `vite preview`)에서, 다른 e2e 가 끝난 뒤 혼자 돈다
 * (playwright.config.ts 의 perf 프로젝트: dependencies = chromium, workers 경합 없음). dev 서버(React 개발 빌드·
 * StrictMode 이중 렌더)는 사용자가 쓰는 빌드가 아니라 재지 않는다.
 *
 * 2,500행(W9: 1,000 넘는 행도 페이지를 이어 받아 전부 닿는다)을 다 받은 뒤, 표 스크롤 영역을 프레임마다 내리며
 * requestAnimationFrame 간격을 모은다. 측정 안정화(R3b): 맨 위에서부터 같은 스크롤을 **3번** 재고, 각 회차의 p50·p95
 * 의 **중앙값**으로 판정한다(한 회차가 GC·스케줄링으로 튀어도 경계가 흔들리지 않게). 가상 스크롤이므로 DOM 행은 계속 100개 미만.
 */
import { expect, test, type Locator } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

const P = ko.page;
/** D10-8: p50 프레임 간격 상한(60fps = 16.7ms, rAF 양자화 여유) — RA 60fps = p50 */
export const T16_P50_FRAME_MS = 17;
/** D10-8: p95 프레임 간격 상한(60Hz 프레임 2개) */
export const T16_P95_FRAME_MS = 34;
/** 측정 반복 횟수 — 판정은 회차별 p50·p95 의 중앙값 */
export const T16_RUNS = 3;

interface RunStats {
  frames: number;
  p50: number;
  p95: number;
  max: number;
  smooth: number;
}

/** 오름차순 정렬한 값의 분위수(최근접 순위) */
function quantile(sorted: readonly number[], q: number): number {
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))] ?? 0;
}

/** 홀수 개 값의 중앙값 */
function median(values: readonly number[]): number {
  return quantile(
    [...values].sort((a, b) => a - b),
    0.5,
  );
}

/** 스크롤 영역을 맨 위로 되돌린 뒤 프레임마다 내리며 rAF 간격을 잰다(한 회차) */
async function measure(scroller: Locator): Promise<RunStats> {
  const frames = await scroller.evaluate(async (el) => {
    const raf = () => new Promise<number>((resolve) => requestAnimationFrame(resolve));
    el.scrollTop = 0;
    // 워밍업 몇 프레임(맨 위 행 렌더가 끝나게)
    for (let i = 0; i < 10; i += 1) await raf();
    const intervals: number[] = [];
    let last = await raf();
    const steps = 180; // 약 3초(60Hz) 동안 프레임마다 스크롤
    // 빠른 휠 스크롤 속도: 프레임마다 행 3개(132px) ≈ 초당 8,000px — 3초에 540행을 지난다
    const step = 132;
    for (let i = 0; i < steps; i += 1) {
      el.scrollTop = Math.min(el.scrollHeight, el.scrollTop + step);
      const now = await raf();
      intervals.push(now - last);
      last = now;
    }
    return intervals;
  });
  const sorted = [...frames].sort((a, b) => a - b);
  return {
    frames: frames.length,
    p50: quantile(sorted, 0.5),
    p95: quantile(sorted, 0.95),
    max: quantile(sorted, 1),
    smooth: frames.filter((f) => f <= 16.7 * 1.2).length,
  };
}

test('T16(D10-8): G2 2,500행 스크롤 — 프레임 간격(rAF) 3회 중앙값 p50 ≤ 17ms(60fps) · p95 ≤ 34ms', async ({
  page,
}, testInfo) => {
  await page.addInitScript(() => window.localStorage.setItem('msw.complexes.rows', '2500'));
  await page.goto('/complexes');
  await expect(page.getByRole('heading', { level: 1, name: P.G2.title })).toBeVisible();
  const table = page.getByRole('table', { name: P.G2.table });
  await expect(table).toHaveAttribute('aria-rowcount', '2501');
  await expect(page.getByText(/2,500 \/ 2,500/)).toBeVisible({ timeout: 30_000 });
  const scroller = page.getByTestId('complex-table-scroll');
  await scroller.scrollIntoViewIfNeeded();

  const runs: RunStats[] = [];
  for (let i = 0; i < T16_RUNS; i += 1) runs.push(await measure(scroller));

  const p50 = median(runs.map((r) => r.p50));
  const p95 = median(runs.map((r) => r.p95));
  const detail = runs
    .map(
      (r, i) =>
        `#${i + 1} p50 ${r.p50.toFixed(1)} · p95 ${r.p95.toFixed(1)} · 최대 ${r.max.toFixed(1)} · ` +
        `60fps(≤20ms) ${r.smooth}/${r.frames}`,
    )
    .join(' | ');
  const summary = `T16 ${T16_RUNS}회 중앙값: p50 ${p50.toFixed(1)}ms · p95 ${p95.toFixed(1)}ms (${detail})`;
  console.log(summary);
  testInfo.annotations.push({ type: 'T16', description: summary });
  for (const r of runs) expect(r.frames).toBeGreaterThanOrEqual(150);
  expect(p50).toBeLessThanOrEqual(T16_P50_FRAME_MS);
  expect(p95).toBeLessThanOrEqual(T16_P95_FRAME_MS);
  expect(await table.locator('tbody tr[aria-rowindex]').count()).toBeLessThan(100);
});
