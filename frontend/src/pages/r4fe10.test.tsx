/**
 * R4 FE10 — 계약 2026-10-09.16 FE 차이 표(`contracts/CHANGELOG.md` .16 F1–F8) 화면 맞춤.
 *  - F1(D21-8): `ComplexRow`·`Complex` 의 `name_prov`·`name_label`(선택 — 없으면 null) → G2 이름 옆 라벨 배지(→ 출처 서랍),
 *    G3 머리 이름 클릭 → 출처 서랍 + 라벨 배지, G3 출처 탭 '단지 이름'. 공고 예정 후보 = '비공식'. MSW 목도 계약 예시 값
 *  - F2(D21-8): 공고 예정 후보 공고일·가격 '확인 불가(공고 전)' — 서버 Fact 그대로(회귀 방지)
 *  - F3(D21-4): G6 생활권 시세 블록 Fact 의 `rd_` 출처 → 출처 서랍(회귀 방지)
 *  - F4(D21-5): 접수 '확인 불가(공식 홈페이지가 다른 단지)' — G3 머리 원문 버튼이 '접수 근거'가 아니라 '다른 단지 페이지'임을
 *    밝히고, 사람 확인(접수 상태) 링크
 *  - F5(D21-6): G3 포함 분류 '범위 경계' 사유 — 계약 .17 F1 서버 `judge_scope_reason` 으로 대체(r4fe11)
 *  - F6(D21-1): 출처 발췌 끝 `[단위 근거] <표 머리 줄>` → 서랍·출처 탭에 '단위 근거' 줄(발췌 하이라이트는 금액 행으로),
 *    가격 채택 보류('출처 상충 — compare 대기') 기준 타입 → G3 머리·가격표 안내 + 보류 Fact(→ 서랍) + 사람 확인 링크
 *  - F7(D21-7)·F8(D21-5): 서버 문자열 그대로(회귀 방지)
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type {
  ChangeEvent,
  ComplexDetail,
  ComplexRow,
  ComplexRowPage,
  Dashboard,
  Fact,
  Intake,
  JudgmentEnvelope,
  JudgmentOps,
  Market,
  Provenance,
} from '@/api/types';
import { t } from '@/i18n';
import { handlers } from '@/mocks/handlers';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute, renderWithProviders } from '@/test/render';
import { JudgmentTable } from './complex/JudgmentsTab';
import { highlightExcerpt } from './complex/ProvenanceTab';
import { splitUnitBasis } from '@/lib/unitBasis';
import { matching, recordRequests } from './_shared/testing';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function example<T>(path: string): Promise<T> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  return (await res?.json()) as T;
}

/** 목 전체(보강 → 생성 순서) */
async function mock<T>(path: string): Promise<T> {
  const res = await getResponse(
    handlers as RequestHandler[],
    new Request(`http://localhost/api${path}`),
  );
  if (!res) throw new Error(`no mock for ${path}`);
  return (await res.json()) as T;
}

const CANDIDATE = 15; // 계약 예시의 트랙 (A) 공고 예정 후보(complex_detail.json 머리 name_prov fp_8801 '비공식')
const CANDIDATE_NAME = '계양신도시 카이브 유보라';

function unknownFact(reason: string, prov: string | null = null, unit = 'won'): Fact {
  return { v: null, label: '확인 불가', reason, prov, checked_at: '2026-10-07', unit } as Fact;
}

/** 이름 출처 키를 뺀다(.15 이전 저장본·시드 = 키 없음) */
function withoutName<T extends { name_prov?: unknown; name_label?: unknown }>(x: T): T {
  const { name_prov: _p, name_label: _l, ...rest } = x;
  return rest as T;
}

// ─── F1 단지 이름 출처·라벨 ─────────────────────────────

