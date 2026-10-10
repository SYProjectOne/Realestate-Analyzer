/**
 * 흐름 (b) G7 사람 확인 → 재판정 → G1·G3 변화 — RA §9 T3 + DECISIONS D9-1.
 *
 * RA §9 T3: 스위첸(김포) 공식 홈페이지 403 → 접수 '확인 불가' → 상황 D(즉시 구매) 후보 제외.
 * G7 에서 사람 확인 '가능' 입력 → intake 행 + rejudge 잡 1(계약 .9 D12-5: 서버 자동 등록 rejudge_job_id — 화면은 진행만,
 * 계약 .11 F6: 201 그대로 + 공통 이름 job_id(= rejudge_job_id) — 화면은 job_id 를 감시하고 발행까지 이전 리비전이라고 알린다)
 * → worker(Mock = 합성 판정 녹화).
 *
 * D9-1로 인한 차이(픽스처 README): 합성 녹화는 보고서 classify(#110 스위첸 review .72)를 따르므로 스위첸은
 * '미해결(분류 판정 미해결)' — 사람 확인 '가능' 뒤에도 판정 대상이 아니다(사다리·점수·상황 후보 없음).
 * 그래서 이 흐름의 '후: ' 기대는 RA 원문 '후보 포함'이 아니라:
 *  - G3 스위첸 접수 배지 = '접수 가능 · 사람 확인'(사람 확인 행이 표시 접수 행)
 *  - G1 상황 D TOP 5 에 스위첸 없음(미해결) · 통합(base) TOP 5 는 비지 않음(재판정 녹화 재생 = 점수 유지)
 * 후보 포함까지의 흐름은 회귀 test_t03(fake: classify auto)이 본다.
 */
import { expect, test } from '@playwright/test';
import ko from '../../frontend/src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce } from '../env';
import { apiGet, ready, watchApi, type Top5Row } from './_util';

const P = ko.page;
const SWITZEN = '오퍼스 한강 스위첸';

test('G7 사람 확인 가능 → 재판정 잡 → G3 접수 배지(가능·사람 확인), D9-1 미해결이라 상황 D 후보 아님', async ({
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
  // 계약 .4 minor 15: entered_by = 역할 enum(운영자·검토자) 선택 — 자유 입력 아님
  await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
  const saved = page.waitForResponse(
    (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
  );
  await form.getByRole('button', { name: P.G7.hc.submit }).click();
  const savedRes = await saved;
  expect(savedRes.status()).toBe(201);
  const hc = (await savedRes.json()) as { rejudge_job_id: number | null; job_id: number | null };
  expect(hc.job_id).not.toBeNull();
  expect(hc.job_id).toBe(hc.rejudge_job_id);
  // 계약 .11 F7: checked_at 은 시간대가 붙은 RFC3339 로 보낸다
  const sent = JSON.parse(savedRes.request().postData() ?? '{}') as { checked_at?: string };
  expect(sent.checked_at ?? '').toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/);
  await expect(form.getByTestId('human-check-result')).toContainText(ko.intake.status['가능']);

  // 계약 .9: 재판정 잡은 자동 등록 — 화면은 그 잡 진행만 보이고 알림에 '재판정 잡 등록' 버튼이 없다(POST /jobs 없음)
  await expect(form.getByTestId('human-check-job')).toContainText('rejudge');
  await expect(form.getByTestId('human-check-job').getByTestId('publish-pending')).toHaveText(ko.job.publishPending);
  await expect(
    page.getByRole('region', { name: ko.app.notifications }).getByRole('button', { name: P.G7.rejudge }),
  ).toHaveCount(0);
  const auto = await apiGet<{ job_name: string; payload: { complex_ids: number[] | null } }>(
    request,
    `/jobs/${hc.job_id}`,
  );
  expect(auto.job_name).toBe('rejudge');
  expect(auto.payload.complex_ids).toEqual([4]);

  runWorkerOnce();
  const jobs = await apiGet<{ items?: { job_name: string; status: string }[] } | { job_name: string; status: string }[]>(
    request,
    '/jobs',
  );
  const items = Array.isArray(jobs) ? jobs : (jobs.items ?? []);
  const rejudge = items.filter((j) => j.job_name === 'rejudge');
  expect(rejudge).toHaveLength(1);
  expect(rejudge[0].status).toBe('done');

  // 후: G3 스위첸 접수 배지 '접수 가능 · 사람 확인'
  await ready(page, '/complexes/4?region=1', P.G3.title);
  const header = page.getByRole('region', { name: SWITZEN }).first();
  await expect(header.getByTestId('intake-badge')).toContainText(ko.intake.status['가능']);
  await expect(header.getByTestId('intake-badge')).toContainText(ko.intake.path.human_check);

  // 계약 .8(D11-1): 발행 스냅샷 12 는 불변 — 사람 확인·재판정은 같은 기준일 새 리비전에 들어간다.
  // 화면(SnapshotPicker 기본 = 목록 첫째)과 같이 지역 최신 리비전을 읽는다.
  const snaps = await apiGet<{ id: number; asof_date: string; revision?: number; revision_of?: number | null }[]>(
    request,
    '/regions/1/snapshots',
  );
  const latest = snaps[0];
  expect(latest.id).not.toBe(12);
  expect(latest.revision ?? 1).toBeGreaterThan(1);
  expect(latest.revision_of).toBe(12);

  // 후: D9-1 — 스위첸은 classify 미해결이라 상황 D 후보가 아니다(판정 범위 미해결, 순위 없음)
  const rows = await apiGet<{ items: { complex_id: number; rank: number | null; judge_scope?: string | null }[] }>(
    request,
    `/snapshots/${latest.id}/complexes?scenario=D&size=100`,
  );
  const sw = rows.items.find((r) => r.complex_id === 4);
  expect(sw?.rank ?? null).toBeNull();
  expect(['미해결', '제외']).toContain(sw?.judge_scope);
  const after = await apiGet<{ top5: Top5Row[] }>(request, `/snapshots/${latest.id}/dashboard?scenario=D`);
  expect(after.top5.length).toBeGreaterThan(0);
  expect(after.top5.map((r) => r.complex_id)).not.toContain(4);
  await ready(page, '/?region=1&scenario=D', P.G1.title);
  await expect(top5.getByRole('listitem').first()).toBeVisible();
  await expect(top5).not.toContainText(SWITZEN);

  // 통합(base) TOP 5 도 비지 않는다(합성 녹화 재생 — 종합 점수 유지)
  const base = await apiGet<{ top5: Top5Row[] }>(request, `/snapshots/${latest.id}/dashboard?scenario=base`);
  expect(base.top5.length).toBeGreaterThan(0);
  await ready(page, '/?region=1', P.G1.title);
  await expect(top5.getByRole('listitem')).not.toHaveCount(0);
  expect(failed).toEqual([]);
});
