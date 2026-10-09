import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { FactLike, UnsoldPoint } from '@/lib/contract';
import { formatCount } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { monthRange, num } from '../util';
import { C05_DEFAULT_MONTHS, type C05Data } from './types';

export function emptyReason(data: C05Data): string | null {
  return data.unsold.length > 0 ? null : t('chart.C05.empty');
}

const scopeKey = (u: UnsoldPoint) => u.scope_code ?? '';

/** 범위(scope_code)가 여럿이면 값 있는 달이 가장 많은 범위(동률이면 먼저 나온 것) */
export function selectScope(unsold: UnsoldPoint[], preferred?: string | null): string | null {
  if (preferred !== undefined && preferred !== null) return preferred;
  const counts = new Map<string, number>();
  for (const u of unsold) {
    const key = scopeKey(u);
    counts.set(key, (counts.get(key) ?? 0) + (num(u.total) === null ? 0 : 1));
  }
  let best: string | null = null;
  let bestCount = -1;
  for (const [key, count] of counts) {
    if (count > bestCount) {
      best = key;
      bestCount = count;
    }
  }
  return best === '' ? null : best;
}

export interface C05Month {
  ym: string;
  total: FactLike | null;
  post_completion: FactLike | null;
}

/** 선택 범위의 최근 N개월 — 월 축은 끊김 없이, 자료 없는 달은 null(connectNulls=false로 끊는다) */
export function recentRows(data: C05Data): C05Month[] {
  const scope = selectScope(data.unsold, data.scope);
  const rows = data.unsold.filter(
    (u) => (u.scope_code ?? null) === scope || (scope === null && !u.scope_code),
  );
  if (rows.length === 0) return [];
  const sorted = [...rows].sort((a, b) => a.ym.localeCompare(b.ym));
  const months = monthRange(sorted[0]!.ym, sorted[sorted.length - 1]!.ym).slice(
    -(data.months ?? C05_DEFAULT_MONTHS),
  );
  return months.map((ym) => {
    const row = sorted.find((u) => u.ym.slice(0, 7) === ym);
    return { ym, total: row?.total ?? null, post_completion: row?.post_completion ?? null };
  });
}

/** 부제: "월말 기준 · 김포시" (범위 이름은 서버 값) */
export function subtitle(data: C05Data): string {
  const scope = selectScope(data.unsold, data.scope);
  const name = data.unsold.find((u) => (u.scope_code ?? null) === scope)?.scope_name;
  return name ? t('chart.C05.basisScope', { scope: name }) : t('chart.C05.basis');
}

export function buildOption(
  data: C05Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const rows = recentRows(data);
  return {
    ...baseOption(palette),
    grid: { left: 56, right: 16, top: 16, bottom: 56 },
    legend: legendStyle(palette),
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(palette),
      valueFormatter: (v) => (typeof v === 'number' ? formatCount(v) : t('empty.unknown')),
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.ym),
      ...axis,
      axisLabel: { ...axis.axisLabel, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatCount(v) },
    },
    series: [
      {
        type: 'line',
        id: 'total',
        name: t('chart.C05.total'),
        connectNulls: false,
        symbol: 'circle',
        itemStyle: { color: palette.strong },
        lineStyle: { color: palette.strong, width: 2 },
        data: rows.map((r) => num(r.total)),
      },
      {
        type: 'line',
        id: 'post',
        name: t('chart.C05.postCompletion'),
        connectNulls: false,
        // 색이 아니라 선 모양(점선)·마커로도 구분
        symbol: 'rect',
        lineStyle: { type: 'dashed', color: palette.fg },
        itemStyle: { color: palette.fg },
        data: rows.map((r) => num(r.post_completion)),
      },
    ],
  };
}

export function toTable(data: C05Data): DataTable {
  return {
    columns: [
      { key: 'ym', header: t('chart.col.month'), unit: 'ym' },
      { key: 'total', header: t('chart.C05.total'), unit: 'count' },
      { key: 'post_completion', header: t('chart.C05.postCompletion'), unit: 'count' },
    ],
    rows: recentRows(data).map((r) => ({
      ym: r.ym,
      total: r.total,
      post_completion: r.post_completion,
    })),
  };
}
