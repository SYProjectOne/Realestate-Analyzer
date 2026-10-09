import type { Label } from '@/api/types';
import { t, type TKey } from '@/i18n';
import { Badge } from './Badge';

export interface LabelBadgeProps {
  label: Label;
  /** 사람 확인(human_check)으로 확정된 값 → "사람 확인됨" (RA §3: 라벨이 아니라 접두어) */
  human?: boolean;
  /** label이 "확인 불가"일 때 사유 → "확인 불가(사유)" */
  reason?: string | null;
  className?: string;
}

const LABEL_KEYS: Record<Label, TKey> = {
  확인됨: 'label.confirmed',
  추정: 'label.estimated',
  비공식: 'label.unofficial',
  재가공: 'label.reprocessed',
  '확인 불가': 'label.unknown',
};

export function labelText(label: Label, reason?: string | null, human?: boolean): string {
  if (label === '확인 불가' && reason) return t('label.unknownWithReason', { reason });
  const base = t(LABEL_KEYS[label]);
  return human ? t('label.humanPrefix', { label: base }) : base;
}

/** 수치 라벨(확인됨·추정·비공식·재가공·확인 불가)을 텍스트 배지로. 비공식·재가공·확인 불가는 회색. */
export function LabelBadge({ label, human = false, reason, className }: LabelBadgeProps) {
  const tone = label === '확인됨' ? 'neutral' : label === '추정' ? 'neutral' : 'muted';
  return (
    <Badge tone={tone} className={className} data-testid="label-badge">
      {labelText(label, reason, human)}
    </Badge>
  );
}
