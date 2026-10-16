/** G3 탭 패널: 가격표 · 납부 조건 · 잔여 이력 · 시세 비교 · 호재 */
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import type { ComplexDetail, Fact, HumanCheckField, LadderHorizon, PriceRange } from '@/api/types';
import { C01Ladder, C02Gap, C08Timeline, C09Catalyst } from '@/charts';
import {
  Badge,
  EmptyState,
  ExternalLink,
  FactCell,
  MetaText,
  SectionHeader,
  Term,
} from '@/components';
import { t, type TKey } from '@/i18n';
import { formatHalfYear } from '@/lib/format';
import { enumText, isUnresolved, tdClass, thClass, useGlobalSearch } from '../_shared';
import { HC_PARAM, HUMAN_CHECK_ANCHOR } from '../ops/humanCheckRules';
import { CompetitionSummaryLine } from './CompetitionSummaryLine';

/** 할인 문구에 필요한 가격 범위 필드 */
export type DiscountPrice = Pick<PriceRange, 'discount' | 'discount_applied'>;

/**
 * 서버가 구매가에서 할인을 뺐는가(계약 .10 `PriceRange.discount_applied`, 5차 minor). 화면은 라벨로 추측하지 않는다 —
 * 확인됨이어도 0·음수·최고가 이상 할인은 서버가 빼지 않는다. 필드가 없으면 계약 기본값 `false`(6차 minor 20 — 모름으로
 * 문구를 숨기면 차감 안 된 할인이 차감된 것처럼 읽힌다).
 */
export function discountApplied(price: DiscountPrice | null | undefined): boolean {
  return price?.discount_applied === true;
}

/**
 * 할인 표시 문구(D11-6): 서버가 뺐으면 '구매가에서 이미 뺐다', 안 뺐으면(필드 없음 포함) '표시만 하고 빼지 않았다'.
 * 할인이 없으면(null) null.
 */
export function discountNote(price: DiscountPrice | null | undefined): string | null {
  const discount = price?.discount;
  if (!discount || discount.v === null) return null;
  return discountApplied(price)
    ? t('page.G3.price.discountApplied')
    : t('page.G3.price.discountNotApplied');
}

/** 헤더용 짧은 문구(툴팁 없이 화면에 보인다 — 모바일, 4차 리뷰 minor) */
export function discountShortNote(price: DiscountPrice | null | undefined): string | null {
  const discount = price?.discount;
  if (!discount || discount.v === null) return null;
  return discountApplied(price)
    ? t('page.G3.price.discountAppliedShort')
    : t('page.G3.price.discountNotAppliedShort');
}

/**
 * 공고문 파서가 찾은 할인인가(계약 .13 F2·D16-1): 파서 할인은 언제나 라벨 '추정'(표시만, 차감 없음). '확인됨'(사람 확인)은
 * 서버가 차감한다. 값이 없으면 false.
 */
export function isEstimatedDiscount(fact: Fact | null | undefined): boolean {
  return !!fact && fact.v !== null && fact.label === '추정';
}

/** G7 사람 확인 폼 주소 — 단지·필드 미리 채움, 전역 쿼리(region·snapshot·scenario) 유지 */
export function humanCheckTo(
  globalSearch: string,
  complexId: number,
  field: HumanCheckField,
): { pathname: string; search: string; hash: string } {
  const params = new URLSearchParams(globalSearch);
  params.set(HC_PARAM.complex, String(complexId));
  params.set(HC_PARAM.field, field);
  return { pathname: '/ops', search: `?${params.toString()}`, hash: HUMAN_CHECK_ANCHOR };
}

/** G7 사람 확인 폼 주소 — 필드 `discount`(계약 .13 F2) */
export function discountHumanCheckTo(
  globalSearch: string,
  complexId: number,
): { pathname: string; search: string; hash: string } {
  return humanCheckTo(globalSearch, complexId, 'discount');
}

/**
 * 채택 보류 표식(서버 `normalize.fields.CONFLICT_HOLD`) — 출처 행 reason 머리. 계약 .16 S2(D21-1): 가격은 다른 출처 종류의
 * 1차 출처와 10배 이상 다르면(표 단위 차이) rank 와 무관하게 보류 → compare. 계약 데이터 모양이라 여기 둔다(화면 문구 아님).
 */
const CONFLICT_HOLD = '출처 상충 — compare 대기';

function isHoldReason(reason: string | null | undefined): boolean {
  return (reason ?? '').startsWith(CONFLICT_HOLD);
}

