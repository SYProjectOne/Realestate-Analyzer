import type { Catalyst, CatalystStage } from '@/api/types';
import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { C09_STAGES, type C09Data } from './types';

export const stageLabel = (s: CatalystStage) => t(`chart.C09.stage.${s}`);

export function emptyReason(data: C09Data): string | null {
  return data.catalysts.length > 0 ? null : t('chart.C09.empty');
}

/** 보드(HTML 그리드)용: 단계별 묶음 */
export function groupByStage(catalysts: Catalyst[]): Record<CatalystStage, Catalyst[]> {
  const out = Object.fromEntries(C09_STAGES.map((s) => [s, [] as Catalyst[]])) as Record<
    CatalystStage,
    Catalyst[]
  >;
  for (const c of catalysts) out[c.stage].push(c);
  return out;
}

/** 타임라인 option — **확정 호재만** expected_ym 시간축 scatter. 보드는 index.tsx의 HTML. */
export function buildOption(
  data: C09Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const confirmed = data.catalysts.filter((c) => c.stage === '확정' && c.expected_ym);
  return {
    ...baseOption(palette),
    grid: { left: 24, right: 24, top: 16, bottom: 32 },
    tooltip: { trigger: 'item' },
    xAxis: { type: 'time', splitLine: { lineStyle: { color: palette.border } } },
    yAxis: { type: 'value', show: false, min: 0, max: 1 },
    series: [
      {
        type: 'scatter',
        name: t('chart.C09.timeline'),
        symbolSize: 10,
        itemStyle: { color: palette.strong },
        label: { show: true, position: 'top', formatter: '{b}' },
        data: confirmed.map((c) => ({ name: c.name, value: [`${c.expected_ym}-01`, 0.5] })),
      },
    ],
  };
}

export function toTable(data: C09Data): DataTable {
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'kind', header: t('chart.col.kind') },
      { key: 'stage', header: t('chart.col.stage') },
      { key: 'expected', header: t('chart.col.expected'), unit: 'ym' },
      { key: 'location', header: t('chart.col.location') },
    ],
    rows: data.catalysts.map((c) => ({
      name: c.name,
      kind: c.kind,
      stage: stageLabel(c.stage),
      expected: c.expected_ym,
      location: c.location_confirmed ? t('chart.yes') : t('chart.C09.noLink'),
    })),
  };
}
