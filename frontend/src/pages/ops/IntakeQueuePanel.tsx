import { Link, useSearchParams } from 'react-router';
import { useIntakeQueue } from '@/api/hooks';
import type { IntakeQueue, IntakeQueueCategory, IntakeQueueItem } from '@/api/types';
import {
  Badge,
  ExternalLink,
  IntakeBadge,
  MetaText,
  MetaValue,
  RawDocumentPreview,
} from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { QueryState, Section, tdClass, thClass, useGlobalSearch } from '../_shared';
import { HUMAN_CHECK_ANCHOR, humanCheckSearch } from './HumanCheckForm';

/** 처음에 접어 두는 분류 — 점수 대상이 아닌 단지·'미정'(확인 불가보다 급하지 않다) */
const COLLAPSED: ReadonlySet<IntakeQueueCategory> = new Set(['not_judged', 'undecided']);

const COLS = ['complex', 'status', 'http', 'checkedAt', 'evidence', 'action'] as const;

/** 대기열 구역 앵커(다른 화면에서 `/ops#intake-queue` 로 들어올 때) */
export const INTAKE_QUEUE_ANCHOR = 'intake-queue';

/**
 * G7 접수 확인 대기열 (계약 2026-10-09.19 · D26-2) — GET /ops/intake-queue.
 * '확인 불가'·'미정' 표시 접수 행을 서버가 저장된 사유·http_status 로 묶어 준다(화면은 묶지 않는다 — 새 사유는 서버가
 * '기타'로 보낸다). 분류마다 건수, 묶음(사유)마다 건수, 항목마다 단지(G3 링크)·접수 배지·HTTP·확인 시각·근거 페이지·
 * 스크린샷·판정 로그 표식, '사람 확인 입력'(위 HumanCheckForm 을 그 단지·접수 상태로 채움 → POST /ops/human-checks →
 * 재판정 자동 등록, D12-5). 이미 입력했고 새 리비전 발행을 기다리는 단지는 '사람 확인 입력됨 — 재판정·발행 대기'.
 */
export function IntakeQueuePanel({
  regionId,
  snapshotId,
  asof,
}: {
  regionId: number | null;
  snapshotId: string | null;
  asof: string | null;
}) {
  const enabled = regionId !== null || snapshotId !== null;
  const query = useIntakeQueue(regionId, snapshotId, enabled);
  const total = query.data?.total;
  return (
    <Section
      title={t('page.G7.iq.title')}
      id={INTAKE_QUEUE_ANCHOR}
      actions={
        total !== undefined && total > 0 ? (
          <Badge tone="strong" data-testid="intake-queue-total">
            <MetaText kind="count" k="page.G7.iq.total" params={{ n: total }} />
          </Badge>
        ) : null
      }
    >
      <p className="text-xs text-muted">{t('page.G7.iq.intro')}</p>
      {!enabled ? (
        <p className="text-sm text-muted">{t('app.noSnapshot')}</p>
      ) : (
        <QueryState
          query={query}
          empty={(q) =>
            q.snapshot_id === null
              ? t('page.G7.iq.noSnapshot')
              : q.groups.length === 0
                ? t('page.G7.iq.none')
                : null
          }
        >
          {(q) => <QueueBody queue={q} asof={asof ?? q.asof_date} />}
        </QueryState>
      )}
    </Section>
  );
}

