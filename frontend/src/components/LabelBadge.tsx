import { t, type TKey } from '@/i18n';
import type { Label } from '@/lib/contract';
import { formatUnknown } from '@/lib/format';
import { Badge } from './Badge';

export interface LabelBadgeProps {
  label: Label;
  /** 사람 확인(human_check)으로 확정된 값 → "사람 확인됨" (RA §3: 라벨이 아니라 접두어) */
  human?: boolean;
  /** '확인 불가'의 사유 또는 다른 라벨의 한정어(예 "대체·보정 c=0.015") */
  reason?: string | null;
  /** 확인일 — '확인 불가(사유, 확인일)'에 쓴다 */
  checkedAt?: string | null;
  className?: string;
}

const LABEL_KEYS: Record<Label, TKey> = {
  확인됨: 'label.confirmed',
  추정: 'label.estimated',
  비공식: 'label.unofficial',
  재가공: 'label.reprocessed',
  '확인 불가': 'label.unknown',
};

/**
 * 계약 fact.json 표시 문자열 규칙:
 *  1. '확인 불가' → '확인 불가(<reason>, <checked_at>)' (확인일 없으면 '확인 불가(<reason>)')
 *  2. 그 밖에 reason이 있으면 '<label>(<reason>)'
 *  3. reason이 없으면 '<label>', human=true면 '사람 확인됨'
 */
export function labelText(
  label: Label,
  reason?: string | null,
  human?: boolean,
  checkedAt?: string | null,
): string {
  if (label === '확인 불가') return formatUnknown(reason, checkedAt);
  const base = t(LABEL_KEYS[label]);
  const named = human ? t('label.humanPrefix', { label: base }) : base;
  return reason ? t('label.withReason', { label: named, reason }) : named;
}

/** 수치 라벨을 텍스트 배지로(색이 아니라 글자가 의미를 나른다). 비공식·재가공·확인 불가는 회색. */
export function LabelBadge({
  label,
  human = false,
  reason,
  checkedAt,
  className,
}: LabelBadgeProps) {
  const tone = label === '확인됨' || label === '추정' ? 'neutral' : 'muted';
  return (
    <Badge tone={tone} className={className} data-testid="label-badge">
      {labelText(label, reason, human, checkedAt)}
    </Badge>
  );
}
