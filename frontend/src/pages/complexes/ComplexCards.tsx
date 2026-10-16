import { useState } from 'react';
import { Link } from 'react-router';
import type { ComplexRow } from '@/api/types';
import {
  Badge,
  Card,
  FactCell,
  IntakeBadge,
  MetaText,
  MetaValue,
  TieBadge,
  UnstableBadge,
} from '@/components';
import { t } from '@/i18n';
import { enumText, JudgeScopeBadge, NameLabelBadge, RejudgeNeededBadge } from '../_shared';

/** 처음 그리는 카드 수 — 나머지는 '단지 더 보기'(목록 순서·정렬은 표와 같다) */
export const CARDS_STEP = 30;

export interface ComplexCardsProps {
  rows: ComplexRow[];
  total: number;
  asof: string | null;
  linkSearch: string;
  /** 'list' = 휴대폰 한 줄 카드(ListTable 보드 휴대폰), 'grid' = 데스크톱 카드 보기(List 보드) */
  variant?: 'list' | 'grid';
  /** '+10% 오를 가능성'의 목표 시점(상황 p10_horizon) — 없으면 확인 불가 */
  p10Target?: string | null;
}

/**
 * G2 카드 목록 — 휴대폰(≤768px, 읽기 전용, R9-UI P5) 과 데스크톱 카드 보기(R11 List 보드, D30-10). 비교 체크 없음.
 * 줄 순서: 접수·되팔기 가능 → 생활권·세대 → 이름 → 현재 가격 → 계약금·입주·작년 경쟁률 → 종합 점수(상대 비교, D30-10) →
 * '더 보기'(주변 시세와 가격 차이 · 오를 가능성). 값은 표와 같은 Fact(FactCell — 라벨·출처). 정렬·필터는 URL 쿼리.
 */
export function ComplexCards({
  rows,
  total,
  asof,
  linkSearch,
  variant = 'list',
  p10Target = null,
}: ComplexCardsProps) {
  const [limit, setLimit] = useState(CARDS_STEP);
  const shown = rows.slice(0, limit);
  return (
    <div className="flex flex-col gap-4">
      <ul
        aria-label={t('page.G2.cards')}
        className={
          variant === 'grid'
            ? 'grid gap-[18px] [grid-template-columns:repeat(auto-fill,minmax(340px,1fr))]'
            : 'flex flex-col gap-2.5'
        }
      >
        {shown.map((row) => (
          <ComplexCard
            key={row.complex_id}
            row={row}
            asof={asof}
            linkSearch={linkSearch}
            variant={variant}
            p10Target={p10Target}
          />
        ))}
      </ul>
      {rows.length > limit ? (
        <button
          type="button"
          onClick={() => setLimit((n) => n + CARDS_STEP)}
          className="min-h-11 self-center rounded-xl border border-border-strong bg-surface px-5 py-2.5 text-[15px] font-semibold text-fg hover:border-accent"
        >
          <MetaText
            kind="count"
            k="page.G2.card.showMore"
            params={{ shown: shown.length, total }}
          />
        </button>
      ) : null}
    </div>
  );
}