function QueueBody({ queue, asof }: { queue: IntakeQueue; asof: string | null }) {
  // 서버 순서(분류 → 건수)를 그대로 쓰고, 같은 분류의 묶음을 한 접이식 구역으로 모은다
  const byCategory = new Map<IntakeQueueCategory, IntakeQueue['groups']>();
  for (const g of queue.groups) {
    byCategory.set(g.category, [...(byCategory.get(g.category) ?? []), g]);
  }
  return (
    <div className="flex flex-col gap-2" data-testid="intake-queue">
      {queue.asof_date ? (
        <p className="text-xs text-muted">
          <MetaText
            kind="seq"
            k="page.G7.iq.basis"
            params={{ date: queue.asof_date, revision: { n: queue.revision ?? 1, as: 'plain' } }}
          />
        </p>
      ) : null}
      {[...byCategory.entries()].map(([category, groups]) => (
        <details
          key={category}
          open={!COLLAPSED.has(category)}
          className="rounded-sm border border-border"
          data-testid={`iq-category-${category}`}
        >
          <summary className="cursor-pointer px-2 py-1 text-sm font-semibold">
            {t(`page.G7.iq.category.${category}` as TKey)} ·{' '}
            <MetaValue kind="count" value={groups.reduce((n, g) => n + g.count, 0)} />
          </summary>
          <div className="flex flex-col gap-3 px-2 pb-2">
            <p className="text-xs text-muted">{t(`page.G7.iq.categoryHint.${category}` as TKey)}</p>
            {groups.map((g) => (
              <div key={`${g.category}:${g.reason}`} className="flex flex-col gap-1">
                <h3 className="text-sm font-medium" data-testid="iq-group">
                  <span data-reason={g.reason}>{g.reason}</span> ·{' '}
                  <MetaText kind="count" k="page.G7.iq.groupCount" params={{ n: g.count }} />
                </h3>
                <ItemTable items={g.items} asof={asof} label={g.reason} />
              </div>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function ItemTable({
  items,
  asof,
  label,
}: {
  items: IntakeQueueItem[];
  asof: string | null;
  label: string;
}) {
  const search = useGlobalSearch();
  const [params] = useSearchParams();
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {COLS.map((k) => (
              <th key={k} scope="col" className={thClass}>
                {t(`page.G7.iq.col.${k}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.intake_id} data-testid="iq-item" data-complex-id={it.complex_id}>
              <th scope="row" className={`${tdClass} text-left font-medium`}>
                <Link to={`/complexes/${it.complex_id}${search}`} className="hover:underline">
                  {it.complex_name}
                </Link>
                {it.human_check_pending ? (
                  <div className="mt-1">
                    <Badge tone="neutral" data-testid="iq-pending">
                      {t('page.G7.iq.pending', {
                        value: it.human_check_pending.value_text,
                        date: formatDate(it.human_check_pending.checked_at, asof),
                      })}
                    </Badge>
                  </div>
                ) : null}
              </th>
              <td className={tdClass}>
                <IntakeBadge intake={it} asof={asof} />
                {it.judgment_ref ? (
                  <div className="mt-1 text-xs text-muted" data-testid="iq-judgment">
                    {t('page.G7.iq.judgment', { ref: it.judgment_ref })}
                  </div>
                ) : null}
              </td>
              <td className={tdClass}>
                {it.http_status === null ? null : (
                  <MetaValue kind="status" value={it.http_status} as="plain" />
                )}
              </td>
              <td className={tdClass}>{formatDate(it.checked_at, asof)}</td>
              <td className={`${tdClass} max-w-xs break-all text-xs`}>
                {it.evidence_url ? (
                  <ExternalLink href={it.evidence_url}>{t('page.G7.iq.evidence')}</ExternalLink>
                ) : (
                  <span className="text-muted">{t('page.G7.iq.noEvidence')}</span>
                )}
                {it.screenshot_raw_document_id !== null ? (
                  <div className="mt-1" data-testid="iq-screenshot">
                    <span className="text-muted">{t('page.G7.iq.screenshot')}</span>
                    <RawDocumentPreview rawId={it.screenshot_raw_document_id} />
                  </div>
                ) : null}
              </td>
              <td className={tdClass}>
                <Link
                  to={{
                    search: humanCheckSearch(params, {
                      complexId: it.complex_id,
                      field: 'intake_status',
                    }),
                    hash: HUMAN_CHECK_ANCHOR,
                  }}
                  title={t('page.G7.iq.actHint')}
                  data-testid="iq-human-check"
                  className="whitespace-nowrap rounded-sm border border-border px-2 py-0.5 text-xs hover:underline"
                  onClick={() => {
                    // 라우터는 해시로 스크롤하지 않는다 — 폼으로 직접 옮긴다
                    requestAnimationFrame(() => {
                      const form = document.getElementById(HUMAN_CHECK_ANCHOR);
                      if (form && typeof form.scrollIntoView === 'function') {
                        form.scrollIntoView({ block: 'start' });
                      }
                    });
                  }}
                >
                  {t('page.G7.iq.act')}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
