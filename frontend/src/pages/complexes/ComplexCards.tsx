import { useState } from 'react';
import { Link } from 'react-router';
import type { ComplexRow } from '@/api/types';
import { Badge, FactCell, IntakeBadge, MetaText, MetaValue, TieBadge } from '@/components';
import { t } from '@/i18n';
import { enumText, JudgeScopeBadge, NameLabelBadge, RejudgeNeededBadge } from '../_shared';

/** 처음 그리는 카드 수 — 나머지는 '더 보기'(목록 순서·정렬은 표와 같다) */
const CARDS_STEP = 30;

export interface ComplexCardsProps {
  rows: ComplexRow[];
  total: number;
  asof: string | null;
  linkSearch: string;
}

/**
 * G2 모바일(≤768px) 카드 목록 — R9-UI P5(30-proposal §6, D28-4). 읽기 전용(비교 체크 없음).
 * 줄 순서: 생활권 → 이름 → 접수·전매 종료 → 현재 구매가 → 계약금·입주 → 종합 점수(상대 비교). 가격 갭·+10% 는 '더 보기'.
 * 값은 표와 같은 Fact(FactCell — 라벨·출처). 정렬·필터는 URL 쿼리(데스크톱과 같다).
 */
export function ComplexCards({ rows, total, asof, linkSearch }: ComplexCardsProps) {
  const [limit, setLimit] = useState(CARDS_STEP);
  const shown = rows.slice(0, limit);
  return (
    <div className="flex flex-col gap-2">
      <ul aria-label={t('page.G2.cards')} className="flex flex-col gap-2">
        {shown.map((row) => (
          <Card key={row.complex_id} row={row} asof={asof} linkSearch={linkSearch} />
        ))}
      </ul>
      {rows.length > limit ? (
        <button
          type="button"
          onClick={() => setLimit((n) => n + CARDS_STEP)}
          className="rounded-sm border border-border px-3 py-2 text-sm"
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

function Card({
  row,
  asof,
  linkSearch,
}: {
  row: ComplexRow;
  asof: string | null;
  linkSearch: string;
}) {
  return (
    <li
      className="flex flex-col gap-1 rounded-sm border border-border bg-surface p-3 text-sm"
      data-complex-id={row.complex_id}
    >
      <span data-field="living_area" className="text-xs text-muted">
        {row.living_area_name ?? enumText('page.common', null)}
      </span>
      <span data-field="name" className="flex flex-wrap items-center gap-1">
        <Link to={`/complexes/${row.complex_id}${linkSearch}`} className="font-medium underline">
          {row.name}
        </Link>
        <NameLabelBadge source={row} />
      </span>
      <span data-field="status" className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <IntakeBadge intake={row.intake} asof={asof} showPath={false} reasonBelow />
        <span className="text-xs text-muted">{t('page.G2.card.resaleEnd')}</span>
        <FactCell wrap fact={row.resale_end} unit="date" asof={asof} />
      </span>
      <span data-field="price" className="flex flex-wrap items-center gap-1">
        <FactCell wrap fact={row.price_low} unit="won" />
        <span aria-hidden>~</span>
        <FactCell wrap fact={row.price_high} unit="won" />
      </span>
      <span data-field="down_move_in" className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-xs text-muted">{t('page.G2.card.down')}</span>
        <FactCell wrap fact={row.down_payment_pct} unit="pct" digits={0} />
        <span className="text-xs text-muted">{t('page.G2.card.moveIn')}</span>
        <FactCell wrap fact={row.move_in_ym} unit="ym" />
      </span>
      <span data-field="total" className="flex flex-wrap items-center gap-1">
        <span className="text-xs text-muted">{t('page.G2.card.total')}</span>
        <FactCell wrap fact={row.total} unit="score" />
        {row.rank !== null ? (
          <Badge tone="neutral">
            <MetaValue kind="rank" value={row.rank} as="rank" />
          </Badge>
        ) : null}
        <TieBadge tie={row.tie_group !== null} />
        <JudgeScopeBadge scope={row.judge_scope} hideTarget />
        <RejudgeNeededBadge needed={row.rejudge_needed} />
        <span className="text-xs text-muted">{t('page.G2.card.relative')}</span>
      </span>
      <details className="text-sm">
        <summary className="cursor-pointer text-xs text-muted">{t('page.G2.card.more')}</summary>
        <dl data-field="more" className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
          <dt className="text-xs text-muted">{t('page.G2.col.gap')}</dt>
          <dd>
            <FactCell wrap fact={row.gap_pct} unit="pct" />
          </dd>
          <dt className="text-xs text-muted">{t('page.G2.col.p10')}</dt>
          <dd>
            <FactCell wrap fact={row.p10} unit="prob" />
          </dd>
        </dl>
      </details>
    </li>
  );
}
