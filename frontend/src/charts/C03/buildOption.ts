import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { BenchmarkView } from '@/lib/contract';
import { formatEok, formatPercent, formatWon } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml, livingAreaName, num, str } from '../util';
import { C03_MIN_SAMPLE, type C03Data } from './types';

export function emptyReason(data: C03Data): string | null {
  return data.benchmarks.length > 0 ? null : t('chart.C03.empty');
}

/**
 * 표본 < 3 배지 — 생활권별("계양구 표본 0, 추정"). 표본 = benchmark_flags.sample_n(분양권 제외),
 * 플래그가 없으면 분양권이 아닌 벤치마크 수. 생활권이 하나뿐이면 이름 없이 "표본 2, 추정".
 */
export function sampleBadges(data: C03Data): string[] {
  const counts = new Map<string, number>();
  if (data.flags && data.flags.length > 0) {
    for (const f of data.flags) counts.set(f.living_area, f.sample_n);
  } else {
    for (const b of data.benchmarks) {
      const key = b.living_area ?? '';
      counts.set(key, (counts.get(key) ?? 0) + (b.is_presale ? 0 : 1));
    }
  }
  const single = counts.size <= 1;
  const out: string[] = [];
  for (const [area, n] of counts) {
    if (n >= C03_MIN_SAMPLE) continue;
    const name = livingAreaName(area, data.livingAreas);
    out.push(
      single || !name
        ? t('badge.sampleEstimated', { n })
        : t('badge.sampleEstimatedArea', { area: name, n }),
    );
  }
  return out;
}

/** (호환) 첫 번째 표본 배지 또는 null */
export function sampleBadge(data: C03Data): string | null {
  return sampleBadges(data)[0] ?? null;
}

/** 분양가 → 실거래 중앙값 연율(%) — 서버 annualized_pct가 없을 때 툴팁용. 계산 불가면 null */
export function annualizedPct(
  sale: number | null,
  median: number | null,
  saleYear: number | null,
  asofYear: number,
): number | null {
  if (sale === null || median === null || saleYear === null || sale <= 0) return null;
  const years = asofYear - saleYear;
  if (years <= 0) return null;
  return (Math.pow(median / sale, 1 / years) - 1) * 100;
}

function annualizedOf(b: BenchmarkView, asofYear: number | null): number | null {
  const server = num(b.annualized_pct ?? null);
  if (server !== null) return server;
  return asofYear === null
    ? null
    : annualizedPct(num(b.sale_price_84_won), num(b.trade_median_won), b.sale_year, asofYear);
}

const rowName = (b: BenchmarkView) => (b.sale_year ? `${b.name} (${b.sale_year})` : b.name);
const fmt = (n: number | null) => (n === null ? t('empty.unknown') : formatWon(n));

