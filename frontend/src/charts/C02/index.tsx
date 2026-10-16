import { Badge } from '@/components/Badge';
import { labelText } from '@/components/LabelBadge';
import { t } from '@/i18n';
import type { IsoDate } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, legendItems, rowCount, toTable } from './buildOption';
import type { C02Data } from './types';

export interface C02GapProps {
  data: C02Data;
  /** 최소 높이. 줄(비교 단지)이 많으면 줄 수만큼 늘어난다 — 이름이 겹쳐 사라지지 않게 */
  height?: number;
  /** G4에서 단지 이름을 제목으로 */
  title?: string;
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C02.source` */
  source?: string;
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

/** 줄 하나 높이(px) — 두 줄 이름(이름 + 신축/대체 배지)이 들어간다 */
const ROW_PX = 34;

/** C2 가격 갭 — 가로 띠(이 단지 가격 범위 vs 비교 단지 실거래 범위) (G3, G4 나란히) */
export function C02Gap({ data, height, title, asof, source }: C02GapProps) {
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
  const h = Math.max(height ?? 0, 64 + rowCount(data) * ROW_PX);
  return (
    <ChartFrame
      title={heading}
      subtitle={t('chart.C02.subtitle')}
      labels={labels}
      badges={adjustedBadges(data).map((text) => (
        <Badge key={text} tone="neutral" data-testid="adjusted-badge">
          {text}
        </Badge>
      ))}
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C02.source')}
    >
      <EChart option={buildOption(data, { palette })} height={h} ariaLabel={heading} />
    </ChartFrame>
  );
}
