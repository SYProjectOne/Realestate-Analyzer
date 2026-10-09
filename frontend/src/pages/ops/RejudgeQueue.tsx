import { useJobs } from '@/api/hooks';
import { Badge, MetaText } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { enumText, idText, QueryState, Section, tdClass, thClass } from '../_shared';

const COLS = ['name', 'status', 'scheduled', 'started', 'finished', 'progress', 'error'] as const;

/** G7 RejudgeQueue — GET /jobs (재조사·재판정·수집·보고서 잡) */
export function RejudgeQueue({ asof }: { asof: string | null }) {
  const query = useJobs({ size: 50 });
  return (
    <Section title={t('page.G7.queue')}>
      <QueryState
        query={query}
        empty={(rows) => (rows.length === 0 ? t('page.G7.job.none') : null)}
      >
        {(jobs) => (
          <div className="overflow-x-auto">
            <table aria-label={t('page.G7.queue')} className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  {COLS.map((k) => (
                    <th key={k} scope="col" className={thClass}>
                      {t(`page.G7.job.${k}` as TKey)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} data-status={job.status}>
                    <th scope="row" className={`${tdClass} text-left font-normal`}>
                      {job.job_name}
                      <span className="block text-xs text-muted">{idText(job.id)}</span>
                    </th>
                    <td className={tdClass}>
                      <Badge
                        tone={
                          job.status === 'failed'
                            ? 'strong'
                            : job.status === 'done'
                              ? 'neutral'
                              : 'muted'
                        }
                      >
                        {enumText('job.status', job.status)}
                      </Badge>
                    </td>
                    <td className={tdClass}>{formatDate(job.scheduled_at, asof)}</td>
                    <td className={tdClass}>
                      {job.started_at ? formatDate(job.started_at, asof) : ''}
                    </td>
                    <td className={tdClass}>
                      {job.finished_at ? formatDate(job.finished_at, asof) : ''}
                    </td>
                    <td className={tdClass}>
                      {job.progress ? (
                        <MetaText
                          kind="progress"
                          k="page.G7.job.progressValue"
                          params={{ done: job.progress.done, total: job.progress.total }}
                        />
                      ) : null}
                      {job.progress?.step ? (
                        <span className="block text-xs text-muted">{job.progress.step}</span>
                      ) : null}
                    </td>
                    <td className={`${tdClass} max-w-xs break-all text-xs text-danger`}>
                      {job.error_text ?? ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryState>
    </Section>
  );
}
