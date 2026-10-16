import type { DataTable } from '@/components/DataTableToggle';
import { t, tDynamic } from '@/i18n';
import type { LadderRow } from '@/lib/contract';
import { formatHalfYear, formatPercent, formatProb } from '@/lib/format';
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
import { escapeHtml, num } from '../util';
import {
  C01_BARS,
  C01_HORIZONS,
  C01_OVERLAY_SYMBOLS,
  C01_SCORE_BAR,
  C01_THRESHOLDS,
  type C01Data,
  type LadderBar,
} from './types';

/** 막대 이름(쉬운 말): "10% 넘게 오를 가능성" */
const barLabel = (bar: LadderBar) => t(`chart.C01.bar.${bar}`);
/** 축·표 열용 짧은 이름: "10% 넘게" */
const barShort = (bar: LadderBar) => t(`chart.C01.barShort.${bar}`);
const verdictText = (verdict: string | null | undefined) =>
  verdict ? tDynamic(`chart.C01.verdict.${verdict}`, verdict) : null;

/** 판정 봉투가 ok가 아니면(review·escaped·blocked·error) 미해결 — 회색 + "미해결" */
export function isUnresolved(row: LadderRow): boolean {
  return row.status !== 'ok';
}

function currentRow(data: C01Data): LadderRow | undefined {
  return data.ladder.find((r) => r.horizon === data.horizon);
}

const hasOverlay = (data: C01Data) => !!data.overlay && data.overlay.length > 0;

export function emptyReason(data: C01Data): string | null {
  if (hasOverlay(data)) return null;
  return currentRow(data) ? null : t('chart.C01.empty');
}

const targetOf = (row: LadderRow) => row.target_label ?? formatHalfYear(row.target_ym);

/**
 * 부제: "목표 시점 2029 상반기" (서버 target_label 우선, 없으면 target_ym → 연도 반기).
 * G4 겹쳐 보기는 단지마다 목표 시점이 달라 "목표 시점 · A 2030 하반기 · B 2031 하반기"로 모두 보인다.
 */
export function subtitle(data: C01Data): string | null {
  if (hasOverlay(data)) {
    const targets = (data.overlay ?? []).flatMap((o) => {
      const row = o.ladder.find((r) => r.horizon === data.horizon);
      return row ? [t('chart.C01.overlayTarget', { name: o.name, target: targetOf(row) })] : [];
    });
    return targets.length > 0
      ? t('chart.C01.subtitleOverlay', { targets: targets.join(' · ') })
      : null;
  }
  const row = currentRow(data);
  return row ? t('chart.C01.subtitle', { target: targetOf(row) }) : null;
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
    isUnresolved(row) ? null : verdictText(row.verdicts[bar]),
  ].filter(Boolean);
  const ann = annualizedOf(row, bar);
  const annText =
    ann === null || isUnresolved(row)
      ? ''
      : `<br/>${t('chart.C01.annualized', { pct: formatPercent(ann * 100) })}`;
  return `${parts.join(' · ')}${annText}`;
}

/** 기준선 0.15 / 0.85 (판정기 기준 — 점선, 글자 "가능성 낮음 기준 15%") */
function thresholdLine(palette: BuildOptionContext['palette'], axis: 'xAxis' | 'yAxis') {
  return {
    symbol: 'none',
    silent: true,
    lineStyle: { type: 'dashed' as const, color: palette.muted, width: 1 },
    label: {
      color: palette.muted,
      fontSize: 10,
      position: axis === 'xAxis' ? ('start' as const) : ('end' as const),
    },
    data: [
      {
        [axis]: C01_THRESHOLDS.unlikely,
        label: { formatter: t('chart.C01.threshold.unlikely') },
      },
      { [axis]: C01_THRESHOLDS.likely, label: { formatter: t('chart.C01.threshold.likely') } },
    ],
  };
}

/** 0~100% 눈금(20%p 간격) */
const PROB_TICKS = { min: 0, max: 1, interval: 0.2 } as const;

/** 막대 색: 점수에 쓰는 +10% = 강조, 다른 상승 막대 = 옅은 강조, 보합·하락 = 회색 계열, 미해결 = grayed */
function barColor(bar: LadderBar, gray: boolean, palette: BuildOptionContext['palette']): string {
  if (gray) return palette.grayed;
  if (bar === C01_SCORE_BAR) return palette.strong;
  return bar === 'p_flat' ? palette.rest : palette.strongSoft;
}