function isHeld(fact: Fact | null | undefined): fact is Fact {
  return !!fact && fact.v === null && isHoldReason(fact.reason);
}

/** 기준 타입 가격 채택 보류 — `serverReason` = 서버 현재 구매가 사유가 이미 보류(계약 .17 F3), `fact` = 보류된 출처 Fact */
export interface HeldBasisPrice {
  type: string;
  fact: Fact | null;
  serverReason: boolean;
}

/**
 * 현재 구매가가 '확인 불가'인데 그 까닭이 기준 타입 최고가의 **채택 보류**인가.
 *  - 계약 .17 F3(D22-5): 서버가 현재 구매가 Fact 사유를 '출처 상충 — compare 대기'로 낸다(가격 셀이 '확인 불가(출처 상충 —
 *    compare 대기)'를 이미 보인다) → `serverReason` true. 보류 출처 Fact 는 찾으면 함께(서랍), 못 찾아도 안내·사람 확인 링크
 *  - 계약 .16 F6(D21-1) 저장본: 사유가 '분양가 미공개'라 화면이 기준 타입의 보류 Fact 를 찾아야 보인다
 * 보류 Fact 찾기: 현재 공고 `price_by_type[기준 타입].max_price_won`(서버 현재 구매가가 먼저 쓰는 값) → 기준 타입 `max_price_won`.
 * 보류가 아니면 null. 판단이 아니라 서버가 붙인 reason 표식 읽기다.
 */
export function heldBasisPrice(detail: ComplexDetail): HeldBasisPrice | null {
  const basis = detail.price.basis_type_code;
  if (!basis || detail.price.price_low.v !== null) return null;
  const serverReason = isHoldReason(detail.price.price_low.reason);
  const current = detail.payment.find((p) => p.is_current) ?? null;
  const notice = current?.price_by_type?.[basis]?.max_price_won;
  const row = detail.types.find((r) => r.type_code === basis)?.max_price_won;
  const fact = isHeld(notice) ? notice : isHeld(row) ? row : null;
  if (!serverReason && !fact) return null;
  return { type: basis, fact, serverReason };
}

/**
 * 채택 보류 안내(G3 머리·가격표): 보류된 출처 Fact(→ 서랍, 상충 출처) + G7 '최고 공급금액' 사람 확인 링크.
 * 서버 가격 사유가 이미 '출처 상충 — compare 대기'면(.17) 긴 설명을 되풀이하지 않고 기준 타입만 밝힌다(FE10 보충 안내 중복 정리).
 * .16 저장본(가격 사유 '분양가 미공개')만 긴 설명을 붙인다.
 */
export function HeldPriceNote({ detail, testId }: { detail: ComplexDetail; testId: string }) {
  const globalSearch = useGlobalSearch();
  const held = heldBasisPrice(detail);
  if (!held) return null;
  return (
    <span className="flex flex-wrap items-center gap-1 text-xs" data-testid={testId}>
      <span>
        {held.serverReason
          ? t('page.G3.price.heldBasis', { type: held.type })
          : t('page.G3.price.held', { type: held.type })}
      </span>
      {held.fact ? (
        <>
          <span className="text-muted">{t('page.G3.price.heldValue')}</span>
          <FactCell fact={held.fact} unit="won" />
        </>
      ) : null}
      <Link
        to={humanCheckTo(globalSearch, detail.header.id, 'max_price_won')}
        className="underline"
      >
        {t('page.G3.price.heldHumanCheck')}
      </Link>
    </span>
  );
}

/**
 * '추정' 할인 안내(D16-1): "공고문에서 찾은 할인(조건 확인 필요) — 사람 확인 시 구매가에 반영" + G7 사람 확인 링크.
 */
export function EstimatedDiscountNote({
  complexId,
  basisType,
  testId = 'discount-estimated',
}: {
  complexId: number;
  /** 계약 .14 F2(D17-4): 사람 확인 할인이 들어갈 기준 타입(price.basis_type_code) — 모르면 null */
  basisType: string | null;
  testId?: string;
}) {
  const globalSearch = useGlobalSearch();
  return (
    <span className="text-xs text-muted" data-testid={testId}>
      {basisType
        ? t('page.G3.price.discountEstimatedBasis', { type: basisType })
        : t('page.G3.price.discountEstimated')}{' '}
      <Link to={discountHumanCheckTo(globalSearch, complexId)} className="underline">
        {t('page.G3.price.discountHumanCheck')}
      </Link>
    </span>
  );
}

