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

  test('G1 홈: 지금 접수 가능 · 지역 현황 4 · TOP 5 · 변경 피드 · C6 차트 SVG', async ({
    page,
  }) => {
    await ready(page, '/', P.G1.title);
    await expect(page.getByRole('list', { name: P.G1.region }).getByRole('listitem')).toHaveCount(
      4,
    );
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

  test('G3 단지 상세: 탭 7개(해시, D28-3) · 원문 하이라이트', async ({ page }) => {
    await ready(page, '/complexes/2', P.G3.title);
    const tabs = page.getByRole('tablist', { name: P.G3.tabs }).getByRole('tab');
    await expect(tabs).toHaveCount(7);
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
    await expect(page.getByRole('region', { name: P.G6.regulation })).toBeVisible();
  });

  test('G7 데이터·운영: 소스 상태 · 사람 확인 → 배지 갱신 + 자동 등록 재판정 진행', async ({
    page,
  }) => {
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
    // 계약 .9: 재판정은 서버가 자동 등록(rejudge_job_id) — 화면은 진행만, 토스트 버튼 없음
    await expect(form.getByTestId('human-check-job')).toContainText(ko.job.title);
    await expect(
      page
        .getByRole('region', { name: ko.app.notifications })
        .getByRole('button', { name: P.G7.rejudge }),
    ).toHaveCount(0);
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
    await expect(item.getByTestId('claim-job')).toContainText(ko.job.name.claim_reverify);
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

test.describe('R7-QUEUE 화면(계약 2026-10-09.19 · D26-2)', () => {
  test('G7 접수 확인 대기열: 사유별 건수 → 사람 확인 입력(폼 미리 채움) → 저장 → 반영 대기', async ({
    page,
  }) => {
    await ready(page, '/ops', P.G7.title);
    const section = page.getByRole('region', { name: P.G7.iq.title });
    await section.scrollIntoViewIfNeeded();
    await expect(section.getByTestId('intake-queue-total')).toHaveText(
      P.G7.iq.total.replace('{n}', '7'),
    );
    const failed = section.getByTestId('iq-category-collect_failed');
    await expect(failed.locator('summary')).toContainText(P.G7.iq.category.collect_failed);
    await expect(failed.getByTestId('iq-group').first()).toContainText('DNS');
    // 판정 대상 아님·미정은 접혀 있다
    await expect(section.getByTestId('iq-category-undecided')).not.toHaveAttribute('open');
    await expect(failed).toHaveAttribute('open');
    const opus = section.locator('[data-testid="iq-item"][data-complex-id="4"]');
    await expect(opus.getByRole('link', { name: '오퍼스 한강 스위첸' })).toHaveAttribute(
      'href',
      /^\/complexes\/4/,
    );
    await opus.getByTestId('iq-human-check').click();
    await expect(page).toHaveURL(/hc_complex=4/);
    await expect(page).toHaveURL(/#human-check$/);
    const form = page.getByRole('form', { name: P.G7.human });
    await expect(form.getByLabel(P.G7.hc.complex)).toHaveValue('4');
    await expect(form.getByLabel(P.G7.hc.field)).toHaveValue('intake_status');
    await form.getByLabel(P.G7.hc.value).selectOption('가능');
    await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
    await form.getByRole('button', { name: P.G7.hc.submit }).click();
    await expect(form.getByTestId('human-check-result')).toContainText(ko.intake.path.human_check);
    await expect(opus.getByTestId('iq-pending')).toContainText('가능');
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
    // R9-UI P5: 모바일 G2 는 표 대신 카드(읽기 전용 — 비교 체크 없음)
    const cards = page.getByRole('list', { name: P.G2.cards });
    await expect(cards.getByRole('listitem').first()).toBeVisible();
    await expect(cards.getByRole('checkbox')).toHaveCount(0);
    await expect(page.getByRole('complementary', { name: P.G2.tray })).toHaveCount(0);
    await ready(page, '/ops', P.G7.title);
    await expect(page.getByText(ko.app.mobileUnsupported)).toBeVisible();
  });
});

test('차트 갤러리 라우트(/__charts, dev)', async ({ page }) => {
  await ready(page, '/__charts', ko.chart.gallery.title);
});

test.describe('R5-FE(D25-1) 차트 지연 로딩 · 전역 쿼리 유지', () => {
  // 낮은 창: G6 아래쪽 차트가 확실히 화면 밖(미리 받기 여백 200px 바깥)에 있게
  test.use({ viewport: { width: 1280, height: 600 } });

  test('G6: 화면 밖 차트는 플레이스홀더(SVG 없음) → 스크롤하면 그려진다', async ({ page }) => {
    await ready(page, '/market', P.G6.title);
    const charts = page.getByTestId('echart');
    await expect.poll(() => charts.count()).toBeGreaterThanOrEqual(2);
    await page.waitForLoadState('networkidle');
    const last = charts.last();
    const pos = await last.evaluate((el) => ({
      top: el.getBoundingClientRect().top,
      limit: window.innerHeight + 200,
    }));
    expect(pos.top).toBeGreaterThan(pos.limit);
    // 위쪽 차트가 그려질 시간(지연 청크 도착)이 지나도 아래 차트는 그대로여야 한다
    await expect(charts.first().locator('svg').first()).toBeVisible();
    await page.waitForTimeout(500);
    await expect(last.locator('svg')).toHaveCount(0);
    await expect(last).toContainText(ko.chart.notRendered);

    await last.scrollIntoViewIfNeeded();
    await expect(last.locator('svg').first()).toBeVisible();
    await expect(last).not.toContainText(ko.chart.notRendered);
  });

  test('?scenario=·?snapshot= 가 TOP 5 카드 → G3, 네비 → G2, 표 행 → G3 에서 유지', async ({
    page,
  }) => {
    const keep = (url: URL) => {
      expect(url.searchParams.get('scenario')).toBe('B');
      expect(url.searchParams.get('snapshot')).toBe('11');
    };
    await ready(page, '/?snapshot=11&scenario=B', P.G1.title);
    const card = page.getByRole('list', { name: P.G1.top5 }).getByRole('listitem').first();
    await card.getByRole('link').first().click();
    await expect(page.getByRole('heading', { level: 1, name: P.G3.title })).toBeVisible();
    keep(new URL(page.url()));
    // R11: G3 현재 위치 줄에도 '단지 찾기' 링크가 있다 — 주 메뉴로 좁힌다
    await page
      .getByRole('navigation', { name: ko.nav.label })
      .getByRole('link', { name: ko.nav.G2 })
      .click();
    await expect(page.getByRole('heading', { level: 1, name: P.G2.title })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/complexes');
    keep(new URL(page.url()));
    await page.getByRole('table', { name: P.G2.table }).locator('tbody tr a').first().click();
    await expect(page).toHaveURL(/\/complexes\/\d+\?/);
    keep(new URL(page.url()));
    await expect(page.getByRole('radio', { name: /^B / })).toHaveAttribute('aria-checked', 'true');
  });
});

test.describe('R9-UI P4 G2 비교 트레이가 표를 가리지 않는다(00-baseline)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('첫 화면: 표 스크롤 영역 아래 끝 ≤ 비교 트레이 위 끝', async ({ page }) => {
    await ready(page, '/complexes', P.G2.title);
    const scroll = page.getByTestId('complex-table-scroll');
    await expect(scroll.locator('tbody tr[aria-rowindex]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const tray = page.getByRole('complementary', { name: P.G2.tray });
    const s = await scroll.boundingBox();
    const tb = await tray.boundingBox();
    expect(s && tb).toBeTruthy();
    expect((s?.y ?? 0) + (s?.height ?? 0)).toBeLessThanOrEqual((tb?.y ?? 0) + 1);
  });
});

test.describe('R9-UI P4 G2 첫 화면 행 수(30-proposal §13-1 목표)', () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test('1440×900: 트레이 위까지 온전히 보이는 행 ≥ 6', async ({ page }) => {
    await ready(page, '/complexes', P.G2.title);
    const scroll = page.getByTestId('complex-table-scroll');
    await expect(scroll.locator('tbody tr[aria-rowindex]').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const n = await page.evaluate(() => {
      const box = document
        .querySelector('[data-testid="complex-table-scroll"]')!
        .getBoundingClientRect();
      const tray =
        document.querySelector('aside')?.getBoundingClientRect().top ?? window.innerHeight;
      const limit = Math.min(box.bottom, tray, window.innerHeight);
      return [...document.querySelectorAll('tbody tr[aria-rowindex]')].filter((tr) => {
        const r = tr.getBoundingClientRect();
        return r.top >= box.top && r.bottom <= limit;
      }).length;
    });
    expect(n).toBeGreaterThanOrEqual(6);
  });
});

test.describe('R9-UI P5 G2 모바일 카드(30-proposal §13-1 목표)', () => {
  test.use({ viewport: { width: 420, height: 900 }, isMobile: true, hasTouch: true });

  test('420×900: 첫 화면에 카드 2장 이상이 보이기 시작하고, 카드마다 구매가·전매 종료 + 가로 넘침 없음', async ({
    page,
  }) => {
    await ready(page, '/complexes', P.G2.title);
    const cards = page.getByRole('list', { name: P.G2.cards }).getByRole('listitem');
    await expect(cards.first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const tops = await cards.evaluateAll((els) => els.map((el) => el.getBoundingClientRect().top));
    expect(tops.filter((top) => top < 900).length).toBeGreaterThanOrEqual(2);
    for (const i of [0, 1]) {
      await expect(cards.nth(i).locator('[data-field="price"] [data-prov]').first()).toBeVisible();
      await expect(cards.nth(i).locator('[data-field="status"]')).toContainText(
        ko.page.G2.card.resaleEnd,
      );
    }
    const { sw, iw } = await page.evaluate(() => ({
      sw: document.scrollingElement?.scrollWidth ?? 0,
      iw: window.innerWidth,
    }));
    expect(sw).toBeLessThanOrEqual(iw);
  });
});

test.describe('R9-UI P3 가로 넘침 없음(00-baseline 레이아웃 결함)', () => {
  for (const [name, width] of [
    ['데스크톱 1440', 1440],
    ['모바일 420', 420],
  ] as const) {
    test(`G1 ${name}: 문서 가로 폭 ≤ 창 폭`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await ready(page, '/', P.G1.title);
      await page.waitForLoadState('networkidle');
      const { sw, iw } = await page.evaluate(() => ({
        sw: document.scrollingElement?.scrollWidth ?? 0,
        iw: window.innerWidth,
      }));
      expect(sw).toBeLessThanOrEqual(iw);
    });
  }
});
