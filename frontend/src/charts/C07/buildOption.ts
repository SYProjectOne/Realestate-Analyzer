import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { Decision } from '@/lib/contract';
import { formatConfidence, formatProb } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, tooltipStyle } from '../palette';
import type { BuildOptionContext, ChartLegendItem, EChartsOption } from '../types';
import { escapeHtml, num } from '../util';
import type { C07Data } from './types';

/** escaped면 막대 대신 판정기 질문. 텍스트는 React가 이스케이프해 렌더한다(HTML로 해석하지 않음) */
export function isEscaped(data: C07Data): boolean {
  const d = data.decision;
  return !!d && (d.status === 'escaped' || d.escaped);
}

/** 판정 없음 → "판정 없음", escaped → "질문 남김: {질문}" */
export function emptyReason(data: C07Data): string | null {
  const d = data.decision;
  if (!d) return t('chart.C07.empty');
  if (isEscaped(data)) return `${t('chart.C07.escape')}: ${d.question ?? t('empty.unknown')}`;
  if (d.items.length === 0) return t('chart.C07.empty');
  return null;
}

/** 판정 봉투가 review·blocked·error면 막대를 회색 + "판정 미해결" */
export function isUnresolved(data: C07Data): boolean {
  const s = data.decision?.status;
  return s === 'review' || s === 'blocked' || s === 'error';
}

export function confidenceValue(data: C07Data): number | null {
  return num(data.decision?.confidence ?? null);
}

/** 봉투가 확정(ok)이 아니면(review·blocked·error·escaped) 동률을 보이지 않는다 */
function tieShown(data: C07Data): boolean {
  return data.decision?.status === 'ok' && !isEscaped(data);
}

/**
 * 동률 = 서버가 준 DecisionSet.tie 만(R3 minor 28). 브라우저는 confidence 로 다시 계산하지 않는다
 * (서버가 meta §2-7 confidence < 0.6 규칙을 이미 적용). 미해결 봉투는 동률 표시에서 뺀다.
 */
export function isTie(data: C07Data): boolean {
  return tieShown(data) && (data.decision?.tie ?? false);
}

export function hasMismatch(data: C07Data): boolean {
  return data.decision?.items.some((item) => item.mismatch) ?? false;
}

export function confidenceText(data: C07Data): string | null {
  const c = confidenceValue(data);
  return c === null ? null : t('chart.C07.confidence', { confidence: formatConfidence(c) });
}

const isCandidate = (item: Decision) => item.option_key === 'complex';
/** 가상 후보 '모집공고 대기'(계약 2026-10-09.5) — 단지처럼 선택·확률을 보이되 complex_id 는 null */
const isVirtual = (item: Decision) => item.option_key === 'wait_new';
/** 막대 색·선택 강조를 받는 판정기 후보(단지 + 가상 후보). escape hatch(질문·추가 조사·해당 없음)는 회색 */
const isOption = (item: Decision) => isCandidate(item) || isVirtual(item);

/** 항목 표시 글자 — 선택·동률은 서버 값 그대로(동률은 확정 봉투일 때만) */
function flagsOf(item: Decision, showTie: boolean): string[] {
  return [
    item.chosen ? t('chart.chosen') : null,
    showTie && item.tie ? t('badge.tie') : null,
    item.mismatch ? t('badge.mismatch') : null,
    // 단지가 아닌 판정기 선택지(질문·추가 조사·해당 없음) = '판정기 보류 선택지'(목업 CP-10). 봉투 escaped(질문 남김)와 다르다
    isVirtual(item) ? t('chart.C07.virtual') : isOption(item) ? null : t('chart.C07.hold'),
  ].filter((x): x is string => x !== null);
}

