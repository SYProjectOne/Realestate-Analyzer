/**
 * 계약 2026-10-09.19 · D26-2 화면 실 API e2e(R7-QUEUE, MSW 끔, devseed 테스트 DB 위 uvicorn) — G7 접수 확인 대기열.
 *  - API: GET /api/ops/intake-queue 쓰기·읽기 전용 토큰 200, 공유 링크 토큰 403(D10-7). 서버가 저장된 사유·http_status 로
 *    묶는다 — devseed 스냅샷의 403·DNS·'접속 실패' 행은 '수집 실패'
 *  - 화면: '수집 실패 · DNS' 묶음의 단지 → '사람 확인 입력'(폼 미리 채움) → 저장(201, 재판정 자동 등록) → 대기열 '사람 확인
 *    입력됨 — 재판정·발행 대기' → worker 1회(재판정·새 리비전 발행) → 새 리비전 대기열에서 그 단지는 사람 확인 행('기타 ·
 *    사람 확인', 경로 사람 확인)이고 반영 대기 표시가 없다. 값은 '확인 불가'로 넣어 판정 범위(참고)가 바뀌지 않게 한다 — 뒤 파일
 *    (writes7~9)의 범위·순위 확인에 영향을 주지 않는다.
 * 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건.
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { READ_TOKEN, runWorkerOnce, skipQueuedJobs, WRITE_TOKEN } from './env';

const P = ko.page;
const DNS_COMPLEX = 14; // devseed '사우역 지엔하임' — 공식 홈페이지 DNS 실패

interface QueueBody {
  snapshot_id: number | null;
  total: number;
  groups: {
    category: string;
    reason: string;
    count: number;
    items: { complex_id: number; human_check_pending: unknown }[];
  }[];
}

function watchApi(page: Page) {
  const failed: string[] = [];
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/') && r.status() >= 400)
      failed.push(`${r.status()} ${r.request().method()} ${url.pathname}${url.search}`);
  });
  return failed;
}

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

function groupOf(body: QueueBody, complexId: number) {
  return body.groups.find((g) => g.items.some((it) => it.complex_id === complexId));
}

test.describe.serial('계약 .19 접수 확인 대기열(실 API)', () => {
  test.beforeAll(() => {
    skipQueuedJobs('region.expand');
    skipQueuedJobs('region.bootstrap');
  });

  test('API: 쓰기·읽기 전용 토큰 200, 공유 링크 토큰 403 · 수집 실패 묶음', async ({ request }) => {
    const write = { Authorization: `Bearer ${WRITE_TOKEN}` };
    const res = await request.get('/api/ops/intake-queue', { headers: write });
    expect(res.status()).toBe(200);
    const body = (await res.json()) as QueueBody;
    expect(body.snapshot_id).not.toBeNull();
    expect(body.total).toBe(body.groups.reduce((n, g) => n + g.count, 0));
    expect(groupOf(body, DNS_COMPLEX)).toMatchObject({ category: 'collect_failed', reason: 'DNS' });
    expect(groupOf(body, 4)).toMatchObject({ category: 'collect_failed', reason: '403' });
    const read = await request.get('/api/ops/intake-queue', {
      headers: { Authorization: `Bearer ${READ_TOKEN}` },
    });
    expect(read.status()).toBe(200);
    const link = await request.post('/api/share-links', {
      headers: write,
      data: { label: 'e2e-r7queue' },
    });
    expect(link.status()).toBe(201);
    const { token, link: created } = (await link.json()) as { token: string; link: { id: number } };
    const shared = await request.get('/api/ops/intake-queue', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(shared.status()).toBe(403);
    expect(((await shared.json()) as { code: string }).code).toBe('forbidden');
    await request.delete(`/api/share-links/${String(created.id)}`, { headers: write });
  });

  test("화면: '사람 확인 입력' → 폼 미리 채움 → 저장 → 반영 대기 → 재판정·발행 → 새 리비전에서 사람 확인 행", async ({
    page,
  }) => {
    const failed = watchApi(page);
    await ready(page, '/ops', P.G7.title);
    const section = page.getByRole('region', { name: P.G7.iq.title });
    await section.scrollIntoViewIfNeeded();
    const failedCat = section.getByTestId('iq-category-collect_failed');
    await expect(failedCat).toHaveAttribute('open');
    await expect(failedCat.locator('summary')).toContainText(P.G7.iq.category.collect_failed);
    const item = section.locator(`[data-testid="iq-item"][data-complex-id="${DNS_COMPLEX}"]`);
    await expect(item).toBeVisible();
    await expect(item.getByTestId('intake-badge')).toContainText('DNS');
    await expect(item.getByRole('link', { name: '사우역 지엔하임' })).toHaveAttribute(
      'href',
      new RegExp(`^/complexes/${DNS_COMPLEX}`),
    );
    await expect(item.getByTestId('iq-pending')).toHaveCount(0);

    await item.getByTestId('iq-human-check').click();
    await expect(page).toHaveURL(new RegExp(`hc_complex=${DNS_COMPLEX}`));
    const form = page.getByRole('form', { name: P.G7.human });
    await expect(form.getByLabel(P.G7.hc.complex)).toHaveValue(String(DNS_COMPLEX));
    await expect(form.getByLabel(P.G7.hc.field)).toHaveValue('intake_status');
    await form.getByLabel(P.G7.hc.value).selectOption('확인 불가');
    await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
    await form.getByLabel(P.G7.hc.note).fill('견본주택 통화: 홈페이지 폐쇄, 접수 일정 미정 안내');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
    );
    await form.getByRole('button', { name: P.G7.hc.submit }).click();
    const res = await saved;
    expect(res.status()).toBe(201);
    const created = (await res.json()) as { rejudge_job_id: number | null };
    expect(created.rejudge_job_id).not.toBeNull();
    // 발행 리비전 대기열은 그대로 — 그 단지에 반영 대기 표시
    await expect(item.getByTestId('iq-pending')).toContainText('확인 불가');

    // worker 1회 → 재판정 + 새 리비전 발행(화면 기본 = 최신 published 리비전)
    runWorkerOnce();
    await expect(form.getByTestId('human-check-job')).toContainText(ko.job.status.done);
    await ready(page, '/ops', P.G7.title);
    const section2 = page.getByRole('region', { name: P.G7.iq.title });
    await section2.scrollIntoViewIfNeeded();
    const other = section2.getByTestId('iq-category-other');
    const after = other.locator(`[data-testid="iq-item"][data-complex-id="${DNS_COMPLEX}"]`);
    await expect(after).toBeVisible();
    await expect(after.getByTestId('intake-badge')).toContainText(ko.intake.path.human_check);
    await expect(after.getByTestId('iq-pending')).toHaveCount(0);
    await expect(other.getByTestId('iq-group').filter({ hasText: '사람 확인' })).toHaveCount(1);
    expect(failed).toEqual([]);
  });
});
