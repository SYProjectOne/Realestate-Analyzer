/**
 * 계약 2026-10-09.18 화면 실 API e2e(R4 FE12, MSW 끔, devseed 테스트 DB 위 uvicorn) — 행 준비는 이 임시 DB 에만, 테스트가
 * 끝나면 넣은 행을 지우고 바꾼 값을 되돌린다(뒤 파일 writes7~9 의 `runWorkerOnce()` 가 넣은 잡을 집지 않게 — queued 재큐잉
 * 잡은 not_before 가 남아 `--once` 가 기다린다).
 *  - F2(D23-4): 청약홈 API 빈 데이터셋 실패 행(raw_document http_status **200** · path null · error_text
 *    'empty_dataset: totalCount 0') → API `/ops/sources` 실패 대상 reason 그 문자열(서버 계산) → G7 소스 표가 '확인 불가(빈
 *    데이터셋 — 청약홈 적재 중, 날짜)'(200·영문 코드 없이), 마지막 오류 칸도 화면 문구
 *  - F3(D23-4): region.bootstrap 지연 재큐잉(queued + stats requeue_count·not_before·requeue_reason 'degraded_source: …')
 *    → API `/jobs` 그대로 → G7 잡 목록 '발행하지 않고 다시 수집(n/6회, 시각 이후 다시 시도)'. 재시도 상한 초과 failed 는 코드
 *    접두 없이. 지역 status bootstrapping → 전역 '첫 적재 중' 안내
 * F1·F4(화면 변경 없음)는 vitest(r4fe12)가 회귀를 고정한다 — devseed 에 같은 회차 원 코드 경쟁률·compare 채택 행이 없다.
 * 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건.
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runSql, skipQueuedJobs, WRITE_TOKEN } from './env';

const P = ko.page;
const REGION = 1;
const EMPTY = 'empty_dataset: totalCount 0';
const EMPTY_REASON = '청약홈 API 빈 데이터셋(조건 없는 totalCount 0 — 재적재 중) 3건';
/** 이 파일이 넣은 행 표식(지울 때 이것만) */
const MARK = 'e2e-r4fe12';

function fill(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => params[k] ?? `{${k}}`);
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

/** 지금 + `minutes` 분의 KST 시각 문자열('YYYY-MM-DDThh:mm:00+09:00')과 그 화면 표시('YYYY-MM-DD hh:mm') */
function kst(minutes: number): { iso: string; day: string; shown: string } {
  const at = new Date(Date.now() + minutes * 60_000 + 9 * 3_600_000);
  const p = (n: number) => String(n).padStart(2, '0');
  const day = `${at.getUTCFullYear()}-${p(at.getUTCMonth() + 1)}-${p(at.getUTCDate())}`;
  const hm = `${p(at.getUTCHours())}:${p(at.getUTCMinutes())}`;
  return { iso: `${day}T${hm}:00+09:00`, day, shown: `${day} ${hm}` };
}

function cleanup(): void {
  runSql([
    ['delete from raw_document where url like ?', [`%${MARK}%`]],
    ['delete from job_run where payload like ?', [`%${MARK}%`]],
    ["update region set status = 'ready' where id = ?", [REGION]],
  ]);
}

