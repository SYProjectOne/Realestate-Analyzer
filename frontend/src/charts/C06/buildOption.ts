import { SCORE_COMPONENTS, type ScoreComponent, type ScoreRow, type Weights } from '@/api/types';
import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatNumber, formatScore } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import type { C06Data } from './types';

const componentLabel = (c: ScoreComponent) => t(`chart.C06.component.${c}`);

/** 이 가중치가 쓰는 성분 6개(liquidity·move_in 중 하나) */
export function componentKeys(weights: Weights): ScoreComponent[] {
  return SCORE_COMPONENTS.filter((c) => weights[c] !== undefined);
}

export function emptyReason(data: C06Data): string | null {
  return data.rows.length > 0 ? null : t('chart.C06.empty');
}

/** 종합 점수 내림차순 */
export function sortedRows(rows: ScoreRow[]): ScoreRow[] {
  return [...rows].sort((a, b) => (num(b.total) ?? -Infinity) - (num(a.total) ?? -Infinity));
}

/** 가중 기여 = w × s. null component는 null(미판정). 프론트는 계산이 아니라 분해 표시만(ADR-11) */
export function contributions(
  row: ScoreRow,
  weights: Weights,
): Record<ScoreComponent, number | null> {
  const out = {} as Record<ScoreComponent, number | null>;
  for (const c of componentKeys(weights)) {
    const s = num(row.components[c]?.score);
    out[c] = s === null ? null : (weights[c] ?? 0) * s;
  }
  return out;
}

/** 제목 옆 "가중치 +10% 확률 0.30 · …" */
export function weightsSubtitle(weights: Weights): string {
  return t('chart.C06.weights', {
    weights: componentKeys(weights)
      .map((c) => `${componentLabel(c)} ${formatNumber(weights[c] ?? 0, 2)}`)
      .join(' · '),
  });
}

export function buildOption(
  data: C06Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const rows = sortedRows(data.rows);
  const keys = componentKeys(data.weights);
  const horizontal = data.orientation === 'horizontal';
  const names = rows.map((r) => r.name);
  const categoryAxis = {
    type: 'category' as const,
    data: names,
    ...(horizontal ? { inverse: true } : {}),
  };
  const valueAxis = {
    type: 'value' as const,
    min: 0,
    axisLabel: { formatter: (v: number) => formatScore(v, 1) },
    splitLine: { lineStyle: { color: palette.border } },
  };
  return {
    ...baseOption(palette),
    grid: { left: horizontal ? 120 : 48, right: 16, top: 16, bottom: 56 },
    legend: { bottom: 0, textStyle: { color: palette.fg } },
    tooltip: {
      trigger: 'item',
      formatter: (p: unknown) => {
        const { dataIndex, seriesIndex } = p as { dataIndex: number; seriesIndex: number };
        const row = rows[dataIndex];
        const c = keys[seriesIndex];
        if (!row || !c) return '';
        const raw = num(row.components[c]?.score);
        const formula = row.components[c]?.formula_text ?? '';
        const value = raw === null ? t('badge.unjudged') : formatScore(raw);
        return `${row.name} · ${componentLabel(c)}<br/>${value}${formula ? `<br/>${formula}` : ''}`;
      },
    },
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? categoryAxis : valueAxis,
    series: keys.map((c, index) => ({
      type: 'bar' as const,
      name: componentLabel(c),
      stack: 'score',
      itemStyle: { color: palette.categorical[index % palette.categorical.length] },
      data: rows.map((row) => {
        const value = contributions(row, data.weights)[c];
        // null component → 빗금 + "미판정"
        return value === null
          ? {
              value: 0,
              itemStyle: {
                color: palette.grayed,
                decal: {
                  symbol: 'rect',
                  dashArrayX: [1, 0],
                  dashArrayY: [2, 4],
                  rotation: Math.PI / 4,
                },
              },
              label: { show: true, formatter: t('badge.unjudged') },
            }
          : value;
      }),
    })),
  };
}

export function toTable(data: C06Data): DataTable {
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'total', header: t('chart.col.total'), unit: 'score' },
      ...componentKeys(data.weights).map((c) => ({
        key: c,
        header: componentLabel(c),
        unit: 'score' as const,
      })),
    ],
    rows: sortedRows(data.rows).map((row) => ({
      name: row.name,
      total: row.total,
      ...Object.fromEntries(
        componentKeys(data.weights).map((c) => [c, row.components[c]?.score ?? null]),
      ),
    })),
  };
}
