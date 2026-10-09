import type { RemainingKind } from '@/api/types';
import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import { baseOption, DEFAULT_PALETTE } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { num } from '../util';
import { C08_SYMBOLS, type C08Data } from './types';

const KINDS = Object.keys(C08_SYMBOLS) as RemainingKind[];
const kindLabel = (k: RemainingKind) => t(`chart.C08.kind.${k}`);

/** 이벤트 0 → "본청약만" */
export function emptyReason(data: C08Data): string | null {
  return data.events.length > 0 ? null : t('chart.C08.empty');
}

export function buildOption(
  data: C08Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  return {
    ...baseOption(palette),
    grid: { left: 88, right: 24, top: 16, bottom: 40 },
    tooltip: { trigger: 'item' },
    xAxis: { type: 'time', splitLine: { lineStyle: { color: palette.border } } },
    yAxis: { type: 'category', data: KINDS.map(kindLabel), inverse: true },
    series: KINDS.map((kind) => ({
      type: 'scatter' as const,
      name: kindLabel(kind),
      symbol: C08_SYMBOLS[kind],
      symbolSize: 12,
      itemStyle: { color: kind === '본청약' ? palette.strong : palette.fg },
      label: {
        show: true,
        position: 'top' as const,
        formatter: (p: { dataIndex: number }) => {
          const ev = data.events.filter((e) => e.kind === kind)[p.dataIndex];
          if (!ev) return '';
          const units = num(ev.units);
          return [units === null ? null : formatCount(units, 'households'), ev.ratio_text]
            .filter(Boolean)
            .join(' · ');
        },
      },
      data: data.events
        .filter((e) => e.kind === kind)
        .map((e) => [e.notice_date.v, kindLabel(kind)]),
    })),
  };
}

export function toTable(data: C08Data): DataTable {
  return {
    columns: [
      { key: 'kind', header: t('chart.col.kind') },
      { key: 'notice_no', header: t('chart.col.noticeNo') },
      { key: 'notice_date', header: t('chart.col.noticeDate'), unit: 'date' },
      { key: 'units', header: t('chart.col.units'), unit: 'households' },
      { key: 'ratio', header: t('chart.col.ratio') },
    ],
    rows: [...data.events]
      .sort((a, b) => String(a.notice_date.v ?? '').localeCompare(String(b.notice_date.v ?? '')))
      .map((e) => ({
        kind: kindLabel(e.kind),
        notice_no: e.notice_no,
        notice_date: e.notice_date,
        units: e.units,
        ratio: e.ratio_text,
      })),
  };
}
