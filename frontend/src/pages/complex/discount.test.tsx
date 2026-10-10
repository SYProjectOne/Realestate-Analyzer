/**
 * D11-6(계약 .8): 공고에 명시된 할인 — `PriceRange.discount`(기준 타입)를 헤더·가격 표에 FactCell 로,
 * 현재 공고 `payment_terms.discount_by_type`(타입별)을 가격 표 열로. 차감 문구는 서버 `discount_applied`(계약 .10 초안,
 * 5차 minor)로만: true → '구매가에서 뺐음', false → '표시만(빼지 않음)' — 확인됨이어도 0·음수·최고가 이상이면 서버가
 * 빼지 않는다. 필드가 없으면 계약 기본값 false(6차 minor 20) = '표시만'. 할인이 없으면(null·{}) 줄·열이 없다.
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
import { discountApplied, discountNote, discountShortNote } from './tabs';

vi.mock('@/charts/EChartRuntime', () => ({ default: () => null }));
beforeEach(() => resetMockState());

async function exampleDetail(): Promise<ComplexDetail> {
  const res = await getResponse(
    generatedHandlers as RequestHandler[],
    new Request('http://localhost/api/complexes/2'),
  );
  return (await res?.json()) as ComplexDetail;
}

const discount = (label: Fact['label'], v = 10_000_000): Fact => ({
  v,
  label,
  reason: label === '확인됨' ? null : '공고문 문구 해석',
  prov: 'fp_9001',
  checked_at: '2026-10-08',
  unit: 'won',
});

function serve(patch: (d: ComplexDetail) => ComplexDetail) {
  server.use(
    http.get(mswPath('/complexes/:id'), async () =>
      HttpResponse.json(patch(await exampleDetail())),
    ),
  );
}

describe('D11-6 할인 표시', () => {
  it('discountNote: 서버 discount_applied 로만 — 라벨로 추측하지 않는다', () => {
    expect(discountNote({ discount: discount('확인됨'), discount_applied: true })).toBe(
      t('page.G3.price.discountApplied'),
    );
    // 확인됨이어도 서버가 빼지 않았으면(0·음수·최고가 이상) '뺐음'이라 하지 않는다
    expect(discountNote({ discount: discount('확인됨', 0), discount_applied: false })).toBe(
      t('page.G3.price.discountNotApplied'),
    );
    expect(
      discountNote({ discount: discount('확인됨', 900_000_000), discount_applied: false }),
    ).toBe(t('page.G3.price.discountNotApplied'));
    expect(discountNote({ discount: discount('추정'), discount_applied: false })).toBe(
      t('page.G3.price.discountNotApplied'),
    );
    // 필드 없음 = 계약 기본값 false(6차 minor 20) → '표시만(빼지 않음)'. 모름(null)으로 문구를 숨기지 않는다
    expect(discountNote({ discount: discount('확인됨') })).toBe(
      t('page.G3.price.discountNotApplied'),
    );
    expect(discountShortNote({ discount: discount('확인됨') })).toBe(
      t('page.G3.price.discountNotAppliedShort'),
    );
    expect(discountApplied({ discount: discount('확인됨') })).toBe(false);
    expect(discountNote(null)).toBeNull();
    expect(
      discountNote({ discount: { ...discount('확인됨'), v: null }, discount_applied: true }),
    ).toBeNull();
  });

  it('확인됨 할인: 헤더·가격 표에 FactCell(1,000만 + 라벨 + 출처), 타입별 할인 열', async () => {
    serve((d) => {
      const basis = d.price.basis_type_code ?? d.types[0]?.type_code ?? '84A';
      return {
        ...d,
        price: { ...d.price, discount: discount('확인됨'), discount_applied: true },
        payment: d.payment.map((p) =>
          p.is_current ? { ...p, discount_by_type: { [basis]: discount('확인됨') } } : p,
        ),
      };
    });
    renderRoute('/complexes/2#price');
    const header = await screen.findByTestId('header-discount');
    expect(header).toHaveTextContent('1,000만');
    expect(header.querySelector('[data-prov="fp_9001"]')).not.toBeNull();
    expect(header).toHaveAttribute('title', t('page.G3.price.discountApplied'));
    // 툴팁만이 아니라 화면에 보이는 문구(모바일 — 4차 minor)
    expect(within(header).getByTestId('header-discount-note')).toHaveTextContent(
      t('page.G3.price.discountAppliedShort'),
    );

    const row = await screen.findByTestId('price-discount');
    expect(row).toHaveTextContent('1,000만');
    expect(row).toHaveTextContent(t('page.G3.price.discountApplied'));
    expect(screen.getByRole('columnheader', { name: t('page.G3.price.discount') })).toBeVisible();
    const detail = await exampleDetail();
    const basis = detail.price.basis_type_code ?? detail.types[0]!.type_code;
    expect(screen.getByTestId(`type-discount-${basis}`)).toHaveTextContent('1,000만');
  });

  it('확인됨이 아닌 할인: 표시만(빼지 않음) 문구 + 라벨 배지', async () => {
    serve((d) => ({
      ...d,
      price: { ...d.price, discount: discount('추정'), discount_applied: false },
    }));
    renderRoute('/complexes/2#price');
    const row = await screen.findByTestId('price-discount');
    expect(row).toHaveTextContent(t('page.G3.price.discountNotApplied'));
    expect(await screen.findByTestId('header-discount-note')).toHaveTextContent(
      t('page.G3.price.discountNotAppliedShort'),
    );
    expect(within(row).getAllByText(/추정/).length).toBeGreaterThan(0);
  });

  it('확인됨이지만 서버가 빼지 않은 할인(최고가 이상): 헤더·가격 표 모두 표시만', async () => {
    serve((d) => ({
      ...d,
      price: {
        ...d.price,
        discount: discount('확인됨', 900_000_000),
        discount_applied: false,
      },
    }));
    renderRoute('/complexes/2#price');
    const row = await screen.findByTestId('price-discount');
    expect(row).toHaveTextContent(t('page.G3.price.discountNotApplied'));
    expect(row).not.toHaveTextContent(t('page.G3.price.discountApplied'));
    const header = await screen.findByTestId('header-discount');
    expect(header).toHaveAttribute('title', t('page.G3.price.discountNotApplied'));
    expect(within(header).getByTestId('header-discount-note')).toHaveTextContent(
      t('page.G3.price.discountNotAppliedShort'),
    );
  });

  it('discount_applied 가 응답에 없으면 계약 기본값 false — 헤더·가격 표 모두 표시만 (6차 minor 20)', async () => {
    serve((d) => {
      const { discount_applied: _omit, ...price } = d.price;
      return { ...d, price: { ...price, discount: discount('확인됨') } };
    });
    renderRoute('/complexes/2#price');
    const row = await screen.findByTestId('price-discount');
    expect(row).toHaveTextContent(t('page.G3.price.discountNotApplied'));
    const header = await screen.findByTestId('header-discount');
    expect(header).toHaveAttribute('title', t('page.G3.price.discountNotApplied'));
    expect(within(header).getByTestId('header-discount-note')).toHaveTextContent(
      t('page.G3.price.discountNotAppliedShort'),
    );
  });

  it('할인 없음(null·{}): 헤더·가격 표에 할인 줄·열이 없다', async () => {
    serve((d) => ({
      ...d,
      price: { ...d.price, discount: null },
      payment: d.payment.map((p) => ({ ...p, discount_by_type: {} })),
    }));
    renderRoute('/complexes/2#price');
    await screen.findByRole('tablist', { name: t('page.G3.tabs') });
    expect(screen.queryByTestId('header-discount')).toBeNull();
    expect(screen.queryByTestId('price-discount')).toBeNull();
    expect(screen.queryByRole('columnheader', { name: t('page.G3.price.discount') })).toBeNull();
  });
});
