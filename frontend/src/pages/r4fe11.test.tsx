/**
 * R4 FE11 — 계약 2026-10-09.17 FE 차이 표(`contracts/CHANGELOG.md` .17 F1–F6) 화면 맞춤.
 *  - F1(D22-5): `ComplexRow.judge_scope_reason`·`Complex.judge_scope_reason`(선택 — 없으면 null) = 서버 `analysis.scope` 사유
 *    그대로 → G2 목록 행·G3 상세 머리·G7 범위 경계 목록. FE10 이 서버 규칙(`has_dong_name` 정규식·첫 행 규칙)을 옮겨 만든
 *    `pages/complex/boundary.ts` 는 지운다(규칙 3 — 판단 복제 금지). 키 없음(.16 이전 저장본)이면 사유를 만들지 않는다.
 *    `rejudge_needed` 면 그 사유는 현재 사실(재판정 뒤) 범위의 것이라고 밝힌다
 *  - F2(D22-5): 발행 리비전 이름 출처 서랍 200 — 실 API e2e(writes12-r4fe10 `test.fail` 표식 제거)
 *  - F3(D22-5): 보류 가격 사유 '출처 상충 — compare 대기'가 서버 가격 Fact 사유로 온다 → 셀이 이미 말하므로 FE10 보충 안내의
 *    긴 설명을 되풀이하지 않는다(보류 출처 Fact·사람 확인 링크만). .16 저장본('분양가 미공개' + 보류 출처)은 FE10 안내 그대로
 *  - F4(D22-4): 접수 '확인 불가(공식 홈페이지 동일성 미확인)' ≠ '다른 단지' — 원문 버튼·안내를 따로
 *  - F5·F6(D22-4·D22-3): G1 첫 적재 요약 한 줄·'법정동' 변경 행 — 서버 문자열 그대로(회귀 방지)
 */
