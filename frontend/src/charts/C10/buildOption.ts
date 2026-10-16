import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { COMPONENT_KEYS, type ComponentKey, type SensitivityCell } from '@/lib/contract';
import { formatNumber, formatRank } from '@/lib/format';
import { componentLabel } from '../C06/buildOption';
import {
  axisStyle,
  baseOption,
  DEFAULT_PALETTE,
  legendStyle,
  seriesColor,
  tooltipStyle,
} from '../palette';
import type {
  BuildOptionContext,
  ChartLegendItem,
  ChartLegendSymbol,
  EChartsOption,
} from '../types';
import { escapeHtml } from '../util';
import { C10_TOP, type C10Data } from './types';

export function emptyReason(data: C10Data): string | null {
  const s = data.sensitivity;
  return s && s.cells.length > 0 ? null : t('chart.C10.empty');
}

/**
 * complex_id → 이름: 호출 측 names → 서버 complex_names(계약 .2) → 변형 순위의 name → "단지 {id}".
 * 화면이 이름을 만들지 않는다 — 서버·호출 측 값을 그대로 고른다.
 */
export function nameOf(data: C10Data, id: number | string): string {
  const key = String(id);
  const fromRanks = data.sensitivity?.cells
    .flatMap((c) => c.ranks)
    .find((r) => String(r.complex_id) === key)?.name;
  return (
    data.names?.[key] ??
    data.sensitivity?.complex_names?.[key] ??
    fromRanks ??
    t('chart.C10.complex', { id: key })
  );
}

const signOf = (delta: number) => (delta > 0 ? '+' : '−');
const ppOf = (delta: number) => formatNumber(Math.abs(delta) * 100, 0);

/**
 * 변형 이름(쉬운 말): "p10+0.10" → "+10% 오를 가능성 비중 +10%p". 내부 키(p10·rerank…)는 화면에 내지 않는다(R9-UI 피드백).
 * 비중 변화 0.10 → 10%p 는 표기 바꾸기(가중치 입력값 — 사실이 아님).
 */
export function variantLabel(
  cell: Pick<SensitivityCell, 'variant' | 'component' | 'delta'>,
): string {
  return t('chart.C10.variantLabel', {
    component: componentLabel(cell.component as ComponentKey),
    sign: signOf(cell.delta),
    pp: ppOf(cell.delta),
  });
}

/** 짧은 이름: "오를 가능성 +10%p"(표·툴팁은 variantLabel 전체) */
export function variantShortLabel(
  cell: Pick<SensitivityCell, 'variant' | 'component' | 'delta'>,
): string {
  return t('chart.C10.variantShort', {
    component: shortName(cell.component as ComponentKey),
    sign: signOf(cell.delta),
    pp: ppOf(cell.delta),
  });
}

/** 기준의 짧은 이름(축 둘째 줄): "오를 가능성" */
export const shortName = (k: ComponentKey) => t(`chart.C10.short.${k}`);

/** 줄이면 / 늘리면 */
export const directionLabel = (delta: number) =>
  delta < 0 ? t('chart.C10.down') : t('chart.C10.up');

/** 순위 변동 칸 문구: 없음 / 있음(진입·이탈 단지) */
export function changedText(row: Pick<C10VariantRow, 'changed' | 'entered' | 'exited'>): string {
  if (!row.changed) return t('chart.C10.changedNo');
  const moves = [
    row.entered.length > 0 ? t('chart.C10.entered', { names: row.entered.join(', ') }) : null,
    row.exited.length > 0 ? t('chart.C10.exited', { names: row.exited.join(', ') }) : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return moves ? t('chart.C10.changedWith', { moves }) : t('chart.C10.changedYes');
}

export interface C10VariantRow {
  variant: string;
  label: string;
  component: ComponentKey;
  delta: number;
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

/** 표·HTML 공용 변형 행(서버 순서) */
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
      delta: cell.delta,
      top5,
      changed: cell.changed,
      stable: !cell.changed,
      componentStable: s.stable_components.includes(cell.component),
      entered: cell.entered.map((id) => nameOf(data, id)),
      exited: cell.exited.map((id) => nameOf(data, id)),
    };
  });
}

