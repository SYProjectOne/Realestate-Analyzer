/**
 * 계약 2026-10-09.8 화면 실 API e2e(MSW 끔, devseed 테스트 DB 위 uvicorn) — 쓰기 흐름은 이 임시 DB 에만 쓴다.
 *  - D11-6 할인: PriceRange.discount 를 헤더·가격 표에 FactCell 로(확인됨 → 구매가에서 뺌, 그 밖 → 표시만)
 *  - D11-5 호재 위치 확인: PATCH /catalysts/{id} → CatalystUpdated(links·reason·job) → 위치 확인됨 → 취소
 *  - M-5 사람 확인: 서버 허용 범위(화면이 먼저 막음) · entity_id(사실 행 지정) → 응답 entity·entity_id
 *  - D11-1 리비전: 사람 확인 → 재판정 잡 → worker 1회 → 같은 기준일 새 리비전 → 헤더 SnapshotPicker 기본 선택
 *  - D11-7 지역 확장: PATCH /regions/{id} → RegionPatched(added·removed·change_event·job_id) → region.expand 잡 표시
 * 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건. 파일 이름이 마지막(writes8)이라 앞 spec 의 읽기 기대를 흔들지 않는다.
 * region.expand 잡은 외부 수집을 하므로 worker 로 돌리지 않는다(마지막 테스트).
 */
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runWorkerOnce, setDiscount, WRITE_TOKEN } from './env';

const P = ko.page;
/** devseed 픽스처 단지: 1 = 더샵 송도그란테르(할인 주입), 2 = 엘리프 검단 포레듀(검단구 생활권) */
const DISCOUNT_COMPLEX = 1;
const DISCOUNT_NAME = '더샵 송도그란테르';
const HC_COMPLEX = 2;
const GEOMDAN_COMPLEX = '엘리프 검단 포레듀';
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