import { screen, waitFor, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type {
  ChangeEvent,
  ComplexDetail,
  ComplexRow,
  ComplexRowPage,
  Dashboard,
  Fact,
  Intake,
} from '@/api/types';
import { t } from '@/i18n';
import { handlers } from '@/mocks/handlers';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';
import { matching, recordRequests } from './_shared/testing';
import { COLUMN_STORAGE_KEY } from './complexes/ComplexTable';

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

function unknownFact(reason: string, prov: string | null = null, unit = 'won'): Fact {
  return { v: null, label: '확인 불가', reason, prov, checked_at: '2026-10-07', unit } as Fact;
}

/** 판정 범위 사유 키를 뺀다(.16 이전 발행 저장본 = 키 없음) */
function withoutScopeReason<T extends { judge_scope_reason?: unknown }>(x: T): T {
  const { judge_scope_reason: _r, ...rest } = x;
  return rest as T;
}

const NO_DONG = '범위 경계(주소에 동 없음)';
const UNMATCHED = '범위 경계(주소가 지역 법정동에 매칭 안 됨)';
const CONFLICT_HOLD = '출처 상충 — compare 대기';

/** 상세 머리를 바꿔 낸다(점수 rejudge_needed 도) */
async function useHeader(
  patch: Partial<ComplexDetail['header']>,
  opts: { strip?: boolean; rejudge?: boolean } = {},
): Promise<ComplexDetail> {
  const detail = await example<ComplexDetail>('/complexes/2');
  const base = opts.strip ? withoutScopeReason(detail.header) : detail.header;
  const next: ComplexDetail = {
    ...detail,
    header: { ...base, ...patch },
    score:
      detail.score && opts.rejudge !== undefined
        ? { ...detail.score, rejudge_needed: opts.rejudge }
        : detail.score,
  };
  server.use(http.get(mswPath('/complexes/:id'), () => HttpResponse.json(next)));
  return next;
}

/** 목록 행을 바꿔 낸다(서버처럼 filter[inclusion_class] 로 거른다) */
async function useRows(map: (row: ComplexRow, i: number) => ComplexRow): Promise<ComplexRow[]> {
  const page = await example<ComplexRowPage>('/snapshots/12/complexes');
  const rows = page.items.map(map);
  server.use(
    http.get(mswPath('/snapshots/:sid/complexes'), ({ request }) => {
      const want = new URL(request.url).searchParams.get('filter[inclusion_class]');
      const items = want ? rows.filter((r) => r.inclusion_class === want) : rows;
      return HttpResponse.json({ ...page, items, total: items.length });
    }),
  );
  return rows;
}

// ─── F1 판정 범위 사유(서버 문자열) ─────────────────────────

describe('F1(D22-5) judge_scope_reason — 서버 analysis.scope 사유 그대로', () => {
  it('FE10 규칙 복제(pages/complex/boundary.ts·has_dong_name 정규식)가 소스에 없다(규칙 3)', () => {
    const boundaryModule = import.meta.glob('./complex/boundary.ts');
    expect(Object.keys(boundaryModule)).toEqual([]);
    const sources = import.meta.glob<string>(['/src/**/*.{ts,tsx}', '!/src/**/*.test.{ts,tsx}'], {
      query: '?raw',
      import: 'default',
      eager: true,
    });
    const offenders = Object.entries(sources)
      .filter(([, text]) => /hasDongName|has_dong_name|동\|읍\|면\|리/.test(text))
      .map(([file]) => file);
    expect(offenders).toEqual([]);
  });

  it('목: 계약 예시 사유를 같은 id 목록 행·상세 머리에(목록 4 · 상세 2), 예시 없는 행은 키 없음', async () => {
    const page = await mock<ComplexRowPage>('/snapshots/12/complexes?page=1&size=100');
    const row = page.items.find((r) => r.complex_id === 4)!;
    expect(row.judge_scope_reason).toBe('포함 확정 · 접수 가능');
    const plain = page.items.find((r) => ![2, 4].includes(r.complex_id))!;
    expect('judge_scope_reason' in plain).toBe(false);
    const detail = await mock<ComplexDetail>('/complexes/2');
    expect(detail.header.judge_scope_reason).toBe('포함 확정 · 접수 가능');
  });

  it('G3 머리: 서버 사유를 그대로(주소에 동이 없어도 서버가 매칭 안 됨이라 하면 그 문구 — 화면이 다시 계산하지 않는다)', async () => {
    const detail = await useHeader({
      inclusion_class: '범위 경계',
      address: '인천광역시 서구 검단신도시 RC3BL',
      legal_dong_code: null,
      judge_scope_reason: UNMATCHED,
    });
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).getByTestId('scope-reason')).toHaveTextContent(UNMATCHED);
    expect(within(head).queryByText(NO_DONG)).toBeNull();
    expect(within(head).getByText(t('page.G3.header.scopeReason'))).toBeInTheDocument();
  });

  it("G3 머리: 범위 경계가 아닌 사유도 보인다('포함/제외 classify 미해결(review, 미분류)')", async () => {
    const reason = '포함/제외 classify 미해결(review, 미분류)';
    const detail = await useHeader({ inclusion_class: '미분류', judge_scope_reason: reason });
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).getByTestId('scope-reason')).toHaveTextContent(reason);
  });

  it('G3 머리: 키 없음(.16 이전 발행 저장본) → 사유 칸 없음, 포함 분류는 맨 분류 문구(화면이 사유를 만들지 않는다)', async () => {
    const detail = await useHeader(
      {
        inclusion_class: '범위 경계',
        address: '인천광역시 서구 검단신도시 RC3BL',
        legal_dong_code: null,
      },
      { strip: true },
    );
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).queryByTestId('scope-reason')).toBeNull();
    expect(within(head).queryByTestId('boundary-reason')).toBeNull();
    expect(within(head).queryByText(NO_DONG)).toBeNull();
    expect(within(head).getByText(t('page.common.inclusion.범위 경계'))).toBeInTheDocument();
  });

  it('G3 머리: rejudge_needed 면 사유가 현재 사실(재판정 뒤) 범위의 것임을 밝힌다', async () => {
    const detail = await useHeader(
      { judge_scope_reason: '분양가 미공개(공고 전)' },
      { rejudge: true },
    );
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const reason = within(head).getByTestId('scope-reason');
    expect(reason).toHaveTextContent('분양가 미공개(공고 전)');
    expect(reason).toHaveTextContent(t('page.common.scopeReasonCurrent'));
  });

  it('G3 머리: rejudge_needed 가 아니면 그 안내 없음', async () => {
    const detail = await useHeader(
      { judge_scope_reason: '포함 확정 · 접수 가능' },
      { rejudge: false },
    );
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const reason = within(head).getByTestId('scope-reason');
    expect(reason).toHaveTextContent('포함 확정 · 접수 가능');
    expect(reason).not.toHaveTextContent(t('page.common.scopeReasonCurrent'));
  });

  it('G2 목록 행: 포함 분류 열에 서버 사유(행마다), 키 없는 행은 없음', async () => {
    // R9-UI P4(D28-4 G2 8열): 단지 분류 열은 기본 숨김 — 열 선택으로 켠 상태
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify({ v: 2, inclusion: true }));
    const rows = await useRows((row, i) =>
      i === 0
        ? { ...row, inclusion_class: '범위 경계', judge_scope_reason: NO_DONG }
        : withoutScopeReason(row),
    );
    renderRoute('/complexes');
    const first = rows[0]!;
    const link = await screen.findByRole('link', { name: first.name });
    const tr = link.closest('tr') as HTMLElement;
    expect(within(tr).getByTestId(`scope-reason-${first.complex_id}`)).toHaveTextContent(NO_DONG);
    const second = rows[1]!;
    const tr2 = (await screen.findByRole('link', { name: second.name })).closest(
      'tr',
    ) as HTMLElement;
    expect(within(tr2).queryByTestId(`scope-reason-${second.complex_id}`)).toBeNull();
  });

  it('G2 목록 행: rejudge_needed 행의 사유에는 현재 사실 기준 안내(title)', async () => {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify({ v: 2, inclusion: true }));
    const rows = await useRows((row, i) =>
      i === 0 ? { ...row, judge_scope_reason: '원 공고 미수집', rejudge_needed: true } : row,
    );
    renderRoute('/complexes');
    const first = rows[0]!;
    const tr = (await screen.findByRole('link', { name: first.name })).closest('tr') as HTMLElement;
    const cell = within(tr).getByTestId(`scope-reason-${first.complex_id}`);
    expect(cell).toHaveTextContent('원 공고 미수집');
    expect(cell).toHaveAttribute(
      'title',
      expect.stringContaining(t('page.common.scopeReasonCurrent')),
    );
  });

  it('G7 범위 경계 목록: 단지마다 서버 사유(주소에 동 없음 / 매칭 안 됨), 키 없으면 이름만', async () => {
    await useRows((row, i) => {
      if (i === 0) return { ...row, inclusion_class: '범위 경계', judge_scope_reason: NO_DONG };
      if (i === 1) return { ...row, inclusion_class: '범위 경계', judge_scope_reason: UNMATCHED };
      if (i === 2) return withoutScopeReason({ ...row, inclusion_class: '범위 경계' as const });
      return row;
    });
    const rec = recordRequests();
    renderRoute('/ops');
    const section = await screen.findByRole('region', { name: t('page.G7.boundary.title') });
    const list = await within(section).findByRole('list', { name: t('page.G7.boundary.title') });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(within(items[0]!).getByTestId('boundary-scope-reason')).toHaveTextContent(NO_DONG);
    expect(within(items[1]!).getByTestId('boundary-scope-reason')).toHaveTextContent(UNMATCHED);
    expect(within(items[2]!).queryByTestId('boundary-scope-reason')).toBeNull();
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', /\/snapshots\/\d+\/complexes$/).length).toBeGreaterThan(
        0,
      ),
    );
    rec.stop();
  });
});

