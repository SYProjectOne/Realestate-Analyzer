import type { DataTable } from '@/components/DataTableToggle';
import { t } from '@/i18n';
import type { Decision } from '@/lib/contract';
import { formatConfidence, formatProb } from '@/lib/format';
import { axisStyle, baseOption, DEFAULT_PALETTE, tooltipStyle } from '../palette';
import type { BuildOptionContext, EChartsOption } from '../types';
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

/** 항목 표시 글자 — 선택·동률은 서버 값 그대로(동률은 확정 봉투일 때만) */
function flagsOf(item: Decision, showTie: boolean): string[] {
  return [
    item.chosen ? t('chart.chosen') : null,
    showTie && item.tie ? t('badge.tie') : null,
    item.mismatch ? t('badge.mismatch') : null,
    isCandidate(item) ? null : t('chart.C07.escape'),
  ].filter((x): x is string => x !== null);
}

/** 가로 막대: 후보(단지)별 prob + escape 선택지(대기·질문·추가 조사, 회색). 선택 = 강조색 + "선택" 글자 */
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
    grid: { left: 148, right: 96, top: 16, bottom: 28 },
    tooltip: {
      trigger: 'item',
      ...tooltipStyle(palette),
      formatter: (p: unknown) => {
        const item = items[(p as { dataIndex: number }).dataIndex];
        if (!item) return '';
        const prob = num(item.prob);
        const lines = [
          escapeHtml(item.label),
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
      ...axis,
      axisLabel: { ...axis.axisLabel, formatter: (v: number) => formatProb(v) },
    },
    yAxis: {
      type: 'category',
      data: items.map((item) => item.label),
      inverse: true,
      ...axis,
      axisLabel: { ...axis.axisLabel, fontSize: 10, width: 136, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        id: 'decide',
        name: t('chart.C07.title'),
        barMaxWidth: 16,
        label: {
          show: true,
          position: 'right',
          color: palette.fg,
          formatter: (p: { dataIndex: number; value: unknown }) => {
            const item = items[p.dataIndex];
            const v = typeof p.value === 'number' ? formatProb(p.value) : t('empty.unknown');
            if (gray) return `${v} · ${t('badge.unresolved')}`;
            const flags = item
              ? flagsOf(item, showTie).filter((f) => f !== t('chart.C07.escape'))
              : [];
            return [v, ...flags].join(' · ');
          },
        },
        data: items.map((item) => ({
          value: num(item.prob),
          itemStyle: {
            color:
              gray || !isCandidate(item)
                ? palette.grayed
                : item.chosen
                  ? palette.strong
                  : palette.muted,
          },
        })),
      },
    ],
  };
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
