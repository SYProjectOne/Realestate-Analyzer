import { expect, test, type Locator, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

/**
 * WP6b 완료 기준: 차트 10개 × (정상·빈·특수) 스크린샷 + 라벨 배지·빈 상태 확인.
 * 라우트(`/__charts`, WP6a) 등록 전이라 테스트 전용 엔트리 html(src/charts/gallery/gallery.html)을 연다.
 * 기준 이미지 갱신: `npx playwright test charts-gallery --update-snapshots`
 */
const GALLERY = '/src/charts/gallery/gallery.html';
const CHARTS = ['C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10'] as const;
const STATES = ['normal', 'empty', 'special'] as const;
const SHOT = { maxDiffPixelRatio: 0.02, animations: 'disabled' } as const;

async function openGallery(page: Page, theme: 'light' | 'dark' = 'light') {
  await page.addInitScript((value) => {
    try {
      window.localStorage.setItem('sa.theme', value);
    } catch {
      // 무시
    }
  }, theme);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(GALLERY);
  await expect(page.getByRole('heading', { level: 1, name: ko.chart.gallery.title })).toBeVisible();
}

/** 카드를 화면에 넣어 lazy 차트를 마운트시키고, 차트가 SVG로 그려질 때까지 기다린다. */
async function settle(card: Locator) {
  await card.scrollIntoViewIfNeeded();
  const charts = card.getByTestId('echart');
  const n = await charts.count();
  for (let i = 0; i < n; i += 1) {
    // 차트마다 뷰포트에 넣어야 IntersectionObserver가 lazy 마운트한다
    await charts.nth(i).scrollIntoViewIfNeeded();
    await expect(charts.nth(i).locator('svg').first()).toBeVisible();
  }
  await expect(card.getByText(ko.chart.notRendered)).toHaveCount(0);
}

for (const id of CHARTS) {
  for (const state of STATES) {
    test(`${id} ${state}`, async ({ page }) => {
      await openGallery(page);
      const card = page.getByTestId(`gallery-${id}-${state}`);
      await settle(card);
      if (state === 'empty') {
        // 빈 데이터 → 차트 대신 빈 상태 문구(role=status)
        await expect(card.getByRole('status')).toBeVisible();
        await expect(card.getByTestId('echart')).toHaveCount(0);
      } else {
        // 라벨·상태는 색이 아니라 텍스트 배지(D7)
        await expect(card.locator('[data-testid$="badge"]').first()).toBeVisible();
      }
      await expect(card).toHaveScreenshot(`${id}-${state}.png`, SHOT);
    });
  }
}

test('C07 escaped: 막대 대신 판정기 질문 텍스트(HTML 이스케이프)', async ({ page }) => {
  await openGallery(page);
  const card = page.getByTestId('gallery-C07-escaped');
  await settle(card);
  await expect(card.getByRole('status')).toContainText(ko.chart.C07.escape);
  await expect(card.getByRole('status')).toContainText('<b>단지 A</b>');
});

test.describe('서비스 워커(MSW)를 막아도 갤러리는 그려진다(9차 리뷰 m19 C05 부하 시간 초과)', () => {
  // 원인: 갤러리 엔트리가 MSW 시작(목 핸들러 동적 import + 서비스 워커 등록·활성)을 기다린 뒤에야 렌더했다.
  // 차트 스크린샷 40건은 API 를 부르지 않는데도 매 테스트(새 컨텍스트)마다 서비스 워커 설치를 기다려, 부하에서
  // 제목 5초를 넘겼다. 렌더는 MSW 와 무관해야 한다 — 서비스 워커를 막으면 수정 전에는 제목이 영영 안 나온다.
  test.use({ serviceWorkers: 'block' });

  test('서비스 워커 차단: 제목·차트 카드가 그려진다', async ({ page }) => {
    await openGallery(page);
    const card = page.getByTestId('gallery-C05-normal');
    await settle(card);
    await expect(card.locator('[data-testid$="badge"]').first()).toBeVisible();
  });
});

test('표로 보기: 차트 데이터를 표로 열고 Fact 셀 → 출처 패널', async ({ page }) => {
  await openGallery(page);
  // 출처 패널은 MSW 응답이 필요하다 — 렌더와 따로 시작한 MSW 가 준비될 때까지 기다린다
  await expect(page.locator('html')).toHaveAttribute('data-msw', 'ready');
  const card = page.getByTestId('gallery-C02-normal');
  await settle(card);
  await card.getByRole('button', { name: ko.table.show }).click();
  await expect(card.getByRole('table')).toBeVisible();
  await card.getByRole('table').getByRole('button').first().click();
  await expect(page.getByRole('dialog', { name: ko.provenance.title })).toBeVisible();
});

for (const id of CHARTS) {
  test(`${id} normal (다크)`, async ({ page }) => {
    await openGallery(page, 'dark');
    expect(await page.evaluate(() => document.documentElement.classList.contains('dark'))).toBe(
      true,
    );
    const card = page.getByTestId(`gallery-${id}-normal`);
    await settle(card);
    await expect(card).toHaveScreenshot(`${id}-normal-dark.png`, SHOT);
  });
}
