import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, toTable } from './buildOption';
import type { C08Data } from './types';

export interface C08TimelineProps {
  data: C08Data;
  height?: number;
  /** 공고일 D± 기준일 (표) */
  asof?: string | null;
}

/** C8 잔여 이력 타임라인 — 공고일 마커(kind별 모양) + 잔여 세대·경쟁률 라벨 (G3) */
export function C08Timeline({ data, height = 220, asof }: C08TimelineProps) {
  const palette = useChartPalette();
  const title = t('chart.C08.title');
  return (
    <ChartFrame
      title={title}
      labels={collectLabels(data.events.flatMap((e) => [e.notice_date, e.units]))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
