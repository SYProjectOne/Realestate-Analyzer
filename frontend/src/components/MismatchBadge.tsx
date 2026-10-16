import { t } from '@/i18n';
import { Badge } from './Badge';

export interface MismatchBadgeProps {
  /** decision.mismatch — 요건 사전 계산(req_*_pre)과 판정기(req_*_judge) 불일치 */
  mismatch: boolean;
}

/** "근거와 달라요"(증거와 상이) 배지. mismatch=false면 렌더하지 않는다. */
export function MismatchBadge({ mismatch }: MismatchBadgeProps) {
  return mismatch ? (
    <Badge tone="caution" data-testid="mismatch-badge">
      {t('badge.mismatch')}
    </Badge>
  ) : null;
}
