import { Link } from 'react-router';
import type { CompetitionSummary, ComplexDetail } from '@/api/types';
import { EmptyState, FactCell, Term } from '@/components';
import { t } from '@/i18n';
import { useGlobalSearch } from '../_shared';
import { Tier } from './Tier';

/**
 * 경쟁률 요약(계약 .20 F2 — 서버 산술 Fact): 기준(본청약 1순위 해당지역) 최고 경쟁률·그 주택형·미달 주택형 수 +
 * 당첨된 사람 가점 최저~최고(계약 .20 Q4·.21 — `winning_score_min/max`, 화면이 타입별 가점을 묶지 않는다, D30-5 A3).
 * 기준 행이 없으면 서버가 준 '확인 불가(사유)' 그대로. 기준 문구(basis)는 보이는 부제 + title.
 */
export function CompetitionSummaryLine({ summary }: { summary: CompetitionSummary }) {
  return (
    <div
      className="grid gap-3 sm:grid-cols-3"
      data-testid="competition-summary"
      title={summary.basis}
    >
      <div className="flex min-w-0 flex-col gap-1 rounded-[14px] bg-subtle p-4">
        <span className="text-[13px] text-muted">{t('page.G3.competition.maxRatio')}</span>
        <span className="flex flex-wrap items-baseline gap-2 text-xl font-bold">
          <FactCell wrap fact={summary.max_ratio} unit="ratio" digits={2} />
          {summary.max_ratio_type_code ? (
            <span className="text-sm font-medium text-fg-2">
              {t('page.G3.compSummary.type', { type: summary.max_ratio_type_code })}
            </span>
          ) : null}
        </span>
      </div>
      <div className="flex min-w-0 flex-col gap-1 rounded-[14px] bg-subtle p-4">
        <span className="text-[13px] text-muted">{t('page.G3.competition.shortfallTypes')}</span>
        <span className="text-xl font-bold">
          <FactCell wrap fact={summary.shortfall_types} unit="count" />
        </span>
      </div>
      <div className="flex min-w-0 flex-col gap-1 rounded-[14px] bg-subtle p-4">
        <span className="inline-flex items-center gap-1 text-[13px] text-muted">
          {t('page.G3.compSummary.points')}
          <Term k="points" />
        </span>
        <span className="flex flex-wrap items-baseline gap-1 text-xl font-bold">
          <FactCell wrap fact={summary.winning_score_min} unit="score" digits={0} />
          <span aria-hidden>~</span>
          <FactCell wrap fact={summary.winning_score_max} unit="score" digits={0} />
        </span>
      </div>
    </div>
  );
}

/** 청약 때 얼마나 몰렸나요? — 머리 경쟁률 요약 카드(기준 부제 + 요약 3칸 + 경쟁률 전체 링크) */
export function CompetitionCard({ detail }: { detail: ComplexDetail }) {
  const globalSearch = useGlobalSearch();
  const summary = detail.competition_summary ?? null;
  return (
    <Tier
      tier="competition"
      title={t('page.G3.compSummary.title')}
      hint={summary ? t('page.G3.compSummary.basis', { basis: summary.basis }) : undefined}
    >
      {summary ? (
        <CompetitionSummaryLine summary={summary} />
      ) : (
        <EmptyState inline reason={t('page.G3.compSummary.none')} />
      )}
      <Link
        to={{ pathname: `/complexes/${detail.header.id}`, search: globalSearch, hash: '#events' }}
        replace
        className="self-start text-sm font-medium text-accent hover:underline"
      >
        {t('page.G3.compSummary.more')}
      </Link>
    </Tier>
  );
}
