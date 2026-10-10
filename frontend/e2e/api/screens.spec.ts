/**
 * R2.5 실 API e2e(MSW 끔, devseed DB 위 uvicorn): G0·G4·G5·G6·G7·G8 + Bearer 다운로드 3종(CSV·원문·보고서)·
 * 원문 미리보기(텍스트·PNG)·토큰 다이얼로그(읽기 전용 → 쓰기 버튼 비활성). G1~G3 은 api.spec.ts.
 * 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건(토큰 확인처럼 의도한 응답만 명시적으로 허용).
 */
import { readFile } from 'node:fs/promises';
import { expect, test, type Download, type Page, type Response } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { READ_TOKEN, runWorkerOnce, WRITE_TOKEN } from './env';

const P = ko.page;

interface Allowed {
  status: number;
  method: string;
  path: RegExp;
}

/** /api 응답 중 4xx/5xx 를 모은다. allowed 에 맞는 것(의도한 401·403)은 뺀다. */
function watchApi(page: Page, allowed: Allowed[] = []): string[] {
  const failed: string[] = [];
  page.on('response', (r: Response) => {
    const url = new URL(r.url());
    if (!url.pathname.startsWith('/api/') || r.status() < 400) return;
    const method = r.request().method();
    if (
      allowed.some(
        (a) => a.status === r.status() && a.method === method && a.path.test(url.pathname),
      )
    )
      return;
    failed.push(`${r.status()} ${method} ${url.pathname}${url.search}`);
  });
  return failed;
}

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

async function body(download: Download): Promise<Buffer> {
  const file = await download.path();
  return readFile(file);
}

test('G0 지역 입력: 자유 지명 resolve → 후보 선택 → 분석 시작 활성(POST 없음)', async ({
  page,
}) => {
  const failed = watchApi(page);
  const posts: string[] = [];
  page.on('request', (r) => {
    if (r.method() === 'POST' && r.url().includes('/api/regions')) posts.push(r.url());
  });
  await ready(page, '/regions/new', P.G0.title);
  const resolved = page.waitForResponse(
    (r) => r.url().includes('/api/regions/resolve') && r.status() === 200,
  );
  await page.getByRole('searchbox', { name: P.G0.search }).fill('검단');
  await resolved;
  const candidates = page.getByRole('list', { name: P.G0.candidates });
  await expect(candidates.getByRole('checkbox').first()).toBeVisible();
  await expect(candidates).toContainText('검단');
  await candidates.getByRole('checkbox').first().check();
  await expect(page.getByRole('list', { name: P.G0.selected }).getByRole('button')).toHaveCount(1);
  await page.getByLabel(P.G0.name, { exact: true }).fill('e2e 검단');
  await expect(page.getByRole('button', { name: P.G0.start })).toBeEnabled();
  expect(posts).toEqual([]);
  expect(failed).toEqual([]);
});

test('G4 비교: 실제 API 3단지 비교 표', async ({ page }) => {
  const failed = watchApi(page);
  await ready(page, '/compare?ids=2,7,4', P.G4.title);
  const grid = page.getByRole('table', { name: P.G4.grid });
  await expect(grid.getByRole('columnheader')).toHaveCount(4);
  await expect(grid).toContainText('엘리프 검단 포레듀');
  await expect(grid).toContainText('김포 칸타빌 에디션');
  await expect(page.getByText(ko.chart.C07.title)).toBeVisible();
  expect(failed).toEqual([]);
});

test('G5 시나리오: 미리보기(요건 표·캐시 적중) — 판정기 호출 없음', async ({ page }) => {
  const failed = watchApi(page);
  const preview = page.waitForResponse(
    (r) => /\/api\/scenarios\/\d+\/preview/.test(r.url()) && r.status() === 200,
  );
  await ready(page, '/scenario?scenario=B', P.G5.title);
  await preview;
  const weights = page.getByRole('group', { name: P.G5.weights });
  await expect(weights.getByRole('slider')).toHaveCount(6);
  await expect(weights.getByTestId('weights-sum')).toContainText('1.00');
  const table = page.getByRole('table', { name: P.G5.requirements });
  await expect(table).toBeVisible();
  expect(await table.locator('tbody tr').count()).toBeGreaterThan(0);
  expect(failed).toEqual([]);
});

test('G6 지역 시장: 실제 API 차트 4종 · 규제 카드', async ({ page }) => {
  const failed = watchApi(page);
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
  expect(failed).toEqual([]);
});

