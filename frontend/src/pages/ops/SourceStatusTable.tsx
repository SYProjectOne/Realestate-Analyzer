import { useCanWrite } from '@/api/auth';
import { useCreateJob, useOpsSources } from '@/api/hooks';
import type { JobName, SourceStatus } from '@/api/types';
import { useToast } from '@/app/toast';
import { Badge, EmptyState } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatCount, formatDate, formatNumber } from '@/lib/format';
import { enumText, QueryState, Section, tdClass, thClass } from '../_shared';

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

/** G7 SourceStatusTable — 소스·최종 수집·성공/실패·http_status·재시도 버튼(POST /jobs retry) */
export function SourceStatusTable({
  regionId,
  asof,
}: {
  regionId: number | null;
  asof: string | null;
}) {
  const query = useOpsSources(regionId);
  return (
    <Section title={t('page.G7.sources')}>
      <QueryState
        query={query}
        empty={(rows) => (rows.length === 0 ? t('page.common.none') : null)}
      >
        {(rows) => <SourceTable rows={rows} asof={asof} />}
      </QueryState>
    </Section>
  );
}

function SourceTable({ rows, asof }: { rows: SourceStatus[]; asof: string | null }) {
  const createJob = useCreateJob();
  const canWrite = useCanWrite();
  const toast = useToast();
  const retry = (job: { job_name: JobName; payload: Record<string, unknown> }) =>
    createJob.mutate(job, { onSuccess: () => toast({ message: t('page.G7.src.retried') }) });
  return (
    <div className="overflow-x-auto">
      <table aria-label={t('page.G7.sources')} className="w-full border-collapse text-sm">
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
            const failing = row.failures_7d > 0 || row.failing_targets.length > 0;
            return (
              <tr key={row.source_kind} className={row.enabled ? '' : 'text-grayed'}>
                <th scope="row" className={`${tdClass} text-left font-medium`}>
                  {enumText('page.G7.sourceKind', row.source_kind)}
                  {row.failing_targets.length > 0 ? (
                    <details className="mt-1 text-xs font-normal">
                      <summary className="cursor-pointer text-danger">
                        {t('page.G7.src.failing')} · {formatCount(row.failing_targets.length)}
                      </summary>
                      <ul className="mt-1 flex flex-col gap-1">
                        {row.failing_targets.map((target) => (
                          <li key={`${target.url}-${target.fetched_at}`} className="break-all">
                            {target.complex_name ? `${target.complex_name} · ` : ''}
                            {formatUnknownTarget(target.http_status, target.reason)} ·{' '}
                            <a
                              href={target.url}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="underline"
                            >
                              {target.url}
                            </a>
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
                <td className={tdClass}>{formatCount(row.successes_7d)}</td>
                <td className={`${tdClass} ${failing ? 'font-semibold text-danger' : ''}`}>
                  {formatCount(row.failures_7d)}
                </td>
                <td className={tdClass}>
                  {row.last_http_status === null
                    ? ''
                    : formatNumber(row.last_http_status).replace(/,/g, '')}
                </td>
                <td className={`${tdClass} max-w-xs break-all text-xs`}>
                  {row.last_error_text ?? ''}
                </td>
                <td className={tdClass}>
                  {row.retry ? (
                    <button
                      type="button"
                      data-write
                      disabled={!canWrite || createJob.isPending}
                      title={canWrite ? undefined : t('auth.readOnlyHint')}
                      onClick={() => row.retry && retry(row.retry)}
                      className="rounded border border-border px-2 py-0.5 text-xs disabled:opacity-50"
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

/** "확인 불가(403)" 형식 — 실패도 데이터(AGENTS 규칙 7) */
function formatUnknownTarget(status: number | null, reason: string): string {
  const code = status === null ? reason : `${String(status)} ${reason}`;
  return t('empty.unknownWithReason', { reason: code.trim() });
}
