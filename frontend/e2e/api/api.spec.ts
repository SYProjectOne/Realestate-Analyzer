/**
 * WP5 완료 기준 — 프론트 연결 스모크(MSW 끔, 실제 API + devseed 픽스처): G1·G2·G3 각 1개.
 * 화면이 부르는 API 응답이 전부 2xx 이고(계약 위반·출처 누락이면 4xx/5xx), 픽스처 값이 화면에 나온다.
 */
import { expect, test, type Page, type Response } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

const P = ko.page;

function watchApi(page: Page): Response[] {
  const failed: Response[] = [];
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) failed.push(r);
  });
  return failed;
}

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

test('G1 홈: 실제 API 대시보드 — 지역 현황 4 · TOP 5(그란테르 1위) · 변경 피드', async ({
  page,
}) => {
  const failed = watchApi(page);
  await ready(page, '/', P.G1.title);
  await expect(page.getByRole('list', { name: P.G1.region }).locator(':scope > li')).toHaveCount(4);
  const top5 = page.getByRole('list', { name: P.G1.top5 }).getByRole('listitem');
  await expect(top5.first()).toContainText('더샵 송도그란테르');
  expect(await top5.count()).toBeGreaterThanOrEqual(5);
  await expect(page.getByRole('list', { name: P.G1.changes })).toBeVisible();
  expect(failed.map((r) => `${r.status()} ${r.url()}`)).toEqual([]);
});

test('G2 단지 리스트: 실제 API 16단지 · 접수 필터', async ({ page }) => {
  const failed = watchApi(page);
  await ready(page, '/complexes', P.G2.title);
  const table = page.getByRole('table', { name: P.G2.table });
  await expect(table.locator('tbody tr').first()).toBeVisible();
  await expect(table).toContainText('엘리프 검단 포레듀');
  await page
    .getByRole('search', { name: P.G2.filters })
    .getByLabel(P.G2.filter.intake_status)
    .selectOption('가능');
  await expect(page).toHaveURL(/intake_status=/);
  await expect(table).not.toContainText('더샵 송도그란테르'); // 접수 '불가' 단지는 빠진다
  expect(failed.map((r) => `${r.status()} ${r.url()}`)).toEqual([]);
});

test('G3 단지 상세: 실제 API — 탭 7개(D28-3) · 원문 하이라이트', async ({ page }) => {
  const failed = watchApi(page);
  await ready(page, '/complexes/2', P.G3.title);
  await expect(page.getByText('엘리프 검단 포레듀').first()).toBeVisible();
  const tabs = page.getByRole('tablist', { name: P.G3.tabs }).getByRole('tab');
  await expect(tabs).toHaveCount(7);
  await page.getByRole('tab', { name: P.G3.tab.provenance }).click();
  await expect(page).toHaveURL(/#provenance$/);
  await expect(page.getByTestId('raw-text').locator('mark')).toBeVisible();
  expect(failed.map((r) => `${r.status()} ${r.url()}`)).toEqual([]);
});
