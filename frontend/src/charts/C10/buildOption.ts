import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { ComponentKey, SensitivityCell } from '@/lib/contract';
import { formatRank, formatScore } from '@/lib/format';
import { componentLabel } from '../C06/buildOption';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml } from '../util';
import type { C10Data } from './types';

export function emptyReason(data: C10Data): string | null {
  const s = data.sensitivity;
  return s && s.cells.length > 0 ? null : t('chart.C10.empty');
}

/** complex_id → 이름(모르면 "단지 {id}") */
export function nameOf(data: C10Data, id: number | string): string {
  return data.names?.[String(id)] ?? t('chart.C10.complex', { id: String(id) });
}

/** 변형 이름: "p10+0.10" → "+10% 확률 +0.10" */
export function variantLabel(
  cell: Pick<SensitivityCell, 'variant' | 'component' | 'delta'>,
): string {
  const sign = cell.delta > 0 ? '+' : '−';
  return `${componentLabel(cell.component as ComponentKey)} ${sign}${formatScore(Math.abs(cell.delta), 2)}`;
}

export interface C10VariantRow {
  variant: string;
  label: string;
  component: ComponentKey;
  /** TOP 5(공동 포함) — 순위순 */
  top5: { complex_id: number; name: string; rank: number | null }[];
  changed: boolean;
  /** 이 변형에서 TOP 5 변동 없음 → 회색 */
  stable: boolean;
  /** 이 성분은 ± 둘 다 변동 없음(stable_components) */
  componentStable: boolean;
  entered: string[];
  exited: string[];
}

/** 표·HTML 공용 변형 행 */
export function variantRows(data: C10Data): C10VariantRow[] {
  const s = data.sensitivity;
  if (!s) return [];
  return s.cells.map((cell) => {
    const rankOf = (id: number) => cell.ranks.find((r) => r.complex_id === id)?.rank ?? null;
    const top5 = cell.top5
      .map((id) => ({ complex_id: id, name: nameOf(data, id), rank: rankOf(id) }))
      .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity));
    return {
      variant: cell.variant,
      label: variantLabel(cell),
      component: cell.component,
      top5,
      changed: cell.changed,
      stable: !cell.changed,
      componentStable: s.stable_components.includes(cell.component),
      entered: cell.entered.map((id) => nameOf(data, id)),
      exited: cell.exited.map((id) => nameOf(data, id)),
    };
  });
}

/** 작은 선: x = 변형 12개, y = 순위(위가 1위), 시리즈 = 기준 TOP 5 단지. 순위 없으면 끊김(null). */
export function buildOption(
  data: C10Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const s = data.sensitivity;
  const baseline = s?.base_top5 ?? [];
  const cells = s?.cells ?? [];
  const ranks = cells.flatMap((c) => c.ranks.map((r) => r.rank ?? 0));
  const maxRank = Math.max(5, ...ranks);
  return {
    ...baseOption(palette),
    grid: { left: 44, right: 16, top: 12, bottom: 88 },
    legend: legendStyle(palette),
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(palette),
      formatter: (params: unknown) => {
        const list = params as { seriesName: string; value: unknown; dataIndex: number }[];
        const cell = cells[list[0]?.dataIndex ?? -1];
        const head = cell ? escapeHtml(variantLabel(cell)) : '';
        const lines = list.map((p) =>
          typeof p.value === 'number'
            ? `${escapeHtml(p.seriesName)} ${formatRank(p.value)}`
            : `${escapeHtml(p.seriesName)} ${t('empty.unknown')}`,
        );
        return [head, ...lines].join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      data: cells.map((c) => c.variant),
      ...axis,
      axisLabel: { ...axis.axisLabel, rotate: 40, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      inverse: true,
      min: 1,
      max: maxRank,
      interval: 1,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatRank(v) },
    },
    series: baseline.map((id, index) => ({
      type: 'line' as const,
      id: String(id),
      name: nameOf(data, id),
      connectNulls: false,
      symbol: ['circle', 'rect', 'triangle', 'diamond', 'pin', 'roundRect'][index % 6],
      symbolSize: 7,
      itemStyle: { color: palette.categorical[index % palette.categorical.length] },
      data: cells.map((c) => c.ranks.find((r) => r.complex_id === id)?.rank ?? null),
    })),
  };
}

export function toTable(data: C10Data): DataTable {
  return {
    columns: [
      { key: 'variant', header: t('chart.col.variant') },
      { key: 'changed', header: t('chart.col.changed') },
      { key: 'top5', header: t('chart.col.top5') },
      { key: 'moves', header: t('chart.col.flags') },
    ],
    rows: variantRows(data).map((row) => ({
      variant: row.label,
      changed: row.changed ? t('chart.yes') : t('chart.no'),
      top5: row.top5
        .map((x) => (x.rank === null ? x.name : `${formatRank(x.rank)} ${x.name}`))
        .join(' · '),
      moves: [
        row.entered.length > 0 ? t('chart.C10.entered', { names: row.entered.join(', ') }) : null,
        row.exited.length > 0 ? t('chart.C10.exited', { names: row.exited.join(', ') }) : null,
      ]
        .filter(Boolean)
        .join(' · '),
    })),
  };
}