/** 변형에 나오는 기준(성분) — 표시 순서는 COMPONENT_KEYS 고정 */
export function componentOrder(data: C10Data): ComponentKey[] {
  const present = new Set(data.sensitivity?.cells.map((c) => c.component) ?? []);
  return COMPONENT_KEYS.filter((k) => present.has(k));
}

/** 차트 x축 순서: 기준마다 (줄이면, 늘리면). 서버 값의 순서만 바꾼다 */
export function orderedCells(data: C10Data): SensitivityCell[] {
  const cells = data.sensitivity?.cells ?? [];
  return componentOrder(data).flatMap((k) =>
    cells.filter((c) => c.component === k).sort((a, b) => a.delta - b.delta),
  );
}

export interface C10CriterionRow {
  component: ComponentKey;
  /** 쉬운 이름 "+10% 오를 가능성" */
  name: string;
  /** 지금 비중 퍼센트 글자 "35" (기준 가중치 × 100 — 표기 바꾸기) */
  weightPct: string;
  /** 무엇을 보나요(ko) */
  why: string;
  /** 공식 용어(ko) */
  term: string;
  down: C10VariantRow | null;
  up: C10VariantRow | null;
}

/** 목업 표: 기준 6줄 × (줄이면 / 늘리면) */
export function criterionRows(data: C10Data): C10CriterionRow[] {
  const s = data.sensitivity;
  if (!s) return [];
  const rows = variantRows(data);
  return componentOrder(data).map((k) => ({
    component: k,
    name: componentLabel(k),
    weightPct: formatNumber((s.base_weights[k] ?? 0) * 100, 0),
    why: t(`chart.C10.why.${k}`),
    term: t(`chart.C10.term.${k}`),
    down: rows.find((r) => r.component === k && r.delta < 0) ?? null,
    up: rows.find((r) => r.component === k && r.delta > 0) ?? null,
  }));
}

/** 결과 줄 "순위 변동(상위 5곳 바뀜): 있음 n개 · 없음 n개" — 서버 changed 를 세기만 한다(D25-3) */
export function changeCounts(data: C10Data): { changed: number; unchanged: number } {
  const cells = data.sensitivity?.cells ?? [];
  const changed = cells.filter((c) => c.changed).length;
  return { changed, unchanged: cells.length - changed };
}

const LINE_SYMBOLS = ['circle', 'rect', 'triangle', 'diamond', 'pin', 'roundRect'];
const LEGEND_SYMBOL: Record<string, ChartLegendSymbol> = {
  circle: 'circle',
  rect: 'rect',
  triangle: 'triangle',
  diamond: 'diamond',
  pin: 'pin',
  roundRect: 'square',
};

function maxRankOf(data: C10Data): number {
  const ranks = (data.sensitivity?.cells ?? []).flatMap((c) => c.ranks.map((r) => r.rank ?? 0));
  return Math.max(C10_TOP, ...ranks);
}

/**
 * 순위 선: x = 기준 6개 × (줄이면/늘리면) — 아래 줄에 '줄이면·늘리면', 그 아래 기준 이름.
 * y = 순위(위가 1위), 계열 = 기준 TOP 5 단지(서버 base_top5 순서·색 고정). 순위 없으면 끊김(null).
 * 6위 아래(상위 5곳 밖)는 주황 띠.
 */
