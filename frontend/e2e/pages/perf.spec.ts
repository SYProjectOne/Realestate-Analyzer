/**
 * T16 "60fps 스크롤"(R3 minor 37) — DOM 행 수 대리 지표 대신 실제 프레임 간격을 잰다.
 *
 * 프로덕션 빌드(MSW 모드, `vite build --mode msw` + `vite preview`)에서, 다른 e2e 가 끝난 뒤 혼자 돈다
 * (playwright.config.ts 의 perf 프로젝트: dependencies = chromium, workers 경합 없음). dev 서버(React 개발 빌드·
 * StrictMode 이중 렌더)는 사용자가 쓰는 빌드가 아니라 재지 않는다.
 *
 * 2,500행(W9: 1,000 넘는 행도 페이지를 이어 받아 전부 닿는다)을 다 받은 뒤, 표 스크롤 영역을 프레임마다 내리며
 * requestAnimationFrame 간격을 모은다. 기준: p95 프레임 간격 ≤ 34ms(60Hz 프레임 2개 = 30fps 이상, 헤드리스·CI
 * 변동을 감안한 하한). 60fps(16.7ms) 비율은 결과 주석으로 남긴다. 가상 스크롤이므로 DOM 행은 계속 100개 미만.
 */
import { expect, test } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

const P = ko.page;
/**
 * p95 프레임 간격 상한 34ms: 60Hz 에서 프레임 2개(33.3ms, rAF 타임스탬프 양자화로 33.4ms 로 찍힌다) —
 * 95% 의 프레임이 '최대 한 번 놓침'(30fps 이상) 안에 있어야 한다. 60fps 비율은 주석으로 남긴다.
 */
export const T16_P95_FRAME_MS = 34;

test('T16: G2 2,500행 스크롤 — 실제 프레임 간격(rAF) p95 ≤ 34ms(30fps 이상)', async ({
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

  const frames = await scroller.evaluate(async (el) => {
    const raf = () => new Promise<number>((resolve) => requestAnimationFrame(resolve));
    // 워밍업 몇 프레임
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
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))] ?? 0;
  const p50 = at(0.5);
  const p95 = at(0.95);
  const smooth = frames.filter((f) => f <= 16.7 * 1.2).length;
  const summary =
    `T16 프레임 ${frames.length}개: p50 ${p50.toFixed(1)}ms · p95 ${p95.toFixed(1)}ms · ` +
    `최대 ${at(1).toFixed(1)}ms · 60fps 프레임(≤20ms) ${smooth}/${frames.length}`;
  console.log(summary);
  testInfo.annotations.push({ type: 'T16', description: summary });
  expect(frames.length).toBeGreaterThanOrEqual(150);
  expect(p95).toBeLessThanOrEqual(T16_P95_FRAME_MS);
  expect(await table.locator('tbody tr[aria-rowindex]').count()).toBeLessThan(100);
});
