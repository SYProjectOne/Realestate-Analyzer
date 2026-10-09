import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import type { C04Data } from './types';

export function emptyReason(data: C04Data): string | null {
  return data.supply.length > 0 ? null : t('chart.C04.empty');
}

/** 연도별 막대, 생활권 스택, 판정 단지 입주 연도에 markPoint. 라벨 "추정 집계". */
export function buildOption(
  data: C04Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const years = [...new Set(data.supply.map((s) => s.year))].sort((a, b) => a - b);
  const areas = [...new Set(data.supply.map((s) => s.living_area))];
  const yearLabels = years.map(String);

  const markPointData = data.markers
    .map((m) => {
      const year = m.move_in_ym.slice(0, 4);
      const total = data.supply
        .filter((s) => String(s.year) === year)
        .reduce((sum, s) => sum + (num(s.units) ?? 0), 0);
      return yearLabels.includes(year)
        ? { name: m.name, coord: [year, total], value: m.name }
        : null;
    })
    .filter((m): m is { name: string; coord: [string, number]; value: string } => m !== null);

  return {
    ...baseOption(palette),
    grid: { left: 56, right: 16, top: 24, bottom: 48 },
    legend: { bottom: 0, textStyle: { color: palette.fg } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (typeof v === 'number' ? formatCount(v, 'households') : ''),
    },
    xAxis: { type: 'category', data: yearLabels },
    yAxis: {
      type: 'value',
      name: t('chart.C04.label'),
      axisLabel: { formatter: (v: number) => formatCount(v) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: areas.map((area, index) => ({
      type: 'bar' as const,
      name: area ?? t('chart.C04.label'),
      stack: 'supply',
      itemStyle: { color: palette.categorical[index % palette.categorical.length] },
      data: years.map((year) => {
        const row = data.supply.find((s) => s.year === year && s.living_area === area);
        return row ? num(row.units) : null;
      }),
      ...(index === areas.length - 1 && markPointData.length > 0
        ? {
            markPoint: {
              symbol: 'pin',
              symbolSize: 36,
              label: { formatter: '{b}' },
              data: markPointData,
            },
          }
        : {}),
    })),
  };
}

export function toTable(data: C04Data): DataTable {
  return {
    columns: [
      { key: 'year', header: t('chart.col.year'), unit: 'text' },
      { key: 'living_area', header: t('chart.col.livingArea') },
      { key: 'units', header: t('chart.col.units'), unit: 'households' },
    ],
    rows: [...data.supply]
      .sort((a, b) => a.year - b.year)
      .map((s) => ({ year: String(s.year), living_area: s.living_area, units: s.units })),
  };
}