function ComplexCard({
  row,
  asof,
  linkSearch,
  variant,
  p10Target,
}: {
  row: ComplexRow;
  asof: string | null;
  linkSearch: string;
  variant: 'list' | 'grid';
  p10Target: string | null;
}) {
  const grid = variant === 'grid';
  const competition = row.competition_summary;
  // 접수·되팔기 가능 줄: 데스크톱 카드(List 보드)는 맨 위, 휴대폰 카드(ListTable 보드)는 이름 아래
  const status = (
    <span data-field="status" className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <IntakeBadge intake={row.intake} asof={asof} showPath={false} reasonBelow />
      <span className="text-xs text-muted">{t('page.G2.card.resaleEnd')}</span>
      <FactCell wrap fact={row.resale_end} unit="date" asof={asof} />
    </span>
  );
  return (
    <Card
      as="li"
      padding="none"
      interactive
      className="flex flex-col overflow-hidden text-sm"
      data-complex-id={row.complex_id}
    >
      <div className={`flex flex-col ${grid ? 'gap-2.5 p-5 pb-4' : 'gap-1.5 p-3.5'}`}>
        {grid ? status : null}
        <span
          data-field="living_area"
          className="flex flex-wrap items-center gap-x-1 text-[13px] text-muted"
        >
          <span>{row.living_area_name ?? enumText('page.common', null)}</span>
          {grid ? (
            <>
              <span aria-hidden>·</span>
              <FactCell wrap fact={row.units_total} unit="households" />
            </>
          ) : null}
        </span>
        <span data-field="name" className="flex flex-wrap items-center gap-1.5">
          <Link
            to={`/complexes/${row.complex_id}${linkSearch}`}
            className={`font-bold text-fg underline-offset-2 hover:underline ${grid ? 'text-[19px] leading-snug' : 'text-base underline'}`}
          >
            {row.name}
          </Link>
          <NameLabelBadge source={row} />
        </span>
        {grid ? null : status}
        <span
          data-field="price"
          className={`flex flex-wrap items-center gap-1 font-bold ${grid ? 'text-[22px] leading-tight' : 'text-[17px]'}`}
        >
          <FactCell wrap fact={row.price_low} unit="won" />
          <span aria-hidden>~</span>
          <FactCell wrap fact={row.price_high} unit="won" />
        </span>
        {grid ? null : (
          <span data-field="down_move_in" className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs text-muted">{t('page.G2.card.down')}</span>
            <FactCell wrap fact={row.down_payment_pct} unit="pct" digits={0} />
            {row.down_payment_won ? <FactCell wrap fact={row.down_payment_won} unit="won" /> : null}
            <span className="text-xs text-muted">{t('page.G2.card.moveIn')}</span>
            <FactCell wrap fact={row.move_in_ym} unit="ym" />
          </span>
        )}
        <span data-field="total" className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted">{t('page.G2.card.total')}</span>
          <span className="font-bold">
            <FactCell wrap fact={row.total} unit="score" />
          </span>
          {row.rank !== null ? (
            <Badge tone="neutral">
              <MetaValue kind="rank" value={row.rank} as="rank" />
            </Badge>
          ) : null}
          <TieBadge tie={row.tie_group !== null} />
          <UnstableBadge unstable={row.unstable} />
          <JudgeScopeBadge scope={row.judge_scope} hideTarget />
          <RejudgeNeededBadge needed={row.rejudge_needed} />
          <span className="text-xs text-muted">{t('page.G2.card.relative')}</span>
        </span>
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-accent">{t('page.G2.card.more')}</summary>
          <dl data-field="more" className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-xs text-muted">{t('page.G2.col.gap')}</dt>
            <dd>
              <FactCell wrap fact={row.gap_pct} unit="pct" />
            </dd>
            <dt className="text-xs text-muted">{t('page.G2.col.p10')}</dt>
            <dd className="flex flex-col gap-0.5">
              <FactCell wrap fact={row.p10} unit="prob" />
              <span className="text-xs text-muted">
                {t('page.G1.p10Target', { target: p10Target ?? t('empty.unknown') })} ·{' '}
                {t('page.G1.p10Note')}
              </span>
            </dd>
          </dl>
        </details>
      </div>
      {grid ? (
        <dl className="mt-auto grid grid-cols-3 border-t border-border bg-subtle text-xs">
          <div className="flex min-w-0 flex-col gap-1 border-r border-border px-3.5 py-3">
            <dt className="text-muted">{t('page.G2.card.down')}</dt>
            <dd className="text-[15px] font-bold" data-field="down">
              <FactCell wrap fact={row.down_payment_won ?? null} unit="won" />
            </dd>
          </div>
          <div className="flex min-w-0 flex-col gap-1 border-r border-border px-3.5 py-3">
            <dt className="text-muted">{t('page.G2.card.moveIn')}</dt>
            <dd className="text-[15px] font-bold">
              <FactCell wrap fact={row.move_in_ym} unit="ym" />
            </dd>
          </div>
          <div className="flex min-w-0 flex-col gap-1 px-3.5 py-3">
            <dt className="text-muted">{t('page.G2.card.competition')}</dt>
            <dd className="text-[15px] font-bold" data-field="competition">
              <FactCell
                wrap
                fact={competition ? competition.max_ratio : null}
                unit="ratio"
                digits={2}
              />
            </dd>
          </div>
        </dl>
      ) : null}
    </Card>
  );
}
