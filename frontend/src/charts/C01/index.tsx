import { Badge } from '@/components/Badge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import { buildOption, emptyReason, subtitle, toTable, unresolvedBadge } from './buildOption';
import type { C01Data } from './types';

export interface C01LadderProps {
  data: C01Data;
  height?: number;
}

/** C1 상승 확률 사다리 (G3, G4 overlay). horizon 탭은 호출 측이 data.horizon으로 넘긴다. */
export function C01Ladder({ data, height = 220 }: C01LadderProps) {
  const palette = useChartPalette();
  const title = t('chart.C01.title');
  const rows =
    data.overlay && data.overlay.length > 0
      ? data.overlay.flatMap((o) => o.ladder.filter((r) => r.horizon === data.horizon))
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
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
