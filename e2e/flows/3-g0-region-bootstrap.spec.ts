/**
 * 흐름 (a) G0 지역 입력 → bootstrap → G1 — DECISIONS D2(자유 지명), D2-4(region.bootstrap).
 *
 * 화면: '송도' 입력 → /regions/resolve 후보 → '인천광역시 연수구 송도동' 선택 → 이름 → 분석 시작(POST /regions 201,
 * job_id) → JobProgress → worker 1회(녹화 재생 수집기 + Mock 판정기, 네트워크 없음) → 완료 → '홈 대시보드로' →
 * G1 이 새 지역(?region=<id>)의 결과를 4xx/5xx 없이 보여 준다. 기존 지역(픽스처 지역 1)의 단지는 바뀌지 않는다.
 *
 * worker CLI(`python -m app.worker --once`)에는 녹화 재생 모드가 없어 같은 진입점(runner.main --once)에 재생 수집기를
 * 넣은 support/replay_worker.py 를 쓴다(WP9 발견 — 보고서 참고).
 */
import { expect, test } from '@playwright/test';
import ko from '../../frontend/src/i18n/ko.json' with { type: 'json' };
import { runReplayWorker } from '../env';
import { apiGet, ready, watchApi } from './_util';

const P = ko.page;
const PICK = '인천광역시 연수구 송도동';

interface ComplexDetail {
  header?: { name?: { v?: string } | string };
  name?: string;
}

test('G0 송도 → 후보 선택 → POST /regions → bootstrap(재생) → G1 결과', async ({ page, request }) => {
  const failed = watchApi(page);
  const fixtureNames = await Promise.all(
    [1, 3].map(async (id) => JSON.stringify(await apiGet<ComplexDetail>(request, `/complexes/${id}`))),
  );

  await ready(page, '/regions/new', P.G0.title);
  const resolved = page.waitForResponse(
    (r) => r.url().includes('/api/regions/resolve') && r.status() === 200,
  );
  await page.getByRole('searchbox', { name: P.G0.search }).fill('송도');
  await resolved;
  const candidates = page.getByRole('list', { name: P.G0.candidates });
  await candidates.getByRole('checkbox', { name: new RegExp(PICK) }).first().check();
  await expect(page.getByRole('list', { name: P.G0.selected })).toContainText('송도동');
  await page.getByLabel(P.G0.name, { exact: true }).fill('송도 e2e');
  const created = page.waitForResponse(
    (r) => r.url().endsWith('/api/regions') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: P.G0.start }).click();
  const post = await created;
  expect(post.status()).toBe(201);
  const body = (await post.json()) as { region?: { id: number }; id?: number; job_id: number };
  const regionId = body.region?.id ?? body.id;
  expect(regionId).toBeTruthy();
  expect(body.job_id).toBeTruthy();
  await expect(page.getByRole('status').filter({ hasText: ko.job.title })).toBeVisible();

  const out = runReplayWorker();
  expect(out).toContain('replay_worker: exit=0');

  await expect(page.getByRole('status').filter({ hasText: ko.job.title })).toHaveAttribute(
    'data-status',
    'done',
    { timeout: 60_000 },
  );
  const region = await apiGet<{ status: string; latest_snapshot?: { id: number } | null }>(
    request,
    `/regions/${regionId}`,
  );
  expect(region.status).toBe('ready');
  expect(region.latest_snapshot?.id).toBeTruthy();

  await page.getByRole('link', { name: P.G0.goDashboard }).click();
  await expect(page).toHaveURL(new RegExp(`region=${regionId}`));
  await expect(page.getByRole('heading', { level: 1, name: P.G1.title })).toBeVisible();
  // soft: 실패해도 아래(G2·기존 지역 불변) 검사까지 본다
  await expect.soft(page.getByRole('list', { name: P.G1.kpis }).getByRole('listitem')).toHaveCount(5);
  // 새 지역의 단지가 G2 에 나온다
  await ready(page, `/complexes?region=${regionId}`, P.G2.title);
  await expect
    .soft(page.getByRole('table', { name: P.G2.table }).locator('tbody tr').first())
    .toBeVisible();

  // 기존 지역의 단지(픽스처)는 새 지역 bootstrap 으로 바뀌지 않는다
  const after = await Promise.all(
    [1, 3].map(async (id) => JSON.stringify(await apiGet<ComplexDetail>(request, `/complexes/${id}`))),
  );
  expect.soft(after.map((s) => JSON.parse(s).header?.name)).toEqual(
    fixtureNames.map((s) => JSON.parse(s).header?.name),
  );
  expect(failed).toEqual([]);
});
