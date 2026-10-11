import { t, tDynamic } from '@/i18n';
import type { IntakeLike } from '@/lib/contract';
import { formatDate, kstDay } from '@/lib/format';
import { Badge } from './Badge';

export interface IntakeBadgeProps {
  /** 표시값 intake(우선순위 human_check > official_popup > headless_shot). null → "접수 상태 확인 불가" */
  intake: IntakeLike | null | undefined;
  /** 경로(공식 팝업·사람 확인 …)를 함께 보일지 (기본 true) */
  showPath?: boolean;
  /** 확인 시각 D± 기준일 */
  asof?: string | null;
  className?: string;
}

/** 확인 시각 → KST 날짜(D15-7·D16-5, 8차 m13 — 앞 10자 UTC 날짜 금지) */
const dayOf = (iso: string | null | undefined) => (iso ? kstDay(iso) : null);

/** 상태 문구. 계약 intake.json: 확인 불가 → '확인 불가(<reason>, <날짜>)' */
export function intakeStatusText(intake: IntakeLike): string {
  const status = tDynamic(`intake.status.${intake.status}`, intake.status);
  if (!intake.reason || (intake.status !== '확인 불가' && intake.status !== '불가')) return status;
  const date = dayOf(intake.checked_at);
  return date
    ? t('intake.withReasonDate', { status, reason: intake.reason, date })
    : t('intake.withReason', { status, reason: intake.reason });
}

/**
 * 접수 상태 배지: "접수 가능 · 공식 팝업" / "접수 가능 · 사람 확인"(human_check = '사람' 접두).
 * 가능 = 강조, 불가 = 보통, 미정·확인 불가 = 회색. 의미는 항상 글자로.
 */
export function IntakeBadge({ intake, showPath = true, asof, className }: IntakeBadgeProps) {
  if (!intake) {
    return (
      <Badge tone="muted" className={className} data-testid="intake-badge">
        {t('intake.none')}
      </Badge>
    );
  }
  const status = intakeStatusText(intake);
  const path = tDynamic(`intake.path.${intake.path}`, intake.path);
  const tone = intake.status === '가능' ? 'strong' : intake.status === '불가' ? 'neutral' : 'muted';
  const title = intake.checked_at ? formatDate(intake.checked_at, asof) : undefined;
  return (
    <Badge tone={tone} className={className} title={title} data-testid="intake-badge">
      {showPath ? `${status} · ${path}` : status}
    </Badge>
  );
}
