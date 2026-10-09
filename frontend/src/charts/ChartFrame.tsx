import type { ReactNode } from 'react';
import type { IsoDate, Label } from '@/api/types';
import { DataTableToggle, type DataTable } from '@/components/DataTableToggle';
import { EmptyState } from '@/components/EmptyState';
import { LabelBadge } from '@/components/LabelBadge';

export interface ChartFrameProps {
  /** 차트 제목(ko.json `chart.Cxx.title`) */
  title: string;
  /** 부제(목표 시점·가중치·출처 기준 등) */
  subtitle?: string;
  /** 데이터에 쓰인 라벨들 — 중복 제거해 텍스트 배지로 */
  labels?: readonly Label[];
  /** 추가 배지(UnstableBadge·TieBadge·"표본 n, 추정" 등) */
  badges?: ReactNode;
  /** "표로 보기" 표. 생략하면 토글 없음 */
  table?: DataTable;
  /** non-null이면 차트 대신 빈 상태 문구 */
  emptyReason?: string | null;
  /** 표의 날짜 D± 기준일 */
  asof?: IsoDate | null;
  /** 차트 본문(EChart 또는 HTML) */
  children: ReactNode;
  className?: string;
}

/** 모든 차트의 공용 틀: 제목·라벨 배지·"표로 보기"·빈 상태 (D7·RA §7-2). */
export function ChartFrame({
  title,
  subtitle,
  labels = [],
  badges,
  table,
  emptyReason = null,
  asof,
  children,
  className = '',
}: ChartFrameProps) {
  const uniqueLabels = [...new Set(labels)];
  return (
    <figure
      className={`flex flex-col gap-2 rounded border border-border bg-surface p-3 ${className}`}
    >
      <figcaption className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {uniqueLabels.map((label) => (
          <LabelBadge key={label} label={label} />
        ))}
        {badges}
        {subtitle ? <span className="w-full text-xs text-muted">{subtitle}</span> : null}
      </figcaption>
      {emptyReason !== null ? <EmptyState message={emptyReason} /> : children}
      {table ? <DataTableToggle table={table} caption={title} asof={asof} /> : null}
    </figure>
  );
}
