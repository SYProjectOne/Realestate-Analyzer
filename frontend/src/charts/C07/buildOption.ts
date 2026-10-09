import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatNumber, formatProb } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { C07_TIE_CONFIDENCE, type C07Data } from './types';

/** escaped → 막대 대신 질문 텍스트. 판정 없음 → "판정 없음" */
export function emptyReason(data: C07Data): string | null {
  const d = data.decision;
  if (!d || d.rows.length === 0) return t('chart.C07.empty');
  if (d.status === 'escaped')
    return `${t('chart.C07.escape')}: ${d.escape?.question ?? t('empty.unknown')}`;
  return null;
}

export function isTie(data: C07Data): boolean {
  const c = data.decision?.confidence;
  return c !== null && c !== undefined && c < C07_TIE_CONFIDENCE;
}

export function confidenceText(data: C07Data): string | null {
  const c = data.decision?.confidence;
  return c === null || c === undefined
    ? null
    : t('chart.C07.confidence', { confidence: formatNumber(c, 2) });
}

export function buildOption(
  data: C07Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const d = data.decision;
  const rows = d?.rows ?? [];
  const names = [...rows.map((r) => r.name), ...(d?.escape ? [t('chart.C07.escape')] : [])];
  const values = [
    ...rows.map((r) => ({
      value: r.prob,
      itemStyle: {
        color: r.status === 'ok' ? (r.chosen ? palette.strong : palette.fg) : palette.grayed,
      },
    })),
    ...(d?.escape ? [{ value: d.escape.prob, itemStyle: { color: palette.grayed } }] : []),
  ];
  return {
    ...baseOption(palette),
    grid: { left: 120, right: 48, top: 16, bottom: 32 },
    tooltip: { trigger: 'item' },
    xAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: { formatter: (v: number) => formatProb(v) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    yAxis: { type: 'category', data: names, inverse: true },
    series: [
      {
        type: 'bar',
        barMaxWidth: 18,
        label: {
          show: true,
          position: 'right',
          formatter: (p: { value: unknown }) =>
            typeof p.value === 'number' ? formatProb(p.value) : t('empty.unknown'),
        },
        data: values,
      },
    ],
  };
}

export function toTable(data: C07Data): DataTable {
  const d = data.decision;
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'prob', header: t('chart.col.prob'), unit: 'prob' },
      { key: 'flags', header: t('chart.col.flags') },
    ],
    rows: (d?.rows ?? []).map((r) => ({
      name: r.name,
      prob: r.prob,
      flags:
        [
          r.chosen ? t('chart.chosen') : null,
          r.tie ? t('badge.tie') : null,
          r.mismatch ? t('badge.mismatch') : null,
        ]
          .filter(Boolean)
          .join(' · ') || null,
    })),
  };
}
