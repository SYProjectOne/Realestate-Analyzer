import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import { C05_DEFAULT_MONTHS, type C05Data } from './types';

export function emptyReason(data: C05Data): string | null {
  return data.unsold.length > 0 ? null : t('chart.C05.empty');
}

/** 최근 N개월(정렬). 결측 월은 null로 남겨 connectNulls=false로 끊는다. */
export function recentRows(data: C05Data): C05Data['unsold'] {
  const months = data.months ?? C05_DEFAULT_MONTHS;
  return [...data.unsold].sort((a, b) => a.ym.localeCompare(b.ym)).slice(-months);
}

export function buildOption(
  data: C05Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const rows = recentRows(data);
  return {
    ...baseOption(palette),
    grid: { left: 56, right: 16, top: 16, bottom: 48 },
    legend: { bottom: 0, textStyle: { color: palette.fg } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (typeof v === 'number' ? formatCount(v) : t('empty.unknown')),
    },
    xAxis: { type: 'category', data: rows.map((r) => r.ym) },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (v: number) => formatCount(v) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: [
      {
        type: 'line',
        name: t('chart.C05.total'),
        connectNulls: false,
        itemStyle: { color: palette.strong },
        data: rows.map((r) => num(r.total)),
      },
      {
        type: 'line',
        name: t('chart.C05.postCompletion'),
        connectNulls: false,
        lineStyle: { type: 'dashed' },
        itemStyle: { color: palette.fg },
        data: rows.map((r) => num(r.post_completion)),
      },
    ],
  };
}

export function toTable(data: C05Data): DataTable {
  return {
    columns: [
      { key: 'ym', header: t('chart.col.month'), unit: 'ym' },
      { key: 'total', header: t('chart.C05.total'), unit: 'count' },
      { key: 'post_completion', header: t('chart.C05.postCompletion'), unit: 'count' },
    ],
    rows: recentRows(data).map((r) => ({
      ym: r.ym,
      total: r.total,
      post_completion: r.post_completion,
    })),
  };
}
