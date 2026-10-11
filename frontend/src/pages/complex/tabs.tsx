/** G3 탭 패널: 가격표 · 납부 조건 · 잔여 이력 · 시세 비교 · 호재 */
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import type { ComplexDetail, Fact, LadderHorizon, PriceRange } from '@/api/types';
import { C01Ladder, C02Gap, C08Timeline, C09Catalyst } from '@/charts';
import { Badge, EmptyState, ExternalLink, FactCell, MetaText } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatHalfYear } from '@/lib/format';
import { enumText, isUnresolved, Section, tdClass, thClass, useGlobalSearch } from '../_shared';
import { HC_PARAM, HUMAN_CHECK_ANCHOR } from '../ops/humanCheckRules';

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

/** G7 사람 확인 폼 주소 — 단지·필드 `discount` 미리 채움, 전역 쿼리(region·snapshot·scenario) 유지 */
export function discountHumanCheckTo(
  globalSearch: string,
  complexId: number,
): { pathname: string; search: string; hash: string } {
  const params = new URLSearchParams(globalSearch);
  params.set(HC_PARAM.complex, String(complexId));
  params.set(HC_PARAM.field, 'discount');
  return { pathname: '/ops', search: `?${params.toString()}`, hash: HUMAN_CHECK_ANCHOR };
}

/**
 * '추정' 할인 안내(D16-1): "공고문에서 찾은 할인(조건 확인 필요) — 사람 확인 시 구매가에 반영" + G7 사람 확인 링크.
 */
export function EstimatedDiscountNote({
  complexId,
  testId = 'discount-estimated',
}: {
  complexId: number;
  testId?: string;
}) {
  const globalSearch = useGlobalSearch();
  return (
    <span className="text-xs text-muted" data-testid={testId}>
      {t('page.G3.price.discountEstimated')}{' '}
      <Link to={discountHumanCheckTo(globalSearch, complexId)} className="underline">
        {t('page.G3.price.discountHumanCheck')}
      </Link>
    </span>
  );
}

/** 현재 공고(is_current)의 타입별 할인(payment_terms.discount_by_type, 키 = type_code) */
function currentDiscounts(detail: ComplexDetail): Record<string, Fact> {
  const current = detail.payment.find((p) => p.is_current) ?? null;
  return current?.discount_by_type ?? {};
}

