import { useEffect, useRef } from 'react';
import { useJob } from '@/api/hooks';
import type { JobRun } from '@/api/types';
import { t, tDynamic } from '@/i18n';

export interface JobProgressViewProps {
  job: JobRun | undefined;
  error?: Error | null;
}

/** 표시 전용(테스트·스토리용). 진행률 수치는 계약에 없으므로 상태 텍스트 + 미정 진행 막대. */
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
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col gap-1 text-sm"
      data-status={job.status}
    >
      <div className="flex items-center gap-2">
        <span className="font-medium">{t('job.title')}</span>
        <span className="text-muted">{job.job_name}</span>
        <span>{status}</span>
      </div>
      {active ? <progress className="h-1 w-full" aria-label={status} /> : null}
      {job.error_text ? (
        <p className="text-danger">{t('job.error', { detail: job.error_text })}</p>
      ) : null}
    </div>
  );
}

export interface JobProgressProps {
  /** POST /jobs·/regions·/reports 응답의 잡 id. null이면 "진행 중인 작업 없음" */
  jobId: string | null | undefined;
  /** 폴링 간격 ms (기본 2000, RA G5) */
  pollMs?: number;
  /** done이 되면 한 번 호출 */
  onDone?: (job: JobRun) => void;
  /** failed가 되면 한 번 호출 */
  onFailed?: (job: JobRun) => void;
}

/** GET /jobs/{id}를 queued/running 동안 폴링해 상태를 보여 준다. */
export function JobProgress({ jobId, pollMs, onDone, onFailed }: JobProgressProps) {
  const { data, error } = useJob(jobId, pollMs);
  const notified = useRef<string | null>(null);

  useEffect(() => {
    if (!data || notified.current === `${data.id}:${data.status}`) return;
    if (data.status === 'done') {
      notified.current = `${data.id}:${data.status}`;
      onDone?.(data);
    } else if (data.status === 'failed') {
      notified.current = `${data.id}:${data.status}`;
      onFailed?.(data);
    }
  }, [data, onDone, onFailed]);

  return <JobProgressView job={data} error={error} />;
}
