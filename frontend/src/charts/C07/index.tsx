import { MismatchBadge } from '@/components/MismatchBadge';
import { TieBadge } from '@/components/TieBadge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { buildOption, confidenceText, emptyReason, isTie, toTable } from './buildOption';
import type { C07Data } from './types';

export interface C07DecisionProps {
  data: C07Data;
  height?: number;
}

/** C7 판정기 확률 — decide prob + escape, confidence, TieBadge(conf<0.6), MismatchBadge (G4, G5) */
export function C07Decision({ data, height = 220 }: C07DecisionProps) {
  const palette = useChartPalette();
  const title = t('chart.C07.title');
  const mismatch = data.decision?.rows.some((r) => r.mismatch) ?? false;
  return (
    <ChartFrame
      title={title}
      subtitle={confidenceText(data) ?? undefined}
      badges={
        <>
          <TieBadge tie={isTie(data)} confidence={data.decision?.confidence} />
          <MismatchBadge mismatch={mismatch} />
        </>
      }
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
