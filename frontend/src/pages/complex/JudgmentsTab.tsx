import type { JudgmentEnvelope } from '@/api/types';
import { Badge, CachedBadge, EmptyState } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatConfidence, formatDate, formatNumber } from '@/lib/format';
import { enumText, idText, isUnresolved, tdClass, thClass } from '../_shared';

const COLS = ['seq', 'tool', 'purpose', 'status', 'confidence', 'duration', 'createdAt'] as const;

/** G3 JudgmentLogTab — 봉투 목록. review/escaped/blocked/error는 회색 + "미해결", 캐시는 배지 */
export function JudgmentsTab({ judgments, asof }: { judgments: JudgmentEnvelope[]; asof: string }) {
  if (judgments.length === 0) return <EmptyState message={t('page.G3.judgment.none')} />;
  return <JudgmentTable judgments={judgments} asof={asof} />;
}

export function JudgmentTable({
  judgments,
  asof,
  caption,
}: {
  judgments: JudgmentEnvelope[];
  asof?: string | null;
  caption?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm" aria-label={caption}>
        <thead>
          <tr>
            {COLS.map((k) => (
              <th key={k} scope="col" className={thClass}>
                {t(`page.G3.judgment.${k}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {judgments.map((env, i) => {
            const unresolved = isUnresolved(env.status);
            return (
              <tr
                key={`${env.judgment_seq ?? 'x'}-${env.input_hash}-${i}`}
                className={unresolved ? 'text-grayed' : ''}
                data-unresolved={unresolved || undefined}
              >
                <td className={tdClass}>{idText(env.judgment_seq)}</td>
                <td className={tdClass}>{env.tool}</td>
                <td className={`${tdClass} break-all`}>{env.purpose}</td>
                <td className={tdClass}>
                  <span className="inline-flex flex-wrap gap-1">
                    <Badge tone={unresolved ? 'muted' : 'neutral'}>
                      {enumText('page.common.status', env.status)}
                    </Badge>
                    {unresolved ? <Badge tone="muted">{t('page.common.unresolved')}</Badge> : null}
                    <CachedBadge cached={env.cached} />
                  </span>
                  {env.error_text ? <span className="block text-xs">{env.error_text}</span> : null}
                </td>
                <td className={tdClass}>
                  {env.confidence === null ? t('empty.unknown') : formatConfidence(env.confidence)}
                </td>
                <td className={tdClass}>
                  {env.duration_ms === null
                    ? t('empty.unknown')
                    : t('page.G3.judgment.ms', { ms: formatNumber(env.duration_ms) })}
                </td>
                <td className={tdClass}>{formatDate(env.created_at, asof)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
