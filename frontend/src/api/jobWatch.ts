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
 *    아니므로, 리비전 목록이 발행 대기(building·ready·contradicted 0) 리비전을 갖고 있고 그 리비전을 진행할 잡
 *    (queued·running)이 남아 있는 동안 목록을 폴링하고(`snapshotsRefetchInterval` — 차례마다 `/jobs` 먼저), 목록에서 어떤
 *    리비전이 published 로 바뀌면 지역(latest_snapshot)·사실 화면을 무효화한다. 잡이 실패해 리비전이 building·ready
 *    로 남으면 폴링을 멈춘다(5차 리뷰 minor — 30분 제한 대신 잡 기준).
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

/** 발행 대기 리비전 폴링 간격(ms) */
export const PENDING_REVISION_POLL_MS = 3000;
/**
 * 진행 중인 잡을 알 수 없을 때(공유 링크 등 `/jobs` 를 못 읽는 토큰·첫 조회 전)만 쓰는 최대 대기(생성 후).
 * `/jobs` 를 읽을 수 있으면 시간 제한 없이 **발행을 진행할 잡이 끝날 때까지** 폴링한다(5차 리뷰 minor).
 */
export const PENDING_REVISION_MAX_AGE_MS = 30 * 60_000;

/** 오류 동안 늦춘 폴링 간격의 상한(ms) — 6차 리뷰 minor 22·23 */
export const POLL_BACKOFF_MAX_MS = 60_000;
/** 연속 오류가 이만큼을 넘으면 폴링을 멈춘다(잡 상세·리비전 목록 공통) */
export const POLL_ERROR_MAX_STREAK = 6;

/** 연속 오류 n 번째(1부터)의 폴링 간격: base × 2ⁿ, 상한 POLL_BACKOFF_MAX_MS */
export function backoffMs(base: number, streak: number): number {
  return Math.min(base * 2 ** Math.max(streak, 0), POLL_BACKOFF_MAX_MS);
}

/** (기준일, 리비전) 순서 비교: a 가 b 보다 앞이면 음수 */
function compareRevision(
  a: Pick<Snapshot, 'asof_date' | 'revision'>,
  b: Pick<Snapshot, 'asof_date' | 'revision'>,
): number {
  if (a.asof_date !== b.asof_date) return a.asof_date < b.asof_date ? -1 : 1;
  return (a.revision ?? 1) - (b.revision ?? 1);
}

/**
 * 발행을 기다리는 리비전인가: building, 또는 ready 이면서 판정기 장애·남은 모순 주장이 없다(publish 잡 대기).
 * 같은 목록(`list`)에 더 뒤 (기준일, 리비전)의 발행 리비전이 있으면 이미 밀려난 리비전이라 기다리지 않는다.
 */
export function isAwaitingPublish(s: Snapshot, list: readonly Snapshot[] = []): boolean {
  if (s.status === 'published' || s.degraded) return false;
  if (s.status === 'ready' && (s.contradicted_claims ?? 0) > 0) return false;
  return !list.some(
    (o) => o.status === 'published' && o.region_id === s.region_id && compareRevision(o, s) > 0,
  );
}

/** 목록에서 발행 대기 리비전들 */
export function awaitingPublish(list: readonly Snapshot[] | undefined): Snapshot[] {
  return (list ?? []).filter((s) => isAwaitingPublish(s, list));
}

/** 리비전을 만들거나 발행하지 않는 잡(보고서·백업) — 발행 대기 판단에서 뺀다 */
const NON_REVISION_JOBS: ReadonlySet<string> = new Set(['report', 'backup']);

/**
 * 이 지역의 리비전을 진행(판정·점수·발행)할 수 있는 잡인가: queued·running 이고, payload 가 이 지역
 * (`region_id`) 또는 이 지역 스냅샷(`snapshot_id`)을 가리키거나 둘 다 없다(참조 갱신 등 지역 무관).
 */
