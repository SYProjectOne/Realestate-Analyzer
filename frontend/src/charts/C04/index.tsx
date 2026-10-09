import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, toTable } from './buildOption';
import type { C04Data } from './types';

export interface C04SupplyProps {
  data: C04Data;
  height?: number;
}

/** C4 입주 물량 — 연도별 생활권 스택 + 판정 단지 입주 마커 (G6, G3). 라벨 "추정 집계" */
export function C04Supply({ data, height = 300 }: C04SupplyProps) {
  const palette = useChartPalette();
  const title = t('chart.C04.title');
  return (
    <ChartFrame
      title={title}
      subtitle={t('chart.C04.label')}
      labels={collectLabels(data.supply.map((s) => s.units))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
