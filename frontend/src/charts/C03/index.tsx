import { Badge } from '@/components/Badge';
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
  sampleBadges,
  substituteBadge,
  toTable,
} from './buildOption';
import type { C03Data } from './types';

export interface C03BenchmarkProps {
  data: C03Data;
  height?: number;
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C03.source` */
  source?: string;
}

/** C3 벤치마크 분양가 → 실거래 범위 dumbbell (G6). 고점 = 삼각형, 분양권 = 마름모, 지역 전체 대체 = 속 빈 원 + '대체(지역 전체)'. */
export function C03Benchmark({ data, height, asof, source }: C03BenchmarkProps) {
  const palette = useChartPalette();
  const title = t('chart.C03.title');
  // 줄마다 34px — 두 줄 이름도 겹치지 않게
  const h = height ?? Math.max(200, 52 + data.benchmarks.length * 34);
  return (
    <ChartFrame
      title={title}
      subtitle={t('chart.C03.subtitle')}
      labels={collectLabels(
        data.benchmarks.flatMap((b) => [b.sale_price_84_won, b.trade_low_won, b.trade_median_won]),
      )}
      badges={
        <>
          {sampleBadges(data).map((text) => (
            <Badge key={text} tone="muted" data-testid="sample-badge">
              {text}
            </Badge>
          ))}
          {substituteBadge(data) ? (
            <Badge tone="muted" data-testid="substitute-badge">
              {substituteBadge(data)}
            </Badge>
          ) : null}
        </>
      }
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C03.source')}
    >
      <EChart option={buildOption(data, { palette })} height={h} ariaLabel={title} />
    </ChartFrame>
  );
}
