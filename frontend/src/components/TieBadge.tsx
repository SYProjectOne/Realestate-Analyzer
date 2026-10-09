import { t } from '@/i18n';
import { metaText } from '@/lib/meta';
import { Badge } from './Badge';

export interface TieBadgeProps {
  /** decision.tie(conf < 0.6) 또는 score_total.tie_group 존재 */
  tie: boolean;
  /** decide confidence(0~1). 있으면 "동률(신뢰도 0.48)" */
  confidence?: number | null;
}

/** "동률" 배지. tie=false면 렌더하지 않는다. */
export function TieBadge({ tie, confidence }: TieBadgeProps) {
  if (!tie) return null;
  const text =
    confidence === null || confidence === undefined
      ? t('badge.tie')
      : metaText('badge.tieWithConfidence', { confidence: { n: confidence, as: 'confidence' } });
  return (
    <Badge tone="strong" data-testid="tie-badge">
      {text}
    </Badge>
  );
}
