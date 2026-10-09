import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml, livingAreaName, num } from '../util';
import type { C04Data, C04Marker } from './types';

export function emptyReason(data: C04Data): string | null {
  return data.supply.length > 0 ? null : t('chart.C04.empty');
}

/** 마커 입주 연월 'YYYY-MM' 또는 null */
export function markerYm(marker: C04Marker): string | null {
  const v = typeof marker.move_in_ym === 'string' ? marker.move_in_ym : marker.move_in_ym.v;
  return typeof v === 'string' && /^\d{4}-\d{2}/.test(v) ? v.slice(0, 7) : null;
}

const UNKNOWN_AREA = '__none__';

/** 연도 x(끊김 없이), 생활권 스택, 판정 단지 입주 연도에 markPoint. 라벨 "추정 집계", 세대 단위. */
export function buildOption(
  data: C04Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const markerYears = data.markers
    .map((m) => markerYm(m)?.slice(0, 4))
    .filter((y): y is string => !!y)
    .map(Number);
  const supplyYears = data.supply.map((s) => s.year);
  const allYears = [...supplyYears, ...(supplyYears.length > 0 ? markerYears : [])];
  const years: number[] = [];
  if (allYears.length > 0) {
    for (let y = Math.min(...allYears); y <= Math.max(...allYears); y += 1) years.push(y);
  }
  const areaIds = [...new Set(data.supply.map((s) => s.living_area ?? UNKNOWN_AREA))];
  const areaName = (id: string) =>
    id === UNKNOWN_AREA ? t('empty.unknown') : (livingAreaName(id, data.livingAreas) ?? id);
  const yearLabels = years.map(String);
  const totalOf = (year: number) =>
    data.supply.filter((s) => s.year === year).reduce((sum, s) => sum + (num(s.units) ?? 0), 0);

  // 같은 연도의 판정 단지는 핀 하나로 묶는다(라벨 겹침 방지). 이름 전부는 툴팁·표에
  const byYear = new Map<number, { name: string; ym: string }[]>();
  for (const m of data.markers) {
    const ym = markerYm(m);
    const year = ym ? Number(ym.slice(0, 4)) : null;
    if (ym === null || year === null || !years.includes(year)) continue;
    byYear.set(year, [...(byYear.get(year) ?? []), { name: m.name, ym }]);
  }
  const markPointData = [...byYear.entries()].map(([year, list]) => {
    const first = list[0]!;
    const text =
      list.length === 1
        ? `${first.name}\n${first.ym}`
        : t('chart.C04.markerMore', { name: first.name, n: formatCount(list.length - 1) });
    return {
      name: list.map((x) => x.name).join(', '),
      coord: [String(year), totalOf(year)],
      value: first.ym,
      label: { formatter: text },
    };
  });

  return {
    ...baseOption(palette),
    grid: { left: 64, right: 16, top: 48, bottom: 48 },
    legend: legendStyle(palette),
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(palette),
      formatter: (params: unknown) => {
        const list = params as { seriesName: string; value: unknown; axisValue: string }[];
        const year = list[0]?.axisValue ?? '';
        const lines = list
          .filter((p) => typeof p.value === 'number')
          .map(
            (p) => `${escapeHtml(p.seriesName)} ${formatCount(p.value as number, 'households')}`,
          );
        const markers = data.markers
          .filter((m) => markerYm(m)?.startsWith(year))
          .map((m) => `${t('chart.C04.marker')}: ${escapeHtml(m.name)} (${markerYm(m) ?? ''})`);
        return [`${year} · ${t('chart.C04.label')}`, ...lines, ...markers].join('<br/>');
      },
    },
    xAxis: { type: 'category', data: yearLabels, ...axis },
    yAxis: {
      type: 'value',
      name: t('chart.C04.label'),
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatCount(v) },
    },
    series: areaIds.map((area, index) => ({
      type: 'bar' as const,
      id: area,
      name: areaName(area),
      stack: 'supply',
      barMaxWidth: 36,
      itemStyle: { color: palette.categorical[index % palette.categorical.length] },
      data: years.map((year) => {
        const row = data.supply.find(
          (s) => s.year === year && (s.living_area ?? UNKNOWN_AREA) === area,
        );
        return row ? num(row.units) : null;
      }),
      // 판정 단지 입주 마커는 스택 맨 위 계열에 한 번만
      ...(index === areaIds.length - 1 && markPointData.length > 0
        ? {
            markPoint: {
              symbol: 'pin',
              symbolSize: 34,
              itemStyle: { color: palette.strong },
              label: { color: palette.fg, position: 'top' as const, fontSize: 10 },
              data: markPointData,
            },
          }
        : {}),
    })),
  };
}

export function toTable(data: C04Data): DataTable {
  return {
    columns: [
      { key: 'year', header: t('chart.col.year'), unit: 'text' },
      { key: 'living_area', header: t('chart.col.livingArea') },
      { key: 'units', header: t('chart.col.units'), unit: 'households' },
      { key: 'complexes', header: t('chart.col.name') },
    ],
    rows: [...data.supply]
      .sort((a, b) => a.year - b.year)
      .map((s) => ({
        year: String(s.year),
        living_area: livingAreaName(s.living_area, data.livingAreas),
        units: s.units,
        complexes: (s.complexes ?? []).join(', '),
      })),
  };
}
