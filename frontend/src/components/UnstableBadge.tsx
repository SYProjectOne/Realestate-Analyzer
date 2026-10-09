import { t } from '@/i18n';
import { Badge } from './Badge';

export interface UnstableBadgeProps {
  /** score_total.unstable / Sensitivity.unstable — 가중치 ±10%p에서 TOP 5 구성 변동 */
  unstable: boolean;
}

/** "순위 불안정" 배지. unstable=false면 렌더하지 않는다. */
export function UnstableBadge({ unstable }: UnstableBadgeProps) {
  return unstable ? (
    <Badge tone="strong" data-testid="unstable-badge">
      {t('badge.unstable')}
    </Badge>
  ) : null;
}
