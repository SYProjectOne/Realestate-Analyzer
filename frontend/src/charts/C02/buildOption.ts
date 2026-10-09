import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatEok, formatWon } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml, num } from '../util';
import type { C02Data } from './types';

/** 비교 단지 배지: "신축(2021)" / "대체(2017)" */
export function compBadge(substitute: boolean, year: number | null): string {
  const y = year === null ? '?' : String(year);
  return substitute ? t('badge.substitute', { year: y }) : t('badge.newBuild', { year: y });
}

/** 비교군 0 → "비교군 없음(사유)". 서버 사유가 이미 "비교군 없음(…)"이면 그대로 쓴다. */
export function emptyReason(data: C02Data): string | null {
  const { gap } = data;
  if (gap && gap.comps.length > 0) return null;
  const reason = gap?.empty_reason ?? null;
  if (reason && reason.startsWith(t('chart.C02.emptyPrefix'))) return reason;
  return t('chart.C02.empty', { reason: reason ?? t('empty.unknown') });
}

interface Whisker {
  name: string;
  low: number | null;
  mid: number | null;
  high: number | null;
  /** 연식 보정 중앙값(대체 비교 단지) */
  adjusted: number | null;
  current: boolean;
}

function whiskers(data: C02Data): Whisker[] {
  const gap = data.gap;
  if (!gap) return [];
  return [
    {
      name: t('chart.C02.current'),
      low: num(gap.price_low),
      mid: num(gap.price_mid),
      high: num(gap.price_high),
      adjusted: null,
      current: true,
    },
    ...gap.comps.map((c) => ({
      name: `${c.name}\n${compBadge(c.substitute, c.completed_year)}`,
      low: num(c.low),
      mid: num(c.median),
      high: num(c.high),
      adjusted: num(c.adjusted_median),
      current: false,
    })),
  ];
}

const fmt = (n: number | null) => (n === null ? t('empty.unknown') : formatWon(n));

/**
 * 점(중앙)+위스커(하단~상단). 떠다니는 막대는 쓰지 않는다(meta §2-7).
 * 0번 = 현재 구매가 범위(강조색), 나머지 = 비교 단지 실거래 범위. 연식 보정 중앙값 = 점선 테두리 빈 점.
 */
export function buildOption(
  data: C02Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const items = whiskers(data);
  const tooltipFor = (index: number) => {
    const w = items[index];
    if (!w) return '';
    const lines = [
      escapeHtml(w.name).replace('\n', ' · '),
      `${t('chart.col.low')} ${fmt(w.low)} ~ ${t('chart.col.high')} ${fmt(w.high)}`,
      `${w.current ? t('chart.col.median') : t('chart.C02.unadjusted')} ${fmt(w.mid)}`,
    ];
    if (w.adjusted !== null) lines.push(`${t('chart.C02.adjusted')} ${fmt(w.adjusted)}`);
    return lines.join('<br/>');
  };

  return {
    ...baseOption(palette),
    grid: { left: 64, right: 16, top: 16, bottom: 88 },
    legend: { ...legendStyle(palette), data: [t('chart.C02.range'), t('chart.C02.adjusted')] },
    tooltip: { trigger: 'item', ...tooltipStyle(palette) },
    xAxis: {
      type: 'category',
      data: items.map((w) => w.name),
      ...axis,
      // 긴 단지명은 칸 폭에서 줄바꿈(최대 3줄) — 이웃 라벨과 겹치지 않게
      axisLabel: {
        ...axis.axisLabel,
        interval: 0,
        fontSize: 10,
        width: 84,
        overflow: 'break',
        lineHeight: 12,
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatEok(v, 1) },
    },
    series: [
      {
        type: 'custom',
        id: 'range',
        name: t('chart.C02.range'),
        itemStyle: { color: palette.fg },
        renderItem: (_params, api) => {
          const x = api.value(0) as number;
          const lowPt = api.coord([x, api.value(1)]) as number[];
          const highPt = api.coord([x, api.value(2)]) as number[];
          const midPt = api.coord([x, api.value(3)]) as number[];
          const color = x === 0 ? palette.strong : palette.fg;
          const cap = 6;
          return {
            type: 'group',
            children: [
              {
                type: 'line',
                shape: { x1: lowPt[0], y1: lowPt[1], x2: highPt[0], y2: highPt[1] },
                style: { stroke: color, lineWidth: 2 },
              },
              {
                type: 'line',
                shape: {
                  x1: (lowPt[0] ?? 0) - cap,
                  y1: lowPt[1],
                  x2: (lowPt[0] ?? 0) + cap,
                  y2: lowPt[1],
                },
                style: { stroke: color, lineWidth: 2 },
              },
              {
                type: 'line',
                shape: {
                  x1: (highPt[0] ?? 0) - cap,
                  y1: highPt[1],
                  x2: (highPt[0] ?? 0) + cap,
                  y2: highPt[1],
                },
                style: { stroke: color, lineWidth: 2 },
              },
              {
                type: 'circle',
                shape: { cx: midPt[0], cy: midPt[1], r: 5 },
                style: { fill: color },
              },
            ],
          };
        },
        encode: { x: 0, y: [1, 2, 3] },
        data: items
          .map((w, i) => [i, w.low, w.high, w.mid ?? w.low ?? w.high])
          .filter((d) => d[1] !== null && d[2] !== null),
        tooltip: {
          formatter: (p: unknown) =>
            tooltipFor(((p as { value: (number | null)[] }).value[0] ?? 0) as number),
        },
      },
      {
        type: 'scatter',
        id: 'adjusted',
        name: t('chart.C02.adjusted'),
        symbolSize: 11,
        itemStyle: {
          color: 'transparent',
          borderColor: palette.fg,
          borderType: 'dashed',
          borderWidth: 1.5,
        },
        data: items.map((w, i) => [i, w.adjusted]).filter((d) => d[1] !== null),
        tooltip: {
          formatter: (p: unknown) =>
            tooltipFor(((p as { value: (number | null)[] }).value[0] ?? 0) as number),
        },
      },
    ],
  };
}

export function toTable(data: C02Data): DataTable {
  const gap = data.gap;
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'kind', header: t('chart.col.kind') },
      { key: 'low', header: t('chart.col.low'), unit: 'won' },
      { key: 'median', header: t('chart.col.median'), unit: 'won' },
      { key: 'high', header: t('chart.col.high'), unit: 'won' },
      { key: 'adjusted', header: t('chart.col.adjusted'), unit: 'won' },
      { key: 'window', header: t('chart.col.window') },
    ],
    rows: gap
      ? [
          {
            name: t('chart.C02.current'),
            kind: '',
            low: gap.price_low,
            median: gap.price_mid,
            high: gap.price_high,
            adjusted: '',
            window: '',
          },
          ...gap.comps.map((c) => ({
            name: c.name,
            kind: compBadge(c.substitute, c.completed_year),
            low: c.low,
            median: c.median,
            high: c.high,
            // 대체·보정이 아닌 비교 단지는 보정값 해당 없음(빈 칸) — 확인 불가와 구분
            adjusted: c.adjusted ? c.adjusted_median : '',
            window: c.trade_window ?? null,
          })),
        ]
      : [],
  };
}
