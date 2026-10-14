/**
 * 계약 2026-10-09.17 화면 실 API e2e(R4 FE11, MSW 끔, devseed 테스트 DB 위 uvicorn) — 행 준비는 이 임시 DB 에만. 행을 고친 뒤 그
 * 지역 발행 저장본을 다시 만든다(env.runSql rematerialize — 계약 .10 D13-1). writes12-r4fe10 과 같은 단지(2·3·16)를 쓴다 — 그
 * 파일이 이미 바꿔 둔 단지라 뒤 파일(writes7~9)에 새 영향이 없다. 이 파일만 돌려도 되도록 행 준비를 스스로 한다.
 *  - F1(D22-5): 범위 경계 + 법정동 없음 + 주소에 동 없음 → API `judge_scope_reason` '범위 경계(주소에 동 없음)'(서버 계산)을
 *    G3 머리·G2 목록 행·G7 범위 경계 목록이 **그대로** 보인다(화면 규칙 복제 없음). 다른 단지도 API 사유 그대로
 *  - F3(D22-5): 기준 타입 가격 채택 보류 → API 현재 구매가 사유 '출처 상충 — compare 대기' → G3 가격 셀 '확인 불가(출처 상충 —
 *    compare 대기…)' + 짧은 안내(기준 타입 + 보류 출처 + 최고 공급금액 사람 확인), FE10 긴 설명 없음
 *  - F4(D22-4): 접수 '확인 불가(공식 홈페이지 동일성 미확인)' → 원문 버튼 '동일성 미확인 — 접수 근거 아님'·안내(다른 단지 아님)
 * F2(발행 리비전 이름 출처 서랍 200)는 writes12-r4fe10 F1 서랍 테스트(test.fail 표식 제거). F5·F6(G1 첫 적재 요약·법정동
 * 변경 행)은 devseed 에 bootstrap·법정동 보정 이벤트가 없어 vitest(r4fe11)가 본다. 모든 테스트: 화면이 부른 /api 응답 4xx/5xx 0건.
 */
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runSql, skipQueuedJobs, WRITE_TOKEN } from './env';

const P = ko.page;
const SNAPSHOT = 12; // devseed 픽스처 발행 스냅샷(writes11-r4·writes12-r4fe10 과 같은 이유로 고정)
const REGION = 1;
const INTAKE_COMPLEX = 2;
const HELD_COMPLEX = 3;
const BOUNDARY_COMPLEX = 16;
const NO_DONG = '범위 경계(주소에 동 없음)';
const CONFLICT_HOLD = '출처 상충 — compare 대기';

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

interface DetailLite {
  header: { id: number; name: string; judge_scope_reason?: string | null };
  price: {
    basis_type_code: string | null;
    price_low: { v: unknown; reason?: string | null };
    price_high: { v: unknown; reason?: string | null };
  };
}

async function detail(request: APIRequestContext, id: number): Promise<DetailLite> {
  const res = await request.get(`/api/complexes/${id}?snapshot=${SNAPSHOT}`, {
    headers: { Authorization: `Bearer ${WRITE_TOKEN}` },
  });
  expect(res.status()).toBe(200);
  return (await res.json()) as DetailLite;
}

const query = `?region=${REGION}&snapshot=${SNAPSHOT}`;

