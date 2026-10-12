/**
 * 계약 2026-10-09.16 화면 실 API e2e(R4 FE10, MSW 끔, devseed 테스트 DB 위 uvicorn) — 행 준비는 이 임시 DB 에만(devseed 가
 * 실행마다 DB 를 새로 만든다). 행을 고친 뒤 그 지역 발행 저장본을 다시 만든다(env.runSql rematerialize — 계약 .10 D13-1).
 *  - F1(D21-8): 단지 이름 출처 행(field_provenance complex·name, 라벨 '비공식')을 넣으면 API 가 name_prov·name_label 을
 *    내고 → G2 이름 옆 '비공식' 배지·G3 이름 버튼(data-prov). 출처 행이 없는 시드 행은 키 없음. 발행 리비전의 이름 출처
 *    서랍은 백엔드 결함(저장본 출처 수집이 name_prov 를 빠뜨림 — 404)이라 test.fail 로 표시(고쳐지면 알린다)
 *  - F4(D21-5): 접수 '확인 불가(공식 홈페이지가 다른 단지)' → G3 원문 버튼 문구·안내·G7 사람 확인(접수 상태) 링크
 *  - F5(D21-6): 범위 경계 + 법정동 없음 + 주소에 동 없음 → G3 '범위 경계(주소에 동 없음)'
 *  - F6(D21-1): 출처 발췌 '[단위 근거]' 줄 → 서랍 '단위 근거', reason '단위 표기 없음 — 원으로 봄' 라벨, 기준 타입 가격 채택
 *    보류('출처 상충 — compare 대기') → G3 머리·가격표 안내 + '최고 공급금액' 사람 확인 링크
 * F2(공고 예정 후보 '공고 전')는 writes11-r4 F5 가 실 API 로 본다. F3(rd_ 생활권 시세)은 devseed 실거래 행에 출처 행이 있어(fp_)
 * 실 API 로 재현하지 않는다 — vitest(r4fe10 F3)가 rd_ 서랍을 본다. 모든 테스트: 화면이 부른 /api 응답 중 4xx/5xx 0건.
 */
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runSql, skipQueuedJobs, WRITE_TOKEN } from './env';

const P = ko.page;
const SNAPSHOT = 12; // devseed 픽스처 발행 스냅샷(writes11-r4 와 같은 이유로 고정)
const REGION = 1;
const CANDIDATE = 15; // 트랙 (A) 공고 예정 후보(applyhome_id null)
const INTAKE_COMPLEX = 2;
const BOUNDARY_COMPLEX = 16;
const HELD_COMPLEX = 3;

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
  header: { id: number; name: string; name_prov?: string | null; name_label?: string | null };
  price: { basis_type_code: string | null; price_low: { v: unknown; reason?: string | null } };
  types: { type_code: string; max_price_won: { prov: string | null } }[];
}

async function detail(request: APIRequestContext, id: number): Promise<DetailLite> {
  const res = await request.get(`/api/complexes/${id}?snapshot=${SNAPSHOT}`, {
    headers: { Authorization: `Bearer ${WRITE_TOKEN}` },
  });
  expect(res.status()).toBe(200);
  return (await res.json()) as DetailLite;
}

const query = `?region=${REGION}&snapshot=${SNAPSHOT}`;
/** F1 첫 테스트가 넣은 이름 출처 id(다음 테스트가 서랍을 연다) */
let nameProv = '';

