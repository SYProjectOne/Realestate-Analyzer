import type { FactLike } from '@/lib/contract';
import { formatFactValue, unitFromHint, type FactUnit, type IsoDate } from '@/lib/format';
import { EmptyState } from './EmptyState';
import { LabelBadge } from './LabelBadge';
import { useOpenProvenance } from './provenanceContext';

export interface FactCellProps {
  /** 계약의 Fact. null/undefined 또는 v=null이면 "확인 불가(사유, 확인일)" */
  fact: FactLike | null | undefined;
  /** 표시 단위 (src/lib/format.ts FactUnit). 생략하면 계약 `fact.unit` 힌트를 따른다 */
  unit?: FactUnit;
  /** 날짜 D± 기준일(보통 스냅샷 asof_date) */
  asof?: IsoDate | null;
  /** 소수 자릿수 덮어쓰기 */
  digits?: number;
  /**
   * 라벨 배지 표시 (기본 true). 화면 코드에서 false 는 lint(no-raw-number-render, R3 minor 27)가 막는다 —
   * 모든 수치는 라벨과 함께 보인다. 갤러리·테스트 전용.
   */
  showLabel?: boolean;
  /** fact 자체가 없을 때 사유 */
  emptyReason?: string;
  /** 클릭 시 출처 패널 열기. 생략하면 앱 전역 ProvenancePanel(context)을 연다 */
  onOpenProvenance?: (prov: string) => void;
  /**
   * 이 Fact 가 나온 리비전(출처 조회 `?snapshot_id=`, D15-8). 보고 있는 리비전과 다른 리비전의 값(G5 '이후' 열 등)이면
   * 넘긴다. 생략하면 연 순간 보고 있는 리비전.
   */
  provSnapshotId?: string | null;
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
  provSnapshotId,
  className = '',
}: FactCellProps) {
  const contextOpen = useOpenProvenance();
  const open: ((prov: string) => void) | null =
    onOpenProvenance ??
    (contextOpen
      ? (prov: string) =>
          provSnapshotId === undefined ? contextOpen(prov) : contextOpen(prov, provSnapshotId)
      : null);
  const resolvedUnit = unit ?? unitFromHint(fact?.unit, fact?.v);
  const text = fact ? formatFactValue(fact, resolvedUnit, { asof, digits }) : null;

  const content =
    text === null ? (
      // 값이 없으면 라벨 배지 대신 "확인 불가(사유, 확인일)" 한 번만
      <EmptyState
        inline
        reason={fact?.reason ?? emptyReason}
        checkedAt={fact ? fact.checked_at : null}
      />
    ) : (
      <>
        <span className="tabular-nums">{text}</span>
        {showLabel && fact ? (
          <LabelBadge
            label={fact.label}
            human={fact.human}
            reason={fact.reason}
            checkedAt={fact.checked_at}
          />
        ) : null}
      </>
    );

  const prov = fact?.prov ?? null;
  const base = `inline-flex items-center gap-1 ${className}`;
  if (prov && open) {
    return (
      <button
        type="button"
        className={`${base} rounded-sm text-left underline decoration-dotted underline-offset-4 hover:decoration-solid focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent`}
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