/**
 * 가격 표 타입 줄의 할인 안내(9차 리뷰 minor 3·D17-4, 계약 .14 F2). 사람 확인 `discount` 는 **기준 타입**에만 들어가고
 * 구매가에서 빠지는 것도 기준 타입 할인뿐이다:
 *  - 기준 타입 줄 '추정' → "사람 확인 시 구매가에 반영(기준 타입 X)" + G7 링크
 *  - 다른 타입 줄 '추정' → "기준 타입(X)이 아니라 반영하지 않음"(링크 없음)
 *  - 다른 타입 줄 그 밖(확인됨 — 기준 타입이 바뀐 옛 사람 확인·공식 구조화 출처) → "기준 타입(X)이 아니라 빼지 않음(표시만)"
 *  - 기준 타입 줄 확인됨 → 안내 없음(차감 문구는 가격 범위 할인 줄이 서버 discount_applied 로)
 */
function TypeDiscountCell({
  fact,
  typeCode,
  isBasis,
  basisType,
  complexId,
}: {
  fact: Fact | undefined;
  typeCode: string;
  isBasis: boolean;
  basisType: string | null;
  complexId: number;
}) {
  if (!fact) return <span className="text-muted">{t('page.common.none')}</span>;
  const testId = `discount-note-type-${typeCode}`;
  const type = basisType ?? t('page.common.none');
  let note: ReactNode = null;
  if (isEstimatedDiscount(fact)) {
    note = isBasis ? (
      <EstimatedDiscountNote complexId={complexId} basisType={basisType} testId={testId} />
    ) : (
      <span className="block text-xs text-muted" data-testid={testId}>
        {t('page.G3.price.discountEstimatedNonBasis', { type })}
      </span>
    );
  } else if (!isBasis && fact.v !== null) {
    note = (
      <span className="block text-xs text-muted" data-testid={testId}>
        {t('page.G3.price.discountNonBasis', { type })}
      </span>
    );
  }
  return (
    <>
      <FactCell fact={fact} unit="won" />
      {note}
    </>
  );
}

/** 현재 공고(is_current)의 타입별 할인(payment_terms.discount_by_type, 키 = type_code) */
function currentDiscounts(detail: ComplexDetail): Record<string, Fact> {
  const current = detail.payment.find((p) => p.is_current) ?? null;
  return current?.discount_by_type ?? {};
}

/** 필수 옵션 칸의 고지문이 2행 이상 같으면 그 문구(각주로 한 번만 보인다). 아니면 null */
export function sharedOptionsNote(types: ComplexDetail['types']): string | null {
  const texts = types.map((r) => r.options_text).filter((x): x is string => !!x);
  if (texts.length < 2) return null;
  const first = texts[0] ?? null;
  return texts.every((x) => x === first) ? first : null;
}

