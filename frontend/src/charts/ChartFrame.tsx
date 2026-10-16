import type { ReactNode } from 'react';
import type { DataTable } from '@/components/DataTableToggle';
import { EmptyState } from '@/components/EmptyState';
import { LabelBadge } from '@/components/LabelBadge';
import { t } from '@/i18n';
import type { Label } from '@/lib/contract';
import type { IsoDate } from '@/lib/format';
import { ChartLegend } from './ChartLegend';
import { ChartFooter } from './ChartTable';
import type { ChartLegendItem } from './types';

export interface ChartFrameProps {
  /** 차트 제목(ko.json `chart.Cxx.title`) */
  title: string;
  /** 부제(목표 시점·월말 기준 등 한 줄) */
  subtitle?: string;
  /** 데이터에 쓰인 라벨들 — 중복 제거해 텍스트 배지로 */
  labels?: readonly Label[];
  /** 추가 배지(UnstableBadge·TieBadge·"표본 n, 추정" 등) */
  badges?: ReactNode;
  /** 차트 위 범례(HTML, 줄바꿈 — 축과 겹치지 않는다). 빈 상태면 그리지 않는다 */
  legend?: readonly ChartLegendItem[];
  /** "표로 보기" 표. 생략하면 토글 없음 */
  table?: DataTable;
  /** non-null이면 차트 대신 빈 상태 문구 */
  emptyReason?: string | null;
  /** 바닥줄 "기준일 …"과 표의 날짜 D± 기준일 */
  asof?: IsoDate | null;
  /** 바닥줄 "자료: …" 출처 설명(쉬운 말). 생략하면 바닥줄은 기준일만(둘 다 없으면 없음) */
  source?: string | null;
  /** 차트 본문(EChart 또는 HTML) */
  children: ReactNode;
  className?: string;
}

/** 바닥줄 글자: "자료: {출처} · 기준일 {날짜}" (값이 있는 것만) */
export function sourceLine(source?: string | null, asof?: IsoDate | null): string | null {
  if (source && asof) return t('chart.sourceAsof', { source, asof });
  if (source) return t('chart.source', { source });
  if (asof) return t('chart.asofOnly', { asof });
  return null;
}

/**
 * 모든 차트의 공용 틀(Shell §8): 제목·라벨 배지·부제 → 범례(위) → 차트(또는 빈 상태) →
 * 바닥줄 "자료: 출처 · 기준일" + [표로 보기] (D7·RA §7-2).
 */
export function ChartFrame({
  title,
  subtitle,
  labels = [],
  badges,
  legend = [],
  table,
  emptyReason = null,
  asof,
  source,
  children,
  className = '',
}: ChartFrameProps) {
  const uniqueLabels = [...new Set(labels)];
  const empty = emptyReason !== null && emptyReason !== undefined;
  return (
    <figure
      className={`m-0 flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-surface p-4 ${className}`}
    >
      <figcaption className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="m-0 text-base font-bold text-fg">{title}</h3>
        {uniqueLabels.map((label) => (
          <LabelBadge key={label} label={label} />
        ))}
        {badges}
        {subtitle ? (
          <span className="w-full text-xs text-muted" data-testid="chart-subtitle">
            {subtitle}
          </span>
        ) : null}
      </figcaption>
      {!empty ? <ChartLegend items={legend} /> : null}
      {empty ? <EmptyState message={emptyReason} /> : children}
      <ChartFooter
        table={table}
        caption={title}
        source={sourceLine(source, asof) ?? undefined}
        asof={asof}
      />
    </figure>
  );
}
