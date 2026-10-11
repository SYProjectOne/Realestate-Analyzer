/**
 * 계약 2026-10-09.13 화면 실 API e2e(R3h FE7 2단계, MSW 끔, devseed 테스트 DB 위 uvicorn) — 쓰기는 이 임시 DB 에만.
 *  - F1·F2(D16-1): 공고문 파서 할인 = '추정'(표시만) → 안내 + G7 사람 확인 링크(단지·discount 미리 채움, 전역 쿼리 유지) →
 *    사람 확인 할인 201 → worker → 새 발행 리비전에서 '확인됨' 할인이 구매가에서 빠진다
 *  - F3(D16-4): 호재 위치를 같은 값으로 다시 저장 → 200 + job_id null → "바뀐 것 없음"(발행 진행 안내 없음)
 * 파일 이름이 writes8 뒤라 앞 spec 의 읽기 기대를 흔들지 않는다. 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건.
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce, setDiscount } from './env';

const P = ko.page;
/** devseed 픽스처 단지 1 = 할인 주입 대상(writes8 과 같은 단지) */
const DISCOUNT_COMPLEX = 1;
const CATALYST = 'GTX-B 개통 2030 vs 2031';

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

async function ready(page: Page, path: string, title: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
}

test.describe.serial('계약 .13 화면(실 API)', () => {
  test.afterAll(() => setDiscount(DISCOUNT_COMPLEX, null));

  test("D16-1 '추정' 할인 → 안내·사람 확인 링크 → 할인 사람 확인 → worker → '확인됨' 차감", async ({
    page,
  }) => {
    const failed = watchApi(page);
    setDiscount(DISCOUNT_COMPLEX, '추정');
    await ready(page, `/complexes/${DISCOUNT_COMPLEX}?region=1#price`, P.G3.title);
    const header = page.getByTestId('header-discount');
    await expect(header.getByTestId('header-discount-estimated')).toContainText(
      P.G3.price.discountEstimated,
    );
    const row = page.getByTestId('price-discount');
    await expect(row).toContainText(P.G3.price.discountNotApplied);
    await expect(row.getByTestId('discount-estimated')).toContainText(P.G3.price.discountEstimated);

    await header.getByRole('link', { name: P.G3.price.discountHumanCheck }).click();
    await expect(page).toHaveURL(/\/ops\?/);
    const url = new URL(page.url());
    expect(url.searchParams.get('region')).toBe('1');
    expect(url.searchParams.get('hc_complex')).toBe(String(DISCOUNT_COMPLEX));
    expect(url.searchParams.get('hc_field')).toBe('discount');
    const form = page.getByRole('form', { name: P.G7.human });
    await expect(form.getByLabel(P.G7.hc.field)).toHaveValue('discount');
    await expect(form.getByLabel(P.G7.hc.complex)).toHaveValue(String(DISCOUNT_COMPLEX));
    await form.getByLabel(P.G7.hc.value).fill('1,000,000원');
    await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
    );
    await form.getByRole('button', { name: P.G7.hc.submit }).click();
    const res = await saved;
    expect(res.status()).toBe(201);
    const hc = (await res.json()) as { field: string; entity: string; job_id: number | null };
    expect(hc).toMatchObject({ field: 'discount', entity: 'payment_terms' });
    expect(hc.job_id).not.toBeNull();
    await expect(form.getByTestId('human-check-job').getByTestId('publish-pending')).toHaveText(
      ko.job.publishPending,
    );
    runWorkerOnce();
    await expect(form.getByTestId('human-check-job').getByTestId('publish-done')).toHaveText(
      ko.job.publishDone,
    );

    // 새 발행 리비전(기본 선택): 사람 확인 할인 = 확인됨 → 서버가 구매가에서 뺀다, '추정' 안내 없음
    await ready(page, `/complexes/${DISCOUNT_COMPLEX}?region=1#price`, P.G3.title);
    const applied = page.getByTestId('price-discount');
    await expect(applied).toContainText('100만');
    await expect(applied).toContainText(P.G3.price.discountApplied);
    await expect(applied).toContainText(ko.label.confirmed);
    await expect(applied.getByTestId('discount-estimated')).toHaveCount(0);
    await expect(page.getByTestId('header-discount-estimated')).toHaveCount(0);
    // 기준 타입 밖 주택형 할인은 여전히 파서 '추정' — 표 아래 안내 한 번은 남는다(D16-1)
    await expect(page.getByTestId('discount-estimated')).toHaveCount(1);
    expect(failed).toEqual([]);
  });

  test('D16-4 호재 위치 같은 값 다시 저장 → 200 + job_id null → "바뀐 것 없음"(발행 진행 안내 없음)', async ({
    page,
  }) => {
    const failed = watchApi(page);
    await ready(page, '/market?region=1', P.G6.title);
    const panel = page.getByRole('region', { name: P.G6.loc.title });
    const item = panel
      .getByRole('list', { name: P.G6.loc.title })
      .locator('li', { hasText: CATALYST });
    const save = async (): Promise<number> => {
      await item.getByRole('button', { name: P.G6.loc.open, exact: true }).click();
      const form = item.getByRole('form', { name: fill(P.G6.loc.formFor, { name: CATALYST }) });
      await form.getByLabel(P.G6.loc.complexes).selectOption([]);
      await form.getByRole('checkbox', { name: '검단구' }).check();
      const done = page.waitForResponse(
        (r) => /\/api\/catalysts\/\d+$/.test(r.url()) && r.request().method() === 'PATCH',
      );
      await form.getByRole('button', { name: P.G6.loc.submit }).click();
      return (await done).status();
    };

    expect(await save()).toBe(202);
    await expect(panel.getByTestId('catalyst-job').getByTestId('publish-pending')).toHaveText(
      ko.job.publishPending,
    );
    runWorkerOnce();
    await expect(item.getByTestId('loc-status')).toHaveText(P.G6.loc.confirmed);

    expect(await save()).toBe(200);
    await expect(panel.getByTestId('catalyst-job-none')).toHaveText(P.G6.loc.unchanged);
    await expect(panel.getByTestId('catalyst-job')).toHaveCount(0);
    await expect(panel.getByTestId('publish-pending')).toHaveCount(0);

    // 되돌림(위치 확인 취소 → 202) — 다른 spec 이 보는 상태로
    const undo = page.waitForResponse(
      (r) => /\/api\/catalysts\/\d+$/.test(r.url()) && r.request().method() === 'PATCH',
    );
    await item.getByRole('button', { name: P.G6.loc.unconfirm }).click();
    expect((await undo).status()).toBe(202);
    runWorkerOnce();
    await expect(item.getByTestId('loc-status')).toHaveText(P.G6.loc.unconfirmed);
    expect(failed).toEqual([]);
  });
});
