/**
 * T16 진단(비게이트) — G2 2,500행 가상 스크롤 프레임 간격을 **CPU 감속(CDP `Emulation.setCPUThrottlingRate`)** 아래에서 잰다.
 * R5-FE3: GitHub CI 러너에서 T16(`e2e/pages/perf.spec.ts`, D10-8 p50 ≤ 17ms · p95 ≤ 34ms)이 경계에 붙어 있었다 — 로컬은
 * 빠른 CPU 라 여유가 안 보인다. 이 스크립트는 같은 빌드(MSW 모드 운영 빌드 + vite preview)·같은 스크롤(프레임마다 132px,
 * 180프레임, 3회)을 감속 배율별로 돌려 실제 여유를 숫자로 본다. 판정(테스트)은 perf.spec.ts 가 한다 — 여기는 보고만.
 *
 * 실행(frontend/): `npx tsx scripts/perf-scroll.ts [--rates 1,2,4] [--runs 3] [--no-build] [--port 5972] [--trace <dir>]`
 *  - `--trace <dir>`: 배율마다 Chrome 트레이스(JSON, DevTools Performance 탭에서 열림)를 남긴다.
 *  - 출력: 배율별 회차 p50·p95·최대·≤20ms 프레임 수, 회차 중앙값. exit 0(진단 전용).
 */
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium, type Page } from '@playwright/test';
import { build, preview } from 'vite';
import { FRONTEND_ROOT } from './lib/openapi-source';

const OUT_DIR = resolve(FRONTEND_ROOT, 'dist/msw-perf');

function arg(name: string): string | null {
  const i = process.argv.indexOf(name);
  return i >= 0 ? (process.argv[i + 1] ?? null) : null;
}

export interface ScrollStats {
  frames: number;
  p50: number;
  p95: number;
  max: number;
  /** ≤ 20ms(60Hz 한 프레임 + 20%) 프레임 수 — perf.spec.ts 의 '60fps' 열과 같다 */
  smooth: number;
}

/** 오름차순 값의 분위수(최근접 순위) — perf.spec.ts 와 같은 정의 */
export function quantile(sorted: readonly number[], q: number): number {
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))] ?? 0;
}

export function stats(intervals: readonly number[]): ScrollStats {
  const sorted = [...intervals].sort((a, b) => a - b);
  return {
    frames: intervals.length,
    p50: quantile(sorted, 0.5),
    p95: quantile(sorted, 0.95),
    max: quantile(sorted, 1),
    smooth: intervals.filter((f) => f <= 16.7 * 1.2).length,
  };
}

/**
 * perf.spec.ts measure() 와 같은 스크롤: 맨 위 → 워밍업 10프레임 → 180프레임 동안 프레임마다 132px.
 * 문자열로 넘긴다 — tsx(esbuild keepNames)가 화살표 함수에 `__name` 도우미를 끼워 브라우저에서 ReferenceError 가 난다.
 */
const SCROLL_FN = `async (el) => {
  const raf = () => new Promise((r) => requestAnimationFrame(r));
  el.scrollTop = 0;
  for (let i = 0; i < 10; i += 1) await raf();
  const intervals = [];
  let last = await raf();
  for (let i = 0; i < 180; i += 1) {
    el.scrollTop = Math.min(el.scrollHeight, el.scrollTop + 132);
    const now = await raf();
    intervals.push(now - last);
    last = now;
  }
  return intervals;
}`;

async function scrollOnce(page: Page): Promise<number[]> {
  return (await page.evaluate(
    `(${SCROLL_FN})(document.querySelector('[data-testid="complex-table-scroll"]'))`,
  )) as number[];
}

async function main(): Promise<void> {
  const rates = (arg('--rates') ?? '1,2,4').split(',').map(Number);
  const runs = Number(arg('--runs') ?? 3);
  const port = Number(arg('--port') ?? 5972);
  const traceDir = arg('--trace');
  if (!process.argv.includes('--no-build')) {
    console.log(`perf-scroll: msw 모드 빌드 → ${OUT_DIR}`);
    await build({
      root: FRONTEND_ROOT,
      mode: 'msw',
      logLevel: 'warn',
      build: { outDir: OUT_DIR, emptyOutDir: true },
    });
  }
  const server = await preview({
    root: FRONTEND_ROOT,
    mode: 'msw',
    logLevel: 'warn',
    build: { outDir: OUT_DIR },
    preview: { port, strictPort: true },
  });
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, locale: 'ko-KR' });
    await page.addInitScript(() => window.localStorage.setItem('msw.complexes.rows', '2500'));
    await page.goto(`http://localhost:${port}/complexes`);
    await page.getByText(/2,500 \/ 2,500/).waitFor({ timeout: 60_000 });
    await page.getByTestId('complex-table-scroll').scrollIntoViewIfNeeded();
    const cdp = await page.context().newCDPSession(page);
    for (const rate of rates) {
      await cdp.send('Emulation.setCPUThrottlingRate', { rate });
      if (traceDir) {
        mkdirSync(traceDir, { recursive: true });
        await browser.startTracing(page, {
          path: resolve(traceDir, `scroll-x${rate}.json`),
          screenshots: false,
          categories: [
            'devtools.timeline',
            'disabled-by-default-devtools.timeline',
            'disabled-by-default-devtools.timeline.frame',
            'blink.user_timing',
            'v8.execute',
          ],
        });
      }
      const all: ScrollStats[] = [];
      for (let i = 0; i < runs; i += 1) all.push(stats(await scrollOnce(page)));
      if (traceDir) await browser.stopTracing();
      const med = (pick: (s: ScrollStats) => number) =>
        quantile(
          all.map(pick).sort((a, b) => a - b),
          0.5,
        );
      const detail = all
        .map(
          (s, i) =>
            `#${i + 1} p50 ${s.p50.toFixed(1)} · p95 ${s.p95.toFixed(1)} · 최대 ${s.max.toFixed(1)} · ≤20ms ${s.smooth}/${s.frames}`,
        )
        .join(' | ');
      const line =
        `CPU ×${rate}: 중앙값 p50 ${med((s) => s.p50).toFixed(1)}ms · p95 ${med((s) => s.p95).toFixed(1)}ms · ` +
        `≤20ms ${med((s) => s.smooth)}/${all[0]?.frames ?? 0} (${detail})`;
      console.log(line);
    }
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  } finally {
    await browser.close();
    await new Promise<void>((done) => server.httpServer.close(() => done()));
  }
}

await main();
