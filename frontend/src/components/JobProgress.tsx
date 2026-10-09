import { useEffect, useRef } from 'react';
import { useJob } from '@/api/hooks';
import { t, tDynamic } from '@/i18n';
import type { JobLike } from '@/lib/contract';
import { formatCount } from '@/lib/format';

export interface JobProgressViewProps {
  job: JobLike | undefined;
  error?: Error | null;
}

/** 표시 전용(테스트·갤러리용). 계약 `progress{done,total,step}`가 있으면 결정 진행 막대, 없으면 미정 막대. */
export function JobProgressView({ job, error }: JobProgressViewProps) {
  if (error) {
    return (
      <div role="status" className="text-sm text-danger">
        {t('job.error', { detail: error.message })}
      </div>
    );
  }
  if (!job) {
    return (
      <div role="status" className="text-sm text-muted">
        {t('job.none')}
      </div>
    );
  }
  const status = tDynamic(`job.status.${job.status}`, job.status);
  const active = job.status === 'queued' || job.status === 'running';
  const progress = job.progress && job.progress.total > 0 ? job.progress : null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col gap-1 text-sm"
      data-status={job.status}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{t('job.title')}</span>
        <span className="text-muted">{job.job_name}</span>
        <span>{status}</span>
        {progress ? (
          <span className="tabular-nums text-muted">
            {t('job.progress', {
              done: formatCount(progress.done),
              total: formatCount(progress.total),
            })}
          </span>
        ) : null}
        {progress?.step ? (
          <span className="text-muted">{t('job.step', { step: progress.step })}</span>
        ) : null}
      </div>
      {active ? (
        progress ? (
          <progress
            className="h-1 w-full"
            aria-label={status}
            max={progress.total}
            value={progress.done}
          />
        ) : (
          <progress className="h-1 w-full" aria-label={status} />
        )
      ) : null}
      {job.error_text ? (
        <p className="text-danger">{t('job.error', { detail: job.error_text })}</p>
      ) : null}
    </div>
  );
}

export interface JobProgressProps {
  /** POST /jobs·/regions·/reports 응답의 잡 id(계약은 숫자). null이면 "진행 중인 작업 없음" */
  jobId: string | number | null | undefined;
  /** 폴링 간격 ms (기본 2000, RA G5) */
  pollMs?: number;
  /** done이 되면 한 번 호출 */
  onDone?: (job: JobLike) => void;
  /** failed가 되면 한 번 호출 */
  onFailed?: (job: JobLike) => void;
}

type JobHookId = Parameters<typeof useJob>[0];

/** GET /jobs/{id}를 queued/running 동안 폴링해 상태를 보여 준다. */
export function JobProgress({ jobId, pollMs, onDone, onFailed }: JobProgressProps) {
  // useJob의 Id 타입(임시 string ↔ 계약 number)과 무관하게 경로에는 문자열로 들어간다
  const { data, error } = useJob(
    (jobId === null || jobId === undefined ? jobId : String(jobId)) as JobHookId,
    pollMs,
  );
  const job = data as JobLike | undefined;
  const notified = useRef<string | null>(null);

  useEffect(() => {
    if (!job || notified.current === `${job.id}:${job.status}`) return;
    if (job.status === 'done') {
      notified.current = `${job.id}:${job.status}`;
      onDone?.(job);
    } else if (job.status === 'failed') {
      notified.current = `${job.id}:${job.status}`;
      onFailed?.(job);
    }
  }, [job, onDone, onFailed]);

  return <JobProgressView job={job} error={error} />;
}
