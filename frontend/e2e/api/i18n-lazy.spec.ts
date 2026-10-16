/**
 * R11-I18N 실 API e2e(vite dev, MSW 끔 — 문자열 이름공간을 라우트마다 지연 로드하는 운영과 같은 경로):
 * 화면 10개 + 용어 사전을 처음 연 화면으로도, 앱 안 이동으로도 열어 키 노출('page.G3.…' 같은 글자)과
 * dev 경고 '[i18n] missing key' 가 0건인지 본다.
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { rawKeysIn } from '../../scripts/lib/raw-keys';

const SCREENS: [string, string][] = [
  ['/regions/new', ko.page.G0.title],
  ['/regions/1/living-areas', ko.page.G0_2.title],
  ['/', ko.page.G1.title],
  ['/complexes', ko.page.G2.title],
  ['/complexes/2', ko.page.G3.title],
  ['/compare?ids=2,7,4', ko.page.G4.title],
  ['/scenario', ko.page.G5.title],
  ['/market', ko.page.G6.title],
  ['/ops', ko.page.G7.title],
  ['/reports', ko.page.G8.title],
  ['/glossary', ko.glossary.heading],
];

function watchMissing(page: Page): string[] {
  const missing: string[] = [];
  page.on('console', (msg) => {
    if (msg.text().includes('[i18n] missing key')) missing.push(msg.text());
  });
  return missing;
}

async function settled(page: Page): Promise<string> {
  await expect(page.locator('h1').first()).toBeVisible();
  await page.waitForLoadState('networkidle');
  return page.locator('body').innerText();
}

for (const [path] of SCREENS) {
  test(`처음 연 화면 ${path}: 키 노출·missing key 0건`, async ({ page }) => {
    const missing = watchMissing(page);
    await page.goto(path);
    const text = await settled(page);
    expect(rawKeysIn(text)).toEqual([]);
    expect(missing).toEqual([]);
  });
}

test('앱 안 이동(G1 → 단지 → 비교 → 용어): 이름공간을 이동마다 받아도 키 노출 0건', async ({
  page,
}) => {
  const missing = watchMissing(page);
  await page.goto('/');
  expect(rawKeysIn(await settled(page))).toEqual([]);
  for (const path of ['/complexes/2', '/compare?ids=2,7,4', '/ops', '/glossary']) {
    await page.evaluate((to) => {
      window.history.pushState({}, '', to);
      window.dispatchEvent(new PopStateEvent('popstate'));
    }, path);
    const title = SCREENS.find(([p]) => p === path)?.[1] ?? '';
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
    expect(rawKeysIn(await settled(page)), path).toEqual([]);
  }
  expect(missing).toEqual([]);
});
