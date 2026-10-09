import { Badge } from '@/components/Badge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, sampleBadges, toTable } from './buildOption';
import type { C03Data } from './types';

export interface C03BenchmarkProps {
  data: C03Data;
  height?: number;
}

/** C3 벤치마크 분양가 → 실거래 범위 dumbbell (G6). 고점 = 삼각형, 분양권 = 마름모. */
export function C03Benchmark({ data, height }: C03BenchmarkProps) {
  const palette = useChartPalette();
  const title = t('chart.C03.title');
  const h = height ?? Math.max(200, 40 + data.benchmarks.length * 28);
  return (
    <ChartFrame
      title={title}
      labels={collectLabels(
        data.benchmarks.flatMap((b) => [b.sale_price_84_won, b.trade_low_won, b.trade_median_won]),
      )}
      badges={sampleBadges(data).map((text) => (
        <Badge key={text} tone="muted" data-testid="sample-badge">
          {text}
        </Badge>
      ))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={h} ariaLabel={title} />
    </ChartFrame>
  );
}
