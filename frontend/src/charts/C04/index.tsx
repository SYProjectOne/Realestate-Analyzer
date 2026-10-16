import { t } from '@/i18n';
import type { IsoDate } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, legendItems, toTable } from './buildOption';
import type { C04Data } from './types';

export interface C04SupplyProps {
  data: C04Data;
  height?: number;
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C04.source` */
  source?: string;
}

/** C4 입주 물량 — 연도별 생활권 스택(큰 생활권 + 나머지 n곳 + 확인 불가) + 판정 단지 입주 핀 (G6, G3). 라벨 "추정 집계" */
export function C04Supply({ data, height = 320, asof, source }: C04SupplyProps) {
  const palette = useChartPalette();
  const title = t('chart.C04.title');
  return (
    <ChartFrame
      title={title}
      subtitle={t('chart.C04.subtitle')}
      labels={collectLabels(data.supply.map((s) => s.units))}
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C04.source')}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
