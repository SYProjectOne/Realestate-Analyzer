/**
 * 계약 2026-10-09.15 화면 실 API e2e(R4 FE9, MSW 끔, devseed 테스트 DB 위 uvicorn) — 쓰기·행 준비는 이 임시 DB 에만.
 *  - F1(D18-1·D20-1): judgment_log.model·provider(0015 열) → G7 판정 로그 '모델' 열, provider 'none' = '로컬'
 *  - F2(D18-2): G7 실제 호출 안내
 *  - F3·F4(D20-1): G0 '청약홈 조회 기간(고급)' → POST /regions applyhome_query 201 → region.applyhome_query 그대로. 형식 오류는
 *    폼이 막고(POST 없음), 같은 값을 서버에 직접 보내면 422 validation_error(loc applyhome_query) — 폼 검사 = 서버 검사
 *  - F5(D20-2): 트랙 (A) 공고 예정 후보(devseed 픽스처 complex 15 — applyhome_id null·track A) → G2 행 범위 '보류 — 공고 후
 *    재판정'·'확인 불가(공고 전…)', G3 머리 '공고 예정 후보(청약홈 미등록)'
 *  - F5·F7: G1 최근 변경 — complex·track(공고 예정 후보) 이벤트 · region·first_load(첫 적재 한 줄) 이벤트 표기
 * 파일 이름이 writes10 뒤라 앞 spec 의 기대를 흔들지 않는다. 모든 테스트: 화면이 부른 /api 응답 중 4xx/5xx 0건.
 */
import { expect, test, type Page } from '@playwright/test';
import ko from '../../src/i18n/ko.json' with { type: 'json' };
import { runSql, skipQueuedJobs, WRITE_TOKEN } from './env';

const P = ko.page;
const CANDIDATE = 15; // devseed 픽스처의 공고 전 단지(applyhome_id null, track 'A', 판정 범위 '보류')
/**
 * devseed 픽스처 발행 스냅샷(id 는 픽스처 snapshots.json 그대로). 앞 spec 의 재판정(mock 판정기)이 만든 뒷 리비전에서는 모든
 * 단지의 포함 분류가 review 라 후보도 '미해결'이 된다 — 픽스처 리비전(저장 범위 '보류')을 고정해서 본다.
 */
const SNAPSHOT = 12;

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

