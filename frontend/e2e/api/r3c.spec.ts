/**
 * R3c(3차 리뷰) 실데이터 화면 확인 — MSW 없이 devseed DB 위 실제 API.
 *  - T3: 스위첸 공식 홈페이지 403 → 화면 문구 "확인 불가(403, <확인일>)" (G2 리스트·G3 헤더)
 *  - T18: 판정기 다운 스냅샷(degraded) → G1·G7 배너. 최신 스냅샷이면 /health judge=degraded("판정기 장애"),
 *    과거 스냅샷만이면 그 기준일을 고를 때 "이 기준일 스냅샷은 미판정 모드" 배너.
 *  - delta_rerank·실거래 건수: 라벨 없는 숫자가 아니라 FactCell(라벨 배지)
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { setSnapshotDegraded } from './env';

const P = ko.page;
const SWITZEN = '오퍼스 한강 스위첸';
/** devseed 픽스처 스냅샷: 11 = 2026-10-07(과거), 12 = 2026-10-08(최신) */
const PAST = 11;
const LATEST = 12;

function watchApi(page: Page): string[] {
  const failed: string[] = [];
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/') && r.status() >= 400)
      failed.push(`${r.status()} ${r.request().method()} ${url.pathname}`);
  });
  return failed;
}

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

const UNKNOWN_403 = /확인 불가\(403, \d{4}-\d{2}-\d{2}\)/;

test.describe('T3 실데이터 문구: 공식 홈페이지 403', () => {
  test('G3 스위첸 헤더 접수 배지 = "확인 불가(403, 날짜)"', async ({ page }) => {
    const failed = watchApi(page);
    await ready(page, '/complexes/4', P.G3.title);
    const badge = page.getByRole('region', { name: SWITZEN }).getByTestId('intake-badge');
    await expect(badge).toContainText(UNKNOWN_403);
    await expect(badge).toContainText(ko.intake.path.official_popup);
    expect(failed).toEqual([]);
  });

  test('G2 리스트 스위첸 행 접수 = "확인 불가(403, 날짜)"', async ({ page }) => {
    const failed = watchApi(page);
    await ready(page, '/complexes', P.G2.title);
    const row = page
      .getByRole('table', { name: P.G2.table })
      .locator('tbody tr', { hasText: SWITZEN });
    await expect(row.getByTestId('intake-badge')).toContainText(UNKNOWN_403);
    expect(failed).toEqual([]);
  });
});

test.describe.serial('T18 판정기 다운(degraded) 배너', () => {
  test.afterEach(() => {
    setSnapshotDegraded(PAST, false);
    setSnapshotDegraded(LATEST, false);
  });

  test('정상 데이터에서는 배너 없음', async ({ page }) => {
    await ready(page, '/', P.G1.title);
    await expect(page.getByRole('list', { name: P.G1.region })).toBeVisible();
    await expect(page.getByTestId('degraded-banner')).toHaveCount(0);
  });

  test('최신 스냅샷 degraded → /health judge=degraded → G1·G7 "판정기 장애" 배너', async ({
    page,
  }) => {
    setSnapshotDegraded(LATEST, true);
    const health = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/health');
    await ready(page, '/', P.G1.title);
    expect(await (await health).json()).toMatchObject({ judge: 'degraded' });
    await expect(page.getByTestId('degraded-banner')).toHaveText(ko.app.degraded);
    await ready(page, '/ops', P.G7.title);
    await expect(page.getByTestId('degraded-banner')).toHaveText(ko.app.degraded);
  });

  test('과거 스냅샷만 degraded → 그 기준일을 고르면 "미판정 모드 스냅샷" 배너, 최신은 없음', async ({
    page,
  }) => {
    setSnapshotDegraded(PAST, true);
    await ready(page, `/?snapshot=${PAST}`, P.G1.title);
    await expect(page.getByTestId('degraded-banner')).toHaveText(ko.app.degradedSnapshot);
    await ready(page, `/ops?snapshot=${PAST}`, P.G7.title);
    await expect(page.getByTestId('degraded-banner')).toHaveText(ko.app.degradedSnapshot);
    await ready(page, `/?snapshot=${LATEST}`, P.G1.title);
    await expect(page.getByRole('list', { name: P.G1.region })).toBeVisible();
    await expect(page.getByTestId('degraded-banner')).toHaveCount(0);
  });
});

test('G6 실거래 건수·G4 rerank 변화는 라벨 배지가 붙은 FactCell', async ({ page }) => {
  const failed = watchApi(page);
  await ready(page, '/market', P.G6.title);
  const prices = page.getByRole('table', { name: P.G6.prices });
  const rows = prices.locator('tbody tr');
  await expect(rows.first()).toBeVisible();
  // 건수 열(이름 th 다음 4번째 td)
  await expect(rows.first().locator('td').nth(3).getByTestId('label-badge')).toBeVisible();
  await ready(page, '/compare?ids=1,2,3', P.G4.title);
  const delta = page.getByTestId('compare-delta-rerank');
  await expect(delta).toBeVisible();
  await expect(delta.locator('td')).toHaveCount(3);
  expect(failed).toEqual([]);
});
