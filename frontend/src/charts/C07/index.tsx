import { Badge } from '@/components/Badge';
import { CachedBadge } from '@/components/CachedBadge';
import { MismatchBadge } from '@/components/MismatchBadge';
import { TieBadge } from '@/components/TieBadge';
import { t } from '@/i18n';
import type { IsoDate } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import {
  buildOption,
  confidenceText,
  confidenceValue,
  emptyReason,
  hasMismatch,
  isEscaped,
  isTie,
  isUnresolved,
  legendItems,
  toTable,
} from './buildOption';
import type { C07Data } from './types';

export interface C07DecisionProps {
  data: C07Data;
  height?: number;
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C07.source` */
  source?: string;
  /** 제목 뒤에 붙일 말(보통 상황 이름) — "판정기 확률 · {상황}" */
  titleSuffix?: string | null;
}

/** C7 판정기 확률 — decide prob + escape, confidence, TieBadge(conf<0.6), MismatchBadge (G4, G5). escaped면 질문 텍스트 */
export function C07Decision({ data, height, asof, source, titleSuffix }: C07DecisionProps) {
  const palette = useChartPalette();
  const title = titleSuffix ? `${t('chart.C07.title')} · ${titleSuffix}` : t('chart.C07.title');
  const d = data.decision;
  const items = d?.items ?? [];
  const h = height ?? Math.max(150, 56 + items.length * 34);
  return (
    <ChartFrame
      title={title}
      subtitle={confidenceText(data) ?? undefined}
      labels={collectLabels([...items.map((item) => item.prob), d?.confidence ?? null])}
      badges={
        <>
          <TieBadge tie={isTie(data)} confidence={confidenceValue(data)} />
          <MismatchBadge mismatch={hasMismatch(data)} />
          <CachedBadge cached={d?.cached ?? false} />
          {isEscaped(data) ? (
            <Badge tone="strong" data-testid="escaped-badge">
              {t('chart.C07.escape')}
            </Badge>
          ) : null}
          {isUnresolved(data) ? (
            <Badge tone="muted" data-testid="unresolved-badge">
              {t('chart.C07.unresolved')}
            </Badge>
          ) : null}
        </>
      }
      legend={legendItems(data, { palette })}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C07.source')}
    >
      <EChart option={buildOption(data, { palette })} height={h} ariaLabel={title} />
    </ChartFrame>
  );
}
