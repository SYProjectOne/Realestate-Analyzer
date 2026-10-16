import { t } from '@/i18n';
import type { IsoDate } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import {
  buildOption,
  emptyReason,
  legendItems,
  recentRows,
  subtitle,
  toTable,
} from './buildOption';
import type { C05Data } from './types';

export interface C05UnsoldProps {
  data: C05Data;
  height?: number;
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C05.source` */
  source?: string;
}

/** C5 미분양 추이 — 합계·준공 후 24개월 (G1 작게, G6). 부제 = 월말 기준·범위, 배지 = 출처 라벨 */
export function C05Unsold({ data, height = 240, asof, source }: C05UnsoldProps) {
  const palette = useChartPalette();
  const title = t('chart.C05.title');
  const rows = recentRows(data);
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle(data)}
      labels={collectLabels(rows.flatMap((r) => [r.total, r.post_completion]))}
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C05.source')}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