// ─── F3 보류 가격 사유 '출처 상충 — compare 대기' ─────────────

describe("F3(D22-5) 현재 구매가 사유 '출처 상충 — compare 대기' — 보충 안내 중복 정리", () => {
  async function useHeld(priceReason: string, heldFact: boolean): Promise<ComplexDetail> {
    const detail = await example<ComplexDetail>('/complexes/2');
    const basis = detail.price.basis_type_code!;
    const held = unknownFact(`${CONFLICT_HOLD}; 단위 표기 없음 — 원으로 봄`, 'fp_7001');
    const types = detail.types.map((row) =>
      heldFact && row.type_code === basis ? { ...row, max_price_won: held } : row,
    );
    const next: ComplexDetail = {
      ...detail,
      price: {
        ...detail.price,
        price_low: unknownFact(priceReason),
        price_high: unknownFact(priceReason),
        price_mid: unknownFact(priceReason),
        discount: null,
      },
      types,
    };
    server.use(http.get(mswPath('/complexes/:id'), () => HttpResponse.json(next)));
    return next;
  }

  it('.17: 가격 셀이 사유를 말하므로 안내는 긴 설명 없이 기준 타입 + 보류 출처 Fact(→ 서랍) + 사람 확인 링크', async () => {
    const detail = await useHeld(CONFLICT_HOLD, true);
    const basis = detail.price.basis_type_code!;
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    // 현재 구매가 하단·상단 + (R11) 주변 거래 비교의 '이 단지 가운데값'(price_mid)도 같은 사유
    expect(
      within(head).getAllByText(
        t('empty.unknownWithReasonDate', { reason: CONFLICT_HOLD, date: '2026-10-07' }),
      ).length,
    ).toBe(3);
    const note = within(head).getByTestId('held-price-note');
    expect(note).not.toHaveTextContent(t('page.G3.price.held', { type: basis }));
    expect(note).toHaveTextContent(t('page.G3.price.heldBasis', { type: basis }));
    expect(note.querySelector('[data-prov="fp_7001"]')).not.toBeNull();
    const link = within(note).getByRole('link', { name: t('page.G3.price.heldHumanCheck') });
    const href = new URL(link.getAttribute('href')!, 'http://localhost');
    expect(href.searchParams.get('hc_field')).toBe('max_price_won');
  });

  it('.17: 서버 사유가 보류인데 보류 출처 Fact 를 상세에서 못 찾아도 사람 확인 링크는 보인다(사유는 서버가 정한다)', async () => {
    const detail = await useHeld(CONFLICT_HOLD, false);
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    const note = within(head).getByTestId('held-price-note');
    expect(
      within(note).getByRole('link', { name: t('page.G3.price.heldHumanCheck') }),
    ).toBeInTheDocument();
    expect(note.querySelector('[data-prov]')).toBeNull();
  });

  it('.17 가격표 탭도 같은 짧은 안내', async () => {
    const detail = await useHeld(CONFLICT_HOLD, true);
    renderRoute('/complexes/2#price');
    const panel = await screen.findByRole('tabpanel');
    const note = within(panel).getByTestId('held-price-note-tab');
    expect(note).not.toHaveTextContent(
      t('page.G3.price.held', { type: detail.price.basis_type_code! }),
    );
  });

  it(".16 저장본(가격 사유 '분양가 미공개' + 보류 출처) → FE10 안내 그대로(긴 설명)", async () => {
    const detail = await useHeld('분양가 미공개', true);
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).getByTestId('held-price-note')).toHaveTextContent(
      t('page.G3.price.held', { type: detail.price.basis_type_code! }),
    );
  });

  it("G2 목록 행 가격 셀 '확인 불가(출처 상충 — compare 대기)'(서버 Fact 그대로)", async () => {
    const rows = await useRows((row, i) =>
      i === 0
        ? {
            ...row,
            price_low: unknownFact(CONFLICT_HOLD),
            price_high: unknownFact(CONFLICT_HOLD),
            price_mid: unknownFact(CONFLICT_HOLD),
          }
        : row,
    );
    renderRoute('/complexes');
    const tr = (await screen.findByRole('link', { name: rows[0]!.name })).closest(
      'tr',
    ) as HTMLElement;
    expect(
      within(tr).getAllByText(
        t('empty.unknownWithReasonDate', { reason: CONFLICT_HOLD, date: '2026-10-07' }),
      ).length,
    ).toBe(2);
  });
});