describe('F1(D21-8) 단지 이름 name_prov·name_label', () => {
  it('목: 목록 예시의 공고 예정 후보 행 = 계약 예시 name_prov fp_8801 · 비공식, 상세 머리도 같은 키', async () => {
    const page = await mock<ComplexRowPage>('/snapshots/12/complexes?page=1&size=100');
    const row = page.items.find((r) => r.complex_id === CANDIDATE)!;
    expect(row.name_prov).toBe('fp_8801');
    expect(row.name_label).toBe('비공식');
    // 계약 예시에 이름 출처가 없는 행은 키가 없다(= null)
    const plain = page.items.find((r) => ![2, 4, CANDIDATE].includes(r.complex_id))!;
    expect('name_prov' in plain).toBe(false);
    const detail = await mock<ComplexDetail>(`/complexes/${CANDIDATE}`);
    expect(detail.header.name_prov).toBe('fp_8801');
    expect(detail.header.name_label).toBe('비공식');
  });

  it("G2: 공고 예정 후보 이름 옆 '비공식' 배지 → 클릭하면 출처 서랍(GET /provenance/fp_8801), 이름 링크는 G3 그대로", async () => {
    const rec = recordRequests();
    renderRoute('/complexes');
    const link = await screen.findByRole('link', { name: CANDIDATE_NAME });
    expect(link).toHaveAttribute(
      'href',
      expect.stringMatching(new RegExp(`^/complexes/${CANDIDATE}`)),
    );
    const row = link.closest('tr') as HTMLElement;
    const badge = within(row).getByTestId(`name-prov-${CANDIDATE}`);
    expect(badge).toHaveTextContent(t('label.unofficial'));
    expect(badge).toHaveAttribute('data-prov', 'fp_8801');
    await userEvent.click(badge);
    await screen.findByRole('dialog', { name: t('provenance.title') });
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/provenance/fp_8801')).toHaveLength(1),
    );
    rec.stop();
  });

  it('G2: 이름 출처 키가 없는 행(옛 행·시드)에는 배지 없음', async () => {
    const page = await example<ComplexRowPage>('/snapshots/12/complexes');
    const first = page.items[0] as ComplexRow;
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes'), () =>
        HttpResponse.json({ ...page, items: [withoutName(first)], total: 1 }),
      ),
    );
    renderRoute('/complexes');
    const link = await screen.findByRole('link', { name: first.name });
    const row = link.closest('tr') as HTMLElement;
    expect(within(row).queryByTestId(`name-prov-${first.complex_id}`)).toBeNull();
  });

  it("G3 머리: 이름 클릭 → 출처 서랍(GET /provenance/fp_8801), 이름 옆 '비공식' 라벨", async () => {
    const rec = recordRequests();
    renderRoute(`/complexes/${CANDIDATE}`);
    const head = await screen.findByRole('region', { name: CANDIDATE_NAME });
    const heading = within(head).getByRole('heading', { level: 2 });
    const name = within(heading).getByRole('button', {
      name: t('page.common.nameProv.open', { name: CANDIDATE_NAME, label: t('label.unofficial') }),
    });
    expect(name).toHaveAttribute('data-prov', 'fp_8801');
    expect(within(name).getByTestId('label-badge')).toHaveTextContent(t('label.unofficial'));
    await userEvent.click(name);
    await screen.findByRole('dialog', { name: t('provenance.title') });
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/provenance/fp_8801')).toHaveLength(1),
    );
    rec.stop();
  });

  it('G3 머리: 이름 출처 키가 없으면 맨 이름(버튼·배지 없음)', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({ ...detail, header: withoutName(detail.header) }),
      ),
    );
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const heading = within(head).getByRole('heading', { level: 2 });
    expect(heading).toHaveTextContent(detail.header.name);
    expect(within(heading).queryByRole('button')).toBeNull();
    expect(within(heading).queryByTestId('label-badge')).toBeNull();
  });

  it("G3 출처 탭: name_prov 가 있으면 가격 다음에 '단지 이름' 항목(라벨 배지), 기본 선택은 가격 그대로", async () => {
    renderRoute(`/complexes/${CANDIDATE}#provenance`);
    const list = await screen.findByRole('list', { name: t('page.G3.provenance.fields') });
    const items = within(list).getAllByRole('listitem');
    const item = within(list)
      .getByRole('button', { name: t('page.G3.provenance.name') })
      .closest('li') as HTMLElement;
    expect(item).toHaveTextContent(CANDIDATE_NAME);
    expect(within(item).getByTestId('label-badge')).toHaveTextContent(t('label.unofficial'));
    // 목 상세(예시 가격 있음): 첫 항목은 가격(선택됨), 이름은 가격 두 항목 다음
    expect(items.indexOf(item)).toBe(2);
    expect(
      within(items[0] as HTMLElement).getByRole('button', { pressed: true }),
    ).toHaveTextContent(t('page.G2.col.price'));
  });
});

// ─── F2 공고 예정 후보 '확인 불가(공고 전)' ─────────────────

