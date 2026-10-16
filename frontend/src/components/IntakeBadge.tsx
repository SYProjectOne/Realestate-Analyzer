import { t, tDynamic } from '@/i18n';
import type { IntakeLike } from '@/lib/contract';
import { formatDate, kstDay, plainReason, unknownTitle } from '@/lib/format';
import { StatusPill, type StatusPillTone } from './StatusPill';

export interface IntakeBadgeProps {
  /** 표시값 intake(우선순위 human_check > official_popup > headless_shot). null → "접수 상태 확인 불가" */
  intake: IntakeLike | null | undefined;
  /** 경로(공식 팝업·사람 확인 …)를 함께 보일지 (기본 true) */
  showPath?: boolean;
  /** 확인 시각 D± 기준일 */
  asof?: string | null;
  /**
   * 사유를 배지 밖 아래 작은 글씨로(R9-UI P4 G2 접수 칸 — 긴 사유가 배지 폭을 키우던 결함). 배지는 상태만,
   * 사유·확인일은 아래 줄(쉬운 말, 원 사유 title).
   */
  reasonBelow?: boolean;
  className?: string;
}

/** 확인 시각 → KST 날짜(D15-7·D16-5, 8차 m13 — 앞 10자 UTC 날짜 금지) */
const dayOf = (iso: string | null | undefined) => (iso ? kstDay(iso) : null);

/** 상태 문구. 계약 intake.json: 확인 불가 → '확인 불가(<reason>, <날짜>)' */
export function intakeStatusText(intake: IntakeLike): string {
  const status = tDynamic(`intake.status.${intake.status}`, intake.status);
  if (!intake.reason || (intake.status !== '확인 불가' && intake.status !== '불가')) return status;
  const date = dayOf(intake.checked_at);
  // P7: 사유는 쉬운 말(원 사유는 배지 title)
  const reason = plainReason(intake.reason, intake.reason_code).text;
  return date
    ? t('intake.withReasonDate', { status, reason, date })
    : t('intake.withReason', { status, reason });
}

/**
 * 접수 상태 배지: "접수 가능 · 공식 팝업" / "접수 가능 · 사람 확인"(human_check = '사람' 접두).
 * 목업 §4 알약: 가능 = 주색 바탕 + 점, 미정 = 테두리, 확인 불가 = 회색 바탕, 불가 = 회색 + 취소선(사유가 없을 때).
 * 의미는 항상 글자로(D7) — 경로(어떻게 확인했나)는 같은 알약 안 옅은 글자.
 */
export function IntakeBadge({
  intake,
  showPath = true,
  asof,
  reasonBelow = false,
  className,
}: IntakeBadgeProps) {
  if (!intake) {
    return (
      <StatusPill tone="muted" className={className} data-testid="intake-badge">
        {t('intake.none')}
      </StatusPill>
    );
  }
  const below =
    reasonBelow && !!intake.reason && (intake.status === '확인 불가' || intake.status === '불가');
  const status = below
    ? tDynamic(`intake.status.${intake.status}`, intake.status)
    : intakeStatusText(intake);
  const path = tDynamic(`intake.path.${intake.path}`, intake.path);
  const struck =
    intake.status === '불가' && status === tDynamic(`intake.status.${intake.status}`, '');
  const tone: StatusPillTone =
    intake.status === '가능'
      ? 'accent'
      : intake.status === '미정'
        ? 'outline'
        : intake.status === '불가'
          ? 'neutral'
          : 'muted';
  const checked = intake.checked_at ? formatDate(intake.checked_at, asof) : null;
  const original =
    intake.status === '확인 불가' || intake.status === '불가'
      ? unknownTitle(intake.reason, intake.reason_code)
      : undefined;
  // 계약 .20(F9): 공급 종류 근거 문구는 title
  const title =
    [checked, original ?? null, intake.supply_kind_basis ?? null].filter(Boolean).join(' · ') ||
    undefined;
  // 공급 종류(저장 문구 후보가 말한 것만, 서버 값 그대로) — 있으면 '접수 가능(선착순)'
  const shownStatus = intake.supply_kind
    ? t('intake.withSupply', { status, kind: intake.supply_kind })
    : status;
  const badge = (
    <StatusPill
      tone={tone}
      dot={intake.status === '가능'}
      className={className}
      title={title}
      wrap
      data-testid="intake-badge"
    >
      {struck ? (
        // 접수 불가(사유 없음)는 상태 글자만 취소선 — 경로 글자까지 긋지 않는다
        <span>
          <span className="line-through">{shownStatus}</span>
          {showPath ? ` · ${path}` : null}
        </span>
      ) : (
        // 글자는 한 덩어리("접수 가능 · 공식 팝업") — 화면 낭독기·검색이 한 번에 읽는다
        <span>{showPath ? `${shownStatus} · ${path}` : shownStatus}</span>
      )}
    </StatusPill>
  );
  if (!below || !intake.reason) return badge;
  const date = dayOf(intake.checked_at);
  const reason = plainReason(intake.reason, intake.reason_code).text;
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      {badge}
      <span data-testid="intake-reason" className="text-xs text-muted" title={original}>
        {date ? t('intake.reasonDate', { reason, date }) : reason}
      </span>
    </span>
  );
}
