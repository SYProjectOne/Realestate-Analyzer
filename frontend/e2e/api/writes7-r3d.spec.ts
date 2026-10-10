/**
 * R3d(4차 리뷰) 실 API e2e(MSW 끔, devseed 테스트 DB 위 uvicorn) — 이 임시 DB 에만 쓴다.
 *  - C-5 G5 실 API: 시나리오 재판정 → worker 1회(rejudge + snapshot.publish) → '이후' 값 = 잡이 쓴 새 리비전
 *    (GET /snapshots/{새 리비전}/dashboard), 이전 대비 표.
 *  - M-15 새로 고침 없는 리비전 전환: 같은 화면에서 잡이 끝나면 헤더 기준일이 새 리비전으로 바뀐다(page.reload 없음).
 *  - M-16 G8 리비전: 보고서 기준·비교 선택이 '기준일 · 리비전 n'으로 구별되고, 새 리비전 기준 보고서 목록 행도 리비전 표기.
 * 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건.
 * 파일 이름 순서: screens(읽기 기대) 뒤, writes8(region.expand 잡을 남김 — worker 로 돌리면 외부 수집) 앞.
 */
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce, WRITE_TOKEN } from './env';

const P = ko.page;

interface SnapshotRow {
  id: number;
  asof_date: string;
  revision?: number;
  status: string;
}

function fill(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => params[k] ?? `{${k}}`);
}

function watchApi(page: Page): string[] {
  const failed: string[] = [];
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/') && r.status() >= 400)
      failed.push(`${r.status()} ${r.request().method()} ${url.pathname}${url.search}`);
  });
  return failed;
}

function seenPaths(page: Page): string[] {
  const paths: string[] = [];
  page.on('request', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/')) paths.push(`${r.method()} ${url.pathname}${url.search}`);
  });
  return paths;
}

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

async function api<T>(request: APIRequestContext, path: string): Promise<T> {
  const res = await request.get(`/api${path}`, {
    headers: { Authorization: `Bearer ${WRITE_TOKEN}` },
  });
  expect(res.status(), path).toBe(200);
  return (await res.json()) as T;
}

/** 지역 1의 최신 published 리비전(기준일 최신 → 리비전 최신) */
async function latestPublished(request: APIRequestContext): Promise<SnapshotRow> {
  const rows = await api<SnapshotRow[]>(request, '/regions/1/snapshots');
  return rows
    .filter((s) => s.status === 'published')
    .sort(
      (a, b) => b.asof_date.localeCompare(a.asof_date) || (b.revision ?? 1) - (a.revision ?? 1),
    )[0]!;
}

const revText = (s: SnapshotRow) =>
  (s.revision ?? 1) > 1
    ? fill(ko.picker.revision, { date: s.asof_date, n: String(s.revision) })
    : s.asof_date;

test.describe.serial('R3d 리비전 화면(실 API)', () => {
  test('C-5·M-15 G5 재판정 → worker → 이후 = 새 리비전, 헤더 기준일이 새로 고침 없이 새 리비전', async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const paths = seenPaths(page);
    const before = await latestPublished(request);
    await ready(page, '/scenario', P.G5.title);
    const picker = page.getByLabel(ko.header.snapshot);
    await expect(picker).toHaveValue(String(before.id));

    const run = page.getByRole('button', { name: P.G5.run });
    await expect(run).toBeEnabled();
    const queued = page.waitForResponse(
      (r) => r.url().endsWith('/api/jobs') && r.request().method() === 'POST',
    );
    await run.click();
    const post = await queued;
    expect(post.status()).toBe(202);
    expect(post.request().postDataJSON()).toMatchObject({
      job_name: 'rejudge',
      payload: { snapshot_id: before.id },
    });
    runWorkerOnce();

    // 같은 기준일 새 리비전이 발행됐다(D11-1)
    const after = await latestPublished(request);
    expect(after.asof_date).toBe(before.asof_date);
    expect(after.revision ?? 1).toBeGreaterThan(before.revision ?? 1);

    // C-5: 이후 값 = 잡이 쓴 리비전 — 그 리비전의 대시보드를 읽었다
    const afterNote = page.getByTestId('g5-after');
    await expect(afterNote).toContainText(revText(after), { timeout: 30_000 });
    await expect(page.getByRole('table', { name: P.G5.diff })).toBeVisible();
    expect(paths.some((p) => p.startsWith(`GET /api/snapshots/${after.id}/dashboard`))).toBe(true);

    // M-15: 새로 고침 없이 헤더 기준일(기본 = 최신 published 리비전)이 새 리비전으로
    await expect(picker).toHaveValue(String(after.id));
    await expect(picker.locator(`option[value="${after.id}"]`)).toHaveText(revText(after));
    expect(failed).toEqual([]);
  });

  test('M-16 G8: 기준·비교 선택이 리비전을 구별 → 새 리비전 기준·이전 리비전 비교 보고서 → 목록 행 리비전 표기', async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const latest = await latestPublished(request);
    expect(latest.revision ?? 1).toBeGreaterThan(1);
    const rows = await api<SnapshotRow[]>(request, '/regions/1/snapshots');
    const sameDayRev1 = rows.find(
      (s) => s.asof_date === latest.asof_date && (s.revision ?? 1) === 1,
    )!;
    expect(sameDayRev1).toBeTruthy();

    await ready(page, '/reports', P.G8.title);
    const base = page.getByLabel(P.G8.snapshot);
    await expect(base).toHaveValue(String(latest.id));
    await expect(base.locator(`option[value="${latest.id}"]`)).toHaveText(revText(latest));
    const compare = page.getByLabel(P.G8.compareSnapshot);
    // 같은 기준일의 리비전 1 은 날짜만, 새 리비전은 '· 리비전 n' — 서로 구별된다
    await expect(compare.locator(`option[value="${sameDayRev1.id}"]`)).toHaveText(
      sameDayRev1.asof_date,
    );
    await expect(compare.locator(`option[value="${latest.id}"]`)).toHaveCount(0); // 기준 자신 제외
    for (const s of rows.filter((x) => x.status === 'building')) {
      await expect(compare.locator(`option[value="${s.id}"]`)).toHaveCount(0);
    }
    await compare.selectOption(String(sameDayRev1.id));
    await page.getByRole('radio', { name: P.G8.formats.html }).check();
    const created = page.waitForResponse(
      (r) => r.url().endsWith('/api/reports') && r.request().method() === 'POST',
    );
    await page.getByRole('button', { name: P.G8.generate }).click();
    const res = await created;
    expect(res.status()).toBe(202);
    expect(res.request().postDataJSON()).toMatchObject({
      snapshot_id: latest.id,
      compare_snapshot_id: sameDayRev1.id,
      format: 'html',
    });
    runWorkerOnce();

    const list = page.getByRole('table', { name: P.G8.list });
    const row = list.locator('tbody tr', { hasText: revText(latest) }).first();
    await expect(row).toBeVisible({ timeout: 60_000 });
    await expect(row.getByRole('button')).toBeVisible({ timeout: 60_000 });
    // 계약 .9 S10: 파일 이름이 리비전을 구별한다(같은 기준일 리비전 보고서끼리 덮어쓰지 않음)
    await expect(row.getByRole('button')).toHaveText(
      new RegExp(
        `^report_r1_${latest.asof_date}-r${latest.revision}_vs_${sameDayRev1.asof_date}-r1_j\\d+\\.html$`,
      ),
    );
    await expect(row.locator('td').nth(2)).toHaveText(sameDayRev1.asof_date);
    expect(failed).toEqual([]);
  });
});
