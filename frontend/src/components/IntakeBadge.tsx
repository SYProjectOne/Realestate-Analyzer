import type { Intake } from '@/api/types';
import { t, tDynamic } from '@/i18n';
import { formatDate } from '@/lib/format';
import { Badge } from './Badge';

export interface IntakeBadgeProps {
  /** 표시값 intake(우선순위 human_check > official_popup > headless_shot). null → "접수 상태 확인 불가" */
  intake: Intake | null | undefined;
  /** 경로(공식 팝업·사람 확인 …)를 함께 보일지 (기본 true) */
  showPath?: boolean;
  /** 확인 시각 D± 기준일 */
  asof?: string | null;
  className?: string;
}

/** 접수 상태 배지: "접수 가능 · 공식 팝업". 가능 = 강조, 미정·확인 불가 = 회색. */
export function IntakeBadge({ intake, showPath = true, asof, className }: IntakeBadgeProps) {
  if (!intake) {
    return (
      <Badge tone="muted" className={className} data-testid="intake-badge">
        {t('intake.none')}
      </Badge>
    );
  }
  const status = tDynamic(`intake.status.${intake.status}`, intake.status);
  const path = tDynamic(`intake.path.${intake.path}`, intake.path);
  const tone = intake.status === '가능' ? 'strong' : intake.status === '불가' ? 'neutral' : 'muted';
  const title = intake.checked_at ? formatDate(intake.checked_at, asof) : undefined;
  return (
    <Badge tone={tone} className={className} title={title} data-testid="intake-badge">
      {showPath ? `${status} · ${path}` : status}
    </Badge>
  );
}