function countRequests(page: Page, method: string, pathname: RegExp): () => number {
  let n = 0;
  page.on('request', (r) => {
    if (r.method() === method && pathname.test(new URL(r.url()).pathname)) n += 1;
  });
  return () => n;
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

test.describe.serial('계약 .8 화면(실 API)', () => {
  test.afterAll(() => setDiscount(DISCOUNT_COMPLEX, null));

  test('D11-6 할인: 확인됨 → 헤더·가격 표 FactCell + 구매가에서 뺌, 추정 → 표시만, 없음 → 줄 없음', async ({
    page,
  }) => {
    const failed = watchApi(page);
    setDiscount(DISCOUNT_COMPLEX, '확인됨');
    await ready(page, `/complexes/${DISCOUNT_COMPLEX}#price`, P.G3.title);
    const header = page.getByRole('region', { name: DISCOUNT_NAME }).getByTestId('header-discount');
    await expect(header).toContainText('1,000만');
    await expect(header).toHaveAttribute('title', P.G3.price.discountApplied);
    const row = page.getByTestId('price-discount');
    await expect(row).toContainText('1,000만');
    await expect(row).toContainText(P.G3.price.discountApplied);
    // 서버 composition 에 '− 할인' 표기(확인됨일 때만 low·high 에서 뺐다)
    await expect(page.getByText(/할인 1,000만/)).toBeVisible();
    // 타입별 할인 열은 납부 조건 응답의 discount_by_type 이 있을 때만 — 현재 서버 payment_view 는 그 필드를
    // 싣지 않는다(선택 필드, 보고의 요청 참고). 기준 타입 할인(price.discount)이 위 두 곳에 보인다.

    setDiscount(DISCOUNT_COMPLEX, '추정');
    await page.reload();
    await expect(page.getByTestId('price-discount')).toContainText(P.G3.price.discountNotApplied);
    await expect(page.getByTestId('price-discount')).toContainText(ko.label.estimated);

    setDiscount(DISCOUNT_COMPLEX, null);
    await page.reload();
    await expect(page.getByRole('tab', { name: P.G3.tab.price })).toBeVisible();
    await expect(page.getByTestId('header-discount')).toHaveCount(0);
    await expect(page.getByTestId('price-discount')).toHaveCount(0);
    expect(failed).toEqual([]);
  });

  test('D11-5 호재 위치 확인: 생활권 지정 → links(같은 생활권·reason)·rejudge 잡 → 위치 확인됨 → 취소', async ({
    page,
  }) => {
    const failed = watchApi(page);
    const patches = countRequests(page, 'PATCH', /^\/api\/catalysts\/\d+$/);
    await ready(page, '/market', P.G6.title);
    const panel = page.getByRole('region', { name: P.G6.loc.title });
    const item = panel
      .getByRole('list', { name: P.G6.loc.title })
      .locator('li', { hasText: CATALYST });
    await expect(item.getByTestId('loc-status')).toHaveText(P.G6.loc.unconfirmed);
    await item.getByRole('button', { name: P.G6.loc.open }).click();
    const form = item.getByRole('form', { name: fill(P.G6.loc.formFor, { name: CATALYST }) });
    // 영향 범위 없이 저장 → 화면이 막는다(서버 422 와 같은 규칙)
    await form.getByRole('button', { name: P.G6.loc.submit }).click();
    await expect(form.getByRole('alert')).toHaveText(P.G6.loc.needTarget);
    expect(patches()).toBe(0);

    await form.getByRole('checkbox', { name: '검단구' }).check();
    const saved = page.waitForResponse(
      (r) => /\/api\/catalysts\/\d+$/.test(r.url()) && r.request().method() === 'PATCH',
    );
    await form.getByRole('button', { name: P.G6.loc.submit }).click();
    const res = await saved;
    expect(res.status()).toBe(200);
    const body = (await res.json()) as {
      links: { complex_id: number; reason: string | null }[];
      job: { job_name: string } | null;
    };
    expect(body.links.length).toBeGreaterThan(0);
    expect(body.job?.job_name).toBe('rejudge');

    const links = panel.getByTestId('catalyst-links');
    await expect(links.locator('tbody tr')).toHaveCount(body.links.length);
    const first = links.locator('tbody tr', { hasText: GEOMDAN_COMPLEX });
    await expect(first).toContainText('같은 생활권');
    await expect(first).toContainText(ko.label.unknown);
    await expect(first.locator('[data-meta="derived"]')).toHaveText('1.00');
    await expect(panel.getByTestId('catalyst-job')).toContainText('rejudge');
    await expect(item.getByTestId('loc-status')).toHaveText(P.G6.loc.confirmed);

    await item.getByRole('button', { name: P.G6.loc.unconfirm }).click();
    await expect(panel.getByTestId('catalyst-links')).toHaveText(P.G6.loc.cleared);
    await expect(item.getByTestId('loc-status')).toHaveText(P.G6.loc.unconfirmed);
    expect(patches()).toBe(2);
    expect(failed).toEqual([]);
  });

  test('M-5 사람 확인: 서버 범위 밖 값은 화면이 막고, entity_id 지정 저장 → 대상 행 · 재판정 → 새 리비전 기본 선택', async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const posts = countRequests(page, 'POST', /^\/api\/ops\/human-checks$/);
    const detail = await api<{ payment: { id: number | null; is_current: boolean }[] }>(
      request,
      `/complexes/${HC_COMPLEX}`,
    );
    const terms = detail.payment.find((p) => p.is_current) ?? detail.payment[0];
    expect(terms?.id).toBeTruthy();
    const termsId = String(terms!.id);

    // ClaimsPanel '사람 확인으로 복원'과 같은 주소(단지·필드·사실 행 미리 채움)
    await ready(
      page,
      `/ops?hc_complex=${HC_COMPLEX}&hc_field=down_payment_pct&hc_entity=${termsId}#human-check`,
      P.G7.title,
    );
    const form = page.getByRole('form', { name: P.G7.human });
    await expect(form.getByLabel(P.G7.hc.field)).toHaveValue('down_payment_pct');
    await expect(form.getByLabel(P.G7.hc.complex)).toHaveValue(String(HC_COMPLEX));
    await expect(form.getByTestId('hc-entity')).toBeVisible();
    await form.getByLabel(P.G7.hc.enteredBy).selectOption('운영자');
    const value = form.getByLabel(P.G7.hc.value);
    const submit = form.getByRole('button', { name: P.G7.hc.submit });
    // 계약금: 소수 둘째 자리까지(서버 422) — 화면이 먼저 막는다
    await value.fill('10.555');
    await submit.click();
    await expect(form.getByRole('alert')).toHaveText(fill(P.G7.hc.decimals, { n: '2' }));
    expect(posts()).toBe(0);

    await value.fill('10');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/ops/human-checks') && r.request().method() === 'POST',
    );
    await submit.click();
    const res = await saved;
    expect(res.status()).toBe(201);
    expect(JSON.parse(res.request().postData() ?? '{}')).toMatchObject({
      complex_id: HC_COMPLEX,
      field: 'down_payment_pct',
      entity_id: Number(termsId),
      value_text: '10',
    });
    expect(await res.json()).toMatchObject({
      entity: 'payment_terms',
      entity_id: Number(termsId),
    });
    await expect(form.getByTestId('human-check-result')).toContainText(
      P.G7.hcField.down_payment_pct,
    );
    await expect(form.getByTestId('human-check-target')).toHaveText(
      fill(P.G7.hc.target, { entity: P.G7.hcEntity.payment_terms, id: `#${termsId}` }),
    );

    // 최고 공급금액: 1,000만 원 미만은 서버 범위 밖 — 화면이 막는다
    await form.getByLabel(P.G7.hc.field).selectOption('max_price_won');
    await form.getByLabel(P.G7.hc.value).fill('5000');
    await submit.click();
    await expect(form.getByRole('alert')).toContainText('이상이어야');
    expect(posts()).toBe(1);

    // 재판정 제안 → 잡 등록 → worker 1회 → 같은 기준일 새 리비전(D11-1: 발행 스냅샷 불변)
    const queued = page.waitForResponse(
      (r) => r.url().endsWith('/api/jobs') && r.request().method() === 'POST',
    );
    await page
      .getByRole('region', { name: ko.app.notifications })
      .getByRole('button', { name: P.G7.rejudge })
      .first()
      .click();
    expect((await queued).status()).toBe(202);
    runWorkerOnce();

    const snapshots = await api<
      {
        id: number;
        asof_date: string;
        revision?: number;
        revision_reason?: string | null;
        status: string;
      }[]
    >(request, '/regions/1/snapshots');
    const latestDay = snapshots
      .map((s) => s.asof_date)
      .sort()
      .at(-1)!;
    const newest = snapshots
      .filter((s) => s.asof_date === latestDay && s.status === 'published')
      .sort((a, b) => (b.revision ?? 1) - (a.revision ?? 1))[0]!;
    expect(newest.revision ?? 1).toBeGreaterThan(1);

    await ready(page, '/', P.G1.title);
    const picker = page.getByLabel(ko.header.snapshot);
    await expect(picker).toHaveValue(String(newest.id));
    const option = picker.locator(`option[value="${newest.id}"]`);
    await expect(option).toHaveText(
      fill(ko.picker.revision, { date: latestDay, n: String(newest.revision) }),
    );
    if (newest.revision_reason) {
      await expect(option).toHaveAttribute(
        'title',
        fill(ko.picker.revisionReason, {
          n: String(newest.revision),
          reason: newest.revision_reason,
        }),
      );
    }
    // 이전 리비전(1)도 고를 수 있다
    await expect(picker.locator('option', { hasText: new RegExp(`^${latestDay}$`) })).toHaveCount(
      1,
    );
    expect(failed).toEqual([]);
  });

  test('D11-7 지역 확장: 시군구 추가 → PATCH → added·change_event·region.expand 잡', async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    await ready(page, '/regions/1/living-areas', P.G0_2.title);
    const panel = page.getByRole('region', { name: P.G0_2.expand.title });
    const current = panel.getByRole('list', { name: P.G0_2.expand.current });
    const region = await api<{ selections: unknown[] }>(request, '/regions/1');
    const before = region.selections.length;
    await expect(current.getByRole('listitem')).toHaveCount(before);
    await panel.getByLabel(P.G0_2.expand.search).fill('부천');
    const candidates = panel.getByRole('list', { name: P.G0_2.expand.candidates });
    // 같은 이름의 행정동·시군구 후보가 함께 온다 — 종류 배지로 시군구를 고른다
    const target = candidates
      .locator('li')
      .filter({ has: page.getByText('경기도 부천시 소사구', { exact: true }) })
      .filter({ has: page.getByText(P.common.candidateKind.sigungu, { exact: true }) });
    await target.getByRole('button', { name: P.G0_2.expand.add }).click();
    await expect(current.getByRole('listitem')).toHaveCount(before + 1);
    await expect(panel.getByTestId('expand-diff')).toContainText(
      fill(P.G0_2.expand.diff, { added: '1', removed: '0' }),
    );
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/regions/1') && r.request().method() === 'PATCH',
    );
    await panel.getByRole('button', { name: P.G0_2.expand.submit }).click();
    const res = await saved;
    expect(res.status()).toBe(200);
    const body = (await res.json()) as {
      job_id: number;
      added: { full_name: string }[];
      removed: unknown[];
      change_event: { severity: string };
    };
    expect(body.added.map((s) => s.full_name)).toEqual(['경기도 부천시 소사구']);
    expect(body.removed).toEqual([]);
    expect(body.change_event.severity).toBe('critical');

    const result = panel.getByTestId('expand-result');
    await expect(result).toContainText(fill(P.G0_2.expand.result, { added: '1', removed: '0' }));
    await expect(result).toContainText('경기도 부천시 소사구');
    const job = panel.getByTestId('expand-job');
    await expect(job).toContainText('region.expand');
    await expect(job).toContainText(ko.job.status.queued);
    await expect(current.getByRole('listitem')).toHaveCount(before + 1);
    expect(failed).toEqual([]);
  });
});
