/**
 * 계약 2026-10-09.14 화면 실 API e2e(R3i FE8 2단계, MSW 끔, devseed 테스트 DB 위 uvicorn) — 쓰기는 이 임시 DB 에만.
 *  - F5(D17-5): 체크리스트 상태 변경 → 202 + job_id(snapshot.publish) → 발행 진행 → worker → 발행됨. 같은 값 → 200 + null
 *  - F6(D17-5): 지역 이름만 변경 → 202 + snapshot.publish → 이름만 안내 + 발행 진행 → worker → 발행됨(되돌림도 같은 경로)
 *  - F3(m2): 할인 형식 오류는 폼이 막는다(POST 없음), 기준 타입 차감 바탕 이상은 서버 422 `discount_not_below_price` → 값 칸
 * 파일 이름이 writes9 뒤라 앞 spec 의 기대를 흔들지 않는다. 모든 테스트: 화면이 부른 /api 응답 중 기대한 422 외 4xx/5xx 0건.
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce, skipQueuedJobs } from './env';

const P = ko.page;

function fill(template: string, params: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => params[k] ?? `{${k}}`);
}

function watchApi(page: Page, allow: (status: number, path: string) => boolean = () => false) {
  const failed: string[] = [];
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/') && r.status() >= 400 && !allow(r.status(), url.pathname))
      failed.push(`${r.status()} ${r.request().method()} ${url.pathname}${url.search}`);
  });
  return failed;
}

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

test.describe.serial('계약 .14 화면(실 API)', () => {
  // 앞 spec 이 남긴 외부 수집 잡은 돌리지 않는다 — runWorkerOnce 가 집으면 시간 초과
  test.beforeAll(() => {
    skipQueuedJobs('region.expand');
  });

  test('F5 체크리스트 상태 변경 → 202 + 발행 잡 → worker → 발행됨, 같은 값 → 200 + 발행 없음', async ({
    page,
  }) => {
    const failed = watchApi(page);
    await ready(page, '/ops?region=1', P.G7.title);
    const table = page.getByRole('table', { name: P.G7.checklist });
    const select = table.getByRole('combobox').first();
    await expect(select).toBeEnabled();
    const before = await select.inputValue();
    const to = before === 'done' ? 'open' : 'done';
    const patched = page.waitForResponse(
      (r) => /\/api\/ops\/checklist\/\d+$/.test(r.url()) && r.request().method() === 'PATCH',
    );
    await select.selectOption(to);
    const res = await patched;
    expect(res.status()).toBe(202);
    expect(((await res.json()) as { job_id: number | null }).job_id).not.toBeNull();
    const box = page.getByTestId('checklist-job');
    await expect(box.getByText(P.G7.check.jobHint)).toBeVisible();
    await expect(box.getByTestId('publish-pending')).toHaveText(ko.job.publishPending);
    runWorkerOnce();
    await expect(box.getByTestId('publish-done')).toHaveText(ko.job.publishDone);

    // 되돌림: 다시 202(바뀜) → worker
    const back = page.waitForResponse(
      (r) => /\/api\/ops\/checklist\/\d+$/.test(r.url()) && r.request().method() === 'PATCH',
    );
    await table.getByRole('combobox').first().selectOption(before);
    expect((await back).status()).toBe(202);
    runWorkerOnce();
    await expect(page.getByTestId('checklist-job').getByTestId('publish-done')).toHaveText(
      ko.job.publishDone,
    );
    expect(failed).toEqual([]);
  });

  test('F6 지역 이름만 변경 → 202 + snapshot.publish → 이름만 안내 + 발행 → worker → 발행됨', async ({
    page,
  }) => {
    const failed = watchApi(page);
    await ready(page, '/regions/1/living-areas', P.G0_2.title);
    const panel = page.getByRole('region', { name: P.G0_2.expand.title });
    const nameBox = panel.getByLabel(P.G0_2.expand.name);
    const original = await nameBox.inputValue();
    const rename = async (name: string) => {
      await nameBox.fill(name);
      const saved = page.waitForResponse(
        (r) => r.url().endsWith('/api/regions/1') && r.request().method() === 'PATCH',
      );
      await panel.getByRole('button', { name: P.G0_2.expand.submit }).click();
      const res = await saved;
      const body = (await res.json()) as { job_id: number | null; change_event: unknown };
      return { status: res.status(), body };
    };
    const first = await rename(`${original} e2e`);
    expect(first.status).toBe(202);
    expect(first.body.change_event).toBeNull();
    expect(first.body.job_id).not.toBeNull();
    await expect(panel.getByTestId('expand-name-publish')).toHaveText(
      P.G0_2.expand.nameOnlyPublish,
    );
    await expect(panel.getByTestId('expand-name-only')).toHaveCount(0);
    await expect(panel.getByTestId('publish-pending')).toHaveText(ko.job.publishPending);
    runWorkerOnce();
    await expect(panel.getByTestId('publish-done')).toHaveText(ko.job.publishDone);

    // 되돌림(다른 spec 이 보는 이름으로) — 같은 경로
    const back = await rename(original);
    expect(back.status).toBe(202);
    runWorkerOnce();
    await expect(panel.getByTestId('publish-done')).toHaveText(ko.job.publishDone);
    expect(failed).toEqual([]);
  });

  test('F3 할인 형식 오류는 폼이 막고, 기준 타입 차감 바탕 이상은 서버 422 discount_not_below_price → 값 칸', async ({
    page,
  }) => {
    const failed = watchApi(
      page,
      (status, path) => status === 422 && path === '/api/ops/human-checks',
    );
    await ready(page, '/ops?region=1&hc_complex=1&hc_field=discount', P.G7.title);
    const form = page.getByRole('form', { name: P.G7.human });
    await expect(form.getByLabel(P.G7.hc.complex)).toHaveValue('1');
    const value = form.getByLabel(P.G7.hc.value);
    await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
    let posts = 0;
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().endsWith('/api/ops/human-checks')) posts += 1;
    });

    await value.fill('1,0');
    await form.getByRole('button', { name: P.G7.hc.submit }).click();
    await expect(value).toHaveAttribute('aria-invalid', 'true');
    await expect(value).toHaveAccessibleDescription(P.G7.hc.badDiscountFormat);
    expect(posts).toBe(0);

    await value.fill('90,000,000,000원');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
    );
    await form.getByRole('button', { name: P.G7.hc.submit }).click();
    const res = await saved;
    expect(res.status()).toBe(422);
    const body = (await res.json()) as { code: string; detail: string };
    expect(body.code).toBe('discount_not_below_price');
    await expect(value).toHaveAccessibleDescription(
      fill(P.G7.hc.discountNotBelowPrice, { detail: body.detail }),
    );
    expect(failed).toEqual([]);
  });
});
