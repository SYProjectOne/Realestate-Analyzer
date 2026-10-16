import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import {
  axisStyle,
  baseOption,
  DEFAULT_PALETTE,
  hatchDecal,
  legendStyle,
  seriesColor,
  tooltipStyle,
} from '../palette';
import type { BuildOptionContext, ChartLegendItem, EChartsOption } from '../types';
import { escapeHtml, livingAreaName, num } from '../util';
import { C04_TOP_AREAS, type C04Data, type C04Marker } from './types';

export function emptyReason(data: C04Data): string | null {
  return data.supply.length > 0 ? null : t('chart.C04.empty');
}

/** 마커 입주 연월 'YYYY-MM' 또는 null */
export function markerYm(marker: C04Marker): string | null {
  const v = typeof marker.move_in_ym === 'string' ? marker.move_in_ym : marker.move_in_ym.v;
  return typeof v === 'string' && /^\d{4}-\d{2}/.test(v) ? v.slice(0, 7) : null;
}

/** 생활권이 비어 있는 입주 물량 줄의 계열 id — '확인 불가(생활권을 모르는 입주 물량)'로 따로 쌓는다(고침 MK-5) */
export const UNKNOWN_AREA = '__none__';

export interface C04AreaGroups {
  /** 따로 색을 받는 큰 생활권(순서 = 쌓는 순서, 아래부터) */
  top: string[];
  /** '나머지 n곳'으로 묶는 생활권 — 계열은 생활권마다 따로(값은 서버 값 그대로), 색·범례만 하나 */
  rest: string[];
  /** 생활권을 모르는 줄이 있나 */
  unknown: boolean;
}

/**
 * 생활권 묶기(목업 Market '나머지 5곳'): 한 해 입주 세대가 가장 큰 생활권부터 C04_TOP_AREAS곳만 따로 색을 주고,
 * 나머지는 회색 '나머지 n곳'. 순서는 생활권별 한 해 최대값(서버 값 비교만 — 새 합계를 만들지 않는다)으로 정한다.
 * 묶어도 막대는 생활권마다 따로 쌓이고, 말풍선·표에는 생활권마다 서버 값이 그대로 나온다.
 */
export function areaGroups(data: Pick<C04Data, 'supply'>): C04AreaGroups {
  const peak = new Map<string, number>();
  let unknown = false;
  for (const s of data.supply) {
    if (!s.living_area) {
      unknown = true;
      continue;
    }
    const v = num(s.units) ?? 0;
    peak.set(s.living_area, Math.max(peak.get(s.living_area) ?? 0, v));
  }
  const ranked = [...peak.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id);
  // 묶을 게 한 곳뿐이면 묶지 않는다
  const top = ranked.length <= C04_TOP_AREAS + 1 ? ranked : ranked.slice(0, C04_TOP_AREAS);
  return { top, rest: ranked.slice(top.length), unknown };
}

function areaNamer(data: C04Data) {
  // 계약 .20 F6: 서버가 준 생활권 표시 이름(living_area_name) 먼저, 없으면(옛 저장본) living_areas[] 에서
  const serverName = new Map(
    data.supply
      .filter((s) => s.living_area && s.living_area_name)
      .map((s) => [s.living_area as string, s.living_area_name as string]),
  );
  return (id: string) =>
    id === UNKNOWN_AREA
      ? t('chart.C04.unknownArea')
      : (serverName.get(id) ?? livingAreaName(id, data.livingAreas) ?? id);
}

/** '나머지 5곳 (부평구·제물포구·…)' */
export function restName(data: C04Data, groups: C04AreaGroups = areaGroups(data)): string {
  const name = areaNamer(data);
  return t('chart.C04.rest', {
    n: formatCount(groups.rest.length),
    names: groups.rest.map(name).join('·'),
  });
}

