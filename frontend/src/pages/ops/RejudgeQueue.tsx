import { useJobs } from '@/api/hooks';
import { Badge, degradedFailureText, JobRequeueNote, MetaText } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { enumText, idText, QueryState, Section, tdClass, thClass } from '../_shared';

const COLS = ['name', 'status', 'scheduled', 'started', 'finished', 'progress', 'error'] as const;

/**
 * G7 RejudgeQueue — GET /jobs (재조사·재판정·수집·보고서 잡).
 * 계약 .18 F3(D23-4): 빈 데이터셋으로 지연 재큐잉된 `region.bootstrap`·`collect.daily`(queued + requeue_reason
 * `degraded_source: …`)는 상태 칸 아래에 '발행하지 않고 다시 수집(n/6회, 다음 시도 시각)' — 실패가 아니다. 상한을 넘겨
 * failed 면 오류 칸에 코드 접두 없는 멈춘 이유. 발행 busy·발행 예외 재시도 재큐잉도 같은 안내 줄(JobRequeueNote).
 */
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
                      <JobRequeueNote job={job} className="mt-1 max-w-xs text-xs text-muted" />
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
                      {degradedFailureText(job) ?? job.error_text ?? ''}
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
