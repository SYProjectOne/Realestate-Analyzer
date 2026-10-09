/**
 * 흐름 (b) G7 사람 확인 → 재판정 → G1 TOP 5·접수 배지 변화 — RA §9 T3.
 *
 * 기대(RA §9 T3): 스위첸(김포) 공식 홈페이지 403 → 접수 '확인 불가' → 상황 D(즉시 구매) 후보 제외.
 * G7 에서 사람 확인 '가능' 입력 → intake 행 + rejudge 잡 1(알림의 '재판정 잡 등록') → worker → 후보 포함:
 * G1(상황 D) TOP 5 에 스위첸이 '접수 가능 · 사람 확인' 배지로 나온다. 통합(base) TOP 5 도 비지 않는다.
 */
import { expect, test } from '@playwright/test';
import ko from '../../frontend/src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce } from '../env';
import { apiGet, ready, watchApi, type Top5Row } from './_util';

const P = ko.page;
const SWITZEN = '오퍼스 한강 스위첸';

test('G7 사람 확인 가능 → 재판정 잡 → G1 상황 D TOP 5 에 스위첸(접수 가능·사람 확인)', async ({
  page,
  request,
}) => {
  const failed = watchApi(page);

  // 전: 상황 D TOP 5 에 스위첸 없음(접수 확인 불가 403)
  await ready(page, '/?region=1&scenario=D', P.G1.title);
  const top5 = page.getByRole('list', { name: P.G1.top5 });
  await expect(top5.getByRole('listitem').first()).toBeVisible();
  await expect(top5).not.toContainText(SWITZEN);
  const before = await apiGet<{ top5: Top5Row[] }>(request, '/snapshots/12/dashboard?scenario=D');
  expect(before.top5.map((r) => r.complex_id)).not.toContain(4);

  // G7 사람 확인 '가능'
  await ready(page, '/ops?region=1', P.G7.title);
  const form = page.getByRole('form', { name: P.G7.human });
  const complex = form.getByLabel(P.G7.hc.complex);
  await expect(complex.locator('option', { hasText: SWITZEN })).toBeAttached();
  await complex.selectOption({ label: SWITZEN });
  await form.getByLabel(P.G7.hc.value).selectOption('가능');
  await form.getByLabel(P.G7.hc.enteredBy).fill('e2e 운영자');
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
  );
  await form.getByRole('button', { name: P.G7.hc.submit }).click();
  expect((await saved).status()).toBe(201);
  await expect(form.getByTestId('human-check-result')).toContainText(ko.intake.status['가능']);

  // 알림의 '재판정 잡 등록' → POST /jobs(rejudge, complex_ids [4])
  const queued = page.waitForResponse(
    (r) => r.url().endsWith('/api/jobs') && r.request().method() === 'POST',
  );
  await page
    .getByRole('region', { name: ko.app.notifications })
    .getByRole('button', { name: P.G7.rejudge })
    .click();
  const job = await queued;
  expect(job.status()).toBe(202);
  expect(job.request().postDataJSON()).toMatchObject({
    job_name: 'rejudge',
    payload: { complex_ids: [4] },
  });

  runWorkerOnce();
  const jobs = await apiGet<{ items?: { job_name: string; status: string }[] } | { job_name: string; status: string }[]>(
    request,
    '/jobs',
  );
  const items = Array.isArray(jobs) ? jobs : (jobs.items ?? []);
  const rejudge = items.filter((j) => j.job_name === 'rejudge');
  expect(rejudge).toHaveLength(1);
  expect(rejudge[0].status).toBe('done');

  // 후: G1 상황 D TOP 5 에 스위첸 + 배지 '접수 가능 · 사람 확인'
  await ready(page, '/?region=1&scenario=D', P.G1.title);
  const card = top5.getByRole('listitem').filter({ hasText: SWITZEN });
  // soft: 실패해도 통합 TOP 5 검사까지 본다
  await expect.soft(card).toHaveCount(1);
  if ((await card.count()) === 1) {
    await expect(card.getByTestId('intake-badge')).toContainText(ko.intake.status['가능']);
    await expect(card.getByTestId('intake-badge')).toContainText(ko.intake.path.human_check);
  }
  // 통합(base) TOP 5 도 비지 않는다
  await ready(page, '/?region=1', P.G1.title);
  await expect.soft(top5.getByRole('listitem')).not.toHaveCount(0);
  expect(failed).toEqual([]);
});
