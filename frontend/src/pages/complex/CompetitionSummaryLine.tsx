import type { CompetitionSummary } from '@/api/types';
import { FactCell } from '@/components';
import { t } from '@/i18n';

/**
 * 경쟁률 요약 한 줄(계약 .20 F2 — 서버 산술 Fact): 기준(본청약 1순위 해당지역) 최고 경쟁률·그 주택형·미달 주택형 수.
 * 기준 행이 없으면 서버가 준 '확인 불가(사유)' 그대로.
 */
export function CompetitionSummaryLine({ summary }: { summary: CompetitionSummary }) {
  return (
    <p
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
      data-testid="competition-summary"
      title={summary.basis}
    >
      <span className="text-xs text-muted">{t('page.G3.competition.maxRatio')}</span>
      <FactCell wrap fact={summary.max_ratio} unit="ratio" digits={2} />
      {summary.max_ratio_type_code ? (
        <span className="text-xs text-muted">{summary.max_ratio_type_code}</span>
      ) : null}
      <span className="text-xs text-muted">{t('page.G3.competition.shortfallTypes')}</span>
      <FactCell wrap fact={summary.shortfall_types} unit="count" />
    </p>
  );
}
