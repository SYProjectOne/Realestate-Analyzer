import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { RemainingEvent, RemainingKind } from '@/lib/contract';
import { formatCount } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type {
  BuildOptionContext,
  ChartLegendItem,
  ChartLegendSymbol,
  EChartsOption,
} from '../types';
import { escapeHtml, num, str, toIsoDay } from '../util';
import { C08_SYMBOLS, type C08Data } from './types';

const KINDS = Object.keys(C08_SYMBOLS) as RemainingKind[];
/** 시간축 양 끝 여유(약 한 달) */
const PAD_MS = 31 * 24 * 60 * 60 * 1000;
const kindLabel = (k: RemainingKind) => t(`chart.C08.kind.${k}`);

/** 이벤트 0 → "본청약만" */
export function emptyReason(data: C08Data): string | null {
  return data.events.length > 0 ? null : t('chart.C08.empty');
}

/** 공고일 → 'YYYY-MM-DD' (월만 확인된 'YYYY-MM'은 1일). 날짜 없으면 null(차트 제외, 표에는 남김) */
export function eventDate(event: RemainingEvent): string | null {
  return toIsoDay(str(event.notice_date));
}

/** 같은 줄(kind)에서 이 간격보다 가까운 이웃 라벨은 위·아래로 엇갈린다 */
const STAGGER_MS = 120 * 24 * 60 * 60 * 1000;

export interface C08LabelItem {
  date: string;
  kind: RemainingKind;
  text: string;
  /** 마커 위(top)·아래(bottom) */
  place: 'top' | 'bottom';
}

/**
 * custom 라벨 계열(RA §7 C8 "scatter + custom 라벨")의 항목: 잔여 세대·경쟁률. 같은 kind 줄에서 가까운
 * 이웃과 겹치지 않게 위·아래를 번갈아 둔다. 라벨 문구가 없는 이벤트는 빠진다.
 */
export function labelItems(data: C08Data): C08LabelItem[] {
  const out: C08LabelItem[] = [];
  for (const kind of KINDS) {
    const row = data.events
      .filter((e) => e.kind === kind)
      .map((event) => ({ event, date: eventDate(event) }))
      .filter((x): x is { event: RemainingEvent; date: string } => x.date !== null)
      .sort((a, b) => a.date.localeCompare(b.date));
    let prev: C08LabelItem | null = null;
    for (const { event, date } of row) {
      const text = eventLabel(event);
      if (!text) continue;
      const close = prev !== null && Date.parse(date) - Date.parse(prev.date) < STAGGER_MS;
      const place: C08LabelItem['place'] = close && prev?.place === 'top' ? 'bottom' : 'top';
      const item: C08LabelItem = { date, kind, text, place };
      out.push(item);
      prev = item;
    }
  }
  return out;
}

/** 차트 라벨에 둘 경쟁률 표기의 최대 길이 — 긴 원문(여러 타입 나열)은 표·"표로 보기"에만 둔다(R9-UI P8) */
const RATIO_LABEL_MAX = 12;

/** 마커 라벨 = 잔여 세대 · 경쟁률(짧은 표기만) */
export function eventLabel(event: RemainingEvent): string {
  const units = num(event.units);
  const ratio = event.ratio_text ?? null;
  const shortRatio = ratio !== null && ratio.length <= RATIO_LABEL_MAX ? ratio : null;
  return [units === null ? null : formatCount(units, 'households'), shortRatio]
    .filter(Boolean)
    .join(' · ');
}