/** 연도 x(끊김 없이), 생활권 스택(큰 생활권 + 나머지 + 확인 불가), 판정 단지 입주 연도에 핀. 라벨 "추정 집계", 세대 단위. */
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
  const groups = areaGroups(data);
  const areaIds = [...groups.top, ...groups.rest, ...(groups.unknown ? [UNKNOWN_AREA] : [])];
  const areaName = areaNamer(data);
  const rest = new Set(groups.rest);
  const restLabel = groups.rest.length > 0 ? restName(data, groups) : '';
  const seriesName = (id: string) => (rest.has(id) ? restLabel : areaName(id));
  const yearLabels = years.map(String);
  // 핀 높이(위치)용 — 화면에 숫자로 보이지 않는다(합계 숫자는 뺐다, 고침 MK-3)
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
    grid: { left: 64, right: 16, top: markPointData.length > 0 ? 64 : 28, bottom: 32 },
    legend: { ...legendStyle(palette), data: [...new Set(areaIds.map(seriesName))] },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...tooltipStyle(palette),
      formatter: (params: unknown) => {
        const list = params as { seriesId: string; value: unknown; axisValue: string }[];
        const year = list[0]?.axisValue ?? '';
        // 생활권마다 서버 값 그대로(묶은 '나머지'도 생활권 이름으로 풀어서). 합계 줄은 없다
        const lines = list
          .filter((p) => typeof p.value === 'number')
          .map(
            (p) =>
              `${escapeHtml(areaName(p.seriesId))} ${formatCount(p.value as number, 'households')}`,
          );
        const markers = data.markers
          .filter((m) => markerYm(m)?.startsWith(year))
          .map((m) => `${t('chart.C04.marker')}: ${escapeHtml(m.name)} (${markerYm(m) ?? ''})`);
        return [`<b>${year} · ${t('chart.C04.label')}</b>`, ...lines, ...markers].join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      data: yearLabels,
      ...axis,
      axisTick: { ...axis.axisTick, alignWithLabel: true },
      axisLabel: { ...axis.axisLabel, color: palette.fg, fontSize: 12 },
    },
    yAxis: {
      type: 'value',
      name: t('chart.axis.households'),
      ...axis,
      splitLine: { lineStyle: { color: palette.grid, type: 'dashed' } },
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatCount(v) },
    },
    series: areaIds.map((area, index) => {
      const isRest = rest.has(area);
      const isUnknown = area === UNKNOWN_AREA;
      const color = isUnknown
        ? palette.grayed
        : isRest
          ? palette.rest
          : seriesColor(palette, groups.top.indexOf(area));
      return {
        type: 'bar' as const,
        id: area,
        name: seriesName(area),
        stack: 'supply',
        barMaxWidth: 56,
        itemStyle: {
          color,
          // 쌓은 칸 사이 바탕색 틈(묶은 '나머지'는 한 덩어리로 보이게 틈 없음)
          borderColor: palette.bg,
          borderWidth: isRest ? 0 : 1,
          ...(isUnknown ? { decal: hatchDecal(palette) } : {}),
        },
        data: years.map((year) => {
          const row = data.supply.find(
            (s) => s.year === year && (s.living_area ?? UNKNOWN_AREA) === area,
          );
          return row ? num(row.units) : null;
        }),
        // 판정 단지 입주 핀은 스택 맨 위 계열에 한 번만
        ...(index === areaIds.length - 1 && markPointData.length > 0
          ? {
              markPoint: {
                symbol: 'pin',
                symbolSize: 30,
                itemStyle: { color: palette.strong },
                label: {
                  color: palette.fg,
                  position: 'top' as const,
                  fontSize: 10,
                  lineHeight: 12,
                  backgroundColor: palette.bg,
                  padding: [2, 4],
                  borderRadius: 4,
                },
                data: markPointData,
              },
            }
          : {}),
      };
    }),
  };
}

/** 범례(차트 위 — 연도 축과 겹치지 않는다): 큰 생활권 · 나머지 n곳 · 점수 매긴 단지 입주(핀) · 확인 불가(있을 때) */
export function legendItems(
  data: C04Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  const { palette } = ctx;
  if (data.supply.length === 0) return [];
  const groups = areaGroups(data);
  const name = areaNamer(data);
  // 연도 축은 마커 연도까지 늘어나므로(buildOption) 연월이 있는 마커는 모두 핀으로 그려진다
  const hasMarker = data.markers.some((m) => markerYm(m) !== null);
  return [
    ...groups.top.map((id, i) => ({
      name: name(id),
      color: seriesColor(palette, i),
      symbol: 'square' as const,
    })),
    ...(groups.rest.length > 0
      ? [{ name: restName(data, groups), color: palette.rest, symbol: 'square' as const }]
      : []),
    ...(hasMarker
      ? [{ name: t('chart.C04.marker'), color: palette.strong, symbol: 'pin' as const }]
      : []),
    ...(groups.unknown
      ? [{ name: t('chart.C04.unknownArea'), color: palette.grayed, symbol: 'hatch' as const }]
      : []),
  ];
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
        living_area: s.living_area
          ? (s.living_area_name ?? livingAreaName(s.living_area, data.livingAreas))
          : t('empty.unknown'),
        units: s.units,
        complexes: (s.complexes ?? []).join(', '),
      })),
  };
}
