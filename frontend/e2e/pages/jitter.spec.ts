/**
 * R8-JITTER — G2 표가 로드 직후 입력 없이 계속 떨리던 회귀(실데이터 101단지, 데스크톱 ~1800×980, 휠 한 번 굴려야 멈춤).
 *
 * jsdom 은 레이아웃이 없어 못 잡는다 — 실제 브라우저에서 101행(첫 페이지 100 + 이어 받기 1, 이어 받기를 늦춰
 * '100 / 101개 나머지 단지를 불러오는 중…' 구간을 만든다)을 띄우고, **사용자 입력 없이** 프레임마다 표 상태
 * (스크롤 위치·전체 높이·그린 행 범위·첫 행 위치)를 모아 몇 프레임 안에 멈추는지 본다.
 *
 * 떨림의 모양(수정 전): 열 너비가 그린 행들의 내용으로 정해지는 표(auto table layout)라 그린 행 범위가 바뀌면 열 너비 →
 * 줄바꿈 → 행 높이(실측)가 바뀌고, 그 높이로 다시 계산한 범위가 또 바뀌어 두 상태(12행 ↔ 13행)를 매 프레임 오갔다.
 * 가운데쯤에서는 위쪽 행 높이 보정(scrollTop 조정)까지 끼어 scrollTop 이 계속 흘렀다.
 */
import { expect, test, type Locator, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

const P = ko.page;
/** 표본 프레임 수(60Hz ≈ 1.5초) */
const FRAMES = 90;
/** 이 프레임 안에 멈춰야 한다(실측·열 너비 정착에 몇 프레임은 준다) */
const SETTLE_FRAMES = 20;
/** 이어 받기 지연 — 첫 표본 동안 '나머지 단지를 불러오는 중…' 이 떠 있게 */
const MORE_DELAY_MS = 6_000;

interface Sampled {
  /** 프레임별 표 상태 서명 */
  sigs: string[];
  /** 정착 뒤(SETTLE_FRAMES 부터) 서명이 바뀐 횟수 */
  changesAfterSettle: number;
  /** 전체 구간 서로 다른 서명 수 */
  distinct: number;
}

/** 입력 없이 FRAMES 프레임 동안 표 상태를 모은다 */
async function sample(scroller: Locator): Promise<Sampled> {
  const sigs = await scroller.evaluate(async (el, frames) => {
    const raf = () => new Promise<number>((resolve) => requestAnimationFrame(resolve));
    const out: string[] = [];
    for (let i = 0; i < frames; i += 1) {
      await raf();
      const rows = el.querySelectorAll('tbody tr[aria-rowindex]');
      const first = rows[0];
      const last = rows[rows.length - 1];
      const top = first
        ? Math.round(first.getBoundingClientRect().top - el.getBoundingClientRect().top)
        : -1;
      out.push(
        [
          Math.round(el.scrollTop),
          el.scrollHeight,
          first?.getAttribute('aria-rowindex'),
          last?.getAttribute('aria-rowindex'),
          top,
        ].join('|'),
      );
    }
    return out;
  }, FRAMES);
  let changesAfterSettle = 0;
  for (let i = SETTLE_FRAMES; i < sigs.length; i += 1) {
    if (sigs[i] !== sigs[i - 1]) changesAfterSettle += 1;
  }
  return { sigs, changesAfterSettle, distinct: new Set(sigs).size };
}

function describe(s: Sampled): string {
  return `정착 뒤 변화 ${s.changesAfterSettle}/${FRAMES - SETTLE_FRAMES}, 서로 다른 상태 ${s.distinct} — ${s.sigs
    .slice(-6)
    .join(' → ')}`;
}

async function open(page: Page, suffix: string | null): Promise<Locator> {
  await page.addInitScript(
    ([delay, tail]) => {
      window.localStorage.setItem('msw.complexes.rows', '101');
      window.localStorage.setItem('msw.complexes.moreDelayMs', delay);
      if (tail) window.localStorage.setItem('msw.complexes.nameSuffix', tail);
    },
    [String(MORE_DELAY_MS), suffix] as const,
  );
  await page.goto('/complexes?scenario=base');
  await expect(page.getByRole('heading', { level: 1, name: P.G2.title })).toBeVisible();
  const table = page.getByRole('table', { name: P.G2.table });
  await expect(table.locator('tbody tr[aria-rowindex]').first()).toBeVisible();
  return page.getByTestId('complex-table-scroll');
}

const CASES = [
  { name: '1800×980 예시 행', viewport: { width: 1800, height: 980 }, suffix: null },
  { name: '1600×900 예시 행', viewport: { width: 1600, height: 900 }, suffix: null },
  { name: '1800×980 긴 이름', viewport: { width: 1800, height: 980 }, suffix: '센트럴파크 2단지' },
  { name: '1440×900 긴 이름', viewport: { width: 1440, height: 900 }, suffix: '센트럴파크 2단지' },
] as const;

for (const c of CASES) {
  test.describe(`R8-JITTER G2 101행 입력 없이 멈춤 — ${c.name}`, () => {
    test.use({ viewport: c.viewport });

    test('이어 받는 중 · 다 받은 뒤 · 가운데 · 끝: 몇 프레임 안에 멈추고 보이는 행이 계속 바뀌지 않는다', async ({
      page,
    }, testInfo) => {
      test.slow();
      const scroller = await open(page, c.suffix);
      const report: string[] = [];
      const check = (phase: string, s: Sampled) => {
        report.push(`${phase}: ${describe(s)}`);
        expect.soft(s.changesAfterSettle, `${phase}: ${describe(s)}`).toBe(0);
      };

      // 1) 맨 위, 이어 받기 중('100 / 101개 나머지 단지를 불러오는 중…')
      await expect(page.getByText(P.G2.loadingMore)).toBeVisible();
      check('맨 위·이어 받는 중', await sample(scroller));
      await expect(page.getByText(P.G2.loadingMore)).toBeVisible();

      // 2) 맨 위, 다 받은 뒤(101 / 101)
      await expect(page.getByText(/101 \/ 101/)).toBeVisible({ timeout: 30_000 });
      check('맨 위·다 받은 뒤', await sample(scroller));

      // 3) 가운데로 한 번 옮긴 뒤(프로그램 스크롤 1회 — 이후 입력 없음)
      await scroller.evaluate((el) => {
        el.scrollTop = 1500;
      });
      check('가운데', await sample(scroller));

      // 4) 끝으로 한 번 옮긴 뒤
      await scroller.evaluate((el) => {
        el.scrollTop = el.scrollHeight;
      });
      check('끝', await sample(scroller));

      testInfo.annotations.push({ type: 'R8-JITTER', description: report.join(' | ') });
      console.log(`[${c.name}] ${report.join('\n  ')}`);
    });
  });
}
