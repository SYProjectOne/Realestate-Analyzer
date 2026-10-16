import { useCanWrite } from '@/api/auth';
import { useCreateJob, useOpsSources } from '@/api/hooks';
import type { JobCreateName, SourceStatus } from '@/api/types';
import { useToast } from '@/app/toast';
import { Badge, EmptyState, ExternalLink, MetaText, MetaValue } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate, formatUnknown } from '@/lib/format';
import { enumText, QueryState, tdClass, thClass } from '../_shared';
import { OpsSection } from './sections';

const COLS = [
  'kind',
  'enabled',
  'lastSuccess',
  'lastAttempt',
  'success',
  'failure',
  'http',
  'error',
  'retry',
] as const;

/** 소스 표 자리(소스 8종 표 높이) — 늦게 채워져도 아래 패널이 밀리지 않게(CLS) */
export const SOURCES_MIN_HEIGHT = 'min-h-96';

/** G7 SourceStatusTable — 소스·최종 수집·성공/실패·http_status·재시도 버튼(POST /jobs retry) */
export function SourceStatusTable({
  regionId,
  asof,
}: {
  regionId: number | null;
  asof: string | null;
}) {
  const query = useOpsSources(regionId);
  const rows = query.data;
  return (
    <OpsSection
      k="sources"
      className={SOURCES_MIN_HEIGHT}
      actions={
        rows && rows.length > 0 ? (
          <Badge tone={failingSources(rows).length > 0 ? 'caution' : 'muted'}>
            <MetaText
              kind="count"
              k="page.G7.sourcesSummary"
              params={{ n: failingSources(rows).length, total: rows.length }}
            />
          </Badge>
        ) : null
      }
    >
      <QueryState
        query={query}
        empty={(rows) => (rows.length === 0 ? t('page.common.none') : null)}
      >
        {(list) => <SourceTable rows={list} asof={asof} />}
      </QueryState>
    </OpsSection>
  );
}

function SourceTable({ rows, asof }: { rows: SourceStatus[]; asof: string | null }) {
  const createJob = useCreateJob();
  const canWrite = useCanWrite();
  const toast = useToast();
  const retry = (job: { job_name: JobCreateName; payload: Record<string, unknown> }) =>
    createJob.mutate(job, { onSuccess: () => toast({ message: t('page.G7.src.retried') }) });
  return (
    <div className="overflow-x-auto">
      <table
        aria-label={t('page.G7.sources')}
        className="w-full min-w-[52rem] border-collapse text-sm"
      >
        <caption className="pb-2 text-left text-xs text-muted">
          {t('page.G7.sourcesCaption')}
        </caption>
        <thead>
          <tr>
            {COLS.map((k) => (
              <th key={k} scope="col" className={thClass}>
                {t(`page.G7.src.${k}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const failing = isFailing(row);
            return (
              <tr
                key={row.source_kind}
                data-enabled={row.enabled}
                className={
                  row.enabled ? (failing ? 'bg-warn-soft/50' : '') : 'bg-subtle text-grayed'
                }
              >
                <th scope="row" className={`${tdClass} text-left font-medium`}>
                  {enumText('page.G7.sourceKind', row.source_kind)}
                  {row.failing_targets.length > 0 ? (
                    <details className="mt-1 text-xs font-normal">
                      <summary className="cursor-pointer text-danger">
                        {t('page.G7.src.failing')} ·{' '}
                        <MetaValue kind="count" value={row.failing_targets.length} />
                      </summary>
                      <ul className="mt-1 flex flex-col gap-1">
                        {row.failing_targets.map((target) => (
                          <li key={`${target.url}-${target.fetched_at}`} className="break-all">
                            {target.complex_name ? `${target.complex_name} · ` : ''}
                            <span title={target.reason} data-reason={target.reason}>
                              {formatUnknownTarget(
                                target.http_status,
                                target.reason,
                                target.fetched_at,
                              )}
                            </span>{' '}
                            · <ExternalLink href={target.url} />
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </th>
                <td className={tdClass}>
                  {row.enabled ? (
                    t('page.common.yes')
                  ) : (
                    <Badge tone="muted">
                      {t('page.G7.src.disabled', { reason: row.disabled_reason ?? '' })}
                    </Badge>
                  )}
                </td>
                <td className={tdClass}>
                  {row.last_success_at ? (
                    formatDate(row.last_success_at, asof)
                  ) : (
                    <EmptyState inline />
                  )}
                </td>
                <td className={tdClass}>
                  {row.last_attempt_at ? (
                    formatDate(row.last_attempt_at, asof)
                  ) : (
                    <EmptyState inline />
                  )}
                </td>
                <td className={tdClass}>
                  <MetaValue kind="count" value={row.successes_7d} />
                </td>
                <td className={`${tdClass} ${failing ? 'font-semibold text-danger' : ''}`}>
                  <MetaValue kind="count" value={row.failures_7d} />
                </td>
                <td className={tdClass}>
                  {row.last_http_status === null ? null : (
                    <MetaValue kind="status" value={row.last_http_status} as="plain" />
                  )}
                </td>
                <td
                  className={`${tdClass} max-w-xs break-all text-xs`}
                  title={row.last_error_text ?? undefined}
                >
                  {row.last_error_text === null ? '' : reasonText(row.last_error_text)}
                </td>
                <td className={tdClass}>
                  {row.retry ? (
                    <button
                      type="button"
                      data-write
                      disabled={!canWrite || createJob.isPending}
                      title={canWrite ? undefined : t('auth.readOnlyHint')}
                      onClick={() => row.retry && retry(row.retry)}
                      className="min-h-10 whitespace-nowrap rounded-[10px] border border-border-strong bg-surface px-3 text-[13px] font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {t('page.G7.src.retry')}
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 최근 7일 실패가 있거나 열리지 않는 대상이 있는 자료(줄 세기 — D25-3) */
export function isFailing(row: SourceStatus): boolean {
  return row.failures_7d > 0 || row.failing_targets.length > 0;
}

/** 실패가 있는 자료 줄 */
export function failingSources(rows: readonly SourceStatus[]): SourceStatus[] {
  return rows.filter(isFailing);
}

/** 청약홈 공식 API 빈 데이터셋 실패(계약 .18 F2·D23-4 — `empty_dataset: totalCount 0`, http_status 200) */
const EMPTY_DATASET = 'empty_dataset';

/** 서버 사유 코드 → 화면 문구. 아는 코드(빈 데이터셋)만 바꾸고, 나머지는 서버 문자열 그대로(원 코드는 title 로 남긴다) */
function reasonText(reason: string): string {
  return reason.startsWith(EMPTY_DATASET) ? t('page.G7.src.reason.emptyDataset') : reason;
}

/**
 * "확인 불가(403, 날짜)" 형식(계약 source_status — 실패도 데이터, AGENTS 규칙 7).
 * 상태 코드가 2xx(또는 없음)인 실패는 상태 코드가 아니라 **사유**를 보인다 — 계약 .18 F2: 빈 데이터셋은 200 이지만 실패라
 * '확인 불가(200, 날짜)'가 아니라 '확인 불가(빈 데이터셋 — 청약홈 적재 중, 날짜)'. 4xx·5xx 는 코드(사유가 코드와 같으면 한 번).
 */
function formatUnknownTarget(status: number | null, reason: string, fetchedAt: string): string {
  const text = reasonText(reason).trim();
  const ok = status === null || (status >= 200 && status < 300);
  const code = ok
    ? text || (status === null ? '' : String(status))
    : !text || text === String(status)
      ? String(status)
      : `${String(status)} ${text}`;
  return formatUnknown(code || null, fetchedAt);
}
