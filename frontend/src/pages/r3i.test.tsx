/**
 * R3i FE8 1단계 — 9차 리뷰(`docs/design/wp/R3_REVIEW9.md`) minor 2·3 의 FE 부분(계약 .13 그대로).
 *  - m3(D17-4): 사람 확인 `discount` 는 **기준 타입**에만 들어간다. 그래서 G3 가격 표에서 '추정' 할인 안내·G7 링크는
 *    기준 타입 줄에만 단다. 기준 타입이 아닌 타입 줄의 '추정' 할인은 "사람 확인 시 구매가에 반영"이 아니라 사실대로
 *    "기준 타입이 아니라 구매가에 반영하지 않음" 안내만(링크 없음).
 *  - m2: 1단계(목 검사 안 함) 테스트는 2단계(계약 .14 F3 — 목·폼이 서버와 같은 엄격한 규칙·오류 code)에서
 *    `r3i2.test.tsx` 로 옮겼다.
 */
import { screen, within } from '@testing-library/react';
import { getResponse, http, HttpResponse, type RequestHandler } from 'msw';
import type { ComplexDetail, Fact } from '@/api/types';
import { t } from '@/i18n';
import { generatedHandlers } from '@/mocks/handlers.gen';
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

/** 예시 상세(단지 2) price.basis_type_code */
const basisOf = '84A';

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
      t('page.G3.price.discountEstimatedNonBasis', { type: basisOf }),
    );
    expect(within(cell).queryByRole('link')).toBeNull();
    expect(
      screen.queryByText(t('page.G3.price.discountEstimatedBasis', { type: basisOf })),
    ).toBeNull();
    expect(screen.queryByRole('link', { name: t('page.G3.price.discountHumanCheck') })).toBeNull();
  });

  it('기준 타입·다른 타입 모두 추정: 기준 타입 줄에만 안내 + 링크, 다른 타입 줄은 링크 없는 사실 안내', async () => {
    const { basis, other } = await typeCodes();
    serve({ [basis]: won('추정'), [other]: won('추정', 5_000_000) }, won('추정'));
    renderRoute('/complexes/2#price');
    const basisCell = await screen.findByTestId(`type-discount-${basis}`);
    const basisNote = within(basisCell).getByTestId(`type-discount-note-${basis}`);
    expect(basisNote).toHaveTextContent(
      t('page.G3.price.discountEstimatedBasis', { type: basisOf }),
    );
    expect(
      within(basisNote).getByRole('link', { name: t('page.G3.price.discountHumanCheck') }),
    ).toBeInTheDocument();
    const otherCell = screen.getByTestId(`type-discount-${other}`);
    expect(within(otherCell).getByTestId(`type-discount-note-${other}`)).toHaveTextContent(
      t('page.G3.price.discountEstimatedNonBasis', { type: basisOf }),
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

  it("기준 타입이 아닌 타입의 '확인됨' 할인(.14 F2 — 기준 타입이 바뀐 옛 사람 확인 등): '표시만(기준 타입 아님)', 링크 없음", async () => {
    const { other } = await typeCodes();
    serve({ [other]: won('확인됨') }, null);
    renderRoute('/complexes/2#price');
    const cell = await screen.findByTestId(`type-discount-${other}`);
    expect(within(cell).getByTestId(`type-discount-note-${other}`)).toHaveTextContent(
      t('page.G3.price.discountNonBasis', { type: basisOf }),
    );
    expect(within(cell).queryByRole('link')).toBeNull();
  });

  it('안내 문구는 ko.json 에 있고 기준 타입이 아닌 줄 문구는 "사람 확인 시 구매가에 반영"을 말하지 않는다', () => {
    const nonBasis = t('page.G3.price.discountEstimatedNonBasis', { type: basisOf });
    expect(nonBasis).not.toBe('page.G3.price.discountEstimatedNonBasis');
    expect(nonBasis).toContain(basisOf);
    expect(nonBasis).not.toMatch(/사람 확인 시 구매가에 반영/);
    expect(nonBasis).toMatch(/기준 타입/);
  });
});
