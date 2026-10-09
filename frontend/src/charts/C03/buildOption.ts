import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatEok, formatPercent } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import { C03_MIN_SAMPLE, type C03Data } from './types';

export function emptyReason(data: C03Data): string | null {
  return data.benchmarks.length > 0 ? null : t('chart.C03.empty');
}

/** 표본이 적으면 배지 문구, 아니면 null */
export function sampleBadge(data: C03Data): string | null {
  const n = data.benchmarks.length;
  return n > 0 && n < C03_MIN_SAMPLE ? t('badge.sampleEstimated', { n }) : null;
}

/** 분양가 → 실거래 중앙값 연율(%) — 툴팁용. 계산 불가면 null */
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

export function buildOption(
  data: C03Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const rows = data.benchmarks;
  const names = rows.map((b) => (b.sale_year ? `${b.name} (${b.sale_year})` : b.name));
  return {
    ...baseOption(palette),
    grid: { left: 140, right: 24, top: 16, bottom: 40 },
    legend: { bottom: 0, textStyle: { color: palette.fg } },
    tooltip: { trigger: 'item' },
    yAxis: { type: 'category', data: names, inverse: true },
    xAxis: {
      type: 'value',
      scale: true,
      axisLabel: { formatter: (v: number) => formatEok(v, 1) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    series: [
      {
        // 실거래 범위(하단~상단) + 분양가 → 중앙값 연결선
        type: 'custom',
        name: t('chart.C03.trade'),
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
        data: rows
          .map((b, i) => [
            i,
            num(b.sale_price_84),
            num(b.trade_low),
            num(b.trade_median),
            num(b.trade_high),
          ])
          .filter((d) => d.slice(1).every((v) => v !== null)),
      },
      {
        type: 'scatter',
        name: t('chart.C03.sale'),
        symbolSize: 9,
        itemStyle: { color: palette.fg },
        data: rows.map((b, i) => ({
          value: [num(b.sale_price_84), i],
          // 분양권은 별도 마커 모양
          symbol: b.is_presale ? 'diamond' : 'circle',
        })),
        tooltip: {
          formatter: (p: unknown) => {
            const index = (p as { dataIndex: number }).dataIndex;
            const b = rows[index];
            if (!b) return '';
            const pct =
              data.asofYear === null
                ? null
                : annualizedPct(
                    num(b.sale_price_84),
                    num(b.trade_median),
                    b.sale_year,
                    data.asofYear,
                  );
            const presale = b.is_presale ? ` · ${t('chart.C03.presale')}` : '';
            const head = `${b.name}${presale}`;
            return pct === null
              ? head
              : `${head}<br/>${t('chart.C03.annualized', { pct: formatPercent(pct) })}`;
          },
        },
      },
      {
        type: 'scatter',
        name: t('chart.C03.peak'),
        symbol: 'triangle',
        symbolSize: 9,
        itemStyle: { color: palette.grayed },
        data: rows.map((b, i) => [num(b.peak), i]).filter((d) => d[0] !== null),
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
    ],
    rows: data.benchmarks.map((b) => ({
      name: b.is_presale ? `${b.name} · ${t('chart.C03.presale')}` : b.name,
      living_area: b.living_area,
      sale_year: b.sale_year === null ? null : String(b.sale_year),
      sale_price: b.sale_price_84,
      low: b.trade_low,
      median: b.trade_median,
      high: b.trade_high,
      peak: b.peak,
    })),
  };
}
