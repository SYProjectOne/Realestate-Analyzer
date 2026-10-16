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
  subtitle,
  toTable,
  unresolvedBadge,
} from './buildOption';
import type { C01Data } from './types';

export interface C01LadderProps {
  data: C01Data;
  height?: number;
  /** 바닥줄 기준일(스냅샷 asof). 생략 가능 */
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C01.source` */
  source?: string;
}

/** C1 상승 가능성 사다리 (G3 가로 막대, G4 겹쳐 보기 = 막대 묶음). horizon 탭은 호출 측이 data.horizon으로 넘긴다. */
export function C01Ladder({ data, height, asof, source }: C01LadderProps) {
  const palette = useChartPalette();
  const title = t('chart.C01.title');
  const overlay = data.overlay && data.overlay.length > 0;
  const rows = overlay
    ? (data.overlay ?? []).flatMap((o) => o.ladder.filter((r) => r.horizon === data.horizon))
    : data.ladder.filter((r) => r.horizon === data.horizon);
  const unresolved = unresolvedBadge(data);
  return (
    <ChartFrame
      title={title}
      subtitle={subtitle(data) ?? undefined}
      labels={collectLabels(rows.flatMap((r) => [r.p5, r.p10, r.p20, r.p_flat]))}
      badges={
        unresolved ? (
          <Badge tone="muted" data-testid="unresolved-badge">
            {unresolved}
          </Badge>
        ) : null
      }
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C01.source')}
    >
      <EChart
        option={buildOption(data, { palette })}
        height={height ?? (overlay ? 280 : 240)}
        ariaLabel={title}
      />
    </ChartFrame>
  );
}