export function PriceTab({ detail }: { detail: ComplexDetail }) {
  const { price, types } = detail;
  const footnote = sharedOptionsNote(types);
  const discounts = currentDiscounts(detail);
  const hasTypeDiscount = Object.keys(discounts).length > 0;
  const note = discountNote(price);
  const complexId = detail.header.id;
  // 기준 타입 할인(price.discount)이 '추정'이면 그 줄에 안내 + 사람 확인 링크(D16-1)
  const estimatedPrice = isEstimatedDiscount(price.discount);
  return (
    <TabSection id="g3-price-title" title={t('page.G3.price.title')} hint={t('page.G3.price.hint')}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        <dt className="text-muted">{t('page.G3.header.price')}</dt>
        <dd className="flex flex-wrap items-center gap-1">
          <FactCell fact={price.price_low} unit="won" />
          <span aria-hidden>~</span>
          <FactCell fact={price.price_high} unit="won" />
        </dd>
        {heldBasisPrice(detail) ? (
          <dd className="col-span-2">
            <HeldPriceNote detail={detail} testId="held-price-note-tab" />
          </dd>
        ) : null}
        {price.discount ? (
          <>
            <dt className="text-muted">{t('page.G3.price.discount')}</dt>
            <dd className="flex flex-wrap items-center gap-1" data-testid="price-discount">
              <FactCell fact={price.discount} unit="won" />
              {note ? <span className="text-xs text-muted">{note}</span> : null}
              {estimatedPrice ? (
                <EstimatedDiscountNote complexId={complexId} basisType={price.basis_type_code} />
              ) : null}
            </dd>
          </>
        ) : null}
        {price.composition ? (
          <>
            <dt className="text-muted">{t('page.G3.price.composition')}</dt>
            <dd>{price.composition}</dd>
          </>
        ) : null}
        {price.change_vs_first_pct ? (
          <>
            <dt className="text-muted">{t('page.G3.price.change')}</dt>
            <dd>
              <FactCell fact={price.change_vs_first_pct} unit="pct" digits={2} />
            </dd>
          </>
        ) : null}
      </dl>
      {types.length === 0 ? (
        <EmptyState reason={t('page.common.none')} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="pb-1 text-left text-xs text-muted">
              {t('page.G3.price.caption')}
            </caption>
            <thead>
              <tr>
                {(
                  [
                    'type',
                    'area',
                    'units',
                    'max',
                    'floorSample',
                    'floorText',
                    'balcony',
                    'options',
                    ...(hasTypeDiscount ? (['discount'] as const) : []),
                  ] as const
                ).map((k) => (
                  <th key={k} scope="col" className={thClass}>
                    {t(`page.G3.price.${k}` as TKey)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {types.map((row) => (
                <tr key={row.type_code}>
                  <th scope="row" className={`${tdClass} text-left font-medium`}>
                    {row.type_code}{' '}
                    {row.is_basis ? <Badge tone="strong">{t('page.G3.price.basis')}</Badge> : null}
                  </th>
                  <td className={tdClass}>
                    <FactCell fact={row.area_m2} unit="m2" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={row.units} unit="households" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={row.max_price_won} unit="won" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={row.floor_sample_price_won} unit="won" />
                  </td>
                  <td className={tdClass}>{row.floor_sample_text ?? t('page.common.none')}</td>
                  <td className={tdClass}>
                    <FactCell fact={row.balcony_won} unit="won" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={row.options_required_won} unit="won" />
                    {row.options_text && footnote !== null && row.options_text === footnote ? (
                      <sup
                        data-testid="options-ref"
                        className="ml-0.5 text-xs text-muted"
                        title={footnote}
                      >
                        {t('page.G3.price.noteRef')}
                      </sup>
                    ) : row.options_text ? (
                      <span className="block text-xs text-muted">{row.options_text}</span>
                    ) : null}
                  </td>
                  {hasTypeDiscount ? (
                    <td className={tdClass} data-testid={`type-discount-${row.type_code}`}>
                      <TypeDiscountCell
                        fact={discounts[row.type_code]}
                        typeCode={row.type_code}
                        isBasis={row.is_basis}
                        basisType={price.basis_type_code}
                        complexId={complexId}
                      />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
          {footnote !== null ? (
            <p data-testid="options-footnote" className="mt-1 text-xs text-muted">
              <span className="font-medium">{t('page.G3.price.noteTitle')}</span> {footnote}
            </p>
          ) : null}
        </div>
      )}
    </TabSection>
  );
}
/** 탭 안 구역(출처 탭도 쓴다): 질문형 h3 + 안내 + 본문(구역 이름 = 제목 — `getByRole('region', { name })`) */
export function TabSection({
  id,
  title,
  hint,
  actions,
  children,
}: {
  id: string;
  title: string;
  hint?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex min-w-0 flex-col gap-4">
      <SectionHeader id={id} level={3} title={title} hint={hint} actions={actions} />
      {children}
    </section>
  );
}

type Payment = ComplexDetail['payment'][number];

/** 두 공고 나란히 보기 표의 행 — 항목 이름 + 공고마다 칸 */
const PAYMENT_ROWS: readonly {
  key: string;
  label: TKey;
  cell: (term: Payment, asof: string) => ReactNode;
}[] = [
  {
    key: 'effective',
    label: 'page.G3.payment.effective',
    cell: (term, asof) => <FactCell wrap fact={term.effective_from} unit="date" asof={asof} />,
  },
  {
    key: 'down',
    label: 'page.G3.payment.down',
    cell: (term) => <FactCell wrap fact={term.down_payment_pct} unit="pct" digits={0} />,
  },
  {
    key: 'downFirst',
    label: 'page.G3.payment.downFirst',
    cell: (term) => <FactCell wrap fact={term.down_payment_first_won} unit="won" />,
  },
  {
    key: 'interim',
    label: 'page.G3.payment.interim',
    cell: (term) => <FactCell wrap fact={term.interim_pct} unit="pct" digits={0} />,
  },
  {
    key: 'balance',
    label: 'page.G3.payment.balance',
    cell: (term) => <FactCell wrap fact={term.balance_pct} unit="pct" digits={0} />,
  },
  {
    key: 'interimTerms',
    label: 'page.G3.payment.interimTerms',
    cell: (term) =>
      term.interim_terms_text ?? <span className="text-muted">{t('page.common.none')}</span>,
  },
  {
    key: 'changeVsFirst',
    label: 'page.G3.payment.changeVsFirst',
    cell: (term) =>
      term.change_vs_first?.down_payment_pct_delta ? (
        <FactCell wrap fact={term.change_vs_first.down_payment_pct_delta} unit="pct" digits={0} />
      ) : (
        <span className="text-muted">{t('page.common.none')}</span>
      ),
  },
];

/**
 * 탭 2 납부 일정 전체(목업 DetailTabs 탭 2): 공고마다 열 하나로 나란히(현재 적용 열 배지) + 공고마다 중도금 일정 표.
 * 비율만 보인다 — 회차별 금액은 계산하지 않는다.
 */
export function PaymentTab({ detail }: { detail: ComplexDetail }) {
  const { payment, asof_date: asof } = detail;
  return (
    <TabSection
      id="g3-payment-title"
      title={t('page.G3.payment.title')}
      hint={t('page.G3.payment.hint')}
    >
      {payment.length === 0 ? (
        <EmptyState reason={t('page.common.none')} />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm" data-testid="payment-compare">
              <thead>
                <tr>
                  <th scope="col" className={thClass}>
                    {t('page.G3.payment.item')}
                  </th>
                  {payment.map((term) => (
                    <th
                      key={`${term.notice_no}-${term.id ?? ''}`}
                      scope="col"
                      className={`${thClass} ${term.is_current ? 'bg-accent-soft' : ''}`}
                    >
                      <span className="flex flex-wrap items-center gap-1">
                        {term.notice_kind ? <Badge tone="neutral">{term.notice_kind}</Badge> : null}
                        <span>
                          {t('page.G3.payment.notice')} {term.notice_no}
                        </span>
                        {term.is_current ? (
                          <Badge tone="strong">{t('page.G3.payment.current')}</Badge>
                        ) : null}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PAYMENT_ROWS.map((row) => (
                  <tr key={row.key}>
                    <th scope="row" className={`${tdClass} text-left font-normal text-fg-2`}>
                      {t(row.label)}
                    </th>
                    {payment.map((term) => (
                      <td
                        key={`${term.notice_no}-${term.id ?? ''}`}
                        className={`${tdClass} ${term.is_current ? 'bg-accent-soft/40' : ''}`}
                      >
                        {row.cell(term, asof)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {payment
            .filter((term) => term.interim_schedule.length > 0)
            .map((term) => (
              <div key={`${term.notice_no}-${term.id ?? ''}-schedule`} className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <caption className="pb-1 text-left text-[13px] font-medium text-fg-2">
                    {t('page.G3.payment.scheduleOf', { no: term.notice_no })}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className={thClass}>
                        {t('page.G3.payment.schedule')}
                      </th>
                      <th scope="col" className={thClass}>
                        {t('page.G3.payment.dueDate')}
                      </th>
                      <th scope="col" className={thClass}>
                        {t('page.G3.payment.pct')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {term.interim_schedule.map((item) => (
                      <tr key={item.seq}>
                        <th scope="row" className={`${tdClass} text-left font-normal`}>
                          <MetaText kind="seq" k="page.G3.payment.seq" params={{ n: item.seq }} />
                        </th>
                        <td className={tdClass}>
                          <FactCell fact={item.due_date} unit="date" asof={asof} />
                        </td>
                        <td className={tdClass}>
                          <FactCell fact={item.pct} unit="pct" digits={0} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
        </>
      )}
    </TabSection>
  );
}

/** 원문 경쟁률 표기 "(△307)" → 미달 세대 수 문자열(표기 변환 — 계산 아님). 아니면 null */
export function shortfallUnits(text: string | null | undefined): string | null {
  const match = /△\s*([\d,]+)/.exec(text ?? '');
  return match?.[1] ?? null;
}

/** 당첨 가점 3칸(계약 .20 F2) 중 값이 있는가 */
function hasPoints(row: ComplexDetail['competition'][number]): boolean {
  return [row.winning_score_min, row.winning_score_max, row.winning_score_avg].some(
    (f) => !!f && f.v !== null,
  );
}

/** 가점 칸 사유 코드(계약 .21 F4) — 세 칸이 모두 같은 '확인 불가' 사유일 때만(서버가 행 단위로 정한다) */
function pointsReason(row: ComplexDetail['competition'][number]): string | null {
  const facts = [row.winning_score_min, row.winning_score_max, row.winning_score_avg];
  const codes = new Set(facts.map((f) => (f && f.v === null ? (f.reason_code ?? null) : 'value')));
  if (codes.size !== 1) return null;
  const [code] = [...codes];
  return code === 'value' ? null : (code ?? null);
}

/** 표에 가점 열을 보일까 — 값이 있거나, '가점 미수집'이 아닌 사유(가점 당첨자 없음·발표 전)가 있는 행이 하나라도 있으면 */
function showPointsColumn(rows: ComplexDetail['competition']): boolean {
  return rows.some((r) => {
    const code = pointsReason(r);
    return hasPoints(r) || code === 'no_winner' || code === 'not_published';
  });
}

/** D29-4: 최저·최고·평균이 모두 0 → 가점제 당첨자 없음 */
function noPointWinners(row: ComplexDetail['competition'][number]): boolean {
  return [row.winning_score_min, row.winning_score_max, row.winning_score_avg].every(
    (f) => !!f && f.v !== null && Number(f.v) === 0,
  );
}

function PointsCell({ row }: { row: ComplexDetail['competition'][number] }) {
  if (noPointWinners(row)) {
    return <span data-testid="no-point-winners">{t('page.G3.competition.noPointWinners')}</span>;
  }
  // 계약 .21 F4: 값 없는 이유를 쉬운 말로 — 팝업 '-'(가점 당첨자 없음, 미달이면 '(미달)')·발표 전·가점 미수집. 원 사유는 title
  const code = pointsReason(row);
  const reason = row.winning_score_min?.reason ?? undefined;
  if (code === 'no_winner') {
    const short = shortfallUnits(row.ratio_or_shortfall_text) !== null;
    return (
      <span data-testid="points-reason" data-reason-code={code} title={reason}>
        {short
          ? t('page.G3.competition.noPointWinnersShortfall')
          : t('page.G3.competition.noPointWinners')}
      </span>
    );
  }
  if (code === 'not_published' || code === 'not_collected') {
    return (
      <span
        data-testid="points-reason"
        data-reason-code={code}
        title={reason}
        className="text-muted"
      >
        {code === 'not_published'
          ? t('page.G3.competition.pointsBeforeAnnounce')
          : t('page.G3.competition.pointsNotCollected')}
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <FactCell fact={row.winning_score_min ?? null} unit="score" digits={0} />
      <span aria-hidden>~</span>
      <FactCell fact={row.winning_score_max ?? null} unit="score" digits={0} />
      <span className="text-xs text-muted">{t('page.G3.competition.pointsAvg')}</span>
      <FactCell fact={row.winning_score_avg ?? null} unit="score" digits={2} />
    </span>
  );
}

export function EventsTab({ detail }: { detail: ComplexDetail }) {
  const { events, competition, asof_date: asof } = detail;
  // 당첨 가점은 수집 전이면 모두 '확인 불가(가점 미수집)' — 그동안은 청약홈 안내 줄(30-proposal §9-2).
  // 계약 .21: '가점 당첨자 없음'·'발표 전' 행이 있어도 열을 보인다(미수집과 구별)
  const showPoints = showPointsColumn(competition);
  // R9-UI P8: 경쟁률 표를 맨 위로(초보 질문 Q5), 추가 모집 이력 차트는 그 아래
  return (
    <div className="flex flex-col gap-6">
      <TabSection
        id="g3-competition-title"
        title={t('page.G3.competition.title')}
        hint={t('page.G3.competition.hint')}
      >
        {detail.competition_summary ? (
          <CompetitionSummaryLine summary={detail.competition_summary} />
        ) : null}
        {competition.length === 0 ? (
          <EmptyState reason={t('page.common.none')} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  {(['round', 'kind', 'type', 'supply', 'applied', 'ratio'] as const).map((k) => (
                    <th key={k} scope="col" className={thClass}>
                      {t(`page.G3.competition.${k}` as TKey)}
                    </th>
                  ))}
                  {showPoints ? (
                    <th scope="col" className={thClass}>
                      <span className="inline-flex items-center gap-1">
                        {t('page.G3.competition.points')}
                        <Term k="points" />
                      </span>
                    </th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {competition.map((row, i) => {
                  const shortfall = shortfallUnits(row.ratio_or_shortfall_text);
                  return (
                    <tr key={row.id ?? i}>
                      <td className={tdClass}>{row.round}</td>
                      <td className={tdClass}>{enumText('chart.C08.kind', row.kind)}</td>
                      <td className={tdClass}>{row.type_code}</td>
                      <td className={tdClass}>
                        <FactCell fact={row.supply} unit="households" />
                      </td>
                      <td className={tdClass}>
                        <FactCell fact={row.applied} unit="count" />
                      </td>
                      <td className={tdClass}>
                        {shortfall !== null ? (
                          <span
                            title={row.ratio_or_shortfall_text ?? undefined}
                            className="font-semibold text-warn-ink"
                          >
                            {t('page.G3.competition.shortfall', { n: shortfall })}
                          </span>
                        ) : (
                          (row.ratio_or_shortfall_text ?? t('empty.unknown'))
                        )}
                      </td>
                      {showPoints ? (
                        <td className={tdClass}>
                          <PointsCell row={row} />
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {/* 당첨 가점 값이 아직 없으면(가점 미수집) 정직하게 표시 */}
        {showPoints ? null : (
          <p className="text-xs text-muted">{t('page.G3.competition.pointsMissing')}</p>
        )}
      </TabSection>
      <C08Timeline data={{ events }} asof={asof} />
    </div>
  );
}

const HORIZONS: readonly LadderHorizon[] = ['move_in_plus_1y', 'asof_plus_3y', 'asof_plus_5y'];

export function LadderTab({ detail }: { detail: ComplexDetail }) {
  const [horizon, setHorizon] = useState<LadderHorizon>('move_in_plus_1y');
  const row = detail.ladder.find((r) => r.horizon === horizon);
  return (
    <TabSection
      id="g3-ladder-title"
      title={t('page.G3.ladder.title')}
      hint={t('page.G3.ladder.note')}
    >
      <div
        role="radiogroup"
        aria-label={t('page.G3.ladder.horizons')}
        className="flex flex-wrap gap-2"
      >
        {HORIZONS.map((h) => {
          const r = detail.ladder.find((x) => x.horizon === h);
          const unresolved = !!r && isUnresolved(r.status);
          return (
            <button
              key={h}
              type="button"
              role="radio"
              aria-checked={h === horizon}
              onClick={() => setHorizon(h)}
              className={`min-h-11 rounded-xl border px-4 text-[15px] ${
                h === horizon
                  ? 'border-accent bg-accent text-accent-fg'
                  : 'border-border-strong bg-surface text-fg hover:border-accent'
              } ${unresolved && h !== horizon ? 'text-grayed' : ''}`}
            >
              {enumText('chart.C01.horizon', h)}
              {r ? ` · ${r.target_label ?? formatHalfYear(r.target_ym)}` : ''}
              {unresolved ? ` · ${t('page.common.unresolved')}` : ''}
            </button>
          );
        })}
      </div>
      <C01Ladder data={{ ladder: detail.ladder, horizon }} height={240} asof={detail.asof_date} />
      {row?.proposition_text ? (
        <div className="flex flex-col gap-1 rounded-xl bg-subtle px-4 py-3 text-sm">
          <span className="text-[13px] font-medium text-muted">
            {t('page.G3.ladder.proposition')}
          </span>
          <p className="text-fg-2">{row.proposition_text}</p>
        </div>
      ) : null}
    </TabSection>
  );
}

export function GapTab({ detail }: { detail: ComplexDetail }) {
  const { gap } = detail;
  const substitute = gap.comps.some((c) => c.substitute);
  // R9-UI P8(30-proposal §9-3): 부호를 문장으로 한 번만 풀고(높고 낮음을 좋고 나쁨으로 바꾸지 않는다), 같은 이름 두 값을 나눈다
  return (
    <TabSection id="g3-gap-title" title={t('page.G3.gap.title')} hint={t('page.G3.gap.hint')}>
      <dl className="grid gap-3 sm:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-1 rounded-[14px] bg-subtle p-4">
          <dt className="inline-flex items-center gap-1 text-[13px] text-muted">
            {t('page.G3.gap.pct')}
            <Term k="gap" />
          </dt>
          <dd className="text-xl font-bold">
            <FactCell wrap fact={gap.gap_pct} unit="pct" />
          </dd>
        </div>
        {gap.gap_pct_unadjusted ? (
          <div className="flex min-w-0 flex-col gap-1 rounded-[14px] bg-subtle p-4">
            <dt className="text-[13px] text-muted">{t('page.G3.gap.unadjusted')}</dt>
            <dd className="text-xl font-bold">
              <FactCell wrap fact={gap.gap_pct_unadjusted} unit="pct" />
            </dd>
          </div>
        ) : null}
        <div className="flex min-w-0 flex-col gap-1 rounded-[14px] bg-subtle p-4">
          <dt className="text-[13px] text-muted">{t('page.G3.gap.score')}</dt>
          <dd className="text-xl font-bold">
            {/* 계약 .20 F7: 점수 s_gap 은 gap_score(옛 이름 score) — 퍼센트(gap_pct, prov …raw)와 다른 출처 */}
            <FactCell wrap fact={gap.gap_score ?? gap.score} unit="score" />
          </dd>
        </div>
      </dl>
      <p className="rounded-xl border border-info-border bg-info-soft px-4 py-3 text-sm text-info-ink">
        {t('page.G3.gap.meaning')}
      </p>
      {/* 계약 .22 F2·F3(D30-5): 비교군 전체 중앙값(보정·미보정) — 서버 저장값 그대로. 키 없음 = .22 전 저장본 → 줄 없음 */}
      {gap.comps_median !== undefined || gap.comps_median_unadjusted ? (
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm" data-testid="gap-comps-median">
          {gap.comps_median !== undefined ? (
            <div className="flex flex-wrap items-center gap-1">
              <dt className="text-muted">{t('page.G3.gap.compsMedian')}</dt>
              <dd>
                <FactCell wrap fact={gap.comps_median} unit="won" />
              </dd>
            </div>
          ) : null}
          {gap.comps_median_unadjusted ? (
            <div className="flex flex-wrap items-center gap-1">
              <dt className="text-muted">{t('page.G3.gap.compsMedianUnadjusted')}</dt>
              <dd>
                <FactCell wrap fact={gap.comps_median_unadjusted} unit="won" />
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}
      <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>{t('page.G3.gap.basis')}</span>
        <Badge tone="neutral">
          <MetaText kind="count" k="page.G3.gap.comps" params={{ n: gap.comps.length }} />
        </Badge>
        {substitute ? <Badge tone="muted">{t('page.G3.gap.substitute')}</Badge> : null}
      </p>
      <C02Gap data={{ gap }} asof={detail.asof_date} />
    </TabSection>
  );
}

export function CatalystsTab({ detail }: { detail: ComplexDetail }) {
  const { catalysts } = detail;
  return (
    <TabSection
      id="g3-catalyst-title"
      title={t('page.G3.catalyst.title')}
      hint={t('page.G3.catalyst.hint')}
    >
      <C09Catalyst data={{ catalysts, compact: true }} asof={detail.asof_date} />
      <section aria-labelledby="g3-catalyst-list" className="flex flex-col gap-2">
        <h4 id="g3-catalyst-list" className="text-[15px] font-bold">
          {t('page.G3.catalyst.list')}
        </h4>
        {catalysts.length === 0 ? (
          <EmptyState message={t('page.G3.catalyst.empty')} />
        ) : (
          <ul className="flex flex-col divide-y divide-border text-sm">
            {catalysts.map((c) => {
              const grayed = c.stage === '언론' || c.stage === '미확정';
              return (
                <li
                  key={c.id}
                  className={`flex flex-wrap items-center gap-2 py-2.5 ${grayed ? 'text-grayed' : ''}`}
                >
                  <span className="font-semibold">{c.name}</span>
                  <Badge tone="neutral">{enumText('page.G3.catalystKind', c.kind)}</Badge>
                  <Badge tone={grayed ? 'muted' : 'strong'}>
                    {enumText('chart.C09.stage', c.stage)}
                  </Badge>
                  <span className="text-xs text-muted">{t('page.G3.catalyst.stageProb')}</span>
                  <FactCell fact={c.stage_prob} unit="prob" />
                  <span className="text-xs text-muted">{t('page.G3.catalyst.expected')}</span>
                  <FactCell fact={c.expected_ym} unit="ym" />
                  {c.distance_m ? (
                    <>
                      <span className="text-xs text-muted">{t('page.G3.catalyst.distance')}</span>
                      <FactCell fact={c.distance_m} unit="number" />
                    </>
                  ) : null}
                  {!c.location_confirmed || c.linked === false ? (
                    <Badge tone="muted">{t('chart.C09.noLink')}</Badge>
                  ) : null}
                  {c.decision && c.decision !== 'auto' ? (
                    <Badge tone="muted">{t('page.common.unresolved')}</Badge>
                  ) : null}
                  {c.source_url ? (
                    <ExternalLink
                      href={c.source_url}
                      fallback={c.source_url}
                      className="text-accent hover:underline"
                    >
                      {t('page.G3.catalyst.source')}
                    </ExternalLink>
                  ) : null}
                  {c.note ? <span className="w-full text-xs text-muted">{c.note}</span> : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </TabSection>
  );
}
