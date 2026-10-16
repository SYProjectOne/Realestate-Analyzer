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
  seriesColor,
  tooltipStyle,
} from '../palette';
import type { BuildOptionContext, ChartLegendItem, EChartsOption } from '../types';
import { escapeHtml, num } from '../util';
import type { C06Data } from './types';

export const componentLabel = (c: ComponentKey) => t(`chart.C06.component.${c}`);

/**
 * 성분 색 자리(색은 성분을 따른다 — 보이는 성분 수가 바뀌어도 다시 칠하지 않는다).
 * liquidity(되팔기 쉬움)와 move_in(입주 시기)은 한 상황에 둘 중 하나만 있어(계약 Weights) 같은 자리를 쓴다.
 */
const COLOR_SLOT: Record<ComponentKey, number> = {
  p10: 0,
  rerank: 1,
  gap: 2,
  benchmark: 3,
  supply: 4,
  liquidity: 5,
  move_in: 5,
};
export const componentColor = (palette: BuildOptionContext['palette'], key: ComponentKey) =>
  seriesColor(palette, COLOR_SLOT[key]);

/** 비중 0.35 → "비중 35%" (가중치 입력값의 표기만 바꾼다 — 사실이 아님) */
export const weightText = (w: number | null | undefined) =>
  t('chart.C06.weightPct', { pct: formatNumber((w ?? 0) * 100, 0) });

/** 성분 최댓값(0~10) — 미판정 툴팁의 "최대 기여 w × 10" (막대 길이는 0) */
const SCORE_MAX = 10;

/** 범례 메모 "빗금 = 미판정(…)" — 미판정 성분이 있을 때만 차트 오른쪽 위에 둔다(m26) */
export const unjudgedNote = () => t('chart.C06.unjudgedNote');

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

/** 비중 한 줄 "비중: +10% 오를 가능성 35% · 비슷한 단지 사이 순위 20% · …" (범례 note와 같은 값) */
export function weightsSubtitle(weights: Weights, keys?: readonly ComponentKey[]): string {
  const list =
    keys ?? COMPONENT_KEYS.filter((k) => weights[k] !== undefined && weights[k] !== null);
  return t('chart.C06.weights', {
    weights: list
      .map((c) =>
        t('chart.C06.weightItem', {
          name: componentLabel(c),
          pct: formatNumber((weights[c] ?? 0) * 100, 0),
        }),
      )
      .join(' · '),
  });
}

function tooltipText(row: ScoreRow, key: ComponentKey, weights: Weights): string {
  const view = viewOf(row, key);
  const head = `<b>${escapeHtml(row.name)} · ${escapeHtml(componentLabel(key))}</b>`;
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
    axisTick: { ...axis.axisTick, alignWithLabel: true },
    // 단지명 + 종합 점수. 긴 이름은 줄바꿈 — 잘라 숨기지 않는다
    axisLabel: horizontal
      ? {
          ...axis.axisLabel,
          color: palette.fg,
          fontSize: 12,
          interval: 0,
          width: 168,
          overflow: 'break' as const,
          lineHeight: 14,
        }
      : {
          ...axis.axisLabel,
          color: palette.fg,
          fontSize: 11,
          interval: 0,
          width: 84,
          overflow: 'break' as const,
          lineHeight: 13,
        },
    ...(horizontal ? { inverse: true } : {}),
  };
  // 미판정(null) 성분이 하나라도 있나 — 범례 메모를 붙인다
  const anyUnjudged = rows.some((row) => keys.some((k) => contribution(viewOf(row, k)) === null));
  const valueAxis = {
    type: 'value' as const,
    min: 0,
    name: t('chart.axis.score'),
    nameLocation: 'end' as const,
    ...axis,
    axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatScore(v, 0) },
  };
  return {
    ...baseOption(palette),
    grid: horizontal
      ? { left: 184, right: 40, top: anyUnjudged ? 24 : 12, bottom: 32 }
      : { left: 40, right: 16, top: anyUnjudged ? 32 : 24, bottom: 56 },
    legend: { ...legendStyle(palette), data: keys.map(componentLabel) },
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
    // m26: 0길이 막대는 빗금이 안 보인다 → "빗금 = 미판정" 메모(오른쪽 위, 범례는 아래)
    ...(anyUnjudged
      ? {
          graphic: [
            {
              type: 'text' as const,
              id: 'unjudged-note',
              right: 8,
              top: 0,
              silent: true,
              style: { text: unjudgedNote(), fill: palette.muted, fontSize: 10 },
            },
          ],
        }
      : {}),
    series: keys.map((key) => ({
      type: 'bar' as const,
      id: key,
      name: componentLabel(key),
      stack: 'score',
      barMaxWidth: horizontal ? 28 : 40,
      // 칸 사이 바탕색 틈 — 이웃 기준과 붙어 보이지 않게
      itemStyle: { color: componentColor(palette, key), borderColor: palette.bg, borderWidth: 1 },
      emphasis: { focus: 'series' as const },
      // 한 행에 미판정 성분이 여럿이면 같은 자리에 "미판정" 라벨이 겹친다 → 하나만 남긴다
      labelLayout: { hideOverlap: true },
      data: rows.map((row) => {
        const view = viewOf(row, key);
        const value = contribution(view);
        if (value !== null) return value;
        // null 성분 → 스택 길이 0(종합 점수를 부풀리지 않는다, R3 minor 26) + 회색 빗금 + "미판정" 라벨.
        // 길이 0 막대는 면이 없어 빗금이 안 보이므로(m26) 점선 테두리로 막대 폭만큼의 선을 남긴다.
        // 판정되면 낼 수 있는 최대 기여(w × 10)는 툴팁에만 쓴다.
        return {
          value: 0,
          itemStyle: {
            color: palette.grayed,
            opacity: 0.6,
            decal: hatchDecal(palette),
            borderColor: palette.fg,
            borderWidth: 1,
            borderType: 'dashed' as const,
          },
          label: {
            show: true,
            position: horizontal ? ('right' as const) : ('top' as const),
            formatter: t('badge.unjudged'),
            color: palette.fg,
            fontSize: 10,
          },
        };
      }),
    })),
  };
}

/** 범례(차트 위): 기준 이름 + "비중 35%" — 목업 Compare 종합 점수 분해 */
export function legendItems(
  data: C06Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  if (data.rows.length === 0) return [];
  const legend: ChartLegendItem[] = componentKeys(data).map((key) => ({
    name: componentLabel(key),
    color: componentColor(ctx.palette, key),
    symbol: 'square',
    note: weightText(data.weights[key]),
  }));
  const unjudged = data.rows.some((row) =>
    componentKeys(data).some((k) => contribution(viewOf(row, k)) === null),
  );
  return unjudged
    ? [...legend, { name: t('badge.unjudged'), color: ctx.palette.grayed, symbol: 'hatch' }]
    : legend;
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
