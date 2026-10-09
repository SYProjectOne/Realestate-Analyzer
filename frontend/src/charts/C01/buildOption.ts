import type { DataTable } from '@/components/DataTableToggle';
import { t, tDynamic } from '@/i18n';
import type { LadderRow } from '@/lib/contract';
import { formatHalfYear, formatPercent, formatProb } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml, num } from '../util';
import {
  C01_BARS,
  C01_HORIZONS,
  C01_OVERLAY_SYMBOLS,
  C01_THRESHOLDS,
  type C01Data,
  type LadderBar,
} from './types';

const barLabel = (bar: LadderBar) => t(`chart.C01.bar.${bar}`);
const verdictText = (verdict: string | null | undefined) =>
  verdict ? tDynamic(`chart.C01.verdict.${verdict}`, verdict) : null;

/** 판정 봉투가 ok가 아니면(review·escaped·blocked·error) 미해결 — 회색 + "미해결" */
export function isUnresolved(row: LadderRow): boolean {
  return row.status !== 'ok';
}

function currentRow(data: C01Data): LadderRow | undefined {
  return data.ladder.find((r) => r.horizon === data.horizon);
}

export function emptyReason(data: C01Data): string | null {
  if (data.overlay && data.overlay.length > 0) return null;
  return currentRow(data) ? null : t('chart.C01.empty');
}

/** 부제: "목표 시점 2029 상반기" (서버 target_label 우선, 없으면 target_ym → 연도 반기) */
export function subtitle(data: C01Data): string | null {
  const row =
    currentRow(data) ??
    data.overlay?.flatMap((o) => o.ladder).find((r) => r.horizon === data.horizon);
  if (!row) return null;
  return t('chart.C01.subtitle', { target: row.target_label ?? formatHalfYear(row.target_ym) });
}

/** 해당 horizon이 미해결이면 배지 문구 "미해결" */
export function unresolvedBadge(data: C01Data): string | null {
  const row = currentRow(data);
  return row && isUnresolved(row) ? t('badge.unresolved') : null;
}

function annualizedOf(row: LadderRow, bar: LadderBar): number | null {
  if (bar === 'p_flat') return null;
  const v = row.annualized[bar];
  return v === null || v === undefined ? null : v;
}

function tooltipLine(row: LadderRow | undefined, bar: LadderBar, prefix = ''): string {
  if (!row) return '';
  const p = num(row[bar]);
  const parts = [
    `${prefix}${escapeHtml(barLabel(bar))}`,
    isUnresolved(row) ? t('badge.unresolved') : p === null ? t('empty.unknown') : formatProb(p),
    verdictText(row.verdicts[bar]),
  ].filter(Boolean);
  const ann = annualizedOf(row, bar);
  const annText =
    ann === null ? '' : `<br/>${t('chart.C01.annualized', { pct: formatPercent(ann * 100) })}`;
  return `${parts.join(' · ')}${annText}`;
}