// ─── F4 공식 홈페이지 동일성 미확인 ≠ 다른 단지 ─────────────

describe("F4(D22-4) 접수 '확인 불가(공식 홈페이지 동일성 미확인)' — '다른 단지'와 구분", () => {
  async function useIntake(reason: string): Promise<ComplexDetail> {
    const detail = await example<ComplexDetail>('/complexes/2');
    const intake: Intake = {
      ...detail.intake_current!,
      status: '확인 불가',
      reason,
      raw_document_id: 9202,
    };
    server.use(
      http.get(mswPath('/complexes/:id'), () =>
        HttpResponse.json({ ...detail, intake_current: intake, intake: [intake] }),
      ),
    );
    return detail;
  }

  it("동일성 미확인: 배지 사유 그대로 · 원문 버튼 '동일성 미확인 — 접수 근거 아님' · 안내(다른 단지 아님) · 사람 확인 링크", async () => {
    const detail = await useIntake('공식 홈페이지 동일성 미확인');
    const rec = recordRequests();
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(within(head).getByTestId('intake-badge')).toHaveTextContent(
      t('intake.withReasonDate', {
        status: t('intake.status.확인 불가'),
        reason: '공식 홈페이지 동일성 미확인',
        date: '2026-10-07',
      }),
    );
    expect(
      within(head).queryByRole('button', { name: t('page.G3.header.siteOtherEvidence') }),
    ).toBeNull();
    expect(
      within(head).queryByRole('button', { name: t('page.G3.header.intakeEvidence') }),
    ).toBeNull();
    const raw = within(head).getByRole('button', {
      name: t('page.G3.header.siteUnconfirmedEvidence'),
    });
    expect(within(head).queryByTestId('site-other-note')).toBeNull();
    const note = within(head).getByTestId('site-unconfirmed-note');
    expect(note).toHaveTextContent(t('page.G3.header.siteUnconfirmedHint'));
    const link = within(note).getByRole('link', { name: t('page.G3.header.siteOtherHumanCheck') });
    const href = new URL(link.getAttribute('href')!, 'http://localhost');
    expect(href.searchParams.get('hc_field')).toBe('intake_status');
    expect(href.searchParams.get('hc_complex')).toBe(String(detail.header.id));
    raw.click();
    await waitFor(() =>
      expect(matching(rec.requests, 'GET', '/provenance/rd_9202')).toHaveLength(1),
    );
    rec.stop();
  });

  it('다른 단지(auto other_complex)는 FE10 문구 그대로, 동일성 미확인 안내 없음', async () => {
    const detail = await useIntake('공식 홈페이지가 다른 단지');
    renderRoute('/complexes/2');
    const head = await screen.findByRole('region', { name: detail.header.name });
    expect(
      within(head).getByRole('button', { name: t('page.G3.header.siteOtherEvidence') }),
    ).toBeInTheDocument();
    expect(within(head).getByTestId('site-other-note')).toBeInTheDocument();
    expect(within(head).queryByTestId('site-unconfirmed-note')).toBeNull();
  });
});

