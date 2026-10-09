import { expect, test } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

test('G1 골격이 MSW 응답으로 렌더된다', async ({ page }) => {
  await page.goto('/');

  // 화면 제목
  await expect(page.getByRole('heading', { level: 1, name: ko.page.G1.title })).toBeVisible();

  // 헤더: RegionPicker가 MSW의 GET /regions 응답으로 채워진다(목 데이터 지역 1개 + "지역 추가")
  const regionSelect = page.getByLabel(ko.header.region);
  await expect(regionSelect.locator('option')).toHaveCount(2);
  await expect(regionSelect.locator('option').last()).toHaveText(ko.header.regionAdd);

  // SnapshotPicker(GET /regions/{id}/snapshots), ScenarioToggle(GET /scenarios)
  await expect(page.getByLabel(ko.header.snapshot).locator('option')).toHaveCount(2);
  await expect(
    page.getByRole('radiogroup', { name: ko.header.scenario }).getByRole('radio'),
  ).toHaveCount(5);

  // D7 고정 문구
  await expect(page.getByText(ko.app.disclaimer)).toBeVisible();
});

test('상황 토글이 URL ?scenario=로 공유된다', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('radio', { name: 'B' }).click();
  await expect(page).toHaveURL(/scenario=sc_B/);
  await page.getByRole('link', { name: ko.nav.G2 }).click();
  await expect(page).toHaveURL(/\/complexes\?.*scenario=sc_B/);
  await expect(page.getByRole('radio', { name: 'B' })).toHaveAttribute('aria-checked', 'true');
});

test('테마 토글이 다크 클래스를 켠다', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: new RegExp(ko.header.theme) }).click();
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  const pressed = await page
    .getByRole('button', { name: new RegExp(ko.header.theme) })
    .getAttribute('aria-pressed');
  expect(isDark).toBe(pressed === 'true');
});