export function PriceTab({ detail }: { detail: ComplexDetail }) {
  const { price, types } = detail;
  const discounts = currentDiscounts(detail);
  const hasTypeDiscount = Object.keys(discounts).length > 0;
  const note = discountNote(price);
  const complexId = detail.header.id;
  // 기준 타입 할인이 '추정'이면 그 줄에, 아니고 타입별 할인 중 '추정'이 있으면 표 아래에 한 번(D16-1)
  const estimatedPrice = isEstimatedDiscount(price.discount);
  const estimatedType = !estimatedPrice && Object.values(discounts).some(isEstimatedDiscount);
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t('page.G3.header.price')}</dt>
        <dd className="flex flex-wrap items-center gap-1">
          <FactCell fact={price.price_low} unit="won" />
          <span aria-hidden>~</span>
          <FactCell fact={price.price_high} unit="won" />
        </dd>
        {price.discount ? (
          <>
            <dt className="text-muted">{t('page.G3.price.discount')}</dt>
            <dd className="flex flex-wrap items-center gap-1" data-testid="price-discount">
              <FactCell fact={price.discount} unit="won" />
              {note ? <span className="text-xs text-muted">{note}</span> : null}
              {estimatedPrice ? <EstimatedDiscountNote complexId={complexId} /> : null}
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
                    {row.options_text ? (
                      <span className="block text-xs text-muted">{row.options_text}</span>
                    ) : null}
                  </td>
                  {hasTypeDiscount ? (
                    <td className={tdClass} data-testid={`type-discount-${row.type_code}`}>
                      {discounts[row.type_code] ? (
                        <FactCell fact={discounts[row.type_code]} unit="won" />
                      ) : (
                        <span className="text-muted">{t('page.common.none')}</span>
                      )}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {estimatedType ? <EstimatedDiscountNote complexId={complexId} /> : null}
    </div>
  );
}

export function PaymentTab({ detail }: { detail: ComplexDetail }) {
  const { payment, asof_date: asof } = detail;
  if (payment.length === 0) return <EmptyState reason={t('page.common.none')} />;
  return (
    <div className="flex flex-col gap-3">
      {payment.map((term) => (
        <Section
          key={`${term.notice_no}-${term.id ?? ''}`}
          title={`${t('page.G3.payment.notice')} ${term.notice_no}`}
          actions={
            <span className="flex gap-1">
              {term.notice_kind ? <Badge tone="neutral">{term.notice_kind}</Badge> : null}
              {term.is_current ? <Badge tone="strong">{t('page.G3.payment.current')}</Badge> : null}
            </span>
          }
        >
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm md:grid-cols-3">
            <Item label={t('page.G3.payment.effective')}>
              <FactCell fact={term.effective_from} unit="date" asof={asof} />
            </Item>
            <Item label={t('page.G3.payment.down')}>
              <FactCell fact={term.down_payment_pct} unit="pct" digits={0} />
            </Item>
            <Item label={t('page.G3.payment.downFirst')}>
              <FactCell fact={term.down_payment_first_won} unit="won" />
            </Item>
            <Item label={t('page.G3.payment.interim')}>
              <FactCell fact={term.interim_pct} unit="pct" digits={0} />
            </Item>
            <Item label={t('page.G3.payment.balance')}>
              <FactCell fact={term.balance_pct} unit="pct" digits={0} />
            </Item>
            <Item label={t('page.G3.payment.interimTerms')}>
              {term.interim_terms_text ?? t('page.common.none')}
            </Item>
            {term.change_vs_first?.down_payment_pct_delta ? (
              <Item label={t('page.G3.payment.changeVsFirst')}>
                <FactCell
                  fact={term.change_vs_first.down_payment_pct_delta}
                  unit="pct"
                  digits={0}
                />
              </Item>
            ) : null}
          </dl>
          {term.interim_schedule.length > 0 ? (
            <table className="w-full border-collapse text-sm">
              <caption className="text-left text-xs text-muted">
                {t('page.G3.payment.schedule')}
              </caption>
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
          ) : null}
        </Section>
      ))}
    </div>
  );
}

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-xs text-muted">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function EventsTab({ detail }: { detail: ComplexDetail }) {
  const { events, competition, asof_date: asof } = detail;
  return (
    <div className="flex flex-col gap-3">
      <C08Timeline data={{ events }} asof={asof} />
      <Section title={t('page.G3.competition.title')}>
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
                </tr>
              </thead>
              <tbody>
                {competition.map((row, i) => (
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
                    <td className={tdClass}>{row.ratio_or_shortfall_text ?? t('empty.unknown')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

const HORIZONS: readonly LadderHorizon[] = ['move_in_plus_1y', 'asof_plus_3y', 'asof_plus_5y'];

export function LadderTab({ detail }: { detail: ComplexDetail }) {
  const [horizon, setHorizon] = useState<LadderHorizon>('move_in_plus_1y');
  const row = detail.ladder.find((r) => r.horizon === horizon);
  return (
    <div className="flex flex-col gap-3">
      <div role="radiogroup" aria-label={t('page.G3.ladder.horizons')} className="flex gap-1">
        {HORIZONS.map((h) => {
          const r = detail.ladder.find((x) => x.horizon === h);
          return (
            <button
              key={h}
              type="button"
              role="radio"
              aria-checked={h === horizon}
              onClick={() => setHorizon(h)}
              className={`rounded border border-border px-2 py-1 text-sm ${
                h === horizon ? 'bg-accent text-accent-fg' : ''
              } ${r && isUnresolved(r.status) ? 'text-grayed' : ''}`}
            >
              {enumText('chart.C01.horizon', h)}
              {r ? ` · ${r.target_label ?? formatHalfYear(r.target_ym)}` : ''}
              {r && isUnresolved(r.status) ? ` · ${t('page.common.unresolved')}` : ''}
            </button>
          );
        })}
      </div>
      <C01Ladder data={{ ladder: detail.ladder, horizon }} height={240} />
      {row?.proposition_text ? (
        <p className="text-sm text-muted">
          <span className="font-medium">{t('page.G3.ladder.proposition')}: </span>
          {row.proposition_text}
        </p>
      ) : null}
    </div>
  );
}

export function GapTab({ detail }: { detail: ComplexDetail }) {
  const { gap } = detail;
  return (
    <div className="flex flex-col gap-3">
      <C02Gap data={{ gap }} />
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t('page.G2.col.gap')}</dt>
        <dd>
          <FactCell fact={gap.gap_pct} unit="pct" />
        </dd>
        {gap.gap_pct_unadjusted ? (
          <>
            <dt className="text-muted">{t('chart.C02.comps')}</dt>
            <dd>
              <FactCell fact={gap.gap_pct_unadjusted} unit="pct" />
            </dd>
          </>
        ) : null}
        <dt className="text-muted">{t('chart.C06.component.gap')}</dt>
        <dd>
          <FactCell fact={gap.score} unit="score" />
        </dd>
      </dl>
    </div>
  );
}

export function CatalystsTab({ detail }: { detail: ComplexDetail }) {
  const { catalysts } = detail;
  return (
    <div className="flex flex-col gap-3">
      <C09Catalyst data={{ catalysts, compact: true }} />
      <Section title={t('page.G3.catalyst.list')}>
        {catalysts.length === 0 ? (
          <EmptyState message={t('chart.C09.empty')} />
        ) : (
          <ul className="flex flex-col divide-y divide-border text-sm">
            {catalysts.map((c) => {
              const grayed = c.stage === '언론' || c.stage === '미확정';
              return (
                <li
                  key={c.id}
                  className={`flex flex-wrap items-center gap-2 py-1.5 ${grayed ? 'text-grayed' : ''}`}
                >
                  <span className="font-medium">{c.name}</span>
                  <Badge tone="neutral">{enumText('page.G3.catalystKind', c.kind)}</Badge>
                  <Badge tone={grayed ? 'muted' : 'strong'}>
                    {enumText('chart.C09.stage', c.stage)}
                  </Badge>
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
                    <ExternalLink href={c.source_url} fallback={c.source_url}>
                      {t('page.G3.catalyst.source')}
                    </ExternalLink>
                  ) : null}
                  {c.note ? <span className="w-full text-xs text-muted">{c.note}</span> : null}
                </li>
              );
            })}
          </ul>
        )}
      </Section>
    </div>
  );
}
