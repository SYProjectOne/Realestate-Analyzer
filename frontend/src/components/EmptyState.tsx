import type { ReactNode } from 'react';
import { formatUnknown } from '@/lib/format';

export interface EmptyStateProps {
  /** 사유. 있으면 "확인 불가(사유)", 없으면 "확인 불가" */
  reason?: string | null;
  /** 확인일. 사유와 함께 있으면 "확인 불가(사유, 확인일)" (계약 fact.json 규칙 1) */
  checkedAt?: string | null;
  /** 사유 대신 통째로 바꿀 문구(예: 차트 "비교군 없음(사유)", "본청약만") */
  message?: string;
  /** true면 표 셀·문장 안에 들어가는 span */
  inline?: boolean;
  /** 블록 모드에서 문구 아래 둘 행동(버튼 등) */
  children?: ReactNode;
  className?: string;
}

/** 빈 값 표시 — D7 "빈 값은 확인 불가(사유)". */
export function EmptyState({
  reason,
  checkedAt,
  message,
  inline = false,
  children,
  className = '',
}: EmptyStateProps) {
  const text = message ?? formatUnknown(reason, checkedAt);
  if (inline) {
    return (
      <span className={`text-grayed ${className}`} data-testid="empty-state">
        {text}
      </span>
    );
  }
  return (
    <div
      role="status"
      data-testid="empty-state"
      className={`flex flex-col items-center justify-center gap-2 rounded-sm border border-dashed border-border p-6 text-sm text-grayed ${className}`}
    >
      <p>{text}</p>
      {children}
    </div>
  );
}