describe('F2(D21-8) 공고 예정 후보 가격 = 확인 불가(공고 전) — 서버 Fact 그대로', () => {
  it('G3 가격표 탭: 현재 구매가 low·high 가 공고 전 사유', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({
          ...detail,
          header: { ...detail.header, id: CANDIDATE, applyhome_id: null, track: 'A' },
          price: {
            ...detail.price,
            price_low: unknownFact('공고 전'),
            price_high: unknownFact('공고 전'),
            discount: null,
          },
          types: [],
        }),
      ),
    );
    renderRoute(`/complexes/${CANDIDATE}#price`);
    const panel = await screen.findByRole('tabpanel');
    expect(
      within(panel).getAllByText(
        t('empty.unknownWithReasonDate', {
          reason: '공고 전',
          date: '2026-10-07',
        }),
      ).length,
    ).toBe(2);
  });
});

// ─── F3 시장 생활권 시세 rd_ 출처 ──────────────────────────

describe('F3(D21-4) G6 생활권 시세 블록 — 실거래 원문 rd_ 출처 서랍', () => {
  it('중앙값·건수 셀 → GET /provenance/rd_9301?snapshot_id=12, 라벨 확인됨', async () => {
    const market = await example<Market>('/snapshots/12/market');
    const fact = (v: number, unit: 'won' | 'count'): Fact =>
      ({ v, label: '확인됨', prov: 'rd_9301', checked_at: '2026-10-07', unit }) as Fact;
    server.use(
      http.get(mswPath('/snapshots/:sid/market'), () =>
        HttpResponse.json({
          ...market,
          living_area_prices: [
            {
              living_area: 'la_1',
              name: '생활권 1',
              median_won: fact(812_000_000, 'won'),
              low_won: fact(700_000_000, 'won'),
              high_won: fact(905_000_000, 'won'),
              n_trades: fact(14, 'count'),
              trade_window: '2026-04~2026-09',
              basis: null,
            },
          ],
        } satisfies Market),
      ),
    );
    const rec = recordRequests();
    renderRoute('/market?snapshot=12');
    const table = await screen.findByRole('table', { name: t('page.G6.prices') });
    const cells = within(within(table).getAllByRole('row')[1] as HTMLElement).getAllByRole('cell');
    const median = (cells[1] as HTMLElement).querySelector<HTMLButtonElement>(
      'button[data-prov="rd_9301"]',
    );
    expect(median).not.toBeNull();
    expect(within(cells[3] as HTMLElement).getByTestId('label-badge')).toHaveTextContent('확인됨');
    await userEvent.click(median!);
    await screen.findByRole('dialog', { name: t('provenance.title') });
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/provenance/rd_9301')).toHaveLength(1),
    );
    expect(
      matching(rec.requests, 'GET', '/provenance/rd_9301')[0]!.url.searchParams.get('snapshot_id'),
    ).toBe('12');
    rec.stop();
  });
});

// ─── F4 공식 홈페이지가 다른 단지 ───────────────────────────

describe('F4(D21-5) 접수 확인 불가(공식 홈페이지가 다른 단지)', () => {
  async function useIntake(intake: Intake): Promise<ComplexDetail> {
    const detail = await example<ComplexDetail>('/complexes/2');
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({ ...detail, intake_current: intake, intake: [intake] }),
      ),
    );
    return detail;
  }

  it("배지 '접수 확인 불가(공식 홈페이지가 다른 단지, 날짜)' · 원문 버튼은 '접수 근거'가 아님 · 사람 확인(접수 상태) 링크", async () => {
    const base = (await example<ComplexDetail>('/complexes/2')).intake_current!;
    const detail = await useIntake({
      ...base,
      status: '확인 불가',
      reason: '공식 홈페이지가 다른 단지',
      raw_document_id: 9202,
    });
    const rec = recordRequests();
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).getByTestId('intake-badge')).toHaveTextContent(
      t('intake.withReasonDate', {
        status: t('intake.status.확인 불가'),
        reason: '공식 홈페이지가 다른 단지',
        date: '2026-10-07',
      }),
    );
    expect(
      within(head).queryByRole('button', { name: t('page.G3.header.intakeEvidence') }),
    ).toBeNull();
    const raw = within(head).getByRole('button', { name: t('page.G3.header.siteOtherEvidence') });
    const note = within(head).getByTestId('site-other-note');
    expect(note).toHaveTextContent(t('page.G3.header.siteOtherHint'));
    const link = within(note).getByRole('link', { name: t('page.G3.header.siteOtherHumanCheck') });
    expect(link.getAttribute('href')).toMatch(/^\/ops\?/);
    const href = new URL(link.getAttribute('href')!, 'http://localhost');
    expect(href.searchParams.get('hc_complex')).toBe(String(detail.header.id));
    expect(href.searchParams.get('hc_field')).toBe('intake_status');
    expect(href.hash).toBe('#human-check');
    await userEvent.click(raw);
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/provenance/rd_9202')).toHaveLength(1),
    );
    rec.stop();
  });

  it("다른 사유(예 '403')·가능은 그대로 '접수 근거 원문', 안내 없음", async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(
      within(head).getByRole('button', { name: t('page.G3.header.intakeEvidence') }),
    ).toBeInTheDocument();
    expect(within(head).queryByTestId('site-other-note')).toBeNull();
  });
});

