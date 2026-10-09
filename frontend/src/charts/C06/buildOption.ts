import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import {
  COMPONENT_KEYS,
  type ComponentKey,
  type ComponentView,
  type ScoreRow,
  type Weights,
} from '@/lib/contract';
import { formatFactValue, formatNumber, formatScore, unitFromHint } from '@/lib/format';
import {
  axisStyle,
  baseOption,
  DEFAULT_PALETTE,
  hatchDecal,
  legendStyle,
  tooltipStyle,
} from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml, num } from '../util';
import type { C06Data } from './types';

export const componentLabel = (c: ComponentKey) => t(`chart.C06.component.${c}`);

/** 성분 최댓값(0~10) — 미판정 빗금 막대 길이 = w × 10 (판정되면 낼 수 있는 최대 기여) */
const SCORE_MAX = 10;

export function emptyReason(data: C06Data): string | null {
  return data.rows.length > 0 ? null : t('chart.C06.empty');
}

/** 그릴 성분 키: data.keys → 없으면 가중치가 있거나 행에 성분이 있는 키(표시 순서 고정) */
export function componentKeys(data: Pick<C06Data, 'rows' | 'weights' | 'keys'>): ComponentKey[] {
  if (data.keys && data.keys.length > 0) return data.keys;
  return COMPONENT_KEYS.filter(
    (k) =>
      (data.weights[k] !== undefined && data.weights[k] !== null) ||
      data.rows.some((row) => row.components[k] !== undefined),
  );
}

/** 종합 점수 내림차순(같으면 이름) */
export function sortedRows(rows: ScoreRow[]): ScoreRow[] {
  return [...rows].sort(
    (a, b) =>
      (num(b.total) ?? -Infinity) - (num(a.total) ?? -Infinity) || a.name.localeCompare(b.name),
  );
}

function viewOf(row: ScoreRow, key: ComponentKey): ComponentView | undefined {
  return row.components[key];
}

/** 성분 하나의 가중 기여 = 서버 contribution(w×s). 없으면 weight × score. 미판정이면 null */
export function contribution(view: ComponentView | undefined): number | null {
  if (!view) return null;
  if (view.contribution !== null && view.contribution !== undefined) return view.contribution;
  const s = num(view.score);
  return s === null ? null : view.weight * s;
}

/** 행의 성분별 가중 기여. 프론트는 계산이 아니라 분해 표시만(ADR-11) — 합 = 종합 점수 ±0.01 */
export function contributions(
  row: ScoreRow,
  keys: readonly ComponentKey[] = COMPONENT_KEYS,
): Partial<Record<ComponentKey, number | null>> {
  const out: Partial<Record<ComponentKey, number | null>> = {};
  for (const k of keys) {
    const view = viewOf(row, k);
    if (view) out[k] = contribution(view);
  }
  return out;
}

/** 제목 아래 "가중치 +10% 확률 0.35 · 판정기 순위 0.20 · …" */
export function weightsSubtitle(weights: Weights, keys?: readonly ComponentKey[]): string {
  const list =
    keys ?? COMPONENT_KEYS.filter((k) => weights[k] !== undefined && weights[k] !== null);
  return t('chart.C06.weights', {
    weights: list
      .map((c) => `${componentLabel(c)} ${formatNumber(weights[c] ?? 0, 2)}`)
      .join(' · '),
  });
}

function tooltipText(row: ScoreRow, key: ComponentKey, weights: Weights): string {
  const view = viewOf(row, key);
  const head = `${escapeHtml(row.name)} · ${escapeHtml(componentLabel(key))}`;
  if (!view) return `${head}<br/>${t('badge.unjudged')}`;
  const score = num(view.score);
  const lines = [head];
  if (score === null) {
    const max = (view.weight ?? weights[key] ?? 0) * SCORE_MAX;
    lines.push(t('chart.C06.unjudgedTip', { max: formatScore(max) }));
  } else {
    lines.push(`${formatScore(score)} × ${formatNumber(view.weight, 2)}`);
    const c = contribution(view);
    if (c !== null) lines.push(t('chart.C06.contribution', { value: formatScore(c) }));
  }
  if (view.raw && view.raw.v !== null) {
    const raw = formatFactValue(view.raw, unitFromHint(view.raw.unit, view.raw.v));
    if (raw) lines.push(t('chart.C06.raw', { raw: escapeHtml(raw) }));
  }
  if (view.formula_text) lines.push(escapeHtml(view.formula_text));
  return lines.join('<br/>');
}

export function buildOption(
  data: C06Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const rows = sortedRows(data.rows);
  const keys = componentKeys(data);
  const horizontal = data.orientation === 'horizontal';
  const names = rows.map((r) => {
    const total = num(r.total);
    return total === null ? r.name : `${r.name}\n${formatScore(total)}`;
  });
  const categoryAxis = {
    type: 'category' as const,
    data: names,
    ...axis,
    axisLabel: horizontal
      ? { ...axis.axisLabel, fontSize: 10, width: 120, overflow: 'truncate' as const }
      : { ...axis.axisLabel, fontSize: 10, interval: 0, width: 88, overflow: 'break' as const },
    ...(horizontal ? { inverse: true } : {}),
  };
  const valueAxis = {
    type: 'value' as const,
    min: 0,
    ...axis,
    axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatScore(v, 1) },
  };
  return {
    ...baseOption(palette),
    grid: horizontal
      ? { left: 132, right: 24, top: 16, bottom: 56 }
      : { left: 40, right: 16, top: 16, bottom: 88 },
    legend: legendStyle(palette),
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const { dataIndex, seriesIndex } = p as { dataIndex: number; seriesIndex: number };
        const row = rows[dataIndex];
        const key = keys[seriesIndex];
        return row && key ? tooltipText(row, key, data.weights) : '';
      },
    },
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? categoryAxis : valueAxis,
    series: keys.map((key, index) => ({
      type: 'bar' as const,
      id: key,
      name: componentLabel(key),
      stack: 'score',
      barMaxWidth: 40,
      itemStyle: { color: palette.categorical[index % palette.categorical.length] },
      emphasis: { focus: 'series' as const },
      data: rows.map((row) => {
        const view = viewOf(row, key);
        const value = contribution(view);
        if (value !== null) return value;
        // null 성분 → 회색 빗금 + "미판정". 길이 = 판정되면 낼 수 있는 최대 기여(w × 10)
        const weight = view?.weight ?? data.weights[key] ?? 0;
        return {
          value: weight * SCORE_MAX,
          itemStyle: { color: palette.grayed, opacity: 0.6, decal: hatchDecal(palette) },
          label: {
            show: true,
            formatter: t('badge.unjudged'),
            color: palette.fg,
            fontSize: 10,
          },
        };
      }),
    })),
  };
}

export function toTable(data: C06Data): DataTable {
  const keys = componentKeys(data);
  return {
    columns: [
      { key: 'rank', header: t('chart.col.rank'), unit: 'rank' },
      { key: 'name', header: t('chart.col.name') },
      { key: 'total', header: t('chart.col.total'), unit: 'score' },
      ...keys.map((c) => ({ key: c, header: componentLabel(c), unit: 'score' as const })),
    ],
    rows: sortedRows(data.rows).map((row) => ({
      rank: row.rank,
      name: row.name,
      total: row.total,
      ...Object.fromEntries(keys.map((c) => [c, viewOf(row, c)?.score ?? null])),
    })),
  };
}
