import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatEok, formatWon } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import type { C02Data } from './types';

/** 비교 단지 배지: "신축(2021)" / "대체(2017)" */
export function compBadge(substitute: boolean, year: number | null): string {
  const y = year === null ? '?' : String(year);
  return substitute ? t('badge.substitute', { year: y }) : t('badge.newBuild', { year: y });
}

export function emptyReason(data: C02Data): string | null {
  const { gap } = data;
  if (gap && gap.comps.length > 0) return null;
  return t('chart.C02.empty', { reason: gap?.empty_reason ?? t('empty.unknown') });
}

interface Whisker {
  name: string;
  low: number | null;
  mid: number | null;
  high: number | null;
}

/**
 * 점(중앙)+위스커(하단~상단). 떠다니는 막대는 쓰지 않는다(meta §2-7).
 * 0번 = 현재 구매가 범위(강조색), 나머지 = 비교 단지 실거래 범위. 보정 중앙값은 점선 테두리 점.
 */
export function buildOption(
  data: C02Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const gap = data.gap;
  const whiskers: Whisker[] = gap
    ? [
        {
          name: t('chart.C02.current'),
          low: num(gap.price_low),
          mid: num(gap.price_mid),
          high: num(gap.price_high),
        },
        ...gap.comps.map((c) => ({
          name: `${c.name} ${compBadge(c.substitute, c.completed_year)}`,
          low: num(c.low),
          mid: num(c.median),
          high: num(c.high),
        })),
      ]
    : [];

  return {
    ...baseOption(palette),
    grid: { left: 64, right: 16, top: 16, bottom: 56 },
    tooltip: { trigger: 'item' },
    xAxis: {
      type: 'category',
      data: whiskers.map((w) => w.name),
      axisLabel: { interval: 0, rotate: 20 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (v: number) => formatEok(v, 1) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: [
      {
        type: 'custom',
        name: t('chart.C02.comps'),
        renderItem: (_params, api) => {
          const x = api.value(0) as number;
          const lowPt = api.coord([x, api.value(1)]) as number[];
          const highPt = api.coord([x, api.value(2)]) as number[];
          const midPt = api.coord([x, api.value(3)]) as number[];
          const color = x === 0 ? palette.strong : palette.fg;
          return {
            type: 'group',
            children: [
              {
                type: 'line',
                shape: { x1: lowPt[0], y1: lowPt[1], x2: highPt[0], y2: highPt[1] },
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
        data: whiskers
          .map((w, i) => [i, w.low, w.high, w.mid ?? w.low ?? w.high])
          .filter((d) => d[1] !== null && d[2] !== null),
        tooltip: {
          formatter: (p: unknown) => {
            const value = (p as { value: (number | null)[] }).value;
            const w = whiskers[value[0] ?? 0];
            if (!w) return '';
            const fmt = (n: number | null) => (n === null ? t('empty.unknown') : formatWon(n));
            return `${w.name}<br/>${fmt(w.low)} ~ ${fmt(w.high)}`;
          },
        },
      },
      {
        type: 'scatter',
        name: t('chart.C02.adjusted'),
        symbolSize: 10,
        itemStyle: {
          color: 'transparent',
          borderColor: palette.fg,
          borderType: 'dashed',
          borderWidth: 1.5,
        },
        data: (gap?.comps ?? [])
          .map((c, i) => [i + 1, num(c.adjusted_median)])
          .filter((d) => d[1] !== null),
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
    ],
    rows: gap
      ? [
          {
            name: t('chart.C02.current'),
            kind: null,
            low: gap.price_low,
            median: gap.price_mid,
            high: gap.price_high,
            adjusted: null,
          },
          ...gap.comps.map((c) => ({
            name: c.name,
            kind: compBadge(c.substitute, c.completed_year),
            low: c.low,
            median: c.median,
            high: c.high,
            adjusted: c.adjusted_median,
          })),
        ]
      : [],
  };
}
