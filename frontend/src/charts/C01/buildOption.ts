import type { LadderRow } from '@/api/types';
import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatHalfYear, formatProb } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import { C01_BARS, C01_HORIZONS, C01_THRESHOLDS, type C01Data } from './types';

const barLabel = (bar: (typeof C01_BARS)[number]) => t(`chart.C01.bar.${bar}`);
const unresolved = (row: LadderRow) =>
  row.status === 'review' || row.status === 'escaped' || row.status === 'blocked';

export function emptyReason(data: C01Data): string | null {
  if (data.overlay && data.overlay.length > 0) return null;
  return data.ladder.some((row) => row.horizon === data.horizon) ? null : t('chart.C01.empty');
}

/** 부제: "목표 시점 2028년 상반기" */
export function subtitle(data: C01Data): string | null {
  const row = data.ladder.find((r) => r.horizon === data.horizon);
  return row ? t('chart.C01.subtitle', { target: formatHalfYear(row.target_ym) }) : null;
}

export function buildOption(
  data: C01Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const categories = C01_BARS.map(barLabel);
  const markLine = {
    symbol: 'none',
    silent: true,
    lineStyle: { type: 'dashed' as const, color: palette.muted },
    data: [
      { xAxis: C01_THRESHOLDS.unlikely, label: { formatter: t('chart.C01.threshold.unlikely') } },
      { xAxis: C01_THRESHOLDS.likely, label: { formatter: t('chart.C01.threshold.likely') } },
    ],
  };
  const common = {
    ...baseOption(palette),
    grid: { left: 80, right: 24, top: 16, bottom: 32 },
    xAxis: {
      type: 'value' as const,
      min: 0,
      max: 1,
      axisLabel: { formatter: (v: number) => formatProb(v) },
      splitLine: { lineStyle: { color: palette.border } },
    },
    yAxis: { type: 'category' as const, data: categories, inverse: true },
    tooltip: { trigger: 'item' as const },
  };

  if (data.overlay && data.overlay.length > 0) {
    return {
      ...common,
      legend: { bottom: 0, textStyle: { color: palette.fg } },
      series: data.overlay.map((series, index) => {
        const row = series.ladder.find((r) => r.horizon === data.horizon);
        return {
          type: 'scatter' as const,
          name: series.name,
          symbolSize: 10,
          itemStyle: { color: palette.categorical[index % palette.categorical.length] },
          data: C01_BARS.map((bar, i) => [row ? num(row[bar]) : null, categories[i]]),
          ...(index === 0 ? { markLine } : {}),
        };
      }),
    };
  }

  const row = data.ladder.find((r) => r.horizon === data.horizon);
  const gray = row ? unresolved(row) : true;
  return {
    ...common,
    series: [
      {
        type: 'bar',
        barMaxWidth: 18,
        itemStyle: { color: gray ? palette.grayed : palette.strong },
        label: {
          show: true,
          position: 'right',
          formatter: (params: { dataIndex: number; value: unknown }) => {
            const bar = C01_BARS[params.dataIndex];
            if (!row || !bar) return '';
            if (gray) return t('badge.unresolved');
            const v = typeof params.value === 'number' ? formatProb(params.value) : '';
            const verdict = row.verdicts[bar];
            return verdict ? `${v} · ${verdict}` : v;
          },
        },
        data: C01_BARS.map((bar) => (row ? num(row[bar]) : null)),
        markLine,
      },
    ],
  };
}

export function toTable(data: C01Data): DataTable {
  return {
    columns: [
      { key: 'horizon', header: t('chart.col.horizon') },
      { key: 'target_ym', header: t('chart.col.target'), unit: 'ym' },
      ...C01_BARS.map((bar) => ({ key: bar, header: barLabel(bar), unit: 'prob' as const })),
    ],
    rows: [...data.ladder]
      .sort((a, b) => C01_HORIZONS.indexOf(a.horizon) - C01_HORIZONS.indexOf(b.horizon))
      .map((row) => ({
        horizon: t(`chart.C01.horizon.${row.horizon}`),
        target_ym: row.target_ym,
        p5: row.p5,
        p10: row.p10,
        p20: row.p20,
        p_flat: row.p_flat,
      })),
  };
}
