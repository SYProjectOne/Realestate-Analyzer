/**
 * T16 성능 측정(RA §9: `/complexes` 첫 페이지 1초 이내, G2 스크롤 60fps(가상화)) — 합성 1,000단지.
 * 측정값을 콘솔(`T16 …` 줄)과 playwright-report/perf-results.json 에 남긴다.
 * 판정: API 첫 페이지(size 50) 중앙값 < 1 s; G2 가상화(DOM 행 < 200, aria-rowcount ≥ 1001);
 *       스크롤 rAF 간격 — D10-8: p50 ≤ 17 ms(60 fps) + p95 ≤ 34 ms(두 프레임 이상 끊김이 5% 이하).
 */

/** D10-8 T16 화면 기준(ms) — RA "60fps" 를 p50 으로 해석, 끊김은 p95 로 묶는다 */
export const FRAME_P50_MAX_MS = 17;
export const FRAME_P95_MAX_MS = 34;
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import ko from '../../frontend/src/i18n/ko.json' with { type: 'json' };
import { AUTH, E2E } from '../env';

const API = process.env.E2E_PERF_API ?? 'http://127.0.0.1:18866';

function stats(xs: number[]): { n: number; p50: number; p95: number; max: number; mean: number } {
  const s = [...xs].sort((a, b) => a - b);
  const q = (p: number): number => s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))] ?? NaN;
  const r = (v: number): number => Math.round(v * 10) / 10;
  return { n: s.length, p50: r(q(0.5)), p95: r(q(0.95)), max: r(s.at(-1) ?? NaN), mean: r(s.reduce((a, b) => a + b, 0) / (s.length || 1)) };
}

test('T16 API 첫 페이지 + G2 가상 스크롤 프레임 간격', async ({ page, request }) => {
  const out: Record<string, unknown> = {};

  // 1) API 첫 페이지(직접 HTTP, 워밍업 1회 뒤 5회)
  for (const size of [50, 1000]) {
    const url = `${API}/api/snapshots/12/complexes?page=1&size=${size}`;
    await request.get(url, { headers: AUTH });
    const ms: number[] = [];
    for (let i = 0; i < 5; i++) {
      const t0 = performance.now();
      const r = await request.get(url, { headers: AUTH });
      ms.push(performance.now() - t0);
      expect(r.status()).toBe(200);
      const body = (await r.json()) as { total: number; items: unknown[] };
      expect(body.total).toBeGreaterThanOrEqual(1000);
      expect(body.items).toHaveLength(size);
    }
    out[`api_first_page_size_${size}_ms`] = stats(ms);
  }

  // 2) G2: 화면이 부른 /complexes 응답 시간(브라우저 측) + 가상 스크롤 rAF
  const listResp = page.waitForResponse((r) => /\/api\/snapshots\/\d+\/complexes\?/.test(r.url()) && r.status() === 200);
  const t0 = Date.now();
  await page.goto('/complexes?region=1');
  const resp = await listResp;
  out.g2_list_request = { url: new URL(resp.url()).search, wall_ms: Date.now() - t0, timing: resp.request().timing() };
  const table = page.getByRole('table', { name: ko.page.G2.table });
  await expect(table).toHaveAttribute('aria-rowcount', /^\d+$/);
  const rowcount = Number(await table.getAttribute('aria-rowcount'));
  expect(rowcount).toBeGreaterThanOrEqual(1001);
  const scroller = page.getByTestId('complex-table-scroll');
  await expect(scroller.locator('tbody tr[aria-rowindex]').first()).toBeVisible();
  const domRows = await scroller.locator('tbody tr[aria-rowindex]').count();
  out.g2_dom_rows = domRows;
  out.g2_aria_rowcount = rowcount;
  expect(domRows).toBeLessThan(200);

  // 진단: 스크롤 없이 rAF 간격(이 브라우저·화면의 기본 프레임 주기) — 스크롤 결과와 비교용
  const idle = await page.evaluate(async () => {
    const deltas: number[] = [];
    let last = performance.now();
    await new Promise<void>((resolve) => {
      const tick = (now: number): void => {
        deltas.push(now - last);
        last = now;
        if (deltas.length > 120) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    return deltas.slice(1);
  });
  out.idle_frame_ms = stats(idle);

  const frames = await scroller.evaluate(async (el: HTMLElement) => {
    const deltas: number[] = [];
    const end = el.scrollHeight - el.clientHeight;
    const step = Math.max(40, end / 240); // 약 4초(60 fps 기준)에 끝까지
    let last = performance.now();
    await new Promise<void>((resolve) => {
      const tick = (now: number): void => {
        deltas.push(now - last);
        last = now;
        el.scrollTop = Math.min(end, el.scrollTop + step);
        if (el.scrollTop >= end || deltas.length > 600) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    return { deltas: deltas.slice(1), reachedEnd: el.scrollTop >= end - 1 };
  });
  const st = stats(frames.deltas);
  out.g2_scroll_frame_ms = {
    ...st,
    fps_p50: Math.round((1000 / st.p50) * 10) / 10,
    reached_end: frames.reachedEnd,
    criterion: { p50_max: FRAME_P50_MAX_MS, p95_max: FRAME_P95_MAX_MS, source: 'D10-8' },
  };
  const lastIndex = Number(await scroller.locator('tbody tr[aria-rowindex]').last().getAttribute('aria-rowindex'));
  out.g2_last_rendered_rowindex = lastIndex;

  console.log(`T16 ${JSON.stringify(out)}`);
  const dir = path.join(E2E, 'playwright-report');
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, 'perf-results.json'), JSON.stringify(out, null, 2), 'utf-8');

  expect((out.api_first_page_size_50_ms as { p50: number }).p50).toBeLessThan(1000);
  expect(st.p50, `G2 스크롤 프레임 간격 p50 ≤ ${FRAME_P50_MAX_MS}ms(D10-8)`).toBeLessThanOrEqual(FRAME_P50_MAX_MS);
  expect(st.p95, `G2 스크롤 프레임 간격 p95 ≤ ${FRAME_P95_MAX_MS}ms(D10-8)`).toBeLessThanOrEqual(FRAME_P95_MAX_MS);
  // 끝까지 스크롤하면 마지막 행(aria-rowcount)이 보여야 한다 — 전체 행이 화면에 닿는가
  // G2 가 실제로 부르는 첫 페이지(size 1000) 응답도 1 s 이내여야 한다(RA §9 T16 '첫 페이지')
  const timing = resp.request().timing();
  expect.soft(timing.responseEnd - timing.requestStart, 'G2 첫 요청(size 1000) ms').toBeLessThan(1000);
  expect.soft(lastIndex, `G2 마지막 행 ${lastIndex} / aria-rowcount ${rowcount}`).toBe(rowcount);
});