/** 가로 막대: 후보(단지 + 가상 후보 '모집공고 대기')별 prob + escape 선택지(질문·추가 조사, 회색). 선택 = 강조색 + "선택" 글자 */
export function buildOption(
  data: C07Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): EChartsOption {
  const { palette } = ctx;
  const axis = axisStyle(palette);
  const items = data.decision?.items ?? [];
  const gray = isUnresolved(data);
  const showTie = tieShown(data);
  return {
    ...baseOption(palette),
    grid: { left: 212, right: 168, top: 12, bottom: 36 },
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const item = items[(p as { dataIndex: number }).dataIndex];
        if (!item) return '';
        const prob = num(item.prob);
        const lines = [
          `<b>${escapeHtml(item.label)}</b>`,
          prob === null ? t('empty.unknown') : formatProb(prob),
          ...flagsOf(item, showTie).map(escapeHtml),
        ];
        return lines.join('<br/>');
      },
    },
    xAxis: {
      type: 'value',
      min: 0,
      max: 1,
      interval: 0.25,
      name: t('chart.axis.choiceProb'),
      nameLocation: 'middle',
      nameGap: 24,
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatProb(v) },
    },
    yAxis: {
      type: 'category',
      data: items.map((item) => item.label),
      inverse: true,
      ...axis,
      axisTick: { ...axis.axisTick, alignWithLabel: true },
      // 후보 이름은 줄바꿈 — 잘라 숨기지 않는다
      axisLabel: {
        ...axis.axisLabel,
        color: palette.fg,
        fontSize: 12,
        interval: 0,
        width: 200,
        overflow: 'break',
        lineHeight: 14,
      },
    },
    series: [
      {
        type: 'bar',
        id: 'decide',
        name: t('chart.C07.title'),
        barMaxWidth: 18,
        showBackground: true,
        backgroundStyle: { color: palette.grid, borderRadius: 4 },
        label: {
          show: true,
          position: 'right',
          color: palette.fg,
          formatter: (p: { dataIndex: number; value: unknown }) => {
            const item = items[p.dataIndex];
            const v = typeof p.value === 'number' ? formatProb(p.value) : t('empty.unknown');
            if (gray) return `${v} · ${t('badge.unresolved')}`;
            const flags = item ? flagsOf(item, showTie) : [];
            return [v, ...flags].join(' · ');
          },
        },
        data: items.map((item) => ({
          value: num(item.prob),
          itemStyle: {
            color:
              gray || !isOption(item)
                ? palette.grayed
                : item.chosen
                  ? palette.strong
                  : palette.strongSoft,
            borderRadius: [0, 4, 4, 0],
          },
        })),
      },
    ],
  };
}

/** 범례(차트 위): 막대 색의 뜻 — 판정기 선택 · 다른 후보 · 보류 선택지(있을 때). 미해결이면 회색 한 가지 */
export function legendItems(
  data: C07Data,
  ctx: BuildOptionContext = { palette: DEFAULT_PALETTE },
): ChartLegendItem[] {
  const { palette } = ctx;
  const items = data.decision?.items ?? [];
  if (items.length === 0 || isEscaped(data)) return [];
  if (isUnresolved(data))
    return [{ name: t('chart.C07.unresolved'), color: palette.grayed, symbol: 'square' }];
  return [
    ...(items.some((i) => isOption(i) && i.chosen)
      ? [{ name: t('chart.chosen'), color: palette.strong, symbol: 'square' as const }]
      : []),
    ...(items.some((i) => isOption(i) && !i.chosen)
      ? [{ name: t('chart.C07.other'), color: palette.strongSoft, symbol: 'square' as const }]
      : []),
    ...(items.some((i) => !isOption(i))
      ? [{ name: t('chart.C07.holdLegend'), color: palette.grayed, symbol: 'square' as const }]
      : []),
  ];
}

export function toTable(data: C07Data): DataTable {
  const items = data.decision?.items ?? [];
  const showTie = tieShown(data);
  return {
    columns: [
      { key: 'name', header: t('chart.col.name') },
      { key: 'prob', header: t('chart.col.prob'), unit: 'prob' },
      { key: 'flags', header: t('chart.col.flags') },
    ],
    rows: items.map((item) => ({
      name: item.label,
      prob: item.prob,
      flags: flagsOf(item, showTie).join(' · '),
    })),
  };
}
