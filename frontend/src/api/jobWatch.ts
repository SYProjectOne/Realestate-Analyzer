/**
 * 잡 완료 → 캐시 무효화 (R3 4차 리뷰 Major 15, D11-1).
 *
 * 재판정·사람 확인·생활권 편집·지역 확장·수집 잡은 같은 기준일의 **새 리비전**을 만든다. 화면 기본 스냅샷은
 * `GET /regions`(latest_snapshot)와 `GET /regions/{id}/snapshots`(리비전 목록)에서 오므로, 잡이 끝나면 그 둘과
 * 사실 화면을 무효화해야 새로 고침 없이 새 리비전으로 넘어간다.
 *
 * 화면마다 `onDone` 을 달면 빠지는 곳이 생긴다(4차 리뷰: G1 재판정은 옛 스냅샷만, G7 잡 목록은 아무것도) —
 * 그래서 QueryCache 를 한 곳에서 지켜본다:
 *  - `['jobs', id]`(JobProgress 폴링)·`['jobs', 'list', …]`(G7 RejudgeQueue) 응답에서 잡 상태가 done 으로 바뀌면
 *    잡 종류에 맞게 무효화한다. 상세 폴링은 첫 응답이 이미 done 이어도(빠른 잡) 완료로 본다.
 *  - 재판정 뒤 새 리비전은 `ready` → (`snapshot.publish` 잡) → `published` 다. 그 publish 잡은 화면이 등록한 잡이
 *    아니므로, 리비전 목록이 발행 대기(building·ready·contradicted 0) 리비전을 갖고 있는 동안 목록을 폴링하고
 *    (`snapshotsRefetchInterval`), 목록에서 어떤 리비전이 published 로 바뀌면 지역(latest_snapshot)·사실 화면을
 *    무효화한다.
 */
import type { Query, QueryClient } from '@tanstack/react-query';
import type { JobRun, Snapshot } from './types';

type Root = 'regions' | 'snapshots' | 'complexes' | 'provenance' | 'ops' | 'reports' | 'jobs';

/** 잡 종류별 무효화 범위 */
function rootsFor(jobName: string): readonly Root[] {
  switch (jobName) {
    case 'report':
      return ['reports'];
    case 'backup':
      return ['ops', 'jobs'];
    default:
      // 수집·재판정·발행·지역 부트스트랩·확장·참조 갱신·주장 재검증 — 리비전·사실이 바뀐다
      return ['regions', 'snapshots', 'complexes', 'provenance', 'ops', 'reports', 'jobs'];
  }
}

/** 잡이 done 이 됐을 때의 무효화(화면 onDone 과 별개로 늘 한 번) */
export function invalidateAfterJob(qc: QueryClient, job: Pick<JobRun, 'job_name'>): void {
  for (const root of rootsFor(job.job_name)) {
    if (root === 'jobs') {
      void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
    } else {
      void qc.invalidateQueries({ queryKey: [root] });
    }
  }
}

/** 리비전이 발행됐을 때: latest_snapshot(지역)·사실 화면(옛 리비전의 '재판정 필요' 배지 포함) */
function invalidateAfterPublish(qc: QueryClient): void {
  void qc.invalidateQueries({
    queryKey: ['regions'],
    // 리비전 목록 자신은 방금 받았다
    predicate: (q) => q.queryKey[2] !== 'snapshots',
  });
  for (const root of ['snapshots', 'complexes', 'reports'] as const) {
    void qc.invalidateQueries({ queryKey: [root] });
  }
}

/** 발행 대기 리비전 폴링 간격(ms)과 최대 대기(생성 후) */
export const PENDING_REVISION_POLL_MS = 3000;
export const PENDING_REVISION_MAX_AGE_MS = 30 * 60_000;

/** 발행을 기다리는 리비전인가: building, 또는 ready 이면서 판정기 장애·남은 모순 주장이 없다(publish 잡 대기) */
export function isAwaitingPublish(s: Snapshot, now: number = Date.now()): boolean {
  if (s.status === 'published' || s.degraded) return false;
  if (s.status === 'ready' && (s.contradicted_claims ?? 0) > 0) return false;
  const created = Date.parse(s.created_at);
  return Number.isFinite(created) && now - created <= PENDING_REVISION_MAX_AGE_MS;
}

/** `useSnapshots` 의 refetchInterval: 발행 대기 리비전이 있으면 폴링 */
export function snapshotsRefetchInterval(
  data: readonly Snapshot[] | undefined,
  now: number = Date.now(),
): number | false {
  return data?.some((s) => isAwaitingPublish(s, now)) ? PENDING_REVISION_POLL_MS : false;
}

function isJob(v: unknown): v is JobRun {
  return (
    !!v &&
    typeof v === 'object' &&
    typeof (v as JobRun).id === 'number' &&
    typeof (v as JobRun).status === 'string' &&
    typeof (v as JobRun).job_name === 'string'
  );
}

/**
 * QueryCache 를 지켜보며 잡 완료·리비전 발행 때 무효화한다. AppProviders 가 한 번 건다. 해제 함수를 돌려준다.
 */
export function watchJobCompletion(qc: QueryClient): () => void {
  const jobStatus = new Map<number, string>();
  const snapStatus = new Map<number, string>();

  const onJob = (job: JobRun, detail: boolean) => {
    const prev = jobStatus.get(job.id);
    jobStatus.set(job.id, job.status);
    if (job.status !== 'done' || prev === 'done') return;
    // 목록은 처음 본 done(옛 잡)을 완료로 치지 않는다. 상세 폴링은 방금 등록한 잡이다
    if (prev === undefined && !detail) return;
    invalidateAfterJob(qc, job);
  };

  const onSnapshots = (rows: readonly Snapshot[]) => {
    let published = false;
    for (const s of rows) {
      const prev = snapStatus.get(s.id);
      snapStatus.set(s.id, s.status);
      if (prev !== undefined && prev !== 'published' && s.status === 'published') published = true;
    }
    if (published) invalidateAfterPublish(qc);
  };

  const handle = (query: Query) => {
    const key = query.queryKey;
    const data: unknown = query.state.data;
    if (key[0] === 'jobs') {
      if (key[1] === 'list' && Array.isArray(data)) {
        for (const job of data) if (isJob(job)) onJob(job, false);
      } else if (key.length === 2 && isJob(data)) {
        onJob(data, true);
      }
    } else if (key[0] === 'regions' && key[2] === 'snapshots' && Array.isArray(data)) {
      onSnapshots(data as Snapshot[]);
    }
  };

  return qc.getQueryCache().subscribe((event) => {
    if (event.type === 'updated' && event.action.type === 'success') handle(event.query);
  });
}
