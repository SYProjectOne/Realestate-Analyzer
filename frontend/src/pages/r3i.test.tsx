/**
 * R3i FE8 1단계 — 9차 리뷰(`docs/design/wp/R3_REVIEW9.md`) minor 2·3 의 FE 부분(계약 .13 그대로).
 *  - m3(D17-4): 사람 확인 `discount` 는 **기준 타입**에만 들어간다. 그래서 G3 가격 표에서 '추정' 할인 안내·G7 링크는
 *    기준 타입 줄에만 단다. 기준 타입이 아닌 타입 줄의 '추정' 할인은 "사람 확인 시 구매가에 반영"이 아니라 사실대로
 *    "기준 타입이 아니라 구매가에 반영하지 않음" 안내만(링크 없음).
 *  - m2: MSW 목의 할인 값 검사가 서버(`demotion.py`)와 어긋났다(목은 '1,0'·할인 ≥ 가격 등 판정이 서버와 다름). 서버가
 *    계약 .14 에서 검사를 엄격하게 바꾸므로 1단계에서 목은 **검사하지 않는다**(서버 성공 응답만 흉내). 422 화면 경로는
 *    테스트가 서버 응답 모양을 `server.use` 로 직접 준다. 2단계에서 .14 오류 code 에 맞춘다.
 */
import { screen, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexDetail, Fact, HumanCheck } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
import { handlers } from '@/mocks/handlers';
import { resetMockState } from '@/mocks/handlers.extra';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderRoute } from '@/test/render';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleDetail(): Promise<ComplexDetail> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/complexes/2'),
  );
  return (await res?.json()) as ComplexDetail;
}

const won = (label: Fact['label'], v = 10_000_000): Fact => ({
  v,
  label,
  reason: label === '추정' ? '공고문 자동 추출 — 조건 확인 필요' : '사람 확인(phone)',
  prov: 'fp_9101',
  checked_at: '2026-10-08',
  unit: 'won',
});

/** 현재 공고의 타입별 할인을 바꾸고 기준 타입 할인(price.discount)을 따로 준다 */
function serve(byType: Record<string, Fact>, basisDiscount: Fact | null) {
  server.use(
    http.get(mswPath('/complexes/:id'), async () => {
      const d = await exampleDetail();
      return HttpResponse.json({
        ...d,
        price: { ...d.price, discount: basisDiscount, discount_applied: false },
        payment: d.payment.map((p) => (p.is_current ? { ...p, discount_by_type: byType } : p)),
      } satisfies ComplexDetail);
    }),
  );
}

async function typeCodes() {
  const d = await exampleDetail();
  const basis = d.types.find((r) => r.is_basis)?.type_code;
  const other = d.types.find((r) => !r.is_basis)?.type_code;
  if (!basis || !other) throw new Error('예시 상세에 기준 타입·다른 타입이 둘 다 있어야 한다');
  return { basis, other };
}

// ─── m3 기준 타입 줄만 사람 확인 링크 ─────────────────────────

describe('m3(D17-4) 추정 할인 안내 — 기준 타입 줄만 사람 확인 링크', () => {
  it('기준 타입이 아닌 타입만 추정 할인: "사람 확인 시 반영" 안내·G7 링크 없음, 사실대로 "반영하지 않음" 안내', async () => {
    const { other } = await typeCodes();
    serve({ [other]: won('추정') }, null);
    renderRoute('/complexes/2#price');
    const cell = await screen.findByTestId(`type-discount-${other}`);
    expect(within(cell).getByTestId(`type-discount-note-${other}`)).toHaveTextContent(
      t('page.G3.price.discountEstimatedNonBasis'),
    );
    expect(within(cell).queryByRole('link')).toBeNull();
    expect(screen.queryByText(t('page.G3.price.discountEstimated'))).toBeNull();
    expect(screen.queryByRole('link', { name: t('page.G3.price.discountHumanCheck') })).toBeNull();
  });

  it('기준 타입·다른 타입 모두 추정: 기준 타입 줄에만 안내 + 링크, 다른 타입 줄은 링크 없는 사실 안내', async () => {
    const { basis, other } = await typeCodes();
    serve({ [basis]: won('추정'), [other]: won('추정', 5_000_000) }, won('추정'));
    renderRoute('/complexes/2#price');
    const basisCell = await screen.findByTestId(`type-discount-${basis}`);
    const basisNote = within(basisCell).getByTestId(`type-discount-note-${basis}`);
    expect(basisNote).toHaveTextContent(t('page.G3.price.discountEstimated'));
    expect(
      within(basisNote).getByRole('link', { name: t('page.G3.price.discountHumanCheck') }),
    ).toBeInTheDocument();
    const otherCell = screen.getByTestId(`type-discount-${other}`);
    expect(within(otherCell).getByTestId(`type-discount-note-${other}`)).toHaveTextContent(
      t('page.G3.price.discountEstimatedNonBasis'),
    );
    expect(within(otherCell).queryByRole('link')).toBeNull();
    // 사람 확인 링크는 기준 타입 할인 자리(헤더·할인 줄·기준 타입 줄)에만 — 표 아래 공통 한 줄 없음
    const links = screen.getAllByRole('link', { name: t('page.G3.price.discountHumanCheck') });
    const allowed = [
      screen.getByTestId('header-discount'),
      screen.getByTestId('price-discount'),
      basisCell,
    ];
    expect(links).toHaveLength(3);
    for (const link of links) expect(allowed.some((box) => box.contains(link))).toBe(true);
  });

  it("기준 타입이 아닌 타입의 '확인됨' 할인: 안내 없음(값만)", async () => {
    const { other } = await typeCodes();
    serve({ [other]: won('확인됨') }, null);
    renderRoute('/complexes/2#price');
    const cell = await screen.findByTestId(`type-discount-${other}`);
    expect(within(cell).queryByTestId(`type-discount-note-${other}`)).toBeNull();
  });

  it('안내 문구는 ko.json 에 있고 기준 타입이 아닌 줄 문구는 "사람 확인 시 구매가에 반영"을 말하지 않는다', () => {
    const nonBasis = t('page.G3.price.discountEstimatedNonBasis');
    expect(nonBasis).not.toBe('page.G3.price.discountEstimatedNonBasis');
    expect(nonBasis).not.toMatch(/사람 확인 시 구매가에 반영/);
    expect(nonBasis).toMatch(/기준 타입/);
  });
});

// ─── m2 목 할인 값 검사 안 함 ─────────────────────────────────

describe('m2 MSW 목은 할인 값을 검사하지 않는다(판정은 서버 — 1단계)', () => {
  async function post(valueText: string): Promise<Response | undefined> {
    return getResponse(
      handlers as RequestHandler[],
      new Request('http://localhost/api/ops/human-checks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          complex_id: 2,
          field: 'discount',
          value_text: valueText,
          kind: 'phone',
          entered_by: '운영자',
          checked_at: '2026-10-08T10:00:00+09:00',
        }),
      }),
    );
  }

  // 서버 규칙과 판정이 어긋났던 값들(9차 리뷰 m2) — 목은 어느 쪽으로도 판정하지 않는다
  it.each(['삼백만', '1,0', ',,5,,', '-0', '٣٠٠٠', '９９', '999999999999', '3,000,000원'])(
    '값 %s → 201(서버 성공 응답 모양, field=discount)',
    async (valueText) => {
      const res = await post(valueText);
      expect(res?.status).toBe(201);
      const body = (await res!.json()) as HumanCheck;
      expect(body.field).toBe('discount');
      expect(body.value_text).toBe(valueText);
    },
  );
});