export function buildOption(
  data: C01Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const categories = C01_BARS.map(barLabel);
  const markLine = {
    symbol: 'none',
    silent: true,
    lineStyle: { type: 'dashed' as const, color: palette.muted },
    label: { color: palette.muted, position: 'end' as const },
    data: [
      { xAxis: C01_THRESHOLDS.unlikely, label: { formatter: t('chart.C01.threshold.unlikely') } },
      { xAxis: C01_THRESHOLDS.likely, label: { formatter: t('chart.C01.threshold.likely') } },
    ],
  };
  const common = {
    ...baseOption(palette),
    grid: { left: 72, right: 96, top: 24, bottom: 28 },
    xAxis: {
      type: 'value' as const,
      min: 0,
      max: 1,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatProb(v) },
    },
    yAxis: { type: 'category' as const, data: categories, inverse: true, ...axis },
  };

  if (data.overlay && data.overlay.length > 0) {
    const overlay = data.overlay;
    return {
      ...common,
      grid: { ...common.grid, bottom: 48 },
      legend: legendStyle(palette),
      tooltip: {
        trigger: 'item',
        ...tooltipStyle(palette),
        formatter: (p: unknown) => {
          const { seriesIndex, dataIndex } = p as { seriesIndex: number; dataIndex: number };
          const series = overlay[seriesIndex];
          const bar = C01_BARS[dataIndex];
          if (!series || !bar) return '';
          const row = series.ladder.find((r) => r.horizon === data.horizon);
          return `${escapeHtml(series.name)}<br/>${tooltipLine(row, bar)}`;
        },
      },
      series: overlay.map((series, index) => {
        const row = series.ladder.find((r) => r.horizon === data.horizon);
        const gray = !row || isUnresolved(row);
        return {
          type: 'scatter' as const,
          id: String(series.complex_id),
          name: series.name,
          symbol: C01_OVERLAY_SYMBOLS[index % C01_OVERLAY_SYMBOLS.length],
          symbolSize: 11,
          itemStyle: {
            color: gray ? palette.grayed : palette.categorical[index % palette.categorical.length],
          },
          data: C01_BARS.map((bar, i) => [row && !gray ? num(row[bar]) : null, categories[i]]),
          ...(index === 0 ? { markLine } : {}),
        };
      }),
    };
  }

  const row = currentRow(data);
  const gray = row ? isUnresolved(row) : true;
  return {
    ...common,
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const bar = C01_BARS[(p as { dataIndex: number }).dataIndex];
        return bar ? tooltipLine(row, bar) : '';
      },
    },
    series: [
      {
        type: 'bar',
        id: 'ladder',
        name: t('chart.C01.title'),
        barMaxWidth: 18,
        showBackground: gray,
        backgroundStyle: { color: palette.border, opacity: 0.35 },
        label: {
          show: true,
          position: 'right',
          color: palette.fg,
          formatter: (params: { dataIndex: number; value: unknown }) => {
            const bar = C01_BARS[params.dataIndex];
            if (!row || !bar) return '';
            if (gray) return t('badge.unresolved');
            const v =
              typeof params.value === 'number' ? formatProb(params.value) : t('empty.unknown');
            const verdict = verdictText(row.verdicts[bar]);
            return verdict ? `${v} · ${verdict}` : v;
          },
        },
        // review 등 미해결: 값이 없어도 회색 바탕 막대 + "미해결" 라벨
        data: C01_BARS.map((bar) => ({
          value: row ? (num(row[bar]) ?? (gray ? 0 : null)) : null,
          itemStyle: { color: gray ? palette.grayed : palette.strong },
        })),
        markLine,
      },
    ],
  };
}

export function toTable(data: C01Data): DataTable {
  const rows =
    data.overlay && data.overlay.length > 0
      ? data.overlay.flatMap((o) =>
          o.ladder.filter((r) => r.horizon === data.horizon).map((r) => ({ name: o.name, row: r })),
        )
      : [...data.ladder]
          .sort((a, b) => C01_HORIZONS.indexOf(a.horizon) - C01_HORIZONS.indexOf(b.horizon))
          .map((r) => ({ name: null, row: r }));
  return {
    columns: [
      ...(data.overlay && data.overlay.length > 0
        ? [{ key: 'name', header: t('chart.col.name') }]
        : []),
      { key: 'horizon', header: t('chart.col.horizon') },
      { key: 'target_ym', header: t('chart.col.target'), unit: 'ym' as const },
      ...C01_BARS.map((bar) => ({ key: bar, header: barLabel(bar), unit: 'prob' as const })),
      { key: 'status', header: t('chart.col.status') },
    ],
    rows: rows.map(({ name, row }) => ({
      name,
      horizon: t(`chart.C01.horizon.${row.horizon}`),
      target_ym: row.target_label ?? row.target_ym,
      p5: row.p5,
      p10: row.p10,
      p20: row.p20,
      p_flat: row.p_flat,
      status: tDynamic(`chart.status.${row.status}`, row.status),
    })),
  };
}