export function buildOption(
  data: C08Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const dated = data.events
    .map((event) => ({ event, date: eventDate(event) }))
    .filter((x): x is { event: RemainingEvent; date: string } => x.date !== null);
  const labels = labelItems(data);
  const asofDay = toIsoDay(data.asof ?? null);
  return {
    ...baseOption(palette),
    grid: { left: 80, right: 40, top: 32, bottom: 36 },
    // 범례는 kind 4종만(라벨 계열은 범례에 넣지 않는다)
    legend: { ...legendStyle(palette), data: KINDS.map(kindLabel) },
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const { seriesId, dataIndex } = p as { seriesId: string; dataIndex: number };
        const item = dated.filter((x) => x.event.kind === seriesId)[dataIndex];
        if (!item) return '';
        const { event } = item;
        return [
          `<b>${escapeHtml(kindLabel(event.kind))} · ${escapeHtml(str(event.notice_date))}</b>`,
          event.notice_no ? escapeHtml(event.notice_no) : null,
          escapeHtml(eventLabel(event)) || null,
          event.result_text ? escapeHtml(event.result_text) : null,
        ]
          .filter(Boolean)
          .join('<br/>');
      },
    },
    xAxis: {
      type: 'time',
      name: t('chart.axis.noticeDate'),
      nameLocation: 'end',
      ...axis,
      splitLine: { show: true, lineStyle: { color: palette.grid } },
      axisLabel: { ...axis.axisLabel, fontSize: 11, hideOverlap: false },
      // 양 끝 마커가 축선에 붙지 않게 한 달씩 여유
      min: (v: { min: number }) => v.min - PAD_MS,
      max: (v: { max: number }) => v.max + PAD_MS,
    },
    yAxis: {
      type: 'category',
      data: KINDS.map(kindLabel),
      inverse: true,
      ...axis,
      axisTick: { ...axis.axisTick, alignWithLabel: true },
      axisLabel: { ...axis.axisLabel, color: palette.fg, fontSize: 12 },
      splitLine: { show: true, lineStyle: { color: palette.grid } },
    },
    series: [
      ...KINDS.map((kind) => ({
        type: 'scatter' as const,
        id: kind,
        name: kindLabel(kind),
        symbol: C08_SYMBOLS[kind],
        symbolSize: 14,
        // 본청약만 진한 글자색, 다시 모집(무순위·임의공급·선착순)은 강조색 — 모양으로도 나눈다(목업 DX-7)
        itemStyle: {
          color: kind === '본청약' ? palette.fg : palette.strong,
          borderColor: palette.bg,
          borderWidth: 1.5,
        },
        data: dated
          .filter((x) => x.event.kind === kind)
          .map((x) => ({ value: [x.date, kindLabel(kind)] })),
        // 기준일 세로 점선(서버 기준일 그대로 — 계산 아님)
        ...(kind === KINDS[0] && asofDay
          ? {
              markLine: {
                symbol: 'none',
                silent: true,
                lineStyle: { type: 'dashed' as const, color: palette.strong, width: 1.5 },
                label: {
                  formatter: t('chart.C08.asof', { date: asofDay }),
                  color: palette.strong,
                  fontSize: 11,
                  // y축이 뒤집혀(inverse) 있어 'start'가 위쪽 — 공고일 눈금과 겹치지 않게 위에 단다
                  position: 'start' as const,
                },
                data: [{ xAxis: asofDay }],
              },
            }
          : {}),
      })),
      {
        // 라벨 = custom 계열(잔여 세대·경쟁률). 가까운 이웃은 위·아래로 엇갈려 겹치지 않는다
        type: 'custom' as const,
        id: 'labels',
        name: t('chart.C08.labels'),
        silent: true,
        z: 3,
        encode: { x: 0, y: 1 },
        data: labels.map((item) => ({
          value: [item.date, kindLabel(item.kind)],
          text: item.text,
          place: item.place,
        })),
        renderItem: (params, api) => {
          const item = labels[params.dataIndex];
          if (!item) return null;
          const pt = api.coord([api.value(0), api.value(1)]) as number[];
          const above = item.place === 'top';
          return {
            type: 'text',
            x: pt[0] ?? 0,
            y: (pt[1] ?? 0) + (above ? -10 : 10),
            style: {
              text: item.text,
              fill: palette.fg,
              fontSize: 11,
              fontWeight: 600,
              align: 'center',
              verticalAlign: above ? 'bottom' : 'top',
              backgroundColor: palette.grid,
              padding: [2, 6],
              borderRadius: 6,
            },
          };
        },
      },
    ],
  };
}

const LEGEND_SYMBOL: Record<string, ChartLegendSymbol> = {
  circle: 'circle',
  rect: 'rect',
  triangle: 'triangle',
  diamond: 'diamond',
};

/** 범례(차트 위): 모집 종류 4가지 — 모양 + 색(본청약만 진한 색) */
export function legendItems(
  data: C08Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  if (data.events.length === 0) return [];
  return KINDS.map((kind) => ({
    name: kindLabel(kind),
    color: kind === '본청약' ? ctx.palette.fg : ctx.palette.strong,
    symbol: LEGEND_SYMBOL[C08_SYMBOLS[kind]] ?? 'circle',
  }));
}

export function toTable(data: C08Data): DataTable {
  return {
    columns: [
      { key: 'kind', header: t('chart.col.kind') },
      { key: 'notice_no', header: t('chart.col.noticeNo') },
      { key: 'notice_date', header: t('chart.col.noticeDate') },
      { key: 'units', header: t('chart.col.units'), unit: 'households' },
      { key: 'ratio', header: t('chart.col.ratio') },
      { key: 'result', header: t('chart.col.flags') },
    ],
    rows: [...data.events]
      .sort((a, b) => (eventDate(a) ?? '').localeCompare(eventDate(b) ?? ''))
      .map((e) => ({
        kind: kindLabel(e.kind),
        notice_no: e.notice_no ?? '',
        notice_date: e.notice_date,
        units: e.units,
        ratio: e.ratio_text ?? '',
        result: e.result_text ?? '',
      })),
  };
}