test.describe.serial('계약 .15 화면(실 API)', () => {
  test.beforeAll(() => {
    skipQueuedJobs('region.expand');
  });

  test('F1·F2 G7 판정 로그: model·provider 열(provider none = 로컬) · 실제 호출 안내', async ({
    page,
  }) => {
    const failed = watchApi(page);
    // 응답이 오는 즉시 본문을 읽는다 — 화면이 URL 쿼리(스냅샷)를 맞추며 다시 그리면 늦게 읽은 본문은 버려질 수 있다
    // (R4 FE11 e2e:api 1회차: 'Response body is not available for a response that was navigated away from')
    const first = page
      .waitForResponse(
        (r) => new URL(r.url()).pathname === '/api/ops/judgments' && r.status() === 200,
      )
      .then((r) => r.json() as Promise<{ items: { judgment_seq: number | null }[] }>);
    await ready(page, '/ops?region=1', P.G7.title);
    const ops = await first;
    const [a, b] = ops.items.map((i) => i.judgment_seq).filter((s): s is number => s !== null);
    expect(a).toBeDefined();
    expect(b).toBeDefined();
    await expect(page.getByTestId('judgment-real-hint')).toHaveText(P.G7.stat.realHint);
    // devseed 판정 행은 .15 이전 녹화 — model·provider 없음 → '기록 없음'
    await expect(page.getByTestId(`judgment-model-${a}`)).toHaveText(P.G3.judgment.modelNone);
    // 0015 열에 응답 모양 그대로(로컬 처리 · 모델 호출) 넣고 다시 읽는다
    expect(
      runSql([
        [
          'update judgment_log set model = ?, provider = ? where seq = ?',
          ['jev-latest', 'none', a!],
        ],
        [
          'update judgment_log set model = ?, provider = ? where seq = ?',
          ['jev-1.13.0', 'typesafe', b!],
        ],
      ]),
    ).toBe(2);
    await page.reload();
    const local = page.getByTestId(`judgment-model-${a}`);
    await expect(local).toContainText('jev-latest');
    await expect(local.getByText(P.G3.judgment.local, { exact: true })).toHaveAttribute(
      'title',
      P.G3.judgment.localHint,
    );
    const real = page.getByTestId(`judgment-model-${b}`);
    await expect(real).toContainText('jev-1.13.0');
    await expect(real).toContainText(fill(P.G3.judgment.provider, { provider: 'typesafe' }));
    expect(failed).toEqual([]);
  });

  test('F3·F4 G0 조회 기간(고급) → POST applyhome_query 201 → 저장 그대로, 형식 오류는 폼과 서버가 같이 막는다', async ({
    page,
    request,
  }) => {
    const failed = watchApi(page);
    await ready(page, '/regions/new', P.G0.title);
    await page.getByRole('searchbox', { name: P.G0.search }).fill('검단');
    const candidates = page.getByRole('list', { name: P.G0.candidates });
    await candidates.getByRole('checkbox').first().check();
    await page.getByLabel(P.G0.name, { exact: true }).fill('e2e 조회 기간');
    const group = page.getByRole('group', { name: P.G0.window.title });
    await group.getByText(P.G0.window.title, { exact: true }).click();
    await expect(group.getByText(P.G0.window.hint)).toBeVisible();
    const from = group.getByLabel(P.G0.window.from);
    const to = group.getByLabel(P.G0.window.to);
    const start = page.getByRole('button', { name: P.G0.start });

    // 형식 오류(월 13) → 폼이 막는다
    await from.fill('2024-13');
    await expect(group.getByText(P.G0.window.invalid)).toBeVisible();
    await expect(start).toBeDisabled();
    // 서버도 같은 값을 422 로 거절한다(폼 검사 = 계약 패턴)
    const bad = await request.post('/api/regions', {
      headers: { Authorization: `Bearer ${WRITE_TOKEN}` },
      data: {
        name: 'e2e 422',
        query_text: '검단',
        selections: [{ kind: 'sigungu', code: '28260', full_name: '인천광역시 서구' }],
        applyhome_query: { from_ym: '2024-13' },
      },
    });
    expect(bad.status()).toBe(422);
    const err = (await bad.json()) as { code: string; field_errors?: { loc: unknown[] }[] };
    expect(err.code).toBe('validation_error');
    expect(JSON.stringify(err.field_errors ?? [])).toContain('applyhome_query');

    // 맞는 값 → 201 + 그 키만 저장
    await from.fill('2024-10');
    await to.fill('2027-03');
    await expect(start).toBeEnabled();
    const created = page.waitForResponse(
      (r) => new URL(r.url()).pathname === '/api/regions' && r.request().method() === 'POST',
    );
    await start.click();
    const res = await created;
    expect(res.status()).toBe(201);
    expect((res.request().postDataJSON() as { applyhome_query?: unknown }).applyhome_query).toEqual(
      { from_ym: '2024-10', to_ym: '2027-03' },
    );
    const body = (await res.json()) as { region: { id: number; applyhome_query: unknown } };
    expect(body.region.applyhome_query).toEqual({ from_ym: '2024-10', to_ym: '2027-03' });
    // 외부 수집 bootstrap 잡은 이 테스트 DB 에서 돌리지 않는다
    skipQueuedJobs('region.bootstrap');
    const got = await request.get(`/api/regions/${body.region.id}`, {
      headers: { Authorization: `Bearer ${WRITE_TOKEN}` },
    });
    expect(((await got.json()) as { applyhome_query: unknown }).applyhome_query).toEqual({
      from_ym: '2024-10',
      to_ym: '2027-03',
    });
    expect(failed).toEqual([]);
  });

  test("F5 트랙 A 공고 예정 후보: G2 행 '보류 — 공고 후 재판정'·'확인 불가(공고 전…)', G3 머리 '공고 예정 후보'", async ({
    page,
  }) => {
    const failed = watchApi(page);
    await ready(page, `/complexes?region=1&snapshot=${SNAPSHOT}`, P.G2.title);
    const link = page.locator(`a[href^="/complexes/${CANDIDATE}"]`).first();
    await expect(link).toBeVisible();
    const row = page.locator('tr', { has: link });
    await expect(row.getByTestId('judge-scope')).toHaveText(P.common.judgeScope['보류']);
    // R9-UI P7: 서버 사유 '공고 전'은 쉬운 말로 보인다(원 사유는 title)
    const plain = `${ko.empty.unknown}(${ko.empty.reasonPlain.pre_notice}`.replace(/[()]/g, '\\$&');
    await expect(row.getByText(new RegExp(`^${plain}`)).first()).toBeVisible();

    await ready(page, `/complexes/${CANDIDATE}?region=1&snapshot=${SNAPSHOT}`, P.G3.title);
    const badge = page.getByTestId('upcoming-badge');
    await expect(badge).toHaveText(P.G3.header.upcoming);
    await expect(badge).toHaveAttribute('title', P.G3.header.upcomingHint);
    await expect(page.getByTestId('judge-scope').first()).toHaveText(P.common.judgeScope['보류']);
    // 청약홈 공고 단지에는 없다
    await ready(page, `/complexes/2?region=1&snapshot=${SNAPSHOT}`, P.G3.title);
    await expect(page.getByTestId('judge-scope').first()).toBeVisible();
    await expect(page.getByTestId('upcoming-badge')).toHaveCount(0);
    expect(failed).toEqual([]);
  });

  test("F5·F7 G1 최근 변경: '공고 예정 후보'(→ G3) · '지역 · 첫 적재' 요약 한 줄(화살표 없음)", async ({
    page,
  }) => {
    const failed = watchApi(page);
    const summary = '첫 적재: 단지 16개, 값 300건(빈 값 → 값 — 변경 이벤트 대신 요약)';
    const insert =
      'insert into change_event (snapshot_id, entity, entity_id, field, old_text, new_text, detected_at, severity, ' +
      `triggers_rejudge, complex_id) values (${SNAPSHOT}, ?, ?, ?, NULL, ?, ?, ?, 0, ?)`;
    expect(
      runSql(
        [
          [insert, ['region', 1, 'first_load', summary, '2026-10-08T23:58:00+09:00', 'info', null]],
          [
            insert,
            [
              'complex',
              CANDIDATE,
              'track',
              'A 공고 예정 후보 e2e(언론, 청약홈 미등록)',
              '2026-10-08T23:59:00+09:00',
              'notice',
              CANDIDATE,
            ],
          ],
        ],
        1,
      ),
    ).toBe(2);
    await ready(page, `/?region=1&snapshot=${SNAPSHOT}`, P.G1.title);
    const feed = page.getByRole('list', { name: P.G1.changes });
    const first = feed.getByRole('listitem').filter({ hasText: summary });
    await expect(first).toHaveCount(1);
    await expect(first.getByText(P.common.changeEntity.region, { exact: true })).toBeVisible();
    // 계약 .20 F5: 서버 summary 한 줄(필드 이름은 summary 안·title) — 내부 필드 이름·빈 값 화살표는 없다
    await expect(first).not.toContainText('first_load');
    await expect(first).not.toContainText(`${P.common.none} →`);
    const track = feed.getByRole('listitem').filter({ hasText: 'A 공고 예정 후보 e2e' });
    // 계약 .20 F5: 서버 summary 한 줄 — 내부 필드 이름(track)은 보이지 않는다
    await expect(track).toHaveCount(1);
    await expect(track).not.toContainText(/\btrack\b/);
    await expect(track.getByRole('link')).toHaveAttribute(
      'href',
      new RegExp(`^/complexes/${CANDIDATE}`),
    );
    expect(failed).toEqual([]);
  });
});
