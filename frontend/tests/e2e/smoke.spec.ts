import { expect as baseExpect, test } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

// 첫 접속은 dev 서버가 화면 청크를 변환하느라 느리다(지연 로드 라우트) — 기본 5초 대신 20초
const expect = baseExpect.configure({ timeout: 20_000 });
test.describe.configure({ timeout: 60_000 });

test('G1 골격이 MSW 응답으로 렌더된다', async ({ page }) => {
  await page.goto('/');

  // 화면 제목
  await expect(page.getByRole('heading', { level: 1, name: ko.page.G1.title })).toBeVisible();

  // 헤더: RegionPicker가 MSW의 GET /regions 응답으로 채워진다(계약 예시 지역 1개 + "지역 추가")
  const regionSelect = page.getByLabel(ko.header.region);
  await expect(regionSelect.locator('option')).toHaveCount(2);
  await expect(regionSelect.locator('option').last()).toHaveText(ko.header.regionAdd);

  // SnapshotPicker(GET /regions/{id}/snapshots — 계약 예시 3개), ScenarioToggle(GET /scenarios — 내장 5개)
  await expect(page.getByLabel(ko.header.snapshot).locator('option')).toHaveCount(3);
  await expect(
    page.getByRole('radiogroup', { name: ko.header.scenario }).getByRole('radio'),
  ).toHaveCount(5);

  // D7 고정 문구
  await expect(page.getByText(ko.app.disclaimer)).toBeVisible();
});

test('상황 토글이 URL ?scenario=로 공유된다(내장 시나리오 = code)', async ({ page }) => {
  await page.goto('/');
  const b = page.getByRole('radio', { name: /^B / });
  await b.click();
  await expect(page).toHaveURL(/scenario=B(&|$)/);
  await page.getByRole('link', { name: ko.nav.G2 }).click();
  await expect(page).toHaveURL(/\/complexes\?.*scenario=B(&|$)/);
  await expect(page.getByRole('radio', { name: /^B / })).toHaveAttribute('aria-checked', 'true');
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