test.describe.serial('계약 .17 화면(실 API)', () => {
  test.beforeAll(() => {
    skipQueuedJobs('region.expand');
    skipQueuedJobs('region.bootstrap');
  });

  test("F1 judge_scope_reason: 서버 '범위 경계(주소에 동 없음)'을 G3 머리·G2 행·G7 범위 경계 목록이 그대로", async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    expect(
      runSql(
        [
          [
            "update complex set inclusion_class = '범위 경계', address = ?, legal_dong_code = NULL where id = ?",
            ['인천광역시 서구 검단신도시 RC3BL', BOUNDARY_COMPLEX],
          ],
        ],
        REGION,
      ),
    ).toBe(1);
    const boundary = await detail(request, BOUNDARY_COMPLEX);
    expect(boundary.header.judge_scope_reason).toBe(NO_DONG); // 서버가 계산(계약 .17 F1)
    const other = await detail(request, INTAKE_COMPLEX);
    const otherReason = other.header.judge_scope_reason;
    expect(typeof otherReason).toBe('string');

    // G3 머리 — '판정 범위 사유' 칸, 포함 분류는 맨 분류 문구
    await ready(page, `/complexes/${BOUNDARY_COMPLEX}${query}`, P.G3.title);
    await expect(page.getByTestId('scope-reason')).toHaveText(NO_DONG);
    await expect(page.getByTestId('boundary-reason')).toHaveCount(0);
    await ready(page, `/complexes/${INTAKE_COMPLEX}${query}`, P.G3.title);
    await expect(page.getByTestId('scope-reason')).toContainText(otherReason!);

    // G2 목록 행 — 포함 분류 열 둘째 줄(R9-UI P4: 단지 분류 열은 기본 숨김 → 열 선택으로 켠 상태)
    await page.addInitScript(() =>
      window.localStorage.setItem('sa.g2.columns', JSON.stringify({ v: 2, inclusion: true })),
    );
    await ready(page, `/complexes${query}`, P.G2.title);
    await expect(page.getByTestId(`scope-reason-${BOUNDARY_COMPLEX}`)).toHaveText(NO_DONG);
    await expect(page.getByTestId(`scope-reason-${INTAKE_COMPLEX}`)).toHaveText(otherReason!);

    // G7 범위 경계 목록 — 단지마다 사유
    await ready(page, `/ops${query}`, P.G7.title);
    const list = page.getByRole('list', { name: P.G7.boundary.title });
    const item = list.getByRole('listitem').filter({ hasText: boundary.header.name });
    await expect(item.getByTestId('boundary-scope-reason')).toHaveText(NO_DONG);
    expect(failed).toEqual([]);
  });

  test("F3 기준 타입 가격 채택 보류 → API 사유 '출처 상충 — compare 대기' → 가격 셀 + 짧은 안내(긴 설명 없음)", async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const before = await detail(request, HELD_COMPLEX);
    const basis = before.price.basis_type_code!;
    expect(basis).toBeTruthy();
    const type = 'select id from complex_type where complex_id = ? and type_code = ?';
    expect(
      runSql(
        [
          [
            `update field_provenance set reason = ? where entity = 'complex_type' and field = 'max_price_won' and chosen = 1 and entity_id = (${type})`,
            [CONFLICT_HOLD, HELD_COMPLEX, basis],
          ],
          [
            'update complex_type set max_price_won = NULL where complex_id = ? and type_code = ?',
            [HELD_COMPLEX, basis],
          ],
        ],
        REGION,
      ),
    ).toBe(2);
    const held = await detail(request, HELD_COMPLEX);
    expect(held.price.price_low.v).toBeNull();
    expect(held.price.price_low.reason).toBe(CONFLICT_HOLD); // 계약 .17 F3(전에는 '분양가 미공개')
    expect(held.price.price_high.reason).toBe(CONFLICT_HOLD);

    await ready(page, `/complexes/${HELD_COMPLEX}${query}`, P.G3.title);
    const head = page.getByRole('region', { name: held.header.name });
    await expect(head.getByText(`${ko.empty.unknown}(${CONFLICT_HOLD}`).first()).toBeVisible();
    const note = page.getByTestId('held-price-note');
    await expect(note).toContainText(fill(P.G3.price.heldBasis, { type: basis }));
    await expect(note).not.toContainText(fill(P.G3.price.held, { type: basis }));
    const link = note.getByRole('link', { name: P.G3.price.heldHumanCheck });
    const href = new URL((await link.getAttribute('href'))!, 'http://localhost');
    expect(href.searchParams.get('hc_field')).toBe('max_price_won');
    expect(href.searchParams.get('hc_complex')).toBe(String(HELD_COMPLEX));

    await page.getByRole('tab', { name: P.G3.tab.price }).click();
    const tabNote = page.getByTestId('held-price-note-tab');
    await expect(tabNote).toBeVisible();
    await expect(tabNote).not.toContainText(fill(P.G3.price.held, { type: basis }));
    expect(failed).toEqual([]);
  });

  test("F4 접수 '확인 불가(공식 홈페이지 동일성 미확인)' → '다른 단지'와 다른 원문 버튼·안내", async ({
    page,
  }) => {
    const failed = watchApi(page);
    expect(
      runSql(
        [
          [
            "update intake_status set status = '확인 불가', reason = ? where complex_id = ? and snapshot_id = ?",
            ['공식 홈페이지 동일성 미확인', INTAKE_COMPLEX, SNAPSHOT],
          ],
        ],
        REGION,
      ),
    ).toBeGreaterThan(0);
    await ready(page, `/complexes/${INTAKE_COMPLEX}${query}`, P.G3.title);
    await expect(page.getByTestId('intake-badge').first()).toContainText(
      `${ko.intake.status['확인 불가']}(공식 홈페이지 동일성 미확인`,
    );
    await expect(page.getByRole('button', { name: P.G3.header.siteOtherEvidence })).toHaveCount(0);
    await expect(page.getByTestId('site-other-note')).toHaveCount(0);
    const raw = page.getByRole('button', { name: P.G3.header.siteUnconfirmedEvidence });
    await expect(raw).toBeVisible();
    const note = page.getByTestId('site-unconfirmed-note');
    await expect(note).toContainText(P.G3.header.siteUnconfirmedHint);
    await expect(note.getByRole('link', { name: P.G3.header.siteOtherHumanCheck })).toBeVisible();
    const opened = page.waitForResponse(
      (r) => new URL(r.url()).pathname.startsWith('/api/provenance/rd_') && r.status() === 200,
    );
    await raw.click();
    await opened;
    expect(failed).toEqual([]);
  });
});
