import { t } from '@/i18n';
import { Badge } from './Badge';

export interface CachedBadgeProps {
  /** JudgmentEnvelope.cached — 같은 input_hash의 이전 결과를 돌려준 것(RA §4-1) */
  cached: boolean;
}

/** "캐시" 배지. cached=false면 렌더하지 않는다. */
export function CachedBadge({ cached }: CachedBadgeProps) {
  return cached ? (
    <Badge tone="muted" data-testid="cached-badge">
      {t('badge.cached')}
    </Badge>
  ) : null;
}
