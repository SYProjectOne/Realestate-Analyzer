import { Badge } from '@/components/Badge';
import { labelText } from '@/components/LabelBadge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, toTable } from './buildOption';
import type { C02Data } from './types';

export interface C02GapProps {
  data: C02Data;
  height?: number;
  /** G4에서 단지 이름을 제목 옆에 */
  title?: string;
}

/** 대체·보정 비교군의 라벨 한정어 배지: "추정(대체·보정 c=0.015)" (T11) */
export function adjustedBadges(data: C02Data): string[] {
  const texts = (data.gap?.comps ?? [])
    .filter((c) => c.adjusted && c.adjusted_median)
    .map((c) => {
      const f = c.adjusted_median!;
      return labelText(f.label, f.reason, f.human);
    });
  return [...new Set(texts)];
}

/** C2 가격 갭 — 점+위스커 (G3, G4 나란히) */
export function C02Gap({ data, height = 300, title }: C02GapProps) {
  const palette = useChartPalette();
  const heading = title ?? t('chart.C02.title');
  const gap = data.gap;
  const labels = gap
    ? collectLabels([
        gap.price_low,
        gap.price_high,
        ...gap.comps.flatMap((c) => [c.low, c.median, c.high]),
      ])
    : [];
  return (
    <ChartFrame
      title={heading}
      labels={labels}
      badges={adjustedBadges(data).map((text) => (
        <Badge key={text} tone="neutral" data-testid="adjusted-badge">
          {text}
        </Badge>
      ))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={heading} />
    </ChartFrame>
  );
}