test('G8 보고서: 생성(POST) → 워커 1회 → 목록 완료 → Bearer 다운로드', async ({ page }) => {
  const failed = watchApi(page);
  await ready(page, '/reports', P.G8.title);
  await page.getByRole('radio', { name: P.G8.formats.html }).check();
  const created = page.waitForResponse(
    (r) => r.url().endsWith('/api/reports') && r.request().method() === 'POST',
  );
  const generate = page.getByRole('button', { name: P.G8.generate });
  await expect(generate).toBeEnabled();
  await generate.click();
  expect((await created).status()).toBe(202);
  await expect(page.getByText(ko.job.title)).toBeVisible();
  runWorkerOnce();
  const list = page.getByRole('table', { name: P.G8.list });
  const fileButton = list.getByRole('button', { name: /^report_.*\.html$/ }).first();
  await expect(fileButton).toBeVisible({ timeout: 30_000 });
  const [download] = await Promise.all([page.waitForEvent('download'), fileButton.click()]);
  expect(download.suggestedFilename()).toMatch(/^report_\d{4}-\d{2}-\d{2}\.html$/);
  const html = (await body(download)).toString('utf-8');
  expect(html).toMatch(/<html/i);
  expect(html).toContain(ko.app.disclaimer);
  expect(failed).toEqual([]);
});

test('G7 사람 확인 입력 → 결과 배지 · 재판정 → 새 리비전의 단지 상세 접수 배지 갱신', async ({
  page,
}) => {
  const failed = watchApi(page);
  await ready(page, '/ops', P.G7.title);
  await expect(page.getByRole('table', { name: P.G7.sources })).toBeVisible();
  const form = page.getByRole('form', { name: P.G7.human });
  const complex = form.getByLabel(P.G7.hc.complex);
  await expect(complex.locator('option', { hasText: '송도 한내들 센트럴리버' })).toBeAttached();
  await complex.selectOption({ label: '송도 한내들 센트럴리버' });
  await form.getByLabel(P.G7.hc.value).selectOption('미정');
  // 계약 2026-10-09.7: entered_by = 역할 enum(운영자·검토자) — 개인 이름을 받지 않는다
  await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
  );
  await form.getByRole('button', { name: P.G7.hc.submit }).click();
  const res = await saved;
  expect(res.status()).toBe(201);
  // 계약 .8 D11-1: 발행 스냅샷은 불변 — 접수 행은 같은 기준일의 새 리비전(쓰기 가능 스냅샷)에 쓴다
  const created = (await res.json()) as { created_intake: { snapshot_id: number | null } | null };
  const revisionId = created.created_intake?.snapshot_id ?? null;
  expect(revisionId).not.toBeNull();
  const result = form.getByTestId('human-check-result');
  await expect(result).toContainText(ko.intake.path.human_check);
  await expect(result).toContainText(ko.intake.status['미정']);
  const rejudge = page
    .getByRole('region', { name: ko.app.notifications })
    .getByRole('button', { name: P.G7.rejudge });
  await expect(rejudge).toBeVisible();
  // 재판정 제안 → 잡 등록 → worker 1회 → 새 리비전 발행(화면 기본 = 최신 published 리비전)
  const queued = page.waitForResponse(
    (r) => r.url().endsWith('/api/jobs') && r.request().method() === 'POST',
  );
  await rejudge.first().click();
  expect((await queued).status()).toBe(202);
  runWorkerOnce();
  // 단지 상세(기본 = 새 리비전)의 현재 접수 배지가 사람 확인으로 바뀐다
  await ready(page, '/complexes/3', P.G3.title);
  await expect(page.getByLabel(ko.header.snapshot)).toHaveValue(String(revisionId));
  const badge = page
    .getByRole('region', { name: '송도 한내들 센트럴리버' })
    .getByTestId('intake-badge');
  await expect(badge).toContainText(ko.intake.path.human_check);
  expect(failed).toEqual([]);
});