export function buildOption(
  data: C03Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const rows = data.benchmarks;
  const tooltipFor = (index: number) => {
    const b = rows[index];
    if (!b) return '';
    const pct = annualizedOf(b, data.asofYear);
    const presale = b.is_presale ? ` · ${t('chart.C03.presale')}` : '';
    const lines = [
      `${escapeHtml(rowName(b))}${presale}`,
      `${t('chart.C03.sale')} ${fmt(num(b.sale_price_84_won))}`,
      `${t('chart.C03.trade')} ${fmt(num(b.trade_low_won))} ~ ${fmt(num(b.trade_high_won))}`,
    ];
    const peak = num(b.peak_won);
    if (peak !== null)
      lines.push(`${t('chart.C03.peak')} ${fmt(peak)} ${escapeHtml(str(b.peak_ym))}`);
    if (pct !== null) lines.push(t('chart.C03.annualized', { pct: formatPercent(pct) }));
    return lines.join('<br/>');
  };
  const byIndex = (p: unknown) => {
    const { value, dataIndex } = p as { value?: unknown; dataIndex: number };
    // custom 시리즈는 value[0]이 행 번호(필터로 dataIndex가 밀릴 수 있음)
    return Array.isArray(value) && typeof value[0] === 'number' && value.length > 2
      ? tooltipFor(value[0])
      : tooltipFor(dataIndex);
  };

  return {
    ...baseOption(palette),
    grid: { left: 168, right: 24, top: 16, bottom: 48 },
    legend: legendStyle(palette),
    tooltip: { trigger: 'item', ...tooltipStyle(palette), formatter: byIndex },
    yAxis: {
      type: 'category',
      data: rows.map(rowName),
      inverse: true,
      ...axis,
      axisLabel: { ...axis.axisLabel, fontSize: 10, width: 156, overflow: 'truncate' },
    },
    xAxis: {
      type: 'value',
      scale: true,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatEok(v, 1) },
    },
    series: [
      {
        // 분양가 → 실거래 중앙값 점선 + 실거래 범위(하단~상단) 위스커 + 중앙값 점
        type: 'custom',
        id: 'dumbbell',
        name: t('chart.C03.range'),
        itemStyle: { color: palette.strong },
        renderItem: (_params, api) => {
          const y = api.value(0) as number;
          const sale = api.coord([api.value(1), y]) as number[];
          const low = api.coord([api.value(2), y]) as number[];
          const median = api.coord([api.value(3), y]) as number[];
          const high = api.coord([api.value(4), y]) as number[];
          return {
            type: 'group',
            children: [
              {
                type: 'line',
                shape: { x1: sale[0], y1: sale[1], x2: median[0], y2: median[1] },
                style: { stroke: palette.muted, lineWidth: 1, lineDash: [4, 3] },
              },
              {
                type: 'line',
                shape: { x1: low[0], y1: low[1], x2: high[0], y2: high[1] },
                style: { stroke: palette.strong, lineWidth: 3 },
              },
              {
                type: 'circle',
                shape: { cx: median[0], cy: median[1], r: 4 },
                style: { fill: palette.strong },
              },
            ],
          };
        },
        encode: { x: [1, 2, 3, 4], y: 0 },
        data: rows
          .map((b, i) => [
            i,
            num(b.sale_price_84_won),
            num(b.trade_low_won),
            num(b.trade_median_won),
            num(b.trade_high_won),
          ])
          .filter((d) => d.slice(1).every((v) => v !== null)),
      },
      {
        type: 'scatter',
        id: 'sale',
        name: t('chart.C03.sale'),
        symbolSize: 9,
        itemStyle: { color: palette.fg },
        data: rows.map((b, i) => ({
          value: [num(b.sale_price_84_won), i],
          // 분양권은 별도 마커 모양(색만으로 구분하지 않음)
          symbol: b.is_presale ? 'diamond' : 'circle',
        })),
        tooltip: { formatter: (p: unknown) => tooltipFor((p as { dataIndex: number }).dataIndex) },
      },
      {
        type: 'scatter',
        id: 'peak',
        name: t('chart.C03.peak'),
        symbol: 'triangle',
        symbolSize: 9,
        itemStyle: { color: palette.grayed },
        data: rows.map((b, i) => [num(b.peak_won), i]).filter((d) => d[0] !== null),
        tooltip: {
          formatter: (p: unknown) =>
            tooltipFor(((p as { value: number[] }).value[1] ?? 0) as number),
        },
      },
    ],
  };
}

export function toTable(data: C03Data): DataTable {
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'living_area', header: t('chart.col.livingArea') },
      { key: 'sale_year', header: t('chart.col.saleYear'), unit: 'text' },
      { key: 'sale_price', header: t('chart.col.salePrice'), unit: 'won' },
      { key: 'low', header: t('chart.col.low'), unit: 'won' },
      { key: 'median', header: t('chart.col.median'), unit: 'won' },
      { key: 'high', header: t('chart.col.high'), unit: 'won' },
      { key: 'peak', header: t('chart.col.peak'), unit: 'won' },
      { key: 'annualized', header: t('chart.col.annualized'), unit: 'pct' },
      { key: 'window', header: t('chart.col.window') },
    ],
    rows: data.benchmarks.map((b) => ({
      name: b.is_presale ? `${b.name} · ${t('chart.C03.presale')}` : b.name,
      living_area: livingAreaName(b.living_area, data.livingAreas),
      sale_year: b.sale_year === null ? null : String(b.sale_year),
      sale_price: b.sale_price_84_won,
      low: b.trade_low_won,
      median: b.trade_median_won,
      high: b.trade_high_won,
      peak: b.peak_won,
      annualized: b.annualized_pct ?? null,
      window: b.trade_window,
    })),
  };
}
