import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { BenchmarkView } from '@/lib/contract';
import { formatCount, formatEok, formatPercent, formatWon } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, ChartLegendItem, EChartsOption } from '../types';
import { escapeHtml, livingAreaName, num, str } from '../util';
import { C03_MIN_SAMPLE, type C03Data } from './types';

export function emptyReason(data: C03Data): string | null {
  return data.benchmarks.length > 0 ? null : t('chart.C03.empty');
}

/**
 * 표본 < 3 배지 — 생활권별("계양구 표본 0, 추정"). 표본 = benchmark_flags.sample_n(자기 생활권 표본만 — 분양권·
 * 지역 전체 대체 행 제외, 계약 2026-10-09.6 N-M4), 플래그가 없으면 분양권·대체 행이 아닌 벤치마크 수.
 * 생활권이 하나뿐이면 이름 없이 "표본 2, 추정".
 */
export function sampleBadges(data: C03Data): string[] {
  const counts = new Map<string, number>();
  // 계약 .20 F6: 서버 생활권 이름
  const names = new Map<string, string>();
  for (const f of data.flags ?? [])
    if (f.living_area_name) names.set(f.living_area, f.living_area_name);
  for (const b of data.benchmarks) {
    if (b.living_area && b.living_area_name) names.set(b.living_area, b.living_area_name);
  }
  if (data.flags && data.flags.length > 0) {
    for (const f of data.flags) counts.set(f.living_area, f.sample_n);
  } else {
    for (const b of data.benchmarks) {
      const key = b.living_area ?? '';
      counts.set(key, (counts.get(key) ?? 0) + (b.is_presale || b.substitute ? 0 : 1));
    }
  }
  const single = counts.size <= 1;
  const out: string[] = [];
  for (const [area, n] of counts) {
    if (n >= C03_MIN_SAMPLE) continue;
    const name = names.get(area) ?? livingAreaName(area, data.livingAreas);
    out.push(
      single || !name
        ? t('badge.sampleEstimated', { n: formatCount(n) })
        : t('badge.sampleEstimatedArea', { area: name, n: formatCount(n) }),
    );
  }
  return out;
}

/** 지역 전체 대체 행(substitute, 라벨 추정)이 하나라도 있으면 "대체(지역 전체)" 배지 문구, 없으면 null */
export function substituteBadge(data: C03Data): string | null {
  return data.benchmarks.some((b) => b.substitute) ? t('badge.substituteRegion') : null;
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

/** 대체 행 표시 접미(" · 대체(지역 전체)") — 색이 아니라 텍스트로 구분(D7) */
const substituteSuffix = (b: BenchmarkView) =>
  b.substitute ? ` · ${t('badge.substituteRegion')}` : '';
const rowName = (b: BenchmarkView) =>
  `${b.sale_year ? `${b.name} (${b.sale_year})` : b.name}${substituteSuffix(b)}`;
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
      `<b>${escapeHtml(rowName(b))}${presale}</b>`,
      `${t('chart.C03.sale')} ${fmt(num(b.sale_price_84_won))}`,
      `${t('chart.C03.trade')} ${fmt(num(b.trade_low_won))} ~ ${fmt(num(b.trade_high_won))}`,
    ];
    const peak = num(b.peak_won);
    if (peak !== null)
      lines.push(`${t('chart.C03.peakShort')} ${fmt(peak)} ${escapeHtml(str(b.peak_ym))}`);
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
    grid: { left: 200, right: 32, top: 12, bottom: 40 },
    legend: legendStyle(palette),
    tooltip: { trigger: 'item', ...tooltipStyle(palette), formatter: byIndex },
    yAxis: {
      type: 'category',
      data: rows.map(rowName),
      inverse: true,
      ...axis,
      axisTick: { ...axis.axisTick, alignWithLabel: true },
      // 긴 단지명은 줄바꿈 — 잘라 숨기지 않는다(전체 이름은 툴팁·표에도)
      axisLabel: {
        ...axis.axisLabel,
        interval: 0,
        color: palette.fg,
        width: 188,
        overflow: 'break',
        lineHeight: 13,
      },
    },
    xAxis: {
      type: 'value',
      scale: true,
      name: t('chart.axis.price84'),
      nameLocation: 'end',
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
                style: { stroke: palette.strong, lineWidth: 4, lineCap: 'round' },
              },
              {
                type: 'circle',
                shape: { cx: median[0], cy: median[1], r: 5 },
                style: { fill: palette.strong, stroke: palette.bg, lineWidth: 2 },
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
          // 분양권·지역 전체 대체 행은 별도 마커 모양(색만으로 구분하지 않음)
          symbol: b.is_presale ? 'diamond' : b.substitute ? 'emptyCircle' : 'circle',
        })),
        tooltip: { formatter: (p: unknown) => tooltipFor((p as { dataIndex: number }).dataIndex) },
      },
      {
        type: 'scatter',
        id: 'peak',
        name: t('chart.C03.peak'),
        // 입주 뒤 가장 높았던 거래 — 아래를 가리키는 삼각형(목업 범례와 같은 모양)
        symbol: 'triangle',
        symbolRotate: 180,
        symbolSize: 9,
        itemStyle: { color: palette.muted },
        data: rows.map((b, i) => [num(b.peak_won), i]).filter((d) => d[0] !== null),
        tooltip: {
          formatter: (p: unknown) =>
            tooltipFor(((p as { value: number[] }).value[1] ?? 0) as number),
        },
      },
    ],
  };
}

/** 범례(차트 위, 목업 '그림 읽는 법'): 분양가 · 실거래 범위 · 중간 값 · 고점 · 분양권 · 대신 채운 줄(있을 때만) */
export function legendItems(
  data: C03Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  const { palette } = ctx;
  if (data.benchmarks.length === 0) return [];
  return [
    { name: t('chart.C03.sale'), color: palette.fg, symbol: 'circle' },
    { name: t('chart.C03.range'), color: palette.strong, symbol: 'range' },
    { name: t('chart.C03.median'), color: palette.strong, symbol: 'circle' },
    ...(data.benchmarks.some((b) => num(b.peak_won) !== null)
      ? [{ name: t('chart.C03.peak'), color: palette.muted, symbol: 'triangleDown' as const }]
      : []),
    ...(data.benchmarks.some((b) => b.is_presale)
      ? [{ name: t('chart.C03.presaleLegend'), color: palette.fg, symbol: 'diamond' as const }]
      : []),
    ...(data.benchmarks.some((b) => b.substitute)
      ? [{ name: t('chart.C03.substituteLegend'), color: palette.fg, symbol: 'ring' as const }]
      : []),
  ];
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
      name: `${b.is_presale ? `${b.name} · ${t('chart.C03.presale')}` : b.name}${substituteSuffix(b)}`,
      living_area: b.living_area_name ?? livingAreaName(b.living_area, data.livingAreas),
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
