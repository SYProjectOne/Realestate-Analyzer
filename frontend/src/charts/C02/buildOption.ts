import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatEok, formatWon } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, ChartLegendItem, EChartsOption } from '../types';
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
  /** 단지 이름(현재 행은 "이 단지 (현재 가격)") */
  name: string;
  /** 신축(연도)/대체(연도) 배지 — 현재 행은 null */
  badge: string | null;
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
      badge: null,
      low: num(gap.price_low),
      mid: num(gap.price_mid),
      high: num(gap.price_high),
      adjusted: null,
      current: true,
    },
    ...gap.comps.map((c) => ({
      name: c.name,
      badge: compBadge(c.substitute, c.completed_year),
      low: num(c.low),
      mid: num(c.median),
      high: num(c.high),
      adjusted: num(c.adjusted_median),
      current: false,
    })),
  ];
}

/** 축 이름: "비교 단지 이름 · 신축(2024)" — 이름과 배지를 두 줄로 */
const axisName = (w: Whisker) => (w.badge ? `${w.name}\n${w.badge}` : w.name);

/** 행 수(현재 + 비교 단지) — 높이 계산용 */
export function rowCount(data: C02Data): number {
  return whiskers(data).length;
}

const fmt = (n: number | null) => (n === null ? t('empty.unknown') : formatWon(n));

/**
 * 가로 띠(목업 Compare·DetailTabs): 줄마다 실거래 범위(하단~상단) 막대 + 중앙값 눈금.
 * 0번 줄 = 이 단지 현재 가격 범위(강조색, 굵게), 나머지 = 비교 단지 실거래 범위(회색). 연식 보정 중앙값 = 점선 빈 점.
 * '주변 전체 중간값' 선은 서버에 없는 값이라 그리지 않는다(고침 CP-2).
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
    const head = w.badge ? `${escapeHtml(w.name)} · ${escapeHtml(w.badge)}` : escapeHtml(w.name);
    const lines = [
      `<b>${head}</b>`,
      t('chart.C02.lowHigh', { low: fmt(w.low), high: fmt(w.high) }),
      `${w.current ? t('chart.C02.median') : t('chart.C02.unadjusted')} ${fmt(w.mid)}`,
    ];
    if (w.adjusted !== null) lines.push(`${t('chart.C02.adjusted')} ${fmt(w.adjusted)}`);
    return lines.join('<br/>');
  };
  const rowOf = (p: unknown) => {
    const { value } = p as { value?: unknown };
    return Array.isArray(value) ? Number(value[0]) : 0;
  };

  return {
    ...baseOption(palette),
    grid: { left: 200, right: 24, top: 12, bottom: 40 },
    legend: {
      ...legendStyle(palette),
      data: [t('chart.C02.range'), t('chart.C02.adjusted')],
    },
    tooltip: { trigger: 'item', ...tooltipStyle(palette) },
    yAxis: {
      type: 'category',
      data: items.map(axisName),
      inverse: true,
      ...axis,
      axisTick: { ...axis.axisTick, alignWithLabel: true },
      // 긴 단지명은 칸 폭에서 줄바꿈 — 잘라 숨기지 않는다
      axisLabel: {
        ...axis.axisLabel,
        interval: 0,
        color: palette.fg,
        width: 188,
        overflow: 'break',
        lineHeight: 14,
      },
    },
    xAxis: {
      type: 'value',
      scale: true,
      name: t('chart.axis.price'),
      nameLocation: 'end',
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatEok(v, 1) },
    },
    series: [
      {
        type: 'custom',
        id: 'range',
        name: t('chart.C02.range'),
        itemStyle: { color: palette.grayed },
        renderItem: (_params, api) => {
          const y = api.value(0) as number;
          const lowPt = api.coord([api.value(1), y]) as number[];
          const highPt = api.coord([api.value(2), y]) as number[];
          const midPt = api.coord([api.value(3), y]) as number[];
          const current = y === 0;
          const band = current ? 12 : 6;
          const color = current ? palette.strong : palette.grayed;
          const tick = current ? 20 : 14;
          return {
            type: 'group',
            children: [
              {
                type: 'rect',
                shape: {
                  x: lowPt[0] ?? 0,
                  y: (lowPt[1] ?? 0) - band / 2,
                  width: Math.max(2, (highPt[0] ?? 0) - (lowPt[0] ?? 0)),
                  height: band,
                  r: band / 2,
                },
                style: { fill: color, opacity: current ? 0.9 : 0.8 },
              },
              {
                type: 'rect',
                shape: {
                  x: (midPt[0] ?? 0) - (current ? 2 : 1),
                  y: (midPt[1] ?? 0) - tick / 2,
                  width: current ? 4 : 2,
                  height: tick,
                  r: 1,
                },
                style: { fill: palette.fg },
              },
            ],
          };
        },
        encode: { y: 0, x: [1, 2, 3] },
        data: items
          .map((w, i) => [i, w.low, w.high, w.mid ?? w.low ?? w.high])
          .filter((d) => d[1] !== null && d[2] !== null),
        tooltip: { formatter: (p: unknown) => tooltipFor(rowOf(p)) },
      },
      {
        type: 'scatter',
        id: 'adjusted',
        name: t('chart.C02.adjusted'),
        symbolSize: 13,
        z: 3,
        itemStyle: {
          color: palette.bg,
          borderColor: palette.fg,
          borderType: 'dashed',
          borderWidth: 1.5,
        },
        data: items.map((w, i) => [w.adjusted, i]).filter((d) => d[0] !== null),
        tooltip: {
          formatter: (p: unknown) => {
            const { value } = p as { value?: unknown };
            return tooltipFor(Array.isArray(value) ? Number(value[1]) : 0);
          },
        },
      },
    ],
  };
}

/** 범례(차트 위): 이 단지 가격 범위 · 비교 단지 실거래 범위 · 가운데값 눈금 · 연식 보정 가운데값(대체 단지가 있을 때만) */
export function legendItems(
  data: C02Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  const { palette } = ctx;
  const items = whiskers(data);
  if (items.length === 0) return [];
  return [
    { name: t('chart.C02.currentRange'), color: palette.strong, symbol: 'range' },
    { name: t('chart.C02.range'), color: palette.grayed, symbol: 'range' },
    { name: t('chart.C02.median'), color: palette.fg, symbol: 'tick' },
    ...(items.some((w) => w.adjusted !== null)
      ? [{ name: t('chart.C02.adjusted'), color: palette.fg, symbol: 'dashedRing' as const }]
      : []),
  ];
}

export function toTable(data: C02Data): DataTable {
  const gap = data.gap;
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      // 열 이름은 목업 DetailTabs '표로 보기 — 주변 시세 비교'의 쉬운 말
      { key: 'kind', header: t('chart.C02.col.kind') },
      { key: 'low', header: t('chart.C02.col.low'), unit: 'won' },
      { key: 'median', header: t('chart.C02.col.median'), unit: 'won' },
      { key: 'high', header: t('chart.C02.col.high'), unit: 'won' },
      { key: 'adjusted', header: t('chart.C02.col.adjusted'), unit: 'won' },
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