// ─── F5 범위 경계 사유 ──────────────────────────────────────
// 계약 .17 F1(D22-5)로 대체: 화면이 서버 규칙(`has_dong_name` 정규식·범위 첫 행)을 옮겨 만들던 `complex/boundary.ts` 는 지웠고
// (규칙 3), 사유는 서버 `judge_scope_reason` 그대로 보인다 — r4fe11.test.tsx 'F1(D22-5) judge_scope_reason'.

// ─── F6 단위 근거·단위 상충 보류 ───────────────────────────

const UNIT_EXCERPT =
  '84A 1 2 61,700 7,000 68,700\n[단위 근거] 주택형 층 공급금액 (단위: 세대, 천원)';

describe('F6(D21-1) 단위 근거 발췌·단위 상충 보류 가격', () => {
  it("splitUnitBasis: 발췌 끝 '[단위 근거] …' 줄을 떼어 낸다(없으면 null)", () => {
    expect(splitUnitBasis(UNIT_EXCERPT)).toEqual({
      body: '84A 1 2 61,700 7,000 68,700',
      unitBasis: '주택형 층 공급금액 (단위: 세대, 천원)',
    });
    expect(splitUnitBasis('공급세대수 1,573세대')).toEqual({
      body: '공급세대수 1,573세대',
      unitBasis: null,
    });
    expect(splitUnitBasis(null)).toEqual({ body: null, unitBasis: null });
  });

  it('highlightExcerpt: 단위 근거가 붙은 발췌도 금액 행으로 원문 위치를 찾는다', () => {
    const text =
      '공급금액표\n주택형 층 공급금액 (단위: 세대, 천원)\n84A 1 2 61,700 7,000 68,700\n끝';
    const parts = highlightExcerpt(text, UNIT_EXCERPT, null, null);
    expect(parts).not.toBeNull();
    expect(parts!.mark).toBe('84A 1 2 61,700 7,000 68,700');
  });

  it("출처 서랍: 발췌 본문 + '단위 근거' 줄 따로, 라벨 '확인됨(단위 표기 없음 — 원으로 봄)'", async () => {
    const base = await example<Provenance>('/provenance/fp_1');
    server.use(
      http.get(mswPath('/provenance/:prov_id'), ({ params }) =>
        HttpResponse.json({
          ...base,
          id: String(params.prov_id),
          value_text: '61,700',
          label: '확인됨',
          reason: '단위 표기 없음 — 원으로 봄',
          excerpt: UNIT_EXCERPT,
          conflicts: [],
          conflict_group: null,
        } satisfies Provenance),
      ),
    );
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', {
      name: (await example<ComplexDetail>('/complexes/2')).header.name,
    });
    const cell = head.querySelector<HTMLButtonElement>('button[data-prov]')!;
    await userEvent.click(cell);
    const dialog = await screen.findByRole('dialog', { name: t('provenance.title') });
    const unit = await within(dialog).findByTestId('provenance-unit-basis');
    expect(unit).toHaveTextContent('주택형 층 공급금액 (단위: 세대, 천원)');
    expect(within(dialog).getByText(t('provenance.unitBasis'))).toBeInTheDocument();
    const quote = within(dialog).getByTestId('provenance-excerpt');
    expect(quote).toHaveTextContent('84A 1 2 61,700 7,000 68,700');
    expect(quote).not.toHaveTextContent('[단위 근거]');
    expect(
      within(dialog).getByText(
        t('label.withReason', {
          label: t('label.confirmed'),
          reason: '단위 표기 없음 — 원으로 봄',
        }),
      ),
    ).toBeInTheDocument();
  });

  async function useHeld(where: 'type' | 'notice'): Promise<ComplexDetail> {
    const detail = await example<ComplexDetail>('/complexes/2');
    const basis = detail.price.basis_type_code!;
    const held = unknownFact('출처 상충 — compare 대기; 단위 표기 없음 — 원으로 봄', 'fp_7001');
    const types = detail.types.map((row) =>
      where === 'type' && row.type_code === basis ? { ...row, max_price_won: held } : row,
    );
    const payment = detail.payment.map((p) =>
      where === 'notice' && p.is_current
        ? {
            ...p,
            price_by_type: {
              [basis]: {
                max_price_won: held,
                floor_sample_price_won: unknownFact('값 없음'),
              },
            },
          }
        : p,
    );
    const next: ComplexDetail = {
      ...detail,
      price: {
        ...detail.price,
        price_low: unknownFact('분양가 미공개'),
        price_high: unknownFact('분양가 미공개'),
        price_mid: unknownFact('분양가 미공개'),
        discount: null,
      },
      types,
      payment,
    };
    server.use(http.get(mswPath('/complexes/:id'), () => HttpResponse.json(next)));
    return next;
  }

  it.each(['type', 'notice'] as const)(
    "기준 타입 가격 채택 보류(%s) → G3 머리 안내 + 보류 Fact(→ 서랍 fp_7001) + '최고 공급금액 사람 확인' 링크",
    async (where) => {
      const detail = await useHeld(where);
      renderRoute('/complexes/2');
      const head = await screen.findByRole('region', { name: detail.header.name });
      const note = within(head).getByTestId('held-price-note');
      expect(note).toHaveTextContent(
        t('page.G3.price.held', { type: detail.price.basis_type_code! }),
      );
      expect(note.querySelector('[data-prov="fp_7001"]')).not.toBeNull();
      const link = within(note).getByRole('link', { name: t('page.G3.price.heldHumanCheck') });
      const href = new URL(link.getAttribute('href')!, 'http://localhost');
      expect(href.pathname).toBe('/ops');
      expect(href.searchParams.get('hc_field')).toBe('max_price_won');
      expect(href.searchParams.get('hc_complex')).toBe(String(detail.header.id));
    },
  );

  it('G3 가격표 탭에도 같은 안내', async () => {
    await useHeld('type');
    renderRoute('/complexes/2#price');
    const panel = await screen.findByRole('tabpanel');
    expect(within(panel).getByTestId('held-price-note-tab')).toBeInTheDocument();
  });

  it('보류가 아니면(가격 있음) 안내 없음', async () => {
    const detail = await example<ComplexDetail>('/complexes/2');
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).queryByTestId('held-price-note')).toBeNull();
  });
});

