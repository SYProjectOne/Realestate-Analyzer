import { t, type TKey } from '@/i18n';
import type { Label } from '@/lib/contract';
import { formatUnknown } from '@/lib/format';

export interface LabelBadgeProps {
  label: Label;
  /** 사람 확인(human_check)으로 확정된 값 → "사람 확인됨" (RA §3: 라벨이 아니라 접두어) */
  human?: boolean;
  /** '확인 불가'의 사유 또는 다른 라벨의 한정어(예 "대체·보정 c=0.015") */
  reason?: string | null;
  /** 확인일 — '확인 불가(사유, 확인일)'에 쓴다 */
  checkedAt?: string | null;
  /**
   * 줄이지 않고 전문을 보인다(출처 패널의 '라벨' 줄). 기본은 사유가 40자를 넘으면 화면에서 줄이고 title 에 전문(P3).
   */
  full?: boolean;
  /** 좁은 칸(카드)에서 줄바꿈 허용 — 긴 라벨이 칸 밖으로 넘치지 않게(P3) */
  wrap?: boolean;
  className?: string;
}

const LABEL_KEYS: Record<Label, TKey> = {
  확인됨: 'label.confirmed',
  추정: 'label.estimated',
  비공식: 'label.unofficial',
  재가공: 'label.reprocessed',
  '확인 불가': 'label.unknown',
};

/** 화면에서 줄이기 시작하는 사유 길이(P3 — 긴 사유가 카드 밖으로 넘쳐 가로 스크롤을 만들던 결함) */
export const LABEL_REASON_MAX = 40;

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

/**
 * 수치 라벨(D7 — 색이 아니라 글자가 의미를 나른다).
 * D28-2(P3): '확인됨'은 작은 회색 글자(`data-tone="quiet"`, 테두리 없음) — 글자는 그대로 남는다.
 * 추정·비공식·재가공·확인 불가·사람 확인은 테두리 배지(`data-tone="badge"`)로 눈에 띈다.
 */
export function LabelBadge({
  label,
  human = false,
  reason,
  checkedAt,
  full = false,
  wrap = false,
  className = '',
}: LabelBadgeProps) {
  const text = labelText(label, reason, human, checkedAt);
  const long = !full && (reason?.length ?? 0) > LABEL_REASON_MAX;
  const shown = long ? t('label.truncated', { text: text.slice(0, LABEL_REASON_MAX) }) : text;
  const title = long ? text : undefined;
  const space = long || wrap ? 'whitespace-normal' : 'whitespace-nowrap';
  if (label === '확인됨' && !human) {
    return (
      <span
        data-testid="label-badge"
        data-tone="quiet"
        title={title}
        className={`inline-flex items-center text-[11px] leading-4 text-muted ${space} ${className}`}
      >
        {shown}
      </span>
    );
  }
  const tone = label === '추정' || human ? 'border-border text-fg' : 'border-border text-grayed';
  return (
    <span
      data-testid="label-badge"
      data-tone="badge"
      title={title}
      className={`inline-flex items-center rounded-sm border px-1.5 py-px text-[11px] leading-4 ${tone} ${space} ${className}`}
    >
      {shown}
    </span>
  );
}
