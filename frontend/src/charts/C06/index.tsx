import { UnstableBadge } from '@/components/UnstableBadge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, toTable, weightsSubtitle } from './buildOption';
import type { C06Data } from './types';

export interface C06ScoreBreakdownProps {
  data: C06Data;
  height?: number;
}

/** C6 종합 점수 분해 — 가중 기여 stacked bar 6요소 (G1, G4). 제목 아래 가중치, 툴팁 = formula_text */
export function C06ScoreBreakdown({ data, height = 300 }: C06ScoreBreakdownProps) {
  const palette = useChartPalette();
  const title = t('chart.C06.title');
  return (
    <ChartFrame
      title={title}
      subtitle={weightsSubtitle(data.weights)}
      labels={collectLabels(data.rows.map((r) => r.total))}
      badges={<UnstableBadge unstable={data.rows.some((r) => r.unstable)} />}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
