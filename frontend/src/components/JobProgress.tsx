import { useEffect, useRef, useState } from 'react';
import { useJob, usePublishJobs } from '@/api/hooks';
import { followPublish, publishPhase, publishTarget, type PublishPhase } from '@/api/jobWatch';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, tDynamic } from '@/i18n';
import type { JobLike } from '@/lib/contract';
import { MetaText } from './MetaValue';

export interface JobProgressViewProps {
  job: JobLike | undefined;
  error?: Error | null;
}

/** 표시 전용(테스트·갤러리용). 계약 `progress{done,total,step}`가 있으면 결정 진행 막대, 없으면 미정 막대. */
export function JobProgressView({ job, error }: JobProgressViewProps) {
  // 잡을 한 번이라도 받았으면 일시 오류 동안(다시 조회 중 — 6차 minor 22) 마지막 상태를 두고 오류 줄만 더한다
  if (error && !job) {
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
          <MetaText
            kind="progress"
            className="tabular-nums text-muted"
            k="job.progress"
            params={{ done: progress.done, total: progress.total }}
          />
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
      {error ? (
        <p className="text-danger" data-testid="job-retrying">
          {t('job.retrying', { detail: error.message })}
        </p>
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

/**
 * 발행을 부르는 쓰기(계약 .11 F3–F6 — 호재 위치 202·생활권 PUT 202·지역 선택 PATCH 202·사람 확인 201 + job_id)가
 * 등록한 잡의 진행. 잡이 새 리비전을 판정·발행할 때까지 화면 기본은 지금 발행 리비전이라는 안내를 같이 보인다.
 * 7차 minor 19(D15-8): rejudge·region.expand 의 done 은 발행이 아니다 — 안내는 그 리비전의 **후속 `snapshot.publish` 잡**이
 * 끝날 때(또는 리비전 목록에서 published 를 볼 때) 닫는다. publish_blocked(남은 모순 주장)·발행 실패·30분 상한은 알린다.
 * 리비전 목록·지역·사실 화면 무효화는 `api/jobWatch` 가 한다.
 */
export function PublishJobProgress({
  jobId,
  onDone,
}: {
  jobId: string | number;
  onDone?: (job: JobLike) => void;
}) {
  const trigger = useJob(String(jobId)).data;
  const triggerDone = !!trigger && (trigger.status === 'done' || trigger.status === 'failed');
  /** 브라우저가 이 잡의 끝을 본 시각(상한 계산 — 서버 시각과 섞지 않는다) */
  const [watch, setWatch] = useState<{ job: string; start: number } | null>(null);
  const watchStart = watch?.job === String(jobId) ? watch.start : null;
  useEffect(() => {
    if (triggerDone && watchStart === null) setWatch({ job: String(jobId), start: Date.now() });
  }, [triggerDone, watchStart, jobId]);

  const { snapshots } = useSnapshot();
  const target = trigger ? publishTarget(trigger) : null;
  const snapshot = target === null ? undefined : snapshots.find((s) => s.id === target);
  const [now, setNow] = useState(() => Date.now());
  /** 끝난(발행·막힘·실패·상한) 뒤에는 발행 잡 목록을 더 부르지 않는다 */
  const polling = useRef(true);
  const list = usePublishJobs(triggerDone, () => polling.current);
  const follow = trigger && list.data ? followPublish(trigger, list.data) : null;
  const phase = publishPhase({
    trigger,
    follow,
    snapshot,
    listSettled: list.data !== undefined || list.isError,
    watchStart: watchStart ?? now,
    now: Math.max(now, list.dataUpdatedAt, list.errorUpdatedAt),
  });
  const waiting = phase.kind === 'trigger' || phase.kind === 'waiting';
  useEffect(() => {
    polling.current = waiting;
  }, [waiting]);
  // 발행 잡 목록을 못 읽는(403) 동안에도 상한을 넘기면 알린다 — 1분마다 시각만 다시 본다
  useEffect(() => {
    if (!triggerDone || !waiting) return;
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, [triggerDone, waiting]);

  return (
    <div className="flex flex-col gap-1" data-testid="publish-job" data-phase={phase.kind}>
      {waiting ? (
        <p className="text-xs text-muted" data-testid="publish-pending">
          {t('job.publishPending')}
        </p>
      ) : null}
      <JobProgress jobId={jobId} onDone={onDone} />
      {follow && follow.id !== trigger?.id ? <JobProgressView job={follow as JobLike} /> : null}
      <PublishOutcome phase={phase} />
    </div>
  );
}

function PublishOutcome({ phase }: { phase: PublishPhase }) {
  switch (phase.kind) {
    case 'published':
      return (
        <p className="text-xs text-muted" role="status" data-testid="publish-done">
          {t('job.publishDone')}
        </p>
      );
    case 'blocked':
      return (
        <p className="text-xs text-danger" role="alert" data-testid="publish-blocked">
          {t('job.publishBlocked', { detail: phase.detail })}
        </p>
      );
    case 'publishFailed':
      return (
        <p className="text-xs text-danger" role="alert" data-testid="publish-failed">
          {t('job.publishFailed', { detail: phase.detail })}
        </p>
      );
    case 'expired':
      return (
        <p className="text-xs text-danger" role="alert" data-testid="publish-expired">
          {t('job.publishExpired')}
        </p>
      );
    default:
      return null;
  }
}
