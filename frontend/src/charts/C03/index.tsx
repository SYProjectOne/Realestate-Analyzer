import { Badge } from '@/components/Badge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, sampleBadge, toTable } from './buildOption';
import type { C03Data } from './types';

export interface C03BenchmarkProps {
  data: C03Data;
  height?: number;
}

/** C3 벤치마크 분양가 → 실거래 범위 dumbbell (G6) */
export function C03Benchmark({ data, height = 320 }: C03BenchmarkProps) {
  const palette = useChartPalette();
  const title = t('chart.C03.title');
  const sample = sampleBadge(data);
  return (
    <ChartFrame
      title={title}
      labels={collectLabels(data.benchmarks.flatMap((b) => [b.sale_price_84_won, b.trade_median_won]))}
      badges={sample ? <Badge tone="muted">{sample}</Badge> : null}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