export function advancesRevision(
  job: Pick<JobRun, 'job_name' | 'status' | 'payload'>,
  snapshots: readonly Pick<Snapshot, 'id' | 'region_id'>[],
): boolean {
  if (job.status !== 'queued' && job.status !== 'running') return false;
  if (NON_REVISION_JOBS.has(job.job_name)) return false;
  const p = (job.payload ?? {}) as Record<string, unknown>;
  const regionIds = new Set(snapshots.map((s) => s.region_id));
  const snapshotIds = new Set(snapshots.map((s) => s.id));
  if (typeof p.region_id === 'number') return regionIds.has(p.region_id);
  if (typeof p.snapshot_id === 'number') return snapshotIds.has(p.snapshot_id);
  return true;
}

/**
 * 리비전 목록을 받은 한 차례(round)에서 본 진행 중 잡:
 *  - JobRun[]: 그 목록을 받기 **직전에** 받은 queued·running 잡(그 사이 끝난 publish 는 목록에 반영돼 있다)
 *  - 'unread': 이번 차례엔 잡을 읽지 않았다(첫 조회·일시 오류) — 다음 차례에 읽는다
 *  - 'forbidden': `/jobs` 를 읽을 수 없는 토큰(공유 링크 403 등)
 *  - { failed: n }: `/jobs` 가 n 차례 연속 일시 오류(5xx·네트워크 — 6차 minor 23). 잡을 모르므로 생성 후 30분 제한 +
 *    늦춘 간격으로 폴링한다(3초 고정 무한 폴링 금지)
 */
export type RoundJobs = readonly JobRun[] | 'unread' | 'forbidden' | { readonly failed: number };

/** `/jobs` 조회가 일시 오류로 끝난 차례: 직전 차례가 실패였으면 횟수 +1 */
export function failedRound(prev: RoundJobs | undefined): RoundJobs {
  const n = prev !== undefined && typeof prev === 'object' && 'failed' in prev ? prev.failed : 0;
  return { failed: n + 1 };
}

/** 발행 대기 리비전 중 생성 후 PENDING_REVISION_MAX_AGE_MS 안의 것이 있는가 */
function hasYoung(pending: readonly Snapshot[], now: number): boolean {
  return pending.some((s) => {
    const created = Date.parse(s.created_at);
    return Number.isFinite(created) && now - created <= PENDING_REVISION_MAX_AGE_MS;
  });
}

/**
 * `useSnapshots` 의 refetchInterval: 발행 대기 리비전이 있으면 폴링.
 *  - 진행 중 잡을 알면 이 지역 리비전을 진행할 잡이 남아 있는 동안 폴링한다(시간 제한 없음). 하나도 없으면(실패·
 *    발행 거부로 끝남) 멈춘다 — 잡은 목록보다 먼저 읽으므로 마지막 publish 결과(published)는 이미 목록에 있다.
 *  - 아직 못 읽었으면('unread') 한 번 더(다음 차례에 잡을 읽는다).
 *  - 읽을 수 없으면('forbidden' — 공유 링크) 생성 후 PENDING_REVISION_MAX_AGE_MS 까지만.
 *  - `/jobs` 가 일시 오류({failed: n})면 생성 후 30분 제한 + 늦춘 간격(6차 minor 23).
 *  - 목록 조회 자체가 연속 오류(`listErrors` ≥ 1)면 늦춘 간격, POLL_ERROR_MAX_STREAK 를 넘으면 멈춘다.
 */
export function snapshotsRefetchInterval(
  data: readonly Snapshot[] | undefined,
  now: number = Date.now(),
  jobs: RoundJobs = 'forbidden',
  listErrors: number = 0,
): number | false {
  const pending = awaitingPublish(data);
  if (pending.length === 0) return false;
  if (listErrors > POLL_ERROR_MAX_STREAK) return false;
  const base = roundInterval(pending, data ?? [], now, jobs);
  if (base === false || listErrors <= 0) return base;
  return backoffMs(base, listErrors);
}

function roundInterval(
  pending: readonly Snapshot[],
  data: readonly Snapshot[],
  now: number,
  jobs: RoundJobs,
): number | false {
  if (jobs === 'unread') return PENDING_REVISION_POLL_MS;
  if (Array.isArray(jobs)) {
    return jobs.some((j) => advancesRevision(j, data)) ? PENDING_REVISION_POLL_MS : false;
  }
  if (!hasYoung(pending, now)) return false;
  if (typeof jobs === 'object' && 'failed' in jobs) {
    return backoffMs(PENDING_REVISION_POLL_MS, jobs.failed);
  }
  return PENDING_REVISION_POLL_MS;
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