test.describe.serial('계약 .16 화면(실 API)', () => {
  test.beforeAll(() => {
    skipQueuedJobs('region.expand');
    skipQueuedJobs('region.bootstrap');
  });

  test("F1 이름 출처: 출처 행 없으면 키 없음 → 넣으면 G2 '비공식' 배지·G3 이름 버튼(data-prov)", async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const before = await detail(request, CANDIDATE);
    expect('name_prov' in before.header).toBe(false); // devseed 시드 = 이름 출처 행 없음(.16: 키 없음)
    expect(
      runSql(
        [
          [
            'insert into field_provenance (entity, entity_id, field, value_text, url, checked_at, label, reason, ' +
              "source_rank, chosen, value_norm, excerpt) values ('complex', ?, 'name', ?, ?, ?, '비공식', ?, 4, 1, ?, ?)",
            [
              CANDIDATE,
              before.header.name,
              'https://news.example.com/e2e/upcoming',
              '2026-10-08',
              '언론 기사(공고 예정)',
              before.header.name,
              `${before.header.name} 내년 상반기 분양 예정`,
            ],
          ],
        ],
        REGION,
      ),
    ).toBe(1);
    const after = await detail(request, CANDIDATE);
    expect(after.header.name_label).toBe('비공식');
    const prov = after.header.name_prov!;
    expect(prov).toMatch(/^fp_\d+$/);

    await ready(page, `/complexes${query}`, P.G2.title);
    const badge = page.getByTestId(`name-prov-${CANDIDATE}`);
    await expect(badge).toHaveText(ko.label.unofficial);
    await expect(badge).toHaveAttribute('data-prov', prov);
    // 출처 행이 없는 다른 단지에는 배지가 없다
    await expect(page.getByTestId(`name-prov-${INTAKE_COMPLEX}`)).toHaveCount(0);

    await ready(page, `/complexes/${CANDIDATE}${query}`, P.G3.title);
    const name = page.getByRole('button', {
      name: fill(P.common.nameProv.open, { name: before.header.name, label: ko.label.unofficial }),
    });
    await expect(name).toHaveAttribute('data-prov', prov);
    await expect(name.getByTestId('label-badge')).toHaveText(ko.label.unofficial);
    nameProv = prov;
    expect(failed).toEqual([]);
  });

  test('F1 이름 출처 서랍: 발행 리비전 저장본에서 GET /provenance/{name_prov}?snapshot_id= 200', async ({
    page,
  }) => {
    // 백엔드 결함(보고·계약 변경 요청): 발행 저장본의 출처 서랍 수집(app/snapshot_view.py `_PROV_RE`)이 `"prov":` 키만 보고
    // `"name_prov":` 를 모으지 않아, 발행 리비전에서 이름 출처 서랍이 404('발행 리비전 12 저장본에 출처 fp_… 없음')다.
    // 화면은 계약대로 보고 있는 리비전(snapshot_id)으로 조회한다. 백엔드가 고치면 이 표식을 지운다(그때 이 테스트가 알린다).
    test.fail(
      true,
      'snapshot_view 저장본 출처 수집이 name_prov 를 빠뜨림(발행 리비전 이름 출처 서랍 404)',
    );
    expect(nameProv).toMatch(/^fp_\d+$/);
    await ready(page, `/complexes/${CANDIDATE}${query}`, P.G3.title);
    const opened = page.waitForResponse(
      (r) => new URL(r.url()).pathname === `/api/provenance/${nameProv}`,
    );
    await page.locator(`button[data-prov="${nameProv}"]`).first().click();
    const res = await opened;
    expect(new URL(res.url()).searchParams.get('snapshot_id')).toBe(String(SNAPSHOT));
    expect(res.status()).toBe(200);
    const dialog = page.getByRole('dialog', { name: ko.provenance.title });
    await expect(dialog.getByText('https://news.example.com/e2e/upcoming')).toBeVisible();
  });

  test("F4 접수 '확인 불가(공식 홈페이지가 다른 단지)' → 원문 버튼 문구·안내·G7 접수 상태 사람 확인", async ({
    page,
  }) => {
    const failed = watchApi(page);
    expect(
      runSql(
        [
          [
            "update intake_status set status = '확인 불가', reason = ? where complex_id = ? and snapshot_id = ?",
            ['공식 홈페이지가 다른 단지', INTAKE_COMPLEX, SNAPSHOT],
          ],
        ],
        REGION,
      ),
    ).toBeGreaterThan(0);
    await ready(page, `/complexes/${INTAKE_COMPLEX}${query}`, P.G3.title);
    await expect(page.getByTestId('intake-badge').first()).toContainText(
      `${ko.intake.status['확인 불가']}(공식 홈페이지가 다른 단지`,
    );
    await expect(page.getByRole('button', { name: P.G3.header.intakeEvidence })).toHaveCount(0);
    const raw = page.getByRole('button', { name: P.G3.header.siteOtherEvidence });
    await expect(raw).toBeVisible();
    const note = page.getByTestId('site-other-note');
    await expect(note).toContainText(P.G3.header.siteOtherHint);
    const opened = page.waitForResponse(
      (r) => new URL(r.url()).pathname.startsWith('/api/provenance/rd_') && r.status() === 200,
    );
    await raw.click();
    await opened;
    await page
      .getByRole('dialog', { name: ko.provenance.title })
      .getByRole('button', { name: ko.provenance.close })
      .first()
      .click();

    await note.getByRole('link', { name: P.G3.header.siteOtherHumanCheck }).click();
    await expect(page.getByRole('heading', { level: 1, name: P.G7.title })).toBeVisible();
    const url = new URL(page.url());
    expect(url.searchParams.get('hc_complex')).toBe(String(INTAKE_COMPLEX));
    expect(url.searchParams.get('hc_field')).toBe('intake_status');
    const form = page.getByRole('form', { name: P.G7.human });
    await expect(form.getByLabel(P.G7.hc.field, { exact: true })).toHaveValue('intake_status');
    await expect(form.getByLabel(P.G7.hc.complex, { exact: true })).toHaveValue(
      String(INTAKE_COMPLEX),
    );
    expect(failed).toEqual([]);
  });

  test("F5 범위 경계 + 법정동 없음 + 주소에 동 없음 → G3 '범위 경계(주소에 동 없음)'", async ({
    page,
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
    await ready(page, `/complexes/${BOUNDARY_COMPLEX}${query}`, P.G3.title);
    await expect(page.getByTestId('boundary-reason')).toHaveText(P.G3.header.boundary.noDong);
    // 범위 경계가 아닌 단지에는 사유가 없다
    await ready(page, `/complexes/${INTAKE_COMPLEX}${query}`, P.G3.title);
    await expect(page.getByTestId('boundary-reason')).toHaveCount(0);
    expect(failed).toEqual([]);
  });

  test("F6 '[단위 근거]' 발췌·'단위 표기 없음 — 원으로 봄' 라벨 → 출처 서랍", async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const d = await detail(request, INTAKE_COMPLEX);
    const [first, second] = d.types
      .map((t) => t.max_price_won.prov)
      .filter((p): p is string => !!p);
    expect(first).toMatch(/^fp_\d+$/);
    expect(second).toMatch(/^fp_\d+$/);
    const id = (p: string) => Number(p.slice(3));
    expect(
      runSql(
        [
          [
            'update field_provenance set excerpt = excerpt || ? where id = ?',
            ['\n[단위 근거] 주택형 공급금액 (단위: 천원)', id(first!)],
          ],
          [
            'update field_provenance set reason = ? where id = ?',
            ['단위 표기 없음 — 원으로 봄', id(second!)],
          ],
        ],
        REGION,
      ),
    ).toBe(2);
    await ready(page, `/complexes/${INTAKE_COMPLEX}${query}#price`, P.G3.title);
    const dialog = page.getByRole('dialog', { name: ko.provenance.title });

    await page.locator(`button[data-prov="${first}"]`).first().click();
    await expect(dialog.getByTestId('provenance-unit-basis')).toHaveText(
      '주택형 공급금액 (단위: 천원)',
    );
    await expect(dialog.getByTestId('provenance-excerpt')).not.toContainText('[단위 근거]');
    await dialog.getByRole('button', { name: ko.provenance.close }).first().click();

    const assumed = fill(ko.label.withReason, {
      label: ko.label.confirmed,
      reason: '단위 표기 없음 — 원으로 봄',
    });
    const cell = page.locator(`button[data-prov="${second}"]`).first();
    await expect(cell.getByTestId('label-badge')).toHaveText(assumed);
    await cell.click();
    await expect(dialog.getByText(assumed).first()).toBeVisible();
    expect(failed).toEqual([]);
  });

  test("F6 기준 타입 가격 채택 보류('출처 상충 — compare 대기') → G3 머리·가격표 안내 + 최고 공급금액 사람 확인", async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    const d = await detail(request, HELD_COMPLEX);
    const basis = d.price.basis_type_code!;
    expect(basis).toBeTruthy();
    const type = 'select id from complex_type where complex_id = ? and type_code = ?';
    expect(
      runSql(
        [
          [
            `update field_provenance set reason = ? where entity = 'complex_type' and field = 'max_price_won' and chosen = 1 and entity_id = (${type})`,
            ['출처 상충 — compare 대기', HELD_COMPLEX, basis],
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

    await ready(page, `/complexes/${HELD_COMPLEX}${query}`, P.G3.title);
    const note = page.getByTestId('held-price-note');
    await expect(note).toContainText(fill(P.G3.price.held, { type: basis }));
    await expect(note.getByText(/출처 상충 — compare 대기/)).toBeVisible();
    const link = note.getByRole('link', { name: P.G3.price.heldHumanCheck });
    const href = new URL((await link.getAttribute('href'))!, 'http://localhost');
    expect(href.pathname).toBe('/ops');
    expect(href.searchParams.get('hc_field')).toBe('max_price_won');
    expect(href.searchParams.get('hc_complex')).toBe(String(HELD_COMPLEX));

    await page.getByRole('tab', { name: P.G3.tab.price }).click();
    await expect(page.getByTestId('held-price-note-tab')).toBeVisible();
    expect(failed).toEqual([]);
  });
});