export function buildOption(
  data: C01Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const probAxis = {
    type: 'value' as const,
    ...PROB_TICKS,
    name: t('chart.axis.prob'),
    ...axis,
    axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatProb(v) },
  };

  if (hasOverlay(data)) {
    // G4 겹쳐 보기 — 막대 묶음 4개(+5/+10/+20/보합·하락) × 단지. 단지 색·순서는 비교 단지 순서 그대로
    const overlay = data.overlay ?? [];
    const categories = C01_BARS.map(barShort);
    return {
      ...baseOption(palette),
      grid: { left: 52, right: 136, top: 28, bottom: 32 },
      legend: { ...legendStyle(palette), data: overlay.map((o) => o.name) },
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
      xAxis: {
        type: 'category',
        data: categories,
        ...axis,
        axisTick: { ...axis.axisTick, alignWithLabel: true },
        axisLabel: { ...axis.axisLabel, interval: 0, fontSize: 12, color: palette.fg },
      },
      yAxis: {
        ...probAxis,
        interval: 0.25,
        nameLocation: 'end',
      },
      series: overlay.map((series, index) => {
        const row = series.ladder.find((r) => r.horizon === data.horizon);
        const gray = !row || isUnresolved(row);
        return {
          type: 'bar' as const,
          id: String(series.complex_id),
          name: series.name,
          barMaxWidth: 28,
          barGap: '15%',
          itemStyle: {
            color: gray ? palette.grayed : seriesColor(palette, index),
            borderRadius: [4, 4, 0, 0],
          },
          // 미해결 단지: 값 대신 회색 바탕 막대 + "미해결"
          showBackground: gray,
          backgroundStyle: { color: palette.border, opacity: 0.35 },
          label: {
            show: true,
            position: 'top' as const,
            color: palette.fg,
            fontSize: 10,
            formatter: (params: { value: unknown }) =>
              gray
                ? t('badge.unresolved')
                : typeof params.value === 'number'
                  ? formatProb(params.value)
                  : t('empty.unknown'),
          },
          data: C01_BARS.map((bar) => (row && !gray ? num(row[bar]) : 0)),
          ...(index === 0 ? { markLine: thresholdLine(palette, 'yAxis') } : {}),
        };
      }),
    };
  }

  const row = currentRow(data);
  const gray = row ? isUnresolved(row) : true;
  // 막대 이름: "+10%"는 종합 점수에 쓰는 막대라 "· 점수에 씀"을 붙인다
  const categories = C01_BARS.map((bar) =>
    bar === C01_SCORE_BAR ? t('chart.C01.usedInScore', { name: barLabel(bar) }) : barLabel(bar),
  );
  return {
    ...baseOption(palette),
    grid: { left: 188, right: 112, top: 28, bottom: 36 },
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const bar = C01_BARS[(p as { dataIndex: number }).dataIndex];
        return bar ? tooltipLine(row, bar) : '';
      },
    },
    xAxis: { ...probAxis, nameLocation: 'end', nameGap: 8 },
    yAxis: {
      type: 'category',
      data: categories,
      inverse: true,
      ...axis,
      axisTick: { ...axis.axisTick, alignWithLabel: true },
      axisLabel: {
        ...axis.axisLabel,
        color: palette.fg,
        fontSize: 12,
        width: 176,
        overflow: 'break',
      },
    },
    series: [
      {
        type: 'bar',
        id: 'ladder',
        name: t('chart.C01.title'),
        barMaxWidth: 22,
        showBackground: true,
        backgroundStyle: { color: palette.grid, opacity: gray ? 1 : 0.6, borderRadius: 4 },
        label: {
          show: true,
          position: 'right',
          color: palette.fg,
          fontSize: 12,
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
          itemStyle: { color: barColor(bar, gray, palette), borderRadius: [0, 4, 4, 0] },
        })),
        markLine: thresholdLine(palette, 'xAxis'),
      },
    ],
  };
}

const LEGEND_SYMBOL: Record<string, ChartLegendSymbol> = {
  circle: 'circle',
  rect: 'rect',
  triangle: 'triangle',
  diamond: 'diamond',
  pin: 'pin',
  roundRect: 'square',
};

/** 범례: 겹쳐 보기만(단지마다 색 + 모양). 한 단지 사다리는 계열이 하나라 범례 없음 */
export function legendItems(
  data: C01Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  if (!hasOverlay(data)) return [];
  return (data.overlay ?? []).map((o, index) => {
    const row = o.ladder.find((r) => r.horizon === data.horizon);
    const gray = !row || isUnresolved(row);
    return {
      name: o.name,
      color: gray ? ctx.palette.grayed : seriesColor(ctx.palette, index),
      symbol: LEGEND_SYMBOL[C01_OVERLAY_SYMBOLS[index % C01_OVERLAY_SYMBOLS.length]!] ?? 'square',
      ...(gray ? { note: t('badge.unresolved') } : {}),
    };
  });
}

export function toTable(data: C01Data): DataTable {
  const rows = hasOverlay(data)
    ? (data.overlay ?? []).flatMap((o) =>
        o.ladder.filter((r) => r.horizon === data.horizon).map((r) => ({ name: o.name, row: r })),
      )
    : [...data.ladder]
        .sort((a, b) => C01_HORIZONS.indexOf(a.horizon) - C01_HORIZONS.indexOf(b.horizon))
        .map((r) => ({ name: null, row: r }));
  return {
    columns: [
      ...(hasOverlay(data) ? [{ key: 'name', header: t('chart.col.name') }] : []),
      { key: 'horizon', header: t('chart.col.horizon') },
      { key: 'target_ym', header: t('chart.col.target'), unit: 'ym' as const },
      ...C01_BARS.map((bar) => ({ key: bar, header: barShort(bar), unit: 'prob' as const })),
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
