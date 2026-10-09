import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { RemainingEvent, RemainingKind } from '@/lib/contract';
import { formatCount } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, legendStyle, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
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

/** 마커 라벨 = 잔여 세대 · 경쟁률 */
export function eventLabel(event: RemainingEvent): string {
  const units = num(event.units);
  return [units === null ? null : formatCount(units, 'households'), event.ratio_text ?? null]
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
  return {
    ...baseOption(palette),
    grid: { left: 72, right: 40, top: 28, bottom: 48 },
    legend: legendStyle(palette),
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const { seriesId, dataIndex } = p as { seriesId: string; dataIndex: number };
        const item = dated.filter((x) => x.event.kind === seriesId)[dataIndex];
        if (!item) return '';
        const { event } = item;
        return [
          `${escapeHtml(kindLabel(event.kind))} · ${escapeHtml(str(event.notice_date))}`,
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
      ...axis,
      axisLabel: { ...axis.axisLabel, fontSize: 10 },
      // 양 끝 마커가 축선에 붙지 않게 한 달씩 여유
      min: (v: { min: number }) => v.min - PAD_MS,
      max: (v: { max: number }) => v.max + PAD_MS,
    },
    yAxis: {
      type: 'category',
      data: KINDS.map(kindLabel),
      inverse: true,
      ...axis,
    },
    series: KINDS.map((kind) => ({
      type: 'scatter' as const,
      id: kind,
      name: kindLabel(kind),
      symbol: C08_SYMBOLS[kind],
      symbolSize: 13,
      itemStyle: { color: kind === '본청약' ? palette.strong : palette.fg },
      data: dated
        .filter((x) => x.event.kind === kind)
        .map((x) => ({
          value: [x.date, kindLabel(kind)],
          label: {
            show: true,
            position: 'top' as const,
            color: palette.fg,
            fontSize: 10,
            formatter: eventLabel(x.event),
            width: 180,
            overflow: 'truncate' as const,
          },
        })),
    })),
  };
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
