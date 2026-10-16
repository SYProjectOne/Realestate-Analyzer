import { t, type TKey } from '@/i18n';
import type { Label } from '@/lib/contract';
import { formatUnknown, unknownTitle, type ReasonCode } from '@/lib/format';

export interface LabelBadgeProps {
  label: Label;
  /** 사람 확인(human_check)으로 확정된 값 → "사람 확인됨" (RA §3: 라벨이 아니라 접두어) */
  human?: boolean;
  /** '확인 불가'의 사유 또는 다른 라벨의 한정어(예 "대체·보정 c=0.015") */
  reason?: string | null;
  /** 확인일 — '확인 불가(사유, 확인일)'에 쓴다 */
  checkedAt?: string | null;
  /** 계약 .20 사유 코드 — '확인 불가' 사유를 쉬운 말로(P7). 없으면 서버 사유 그대로 */
  reasonCode?: ReasonCode | null;
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
  raw = false,
  code?: ReasonCode | null,
): string {
  if (label === '확인 불가') return formatUnknown(reason, checkedAt, { raw, code });
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
  reasonCode,
  full = false,
  wrap = false,
  className = '',
}: LabelBadgeProps) {
  // 출처 패널(full)은 서버 사유 그대로(P7 — 원 사유가 1클릭 안에 있다)
  const text = labelText(label, reason, human, checkedAt, full, reasonCode);
  const long = !full && (reason?.length ?? 0) > LABEL_REASON_MAX;
  const shown = long ? t('label.truncated', { text: text.slice(0, LABEL_REASON_MAX) }) : text;
  // title: 줄였으면 전문, 사유를 쉬운 말로 바꿨으면 원 사유(P3·P7)
  const original = !full && label === '확인 불가' ? unknownTitle(reason, reasonCode) : undefined;
  const title = [long ? text : null, original ?? null].filter(Boolean).join(' · ') || undefined;
  const space = long || wrap ? 'whitespace-normal' : 'whitespace-nowrap';
  if (label === '확인됨' && !human) {
    return (
      <span
        data-testid="label-badge"
        data-tone="quiet"
        title={title}
        className={`inline-flex items-center align-middle text-[11px] font-medium leading-4 text-muted ${space} ${className}`}
      >
        {shown}
      </span>
    );
  }
  // 목업 §3: 추정·비공식·재가공·확인 불가·사람 확인됨 = 점선 테두리 배지(주의 색). 추정이 아닌 것은 글자를 조금 낮춘다
  const tone = label === '추정' || human ? 'font-semibold' : 'font-medium';
  return (
    <span
      data-testid="label-badge"
      data-tone="badge"
      title={title}
      className={`inline-flex max-w-full items-center rounded border border-dashed border-est-border px-1.5 py-px align-middle text-[11px] leading-4 text-est ${tone} ${space} ${className}`}
    >
      {shown}
    </span>
  );
}
