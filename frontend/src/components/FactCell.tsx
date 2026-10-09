import type { Fact, IsoDate } from '@/api/types';
import { formatFactValue, type FactUnit } from '@/lib/format';
import { EmptyState } from './EmptyState';
import { LabelBadge } from './LabelBadge';
import { useOpenProvenance } from './provenanceContext';

export interface FactCellProps {
  /** 계약의 Fact. null/undefined 또는 v=null이면 "확인 불가(사유)" */
  fact: Fact | null | undefined;
  /** 표시 단위 (src/lib/format.ts FactUnit) */
  unit: FactUnit;
  /** 날짜 D± 기준일(보통 스냅샷 asof_date) */
  asof?: IsoDate | null;
  /** 소수 자릿수 덮어쓰기 */
  digits?: number;
  /** 라벨 배지 표시 (기본 true). 표에서 열 머리에 라벨을 따로 둘 때만 끈다 */
  showLabel?: boolean;
  /** fact 자체가 없을 때 사유 */
  emptyReason?: string;
  /** 클릭 시 출처 패널 열기. 생략하면 앱 전역 ProvenancePanel(context)을 연다 */
  onOpenProvenance?: (prov: string) => void;
  className?: string;
}

/**
 * 숫자를 화면에 그리는 유일한 컴포넌트 (RA §7 공통 규칙, ESLint no-raw-number-render).
 * 값 + 라벨 배지, prov가 있으면 버튼이 되어 클릭 시 onOpenProvenance(prov).
 */
export function FactCell({
  fact,
  unit,
  asof,
  digits,
  showLabel = true,
  emptyReason,
  onOpenProvenance,
  className = '',
}: FactCellProps) {
  const contextOpen = useOpenProvenance();
  const open = onOpenProvenance ?? contextOpen;
  const text = fact ? formatFactValue(fact, unit, { asof, digits }) : null;

  const content =
    text === null ? (
      <EmptyState inline reason={fact?.reason ?? emptyReason} />
    ) : (
      <>
        <span className="tabular-nums">{text}</span>
        {showLabel && fact ? (
          <LabelBadge label={fact.label} human={fact.human} reason={fact.reason} />
        ) : null}
      </>
    );

  const prov = fact?.prov ?? null;
  const base = `inline-flex items-center gap-1 ${className}`;
  if (prov && open) {
    return (
      <button
        type="button"
        className={`${base} rounded text-left underline decoration-dotted underline-offset-4 hover:decoration-solid focus:outline-none focus-visible:ring-2 focus-visible:ring-accent`}
        onClick={() => open(prov)}
        data-prov={prov}
      >
        {content}
      </button>
    );
  }
  return (
    <span className={base} data-prov={prov ?? undefined}>
      {content}
    </span>
  );
}
