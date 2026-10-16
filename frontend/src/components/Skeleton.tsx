import { t } from '@/i18n';

export interface SkeletonProps {
  /** 뼈대 줄 수(기본 3) */
  lines?: number;
  /** 보이는 글("불러오는 중…") — 기본 app.loading */
  label?: string;
  /** 카드 안에 그릴지(기본 true) */
  card?: boolean;
  className?: string;
}

const WIDTHS = ['w-3/5', 'w-11/12', 'w-3/4', 'w-2/3', 'w-5/6'];

/** 불러오는 중 뼈대(목업 §7 첫 카드): 회색 줄 + "불러오는 중…"(role=status). 줄은 장식(aria-hidden) */
export function Skeleton({ lines = 3, label, card = true, className = '' }: SkeletonProps) {
  return (
    <div
      role="status"
      data-testid="skeleton"
      className={`flex flex-col gap-2.5 ${card ? 'rounded-2xl border border-border bg-surface p-4 sm:p-[18px]' : ''} ${className}`}
    >
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          aria-hidden
          className={`block h-3 rounded-md bg-chip motion-safe:animate-pulse ${WIDTHS[i % WIDTHS.length]}`}
        />
      ))}
      <span className="text-[13px] text-muted">{label ?? t('app.loading')}</span>
    </div>
  );
}
