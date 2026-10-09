import { Badge } from '@/components/Badge';
import { TieBadge } from '@/components/TieBadge';
import { UnstableBadge } from '@/components/UnstableBadge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels, num } from '../util';
import { buildOption, componentKeys, emptyReason, toTable, weightsSubtitle } from './buildOption';
import type { C06Data } from './types';

export interface C06ScoreBreakdownProps {
  data: C06Data;
  height?: number;
}

/** C6 종합 점수 분해 — 가중 기여 stacked bar (G1, G4). 제목 아래 가중치, 툴팁 = formula_text + 원값 */
export function C06ScoreBreakdown({ data, height }: C06ScoreBreakdownProps) {
  const palette = useChartPalette();
  const title = t('chart.C06.title');
  const keys = componentKeys(data);
  const unjudged = data.rows.some((row) =>
    keys.some((k) => {
      const view = row.components[k];
      return !view || num(view.score) === null;
    }),
  );
  const h =
    height ?? (data.orientation === 'horizontal' ? Math.max(180, 72 + data.rows.length * 36) : 320);
  return (
    <ChartFrame
      title={title}
      subtitle={weightsSubtitle(data.weights, keys)}
      labels={collectLabels(data.rows.map((r) => r.total))}
      badges={
        <>
          <UnstableBadge unstable={data.rows.some((r) => r.unstable)} />
          <TieBadge
            tie={data.rows.some((r) => r.tie_group !== null && r.tie_group !== undefined)}
          />
          {unjudged ? (
            <Badge tone="muted" data-testid="unjudged-badge">
              {t('badge.unjudged')}
            </Badge>
          ) : null}
        </>
      }
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={h} ariaLabel={title} />
    </ChartFrame>
  );
}