test.describe.serial('계약 .18 화면(실 API)', () => {
  test.beforeAll(() => {
    skipQueuedJobs('region.expand');
    skipQueuedJobs('region.bootstrap');
  });
  test.afterAll(() => cleanup());

  test("F2 빈 데이터셋 실패 행(200) → G7 '확인 불가(빈 데이터셋 — 청약홈 적재 중, 날짜)'", async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const at = kst(-60);
    const url = `https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?${MARK}`;
    expect(
      runSql([
        [
          'insert into raw_document (source_kind, url, fetched_at, http_status, sha256, path, region_id, error_text) values (?, ?, ?, 200, ?, NULL, ?, ?)',
          [
            'applyhome_list',
            url,
            at.iso,
            `${MARK}-${String(Date.now())}`.padEnd(64, '0'),
            REGION,
            EMPTY,
          ],
        ],
      ]),
    ).toBe(1);

    // 서버가 그 행을 실패로 센다(계약 .18 F2 — http_status 200 · reason 사유 문자열)
    const res = await request.get(`/api/ops/sources?region_id=${REGION}`, {
      headers: { Authorization: `Bearer ${WRITE_TOKEN}` },
    });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as {
      source_kind: string;
      failing_targets: { url: string; http_status: number | null; reason: string }[];
    }[];
    const target = rows
      .find((r) => r.source_kind === 'applyhome_list')
      ?.failing_targets.find((t) => t.url === url);
    expect(target).toEqual(expect.objectContaining({ http_status: 200, reason: EMPTY }));

    await ready(page, `/ops?region=${REGION}`, P.G7.title);
    const table = page.getByRole('table', { name: P.G7.sources });
    const row = table.getByRole('row').filter({
      has: page.getByRole('rowheader', { name: new RegExp(P.G7.sourceKind.applyhome_list) }),
    });
    await row.getByText(P.G7.src.failing).click();
    const item = row
      .getByRole('listitem')
      .filter({ has: page.locator(`[data-reason="${EMPTY}"]`) });
    await expect(item).toContainText(
      fill(ko.empty.unknownWithReasonDate, { reason: P.G7.src.reason.emptyDataset, date: at.day }),
    );
    await expect(item).not.toContainText(`${ko.empty.unknown}(200`);
    await expect(row).not.toContainText('empty_dataset');
    expect(failed).toEqual([]);
  });

  test("F3 bootstrap 빈 데이터셋 재큐잉 → G7 잡 목록 '발행하지 않고 다시 수집', 상한 초과 실패는 코드 접두 없이, 지역 '첫 적재 중'", async ({
    page,
  }) => {
    const failed = watchApi(page);
    const nb = kst(30);
    const queuedStats = {
      region_id: REGION,
      daily: { degraded_sources: { applyhome: EMPTY_REASON } },
      requeue_count: 2,
      requeue_reason: `degraded_source: region.bootstrap: applyhome ${EMPTY_REASON} — 발행하지 않고 재시도`,
      not_before: nb.iso,
    };
    const payload = JSON.stringify({ region_id: REGION, e2e: MARK });
    const now = kst(0).iso;
    expect(
      runSql([
        [
          "insert into job_run (job_name, kind, payload, scheduled_at, status, stats) values ('region.bootstrap', 'manual', ?, ?, 'queued', ?)",
          [payload, now, JSON.stringify(queuedStats)],
        ],
        [
          "insert into job_run (job_name, kind, payload, scheduled_at, started_at, finished_at, status, stats, error_text) values ('collect.daily', 'manual', ?, ?, ?, ?, 'failed', ?, ?)",
          [
            payload,
            now,
            now,
            now,
            JSON.stringify({ requeue_count: 6 }),
            `degraded_source: collect.daily: applyhome ${EMPTY_REASON} — 재시도 6회 뒤에도 그대로`,
          ],
        ],
        ["update region set status = 'bootstrapping' where id = ?", [REGION]],
      ]),
    ).toBe(3);
    try {
      await ready(page, `/ops?region=${REGION}`, P.G7.title);
      const queue = page.getByRole('table', { name: P.G7.queue });
      const requeued = queue
        .locator('tr[data-status="queued"]')
        .filter({ hasText: 'region.bootstrap' });
      const note = requeued.getByTestId('job-requeued');
      await expect(note).toHaveAttribute('data-requeue', 'degraded');
      await expect(note).toContainText(
        fill(ko.job.requeuedDegraded, {
          detail: EMPTY_REASON,
          n: '2',
          max: '6',
          at: fill(ko.job.requeuedAt, { at: nb.shown }),
        }),
      );
      await expect(note).toContainText(ko.job.requeuedDegradedBootstrap);
      const stopped = queue
        .locator('tr[data-status="failed"]')
        .filter({ hasText: 'collect.daily' })
        .first();
      await expect(stopped).toContainText(
        fill(ko.job.degradedFailed, {
          max: '6',
          detail: `applyhome ${EMPTY_REASON} — 재시도 6회 뒤에도 그대로`,
        }),
      );
      await expect(queue).not.toContainText('degraded_source');

      // 지역 status bootstrapping(서버 값) → 전역 '첫 적재 중' 안내
      const banner = page.getByTestId('region-loading-banner');
      await expect(banner).toHaveAttribute('data-region-status', 'bootstrapping');
      await expect(banner).toContainText(ko.app.regionBootstrapping);
      expect(failed).toEqual([]);
    } finally {
      cleanup();
    }
  });
});
