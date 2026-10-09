import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatRank } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { c10Name, type C10Data } from './types';

export function emptyReason(data: C10Data): string | null {
  const s = data.sensitivity;
  return s && s.cells.length > 0 ? null : t('chart.C10.empty');
}

/** 작은 선: x = 변형(기준 + 12), y = 순위(위가 1위), 시리즈 = 기준 TOP 5 단지. TOP 5 밖이면 끊김(null). */
export function buildOption(
  data: C10Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const s = data.sensitivity;
  const baseline = s?.base_top5 ?? [];
  const cells = s?.cells ?? [];
  const variants = [t('chart.C10.baseline'), ...cells.map((c) => c.variant)];
  return {
    ...baseOption(palette),
    grid: { left: 40, right: 16, top: 16, bottom: 56 },
    legend: { bottom: 0, textStyle: { color: palette.fg } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: variants, axisLabel: { rotate: 30 } },
    yAxis: {
      type: 'value',
      inverse: true,
      min: 1,
      max: 5,
      interval: 1,
      axisLabel: { formatter: (v: number) => formatRank(v) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: baseline.map((id, index) => ({
      type: 'line' as const,
      name: c10Name(data, id),
      connectNulls: false,
      itemStyle: { color: palette.categorical[index % palette.categorical.length] },
      data: [
        index + 1,
        ...cells.map((c) => {
          const pos = c.top5.indexOf(id);
          return pos < 0 ? null : pos + 1;
        }),
      ],
    })),
  };
}

export function toTable(data: C10Data): DataTable {
  const cells = data.sensitivity?.cells ?? [];
  return {
    columns: [
      { key: 'variant', header: t('chart.col.variant') },
      { key: 'changed', header: t('chart.col.changed') },
      { key: 'top5', header: t('chart.col.top5') },
    ],
    rows: cells.map((c) => ({
      variant: c.variant,
      changed: c.changed ? t('chart.yes') : t('chart.no'),
      top5: c.top5.map((id, i) => `${formatRank(i + 1)} ${c10Name(data, id)}`).join(' · '),
    })),
  };
}
