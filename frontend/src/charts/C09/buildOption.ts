import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { CatalystStage, CatalystView } from '@/lib/contract';
import { axisStyle, baseOption, DEFAULT_PALETTE, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
import { escapeHtml, str, toIsoDay } from '../util';
import { C09_STAGES, type C09Data } from './types';

export const stageLabel = (s: CatalystStage) => t(`chart.C09.stage.${s}`);

export function emptyReason(data: C09Data): string | null {
  return data.catalysts.length > 0 ? null : t('chart.C09.empty');
}

/** 보드(HTML 그리드)용: 단계별 묶음(열 순서 고정) */
export function groupByStage(catalysts: CatalystView[]): Record<CatalystStage, CatalystView[]> {
  const out = Object.fromEntries(C09_STAGES.map((s) => [s, [] as CatalystView[]])) as Record<
    CatalystStage,
    CatalystView[]
  >;
  // 보드 5열 밖 단계('호재 아님' — 계약 .8, D11-2 판정 제외)는 보드에 넣지 않는다(excludedCatalysts 로 따로 센다)
  for (const c of catalysts) out[c.stage]?.push(c);
  return out;
}

/** 보드 단계 밖(예: '호재 아님' — D11-2 판정 제외, 사람이 넣은 호재는 판정과 무관하게 남는다) */
export function excludedCatalysts(catalysts: CatalystView[]): CatalystView[] {
  return catalysts.filter((c) => !(C09_STAGES as readonly string[]).includes(c.stage));
}

/** 타임라인 항목: **확정 + 예정 연월 있는 것만**, 날짜순. 이름 겹침을 피하려고 4단으로 엇갈린다 */
export function timelineItems(catalysts: CatalystView[]) {
  return catalysts
    .map((c) => ({ c, date: toIsoDay(str(c.expected_ym)) }))
    .filter((x): x is { c: CatalystView; date: string } => x.c.stage === '확정' && x.date !== null)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((x, index) => ({ ...x, level: index % 4 }));
}

/** 타임라인 option — 확정 호재만 time scatter. 보드는 index.tsx의 HTML. */
export function buildOption(
  data: C09Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const items = timelineItems(data.catalysts);
  return {
    ...baseOption(palette),
    grid: { left: 24, right: 24, top: 8, bottom: 28 },
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const item = items[(p as { dataIndex: number }).dataIndex];
        if (!item) return '';
        return [
          escapeHtml(item.c.name),
          `${escapeHtml(item.c.kind)} · ${escapeHtml(str(item.c.expected_ym))}`,
          item.c.note ? escapeHtml(item.c.note) : null,
        ]
          .filter(Boolean)
          .join('<br/>');
      },
    },
    xAxis: { type: 'time', ...axis, axisLabel: { ...axis.axisLabel, fontSize: 10 } },
    yAxis: { type: 'value', show: false, min: -0.6, max: 3.8 },
    series: [
      {
        type: 'scatter',
        id: 'timeline',
        name: t('chart.C09.timeline'),
        symbolSize: 10,
        itemStyle: { color: palette.strong },
        // 겹치는 이름은 숨긴다(전부는 툴팁·보드·표에)
        labelLayout: { hideOverlap: true },
        data: items.map((x) => ({
          name: x.c.name,
          value: [x.date, x.level],
          label: {
            show: true,
            position: 'right' as const,
            width: 150,
            overflow: 'truncate' as const,
            color: palette.fg,
            fontSize: 10,
            formatter: `${x.c.name} (${str(x.c.expected_ym) ?? ''})`,
          },
        })),
      },
    ],
  };
}

export function toTable(data: C09Data): DataTable {
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'kind', header: t('chart.col.kind') },
      { key: 'stage', header: t('chart.col.stage') },
      { key: 'stage_prob', header: t('chart.col.prob'), unit: 'prob' },
      { key: 'expected', header: t('chart.col.expected'), unit: 'ym' },
      { key: 'location', header: t('chart.col.location') },
    ],
    rows: data.catalysts.map((c) => ({
      name: c.name,
      kind: c.kind,
      stage: stageLabel(c.stage),
      stage_prob: c.stage_prob,
      expected: c.expected_ym,
      location: c.location_confirmed ? t('chart.yes') : t('chart.C09.noLink'),
    })),
  };
}
