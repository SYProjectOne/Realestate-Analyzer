import type { JudgmentEnvelope } from '@/api/types';
import { Badge, CachedBadge, EmptyState, MetaText, MetaValue } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { enumText, idText, isUnresolved, tdClass, thClass } from '../_shared';

const COLS = [
  'seq',
  'tool',
  'purpose',
  'status',
  'model',
  'confidence',
  'duration',
  'createdAt',
] as const;

/**
 * G3 JudgmentLogTab — 봉투 목록. review/escaped/blocked/error는 회색 + "미해결", 캐시는 배지.
 * 계약 .15 F1(D18-1·D20-1): '모델' 열 = 그 응답의 실제 `model`, `provider='none'`(판정기가 모델을 부르지 않은 로컬 처리 —
 * 비용 없음)이면 '로컬' 배지, 그 밖의 provider 는 괄호로. 둘 다 없으면(blocked·error·.15 이전 행) '기록 없음'.
 * 캐시 키(adapter_version)의 고정 모델과 다를 수 있다(G7 통계의 어댑터 배지가 고정 모델).
 */
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
                <td
                  className={tdClass}
                  data-testid={`judgment-model-${env.judgment_seq ?? `i${i}`}`}
                >
                  <ModelCell model={env.model ?? null} provider={env.provider ?? null} />
                </td>
                <td className={tdClass}>
                  {env.confidence === null ? (
                    t('empty.unknown')
                  ) : (
                    <MetaValue kind="confidence" value={env.confidence} as="confidence" />
                  )}
                </td>
                <td className={tdClass}>
                  {env.duration_ms === null ? (
                    t('empty.unknown')
                  ) : (
                    <MetaText
                      kind="duration"
                      k="page.G3.judgment.ms"
                      params={{ ms: { n: env.duration_ms, as: 'number' } }}
                    />
                  )}
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

function ModelCell({ model, provider }: { model: string | null; provider: string | null }) {
  if (model === null && provider === null) {
    return <span className="text-xs text-muted">{t('page.G3.judgment.modelNone')}</span>;
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {model !== null ? <span className="break-all">{model}</span> : null}
      {provider === 'none' ? (
        <Badge tone="muted" title={t('page.G3.judgment.localHint')}>
          {t('page.G3.judgment.local')}
        </Badge>
      ) : provider !== null ? (
        <span className="text-xs text-muted">{t('page.G3.judgment.provider', { provider })}</span>
      ) : null}
    </span>
  );
}