export function buildOption(
  data: C10Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const s = data.sensitivity;
  const baseline = s?.base_top5 ?? [];
  const cells = orderedCells(data);
  const groups = componentOrder(data);
  const maxRank = maxRankOf(data);
  const band =
    maxRank > C10_TOP
      ? {
          silent: true,
          itemStyle: { color: palette.band },
          label: {
            show: true,
            position: 'insideTopRight' as const,
            formatter: t('chart.C10.outside'),
            color: palette.muted,
            fontSize: 10,
          },
          data: [
            [{ yAxis: C10_TOP + 0.5 }, { yAxis: maxRank }] as [
              { yAxis: number },
              { yAxis: number },
            ],
          ],
        }
      : null;
  return {
    ...baseOption(palette),
    grid: { left: 56, right: 16, top: 16, bottom: 56 },
    legend: { ...legendStyle(palette), data: baseline.map((id) => nameOf(data, id)) },
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(palette),
      formatter: (params: unknown) => {
        const list = params as { seriesName: string; value: unknown; dataIndex: number }[];
        const cell = cells[list[0]?.dataIndex ?? -1];
        const head = cell ? `<b>${escapeHtml(variantLabel(cell))}</b>` : '';
        const lines = list.map((p) =>
          typeof p.value === 'number'
            ? `${escapeHtml(p.seriesName)} ${formatRank(p.value)}${
                p.value > C10_TOP ? ` (${t('chart.C10.outside')})` : ''
              }`
            : `${escapeHtml(p.seriesName)} ${t('empty.unknown')}`,
        );
        return [head, ...lines].join('<br/>');
      },
    },
    xAxis: [
      {
        type: 'category',
        data: cells.map((c) => directionLabel(c.delta)),
        ...axis,
        axisTick: { ...axis.axisTick, alignWithLabel: true },
        axisLabel: { ...axis.axisLabel, interval: 0, fontSize: 11 },
      },
      {
        // 둘째 줄: 기준 이름(두 칸씩 묶음) — 묶음 사이 점선
        type: 'category',
        data: groups.map(shortName),
        position: 'bottom',
        offset: 20,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { interval: 0, color: palette.fg, fontSize: 12, fontWeight: 600 },
        splitLine: {
          show: true,
          interval: 0,
          lineStyle: { color: palette.border, type: 'dashed' },
        },
      },
    ],
    yAxis: {
      type: 'value',
      inverse: true,
      min: 1,
      max: maxRank,
      interval: 1,
      name: t('chart.axis.rank'),
      nameLocation: 'start',
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatRank(v) },
    },
    series: baseline.map((id, index) => ({
      type: 'line' as const,
      id: String(id),
      name: nameOf(data, id),
      xAxisIndex: 0,
      connectNulls: false,
      symbol: LINE_SYMBOLS[index % LINE_SYMBOLS.length],
      symbolSize: 10,
      lineStyle: { color: seriesColor(palette, index), width: 2, opacity: 0.4 },
      itemStyle: { color: seriesColor(palette, index) },
      data: cells.map((c) => c.ranks.find((r) => r.complex_id === id)?.rank ?? null),
      ...(index === 0 && band ? { markArea: band } : {}),
    })),
  };
}

/** 범례(순위 선 위): 기준 TOP 5 단지(색 + 모양) · 상위 5곳 밖 띠(있을 때) */
export function legendItems(
  data: C10Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  const s = data.sensitivity;
  if (!s || s.cells.length === 0) return [];
  const items: ChartLegendItem[] = s.base_top5.map((id, index) => ({
    name: nameOf(data, id),
    color: seriesColor(ctx.palette, index),
    symbol: LEGEND_SYMBOL[LINE_SYMBOLS[index % LINE_SYMBOLS.length]!] ?? 'circle',
  }));
  return maxRankOf(data) > C10_TOP
    ? [...items, { name: t('chart.C10.outsideBand'), color: ctx.palette.band, symbol: 'square' }]
    : items;
}

export function toTable(data: C10Data): DataTable {
  return {
    columns: [
      { key: 'variant', header: t('chart.col.variant') },
      { key: 'changed', header: t('chart.C10.changedCol') },
      { key: 'top5', header: t('chart.col.top5') },
      { key: 'moves', header: t('chart.col.flags') },
    ],
    rows: variantRows(data).map((row) => ({
      variant: row.label,
      changed: row.changed ? t('chart.C10.changedYes') : t('chart.C10.changedNo'),
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
