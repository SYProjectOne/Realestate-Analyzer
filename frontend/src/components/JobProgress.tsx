import { useEffect, useRef, useState } from 'react';
import { useJob, usePublishChain } from '@/api/hooks';
import {
  nextPublishJobId,
  PUBLISH_CHAIN_MAX,
  publishPhase,
  publishTarget,
  requeueCount,
  type PublishPhase,
} from '@/api/jobWatch';
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
  // 계약 .13 F4(D16-3): 발행 busy → 다시 queued(지연 재큐잉) — 실패가 아니라 기다리는 중이라고 보인다
  const requeued = requeueCount(job);
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
      {requeued !== null ? (
        <p className="text-muted" data-testid="job-requeued">
          <MetaText kind="count" k="job.requeued" params={{ n: requeued }} />
        </p>
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
 * 발행을 부르는 쓰기(호재 위치 PATCH 202·호재 URL POST 201·생활권 PUT 202·지역 선택 PATCH 202·사람 확인 201 — 응답 `job_id`)가
 * 등록한 잡의 진행. 잡이 새 리비전을 판정·발행할 때까지 화면 기본은 지금 발행 리비전이라는 안내를 같이 보인다.
 * 7차 minor 19(D15-8)·계약 .12 F15: rejudge 의 done 은 발행이 아니다 — 잡 stats `publish_job_id` 를 이어 감시하고(후속 잡이
 * 다른 발행에 포함되면 그 발행 잡까지, F4) 사슬 끝의 발행 잡이 끝날 때(또는 리비전 목록이 published 를 보일 때) 안내를 닫는다.
 * publish_blocked(남은 모순 주장)·발행 실패·미룸(deferred_to)·30분 상한은 알린다. 리비전 목록·지역·사실 화면 무효화는
 * `api/jobWatch` 가 한다.
 */
export function PublishJobProgress({
  jobId,
  onDone,
}: {
  jobId: string | number;
  onDone?: (job: JobLike) => void;
}) {
  return <PublishChain key={String(jobId)} jobId={jobId} onDone={onDone} />;
}

function PublishChain({
  jobId,
  onDone,
}: {
  jobId: string | number;
  onDone?: (job: JobLike) => void;
}) {
  const chain = usePublishChain(jobId);
  const trigger = chain[0];
  const last = chain.filter((j) => j !== undefined).pop();
  const triggerDone = !!trigger && (trigger.status === 'done' || trigger.status === 'failed');
  /** 브라우저가 발행 유발 잡의 끝을 본 시각(상한 계산 — 서버 시각과 섞지 않는다) */
  const [watchStart, setWatchStart] = useState<number | null>(null);
  useEffect(() => {
    if (triggerDone && watchStart === null) setWatchStart(Date.now());
  }, [triggerDone, watchStart]);
  const [now, setNow] = useState(() => Date.now());

  const { snapshots } = useSnapshot();
  const target = last ? publishTarget(last) : null;
  const snapshot = target === null ? undefined : snapshots.find((s) => s.id === target);
  // 사슬이 상한에 닿았는데 마지막 잡이 또 다음 잡을 가리키면 더 잇지 않는다(usePublishChain) — 알린다(8차 m16)
  const capped =
    chain.length >= PUBLISH_CHAIN_MAX &&
    chain[chain.length - 1] !== undefined &&
    nextPublishJobId(chain[chain.length - 1] as NonNullable<(typeof chain)[number]>) !== null;
  const phase = publishPhase({
    trigger,
    last,
    snapshot,
    watchStart: watchStart ?? now,
    now,
    capped,
  });
  const waiting = phase.kind === 'trigger' || phase.kind === 'waiting' || phase.kind === 'deferred';
  // 잡 폴링이 멈춘 뒤(미룸·겹친 발행)에도 상한을 넘기면 알린다 — 1분마다 시각만 다시 본다
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
      {chain
        .slice(1)
        .map((job, i) =>
          job ? <JobProgressView key={job.id} job={job as JobLike} /> : <span key={`p${i}`} />,
        )}
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
      // 8차 m19: 사유는 ko.json 문구 + 포맷한 숫자(남은 모순 주장 수), 서버 사유는 코드 접두를 뗀 것
      return (
        <p className="text-xs text-danger" role="alert" data-testid="publish-blocked">
          {phase.contradicted !== null ? (
            <MetaText
              kind="count"
              k="job.publishBlockedContradicted"
              params={{ n: phase.contradicted }}
            />
          ) : phase.detail !== null ? (
            t('job.publishBlocked', { detail: phase.detail })
          ) : (
            t('job.publishBlockedUnknown')
          )}
        </p>
      );
    case 'capped':
      return (
        <p className="text-xs text-danger" role="alert" data-testid="publish-capped">
          <MetaText kind="count" k="job.publishChainCapped" params={{ n: PUBLISH_CHAIN_MAX }} />
        </p>
      );
    case 'publishFailed':
      return (
        <p className="text-xs text-danger" role="alert" data-testid="publish-failed">
          {t('job.publishFailed', { detail: phase.detail })}
        </p>
      );
    case 'deferred':
      return (
        <p className="text-xs text-muted" role="status" data-testid="publish-deferred">
          {t('job.publishDeferred')}
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
