/**
 * WP6a 완료 기준 — Playwright(MSW): 화면 10개 핵심 요소, 숫자 셀 → 출처 패널,
 * G2 2,500행 가상 스크롤(W8·W9 — 프레임 간격 T16 은 perf.spec.ts), 다크 테마, 모바일 읽기 전용, 차트 실제 렌더(SVG).
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };

const P = ko.page;

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

test.describe('화면 10개 핵심 요소', () => {
  test('G0 지역 입력: 자동완성 → 후보 선택 → 분석 시작 → 작업 진행', async ({ page }) => {
    await ready(page, '/regions/new', P.G0.title);
    await page.getByRole('searchbox', { name: P.G0.search }).fill('검단');
    const candidates = page.getByRole('list', { name: P.G0.candidates });
    await expect(candidates.getByRole('checkbox').first()).toBeVisible();
    await candidates.getByRole('checkbox').first().check();
    await page.getByLabel(P.G0.name, { exact: true }).fill('e2e 지역');
    await page.getByRole('button', { name: P.G0.start }).click();
    await expect(page.getByText(ko.job.title)).toBeVisible();
  });

  test('G0-2 생활권 편집: 생활권 카드 · 세대수 · 저장', async ({ page }) => {
    await ready(page, '/regions/1/living-areas', P.G0_2.title);
    await expect(page.getByRole('textbox', { name: P.G0_2.areaName }).first()).toBeVisible();
    expect(await page.getByRole('textbox', { name: P.G0_2.areaName }).count()).toBeGreaterThan(1);
    await expect(page.getByRole('button', { name: P.G0_2.save, exact: true })).toBeVisible();
    // D11-7 지역 범위 확장 패널(계약 .8 초안)
    await expect(page.getByRole('region', { name: P.G0_2.expand.title })).toBeVisible();
  });

  test('G1 홈: KPI 5 · TOP 5 · 변경 피드 · C6 차트 SVG', async ({ page }) => {
    await ready(page, '/', P.G1.title);
    await expect(page.getByRole('list', { name: P.G1.kpis }).getByRole('listitem')).toHaveCount(5);
    expect(
      await page.getByRole('list', { name: P.G1.top5 }).getByRole('listitem').count(),
    ).toBeGreaterThanOrEqual(5);
    await expect(page.getByRole('list', { name: P.G1.changes })).toBeVisible();
    const chart = page.getByRole('img', { name: ko.chart.C06.title });
    await chart.scrollIntoViewIfNeeded();
    await expect(chart.locator('svg').first()).toBeVisible();
  });

  test('G2 단지 리스트: 표 · 필터(URL) · CSV', async ({ page }) => {
    await ready(page, '/complexes', P.G2.title);
    const table = page.getByRole('table', { name: P.G2.table });
    await expect(table.locator('tbody tr').first()).toBeVisible();
    await page
      .getByRole('search', { name: P.G2.filters })
      .getByLabel(P.G2.filter.intake_status)
      .selectOption('가능');
    await expect(page).toHaveURL(/intake_status=/);
    // CSV 는 Bearer fetch → Blob 저장(링크 아님)
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: P.G2.csv }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.csv$/);
  });

  test('G3 단지 상세: 탭 8개(해시) · 원문 하이라이트', async ({ page }) => {
    await ready(page, '/complexes/2', P.G3.title);
    const tabs = page.getByRole('tablist', { name: P.G3.tabs }).getByRole('tab');
    await expect(tabs).toHaveCount(8);
    await page.getByRole('tab', { name: P.G3.tab.provenance }).click();
    await expect(page).toHaveURL(/#provenance$/);
    await expect(page.getByTestId('raw-text').locator('mark')).toBeVisible();
  });

  test('G4 비교: 3열 비교 표 · C7', async ({ page }) => {
    await ready(page, '/compare?ids=2,7,4', P.G4.title);
    await expect(
      page.getByRole('table', { name: P.G4.grid }).getByRole('columnheader'),
    ).toHaveCount(4);
    await expect(page.getByText(ko.chart.C07.title)).toBeVisible();
  });

  test('G5 시나리오: 폼 · 슬라이더 6개(합 1) · 요건 표', async ({ page }) => {
    await ready(page, '/scenario?scenario=B', P.G5.title);
    const weights = page.getByRole('group', { name: P.G5.weights });
    await expect(weights.getByRole('slider')).toHaveCount(6);
    await expect(weights.getByTestId('weights-sum')).toContainText('1.00');
    await expect(page.getByRole('table', { name: P.G5.requirements })).toBeVisible();
  });

  test('G6 지역 시장: C3·C4·C5·C9 · 규제 카드', async ({ page }) => {
    await ready(page, '/market', P.G6.title);
    for (const title of [
      ko.chart.C03.title,
      ko.chart.C04.title,
      ko.chart.C05.title,
      ko.chart.C09.title,
    ]) {
      await expect(page.getByText(title, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByRole('heading', { name: P.G6.regulation })).toBeVisible();
  });

  test('G7 데이터·운영: 소스 상태 · 사람 확인 → 배지 갱신 + 재판정 토스트', async ({ page }) => {
    await ready(page, '/ops', P.G7.title);
    await expect(page.getByRole('table', { name: P.G7.sources })).toBeVisible();
    const form = page.getByRole('form', { name: P.G7.human });
    const complex = form.getByLabel(P.G7.hc.complex);
    await expect(complex.locator('option').nth(1)).toBeAttached();
    await complex.selectOption({ index: 1 });
    await form.getByLabel(P.G7.hc.value).selectOption('가능');
    await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
    await form.getByRole('button', { name: P.G7.hc.submit }).click();
    await expect(form.getByTestId('human-check-result')).toContainText(ko.intake.path.human_check);
    await expect(
      page
        .getByRole('region', { name: ko.app.notifications })
        .getByRole('button', { name: P.G7.rejudge }),
    ).toBeVisible();
  });

  test('G8 보고서: 생성 버튼 · 목록 · 다운로드', async ({ page }) => {
    await ready(page, '/reports', P.G8.title);
    await expect(page.getByRole('button', { name: P.G8.generate })).toBeEnabled();
    const list = page.getByRole('table', { name: P.G8.list });
    await expect(list).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      list.getByRole('button').first().click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^report_/);
  });
});

test.describe('R3 F3 화면(계약 2026-10-09.4)', () => {
  test('G7 contradicted 주장 문장 수정 → claim.reverify 잡 진행', async ({ page }) => {
    await ready(page, '/ops', P.G7.title);
    const section = page.getByRole('region', { name: P.G7.claims.title });
    const item = section.getByTestId('claim-6990');
    await expect(item.getByText(P.G7.claims.remaining)).toBeVisible();
    await item.getByLabel(P.G7.claims.revise).fill('고친 문장이다.');
    await item.getByRole('button', { name: P.G7.claims.submit }).click();
    await expect(item.getByTestId('claim-job')).toContainText('claim.reverify');
  });

  test('G7 공유 링크 발급 → /share#토큰 으로 들어오면 읽기 전용', async ({ page }) => {
    await ready(page, '/ops', P.G7.title);
    const section = page.getByRole('region', { name: P.G7.share.title });
    await section.getByLabel(P.G7.share.label).fill('검토 요청');
    await section.getByRole('button', { name: P.G7.share.create }).click();
    const link = section.getByTestId('share-created').getByRole('textbox');
    await expect(link).toHaveValue(/\/share#.+/);
    const url = await link.inputValue();
    await page.goto(url);
    await expect(page.getByRole('heading', { level: 1, name: P.G1.title })).toBeVisible();
    await expect(page).toHaveURL(/\/$/);
    expect(new URL(page.url()).hash).toBe('');
    await expect(page.getByTestId('readonly-banner')).toBeVisible();
  });

  test('G6 호재 URL 입력 → 후보 저장 + 분류 잡', async ({ page }) => {
    await ready(page, '/market', P.G6.title);
    const form = page.getByRole('form', { name: P.G6.catalyst.title });
    await form.getByLabel(P.G6.catalyst.url).fill('https://www.example-news.kr/article/1');
    await form.getByLabel(P.G6.catalyst.titleField).fill('e2e 호재');
    await form.getByRole('button', { name: P.G6.catalyst.submit }).click();
    await expect(page.getByTestId('catalyst-created')).toContainText('e2e 호재');
  });
});

test('숫자 셀 클릭 → 출처 패널', async ({ page }) => {
  await ready(page, '/', P.G1.title);
  const card = page.getByRole('list', { name: P.G1.top5 }).getByRole('listitem').first();
  await card.locator('button[data-prov]').first().click();
  const dialog = page.getByRole('dialog', { name: ko.provenance.title });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(ko.provenance.url)).toBeVisible();
  await expect(page).toHaveURL(/\/(\?.*)?$/);
});

test('G2 1,000행 넘는 목록: 첫 페이지 먼저, 나머지 이어 받아 마지막 행까지(W8·W9)', async ({
  page,
}) => {
  await page.addInitScript(() => window.localStorage.setItem('msw.complexes.rows', '2500'));
  await ready(page, '/complexes', P.G2.title);
  const table = page.getByRole('table', { name: P.G2.table });
  await expect(table).toHaveAttribute('aria-rowcount', '2501');
  await expect(table.locator('tbody tr[aria-rowindex]').first()).toBeVisible();
  await expect(page.getByText(/2,500 \/ 2,500/)).toBeVisible({ timeout: 30_000 });
  expect(await table.locator('tbody tr[aria-rowindex]').count()).toBeLessThan(100);
  await page.getByTestId('complex-table-scroll').evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(table.locator('tr[aria-rowindex="2501"]')).toBeVisible();
  expect(await table.locator('tbody tr[aria-rowindex]').count()).toBeLessThan(100);
});

test('다크 테마: html.dark + 배경색 전환', async ({ page }) => {
  await ready(page, '/', P.G1.title);
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.getByRole('button', { name: new RegExp(ko.header.theme) }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  const after = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(after).not.toBe(before);
});

test.describe('모바일(≤768px)', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('G1·G2·G3 읽기 전용, G7은 데스크톱 안내', async ({ page }) => {
    await ready(page, '/', P.G1.title);
    await expect(page.getByText(ko.app.mobileReadOnly)).toBeVisible();
    await ready(page, '/complexes', P.G2.title);
    await expect(
      page.getByRole('table', { name: P.G2.table }).locator('tbody tr').first(),
    ).toBeVisible();
    await expect(page.getByRole('table', { name: P.G2.table }).getByRole('checkbox')).toHaveCount(
      0,
    );
    await expect(page.getByRole('complementary', { name: P.G2.tray })).toHaveCount(0);
    await ready(page, '/ops', P.G7.title);
    await expect(page.getByText(ko.app.mobileUnsupported)).toBeVisible();
  });
});

test('차트 갤러리 라우트(/__charts, dev)', async ({ page }) => {
  await ready(page, '/__charts', ko.chart.gallery.title);
});