// ─── F5·F6 G1 서버 문자열 그대로 ───────────────────────────

describe('F5(D22-4)·F6(D22-3) G1 최근 변경 — 서버 문자열 그대로', () => {
  function ev(partial: Partial<ChangeEvent>): ChangeEvent {
    return {
      id: 1,
      snapshot_id: 12,
      entity: 'region',
      entity_id: 1,
      field: 'first_load',
      old_text: null,
      new_text: null,
      detected_at: '2026-10-08T09:00:00+09:00',
      severity: 'info',
      triggers_rejudge: false,
      complex_id: null,
      complex_name: null,
      tab: null,
      ...partial,
    };
  }

  it('F5 첫 적재 요약은 한 줄 그대로', async () => {
    const summary =
      '첫 적재: 단지 46개, 값 1210건(첫 적재 중 기록·덮어쓰기 — 변경 이벤트 대신 요약)';
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () =>
        HttpResponse.json({ ...dash, changes: [ev({ new_text: summary })] }),
      ),
    );
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    expect(within(feed).getAllByText(summary)).toHaveLength(1);
  });

  it("F6 complex·legal_dong_code(critical) 변경 행 — '법정동' 필드 문구 + 새 값", async () => {
    const dash = await example<Dashboard>('/snapshots/12/dashboard');
    server.use(
      http.get(mswPath('/snapshots/:sid/dashboard'), () =>
        HttpResponse.json({
          ...dash,
          changes: [
            ev({
              entity: 'complex',
              entity_id: 46,
              field: 'legal_dong_code',
              new_text: '2829010400',
              severity: 'critical',
              triggers_rejudge: true,
              complex_id: 46,
              complex_name: '검단 테스트 단지',
              tab: null,
            }),
          ],
        }),
      ),
    );
    renderRoute('/');
    const feed = await screen.findByRole('list', { name: t('page.G1.changes') });
    expect(within(feed).getByText(/법정동/)).toBeInTheDocument();
    expect(within(feed).getByText(/2829010400/)).toBeInTheDocument();
  });
});