test.describe('Bearer 다운로드·미리보기', () => {
  test('G2 CSV: 같은 필터로 fetch(Bearer) → 파일 저장(BOM·라벨 열)', async ({ page }) => {
    const failed = watchApi(page);
    await ready(page, '/complexes?intake_status=가능', P.G2.title);
    const table = page.getByRole('table', { name: P.G2.table });
    await expect(table.locator('tbody tr').first()).toBeVisible();
    const csvReq = page.waitForRequest((r) => r.url().includes('/complexes.csv'));
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: P.G2.csv }).click(),
    ]);
    const req = await csvReq;
    expect(req.headers()['authorization']).toBe(`Bearer ${WRITE_TOKEN}`);
    expect(decodeURIComponent(req.url())).toContain('filter[intake_status]=가능');
    expect(download.suggestedFilename()).toMatch(/^complexes_.*\.csv$/);
    const text = (await body(download)).toString('utf-8');
    expect(text.charCodeAt(0)).toBe(0xfeff);
    expect(text).toContain('_label');
    expect(text).not.toContain('더샵 송도그란테르'); // 접수 '불가' 단지는 필터로 빠진다
    expect(failed).toEqual([]);
  });

  test('G3 원문: 텍스트 미리보기 + 원문 파일 저장', async ({ page }) => {
    const failed = watchApi(page);
    await ready(page, '/complexes/2#provenance', P.G3.title);
    await expect(page.getByTestId('raw-text').locator('mark')).toBeVisible();
    const raw = page.getByTestId('raw-document').first();
    await raw.getByRole('button', { name: ko.provenance.rawPreview }).click();
    await expect(raw.getByTestId('raw-preview-text')).not.toBeEmpty();
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      raw.getByRole('button', { name: ko.provenance.rawSave }).click(),
    ]);
    expect(download.suggestedFilename()).not.toBe('download');
    expect((await body(download)).length).toBeGreaterThan(0);
    expect(failed).toEqual([]);
  });

  test('G3 접수 근거 원문(PNG): 출처 패널에서 이미지 미리보기', async ({ page }) => {
    const failed = watchApi(page);
    await ready(page, '/complexes/2', P.G3.title);
    await page.getByRole('button', { name: P.G3.header.intakeEvidence }).click();
    const panel = page.getByRole('dialog', { name: ko.provenance.title });
    await expect(panel).toBeVisible();
    const png = page.waitForResponse((r) => /\/api\/raw\/\d+$/.test(new URL(r.url()).pathname));
    await panel.getByRole('button', { name: ko.provenance.rawPreview }).click();
    const res = await png;
    expect(res.headers()['content-type']).toBe('image/png');
    expect(res.request().headers()['authorization']).toBe(`Bearer ${WRITE_TOKEN}`);
    const img = panel.getByTestId('raw-preview-image');
    await expect(img).toBeVisible();
    await expect
      .poll(() => img.evaluate((el) => (el as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0);
    expect(failed).toEqual([]);
  });
});

test.describe('API 토큰', () => {
  test('읽기 전용 토큰 저장 → 안내 배너 · 쓰기 버튼 비활성 · 다운로드는 동작', async ({ page }) => {
    // 토큰 확인(probeToken)의 빈 본문 POST /jobs 403 은 의도한 응답
    const failed = watchApi(page, [{ status: 403, method: 'POST', path: /^\/api\/jobs$/ }]);
    await ready(page, '/', P.G1.title);
    await page.getByTestId('token-button').click();
    const dialog = page.getByRole('dialog', { name: ko.auth.title });
    await dialog.getByLabel(ko.auth.label, { exact: true }).fill(READ_TOKEN);
    await dialog.getByRole('button', { name: ko.auth.save }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByTestId('readonly-banner')).toContainText(ko.auth.readOnlyBanner);
    await expect(page.getByTestId('token-button')).toContainText(ko.auth.state.read);
    expect(await page.evaluate(() => window.localStorage.getItem('sa.token.role'))).toBe('read');

    await page.getByRole('link', { name: ko.nav.G7 }).click();
    await expect(page.getByRole('heading', { level: 1, name: P.G7.title })).toBeVisible();
    const submit = page
      .getByRole('form', { name: P.G7.human })
      .getByRole('button', { name: P.G7.hc.submit });
    await expect(submit).toBeDisabled();
    await expect(submit).toHaveAttribute('title', ko.auth.readOnlyHint);

    await page.getByRole('link', { name: ko.nav.G8 }).click();
    await expect(page.getByRole('heading', { level: 1, name: P.G8.title })).toBeVisible();
    await expect(page.getByRole('button', { name: P.G8.generate })).toBeDisabled();

    await page.getByRole('link', { name: ko.nav.G2 }).click();
    const csvReq = page.waitForRequest((r) => r.url().includes('/complexes.csv'));
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: P.G2.csv }).click(),
    ]);
    expect((await csvReq).headers()['authorization']).toBe(`Bearer ${READ_TOKEN}`);
    expect(download.suggestedFilename()).toMatch(/\.csv$/);
    expect(failed).toEqual([]);
  });

  test('저장된 토큰이 틀리면(401) 다이얼로그 → 쓰기 토큰 입력 → 화면이 다시 뜬다', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      if (!window.sessionStorage.getItem('e2e.seeded')) {
        window.sessionStorage.setItem('e2e.seeded', '1');
        window.localStorage.setItem('sa.token', 'wrong-token');
      }
    });
    // 틀린 토큰의 401 과 토큰 확인(쓰기 토큰 → 빈 본문 POST /jobs 422)은 의도한 응답
    const failed = watchApi(page, [
      { status: 401, method: 'GET', path: /^\/api\// },
      { status: 422, method: 'POST', path: /^\/api\/jobs$/ },
    ]);
    await page.goto('/');
    const dialog = page.getByRole('dialog', { name: ko.auth.title });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(ko.auth.reason.invalid);
    await dialog.getByLabel(ko.auth.label, { exact: true }).fill(WRITE_TOKEN);
    await dialog.getByRole('button', { name: ko.auth.save }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByTestId('token-button')).toContainText(ko.auth.state.write);
    await expect(page.getByRole('list', { name: P.G1.kpis }).getByRole('listitem')).toHaveCount(5);
    await expect(page.getByTestId('readonly-banner')).toHaveCount(0);
    expect(failed).toEqual([]);
  });
});