// ─── F7·F8 서버 문자열 그대로 ───────────────────────────────

describe('F7(D21-7)·F8(D21-5) 서버 문자열 그대로', () => {
  it("G1 첫 적재 요약 새 문구('첫 적재 중 기록·덮어쓰기')를 그대로 한 줄", async () => {
    const summary =
      '첫 적재: 단지 17개, 값 300건(첫 적재 중 기록·덮어쓰기 — 변경 이벤트 대신 요약)';
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    const ev: ChangeEvent = {
      id: 1,
      snapshot_id: 12,
      entity: 'region',
      entity_id: 1,
      field: 'first_load',
      old_text: null,
      new_text: summary,
      detected_at: '2026-10-08T09:00:00+09:00',
      severity: 'info',
      triggers_rejudge: false,
      complex_id: null,
      complex_name: null,
      tab: null,
    };
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () =>
        HttpResponse.json({ ...dash, changes: [ev] }),
      ),
    );
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    expect(within(feed).getByText(summary)).toBeInTheDocument();
  });

  it("판정 로그 purpose 'classify:site_identity:batch0' 그대로", async () => {
    const ops = await example<JudgmentOps>('/ops/judgments');
    const base = ops.items[0] as JudgmentEnvelope;
    renderWithProviders(
      <JudgmentTable
        judgments={[
          {
            ...base,
            tool: 'classify',
            purpose: 'classify:site_identity:batch0',
            judgment_seq: 931,
          },
        ]}
        caption="log"
      />,
    );
    expect(screen.getByText('classify:site_identity:batch0')).toBeInTheDocument();
  });
});
