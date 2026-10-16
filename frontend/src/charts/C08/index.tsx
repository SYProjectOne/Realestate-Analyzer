import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, legendItems, toTable } from './buildOption';
import type { C08Data } from './types';

export interface C08TimelineProps {
  data: C08Data;
  height?: number;
  /** 공고일 D± 기준일 (표) */
  asof?: string | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C08.source` */
  source?: string;
}

/** C8 잔여 이력 타임라인 — 공고일 마커(kind별 모양) + 잔여 세대·경쟁률 라벨 (G3) */
export function C08Timeline({ data, height = 260, asof, source }: C08TimelineProps) {
  const palette = useChartPalette();
  const title = t('chart.C08.title');
  // 기준일 점선: data.asof 가 없으면 바닥줄 기준일(asof)을 쓴다
  const withAsof = { ...data, asof: data.asof ?? asof ?? null };
  return (
    <ChartFrame
      title={title}
      labels={collectLabels(data.events.flatMap((e) => [e.notice_date, e.units]))}
      subtitle={t('chart.C08.subtitle')}
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C08.source')}
    >
      <EChart option={buildOption(withAsof, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
