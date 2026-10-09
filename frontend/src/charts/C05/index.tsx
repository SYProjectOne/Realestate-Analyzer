import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, recentRows, subtitle, toTable } from './buildOption';
import type { C05Data } from './types';

export interface C05UnsoldProps {
  data: C05Data;
  height?: number;
}

/** C5 미분양 추이 — 합계·준공 후 24개월 (G1 작게, G6). 부제 = 월말 기준·범위, 배지 = 출처 라벨 */
export function C05Unsold({ data, height = 240 }: C05UnsoldProps) {
  const palette = useChartPalette();
  const title = t('chart.C05.title');
  const rows = recentRows(data);
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle(data)}
      labels={collectLabels(rows.flatMap((r) => [r.total, r.post_completion]))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
