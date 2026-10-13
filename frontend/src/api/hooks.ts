/**
 * TanStack Query 훅 — RA §4-2 + D2-3 엔드포인트마다 하나 (계약 2026-10-09.4, operationId 주석).
 *
 * 화면은 이 훅만 부른다. 반환 타입은 `./types`(생성 타입 별칭).
 * 쿼리 키는 `queryKeys`로만 만든다(무효화 일관성).
 * id 인자는 `IdLike`(number | string): URL 경로·쿼리에서 온 문자열을 그대로 넘겨도 된다.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryClient,
  type QueryState,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiFetch, ApiError, type QueryParams } from './client';
import { fetchFile, type FetchedFile, type FileRequest } from './download';
import {
  awaitingPublish,
  awaitsRedeferral,
  backoffMs,
  DEFERRED_POLL_MS,
  failedRound,
  nextPublishJobId,
  POLL_ERROR_MAX_STREAK,
  PUBLISH_CHAIN_MAX,
  snapshotsRefetchInterval,
  snapshotsWatchExpired,
  type RoundJobs,
} from './jobWatch';
import type {
  CatalystCreate,
  CatalystCreated,
  CatalystPatch,
  CatalystUpdated,
  ChangeEvent,
  ChangeSeverity,
  ChecklistItem,
  ChecklistPatch,
  ClaimListParams,
  ClaimPatch,
  ClaimView,
  CompareView,
  ComplexDetail,
  ComplexListParams,
  ComplexRowPage,
  Dashboard,
  Health,
  HumanCheck,
  HumanCheckCreate,
  IntakeQueue,
  JobCreate,
  JobListParams,
  JobRun,
  JudgmentOps,
  JudgmentOpsParams,
  LivingAreasUpdate,
  LivingAreasUpdated,
  Market,
  Provenance,
  Region,
  RegionCandidate,
  RegionCreate,
  RegionCreated,
  RegionPatch,
  RegionPatched,
  Report,
  ReportRequest,
  Scenario,
  ScenarioCreate,
  ScenarioPreview,
  Sensitivity,
  Snapshot,
  ShareLink,
  ShareLinkCreate,
  ShareLinkCreated,
  SourceStatus,
} from './types';

type Q<T> = UseQueryResult<T, Error>;
type M<TVars, TData> = UseMutationResult<TData, Error, TVars>;

/** 경로·쿼리 id. 계약은 정수, URL에서 읽으면 문자열 */
export type IdLike = number | string;
/** 시나리오 쿼리 값: 내장 code(base|A|B|C|D) 또는 사용자 시나리오 id */
export type ScenarioKey = string;

const enc = (v: IdLike) => encodeURIComponent(String(v));
const key = (v: IdLike | null | undefined) => (v === null || v === undefined ? '' : String(v));
const has = (v: IdLike | null | undefined): v is IdLike =>
  v !== null && v !== undefined && v !== '';

export interface ChangesParams {
  since?: string | null;
  compare_snapshot?: IdLike | null;
  severity?: ChangeSeverity | null;
}

export interface ChecklistParams {
  status?: ChecklistItem['status'] | null;
  complex_id?: IdLike | null;
}

export const queryKeys = {
  health: () => ['health'] as const,
  regions: () => ['regions'] as const,
  region: (id: IdLike) => ['regions', key(id)] as const,
  regionResolve: (q: string) => ['regions', 'resolve', q] as const,
  snapshots: (regionId: IdLike) => ['regions', key(regionId), 'snapshots'] as const,
  dashboard: (sid: IdLike, scenario: ScenarioKey | null) =>
    ['snapshots', key(sid), 'dashboard', scenario] as const,
  complexes: (sid: IdLike, params: ComplexListParams) =>
    ['snapshots', key(sid), 'complexes', params] as const,
  complex: (id: IdLike, snapshot: IdLike | null, scenario: ScenarioKey | null) =>
    ['complexes', key(id), key(snapshot), scenario] as const,
  provenance: (provId: string, snapshot: IdLike | null = null) =>
    ['provenance', provId, key(snapshot)] as const,
  rawText: (rawId: IdLike) => ['raw', key(rawId), 'text'] as const,
  rawFile: (rawId: IdLike) => ['raw', key(rawId), 'file'] as const,
  compare: (sid: IdLike, ids: readonly IdLike[], scenario: ScenarioKey | null) =>
    ['snapshots', key(sid), 'compare', ids.map(String), scenario] as const,
  sensitivity: (sid: IdLike, scenario: ScenarioKey | null) =>
    ['snapshots', key(sid), 'sensitivity', scenario] as const,
  scenarios: () => ['scenarios'] as const,
  scenarioPreview: (id: IdLike, snapshot: IdLike | null) =>
    ['scenarios', key(id), 'preview', key(snapshot)] as const,
  jobs: (params: JobListParams) => ['jobs', 'list', params] as const,
  job: (id: IdLike) => ['jobs', key(id)] as const,
  market: (sid: IdLike, livingArea: string | null, scenario: ScenarioKey | null = null) =>
    ['snapshots', key(sid), 'market', livingArea, scenario] as const,
  changes: (sid: IdLike, params: ChangesParams) =>
    ['snapshots', key(sid), 'changes', params] as const,
  opsSources: (regionId: IdLike | null) => ['ops', 'sources', key(regionId)] as const,
  opsJudgments: (params: JudgmentOpsParams) => ['ops', 'judgments', params] as const,
  checklist: (params: ChecklistParams) => ['ops', 'checklist', params] as const,
  intakeQueue: (regionId: IdLike | null, snapshot: IdLike | null) =>
    ['ops', 'intake-queue', key(regionId), key(snapshot)] as const,
  reports: (snapshotId: IdLike | null) => ['reports', key(snapshotId)] as const,
  claims: (sid: IdLike, params: ClaimListParams) =>
    ['snapshots', key(sid), 'claims', params] as const,
  shareLinks: () => ['share-links'] as const,
};

// ─── 공통 ───────────────────────────────────────────────────

/**
 * GET /health 는 DB 장애면 503 + 같은 Health 본문(status=degraded, db=error)을 준다(계약 2026-10-09.3) —
 * 오류로 버리지 않고 본문을 그대로 쓴다(배너가 떠야 한다). 인증 없음.
 */
async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  try {
    return await apiFetch<Health>('/health', { signal });
  } catch (err) {
    const body = err instanceof ApiError && err.status === 503 ? err.body : null;
    if (body && typeof body === 'object' && 'status' in body) return body as Health;
    throw err;
  }
}

/** GET /health (getHealth) — status=degraded면 전역 배너 */
export function useHealth(): Q<Health> {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => fetchHealth(signal),
    staleTime: 60_000,
  });
}

// ─── 지역 (D2-3) ───────────────────────────────────────────

/** GET /regions (listRegions) — 헤더 RegionPicker, G1 "지역 없음 → G0" 판단 */
export function useRegions(): Q<Region[]> {
  return useQuery({
    queryKey: queryKeys.regions(),
    queryFn: ({ signal }) => apiFetch<Region[]>('/regions', { signal }),
  });
}

/** GET /regions/{id} (getRegion) — G0-2 */
export function useRegion(id: IdLike | null | undefined): Q<Region> {
  return useQuery({
    queryKey: queryKeys.region(key(id)),
    queryFn: ({ signal }) => apiFetch<Region>(`/regions/${enc(key(id))}`, { signal }),
    enabled: has(id),
  });
}

/** GET /regions/resolve?q= (resolveRegion) — G0 자동완성. 디바운스는 호출 측. 2자 미만이면 호출하지 않는다. */
export function useResolveRegion(q: string): Q<RegionCandidate[]> {
  const trimmed = q.trim();
  return useQuery({
    queryKey: queryKeys.regionResolve(trimmed),
    queryFn: ({ signal }) =>
      apiFetch<RegionCandidate[]>('/regions/resolve', { query: { q: trimmed }, signal }),
    enabled: trimmed.length >= 2,
    placeholderData: keepPreviousData,
  });
}

/** POST /regions (createRegion, 201) — G0 "분석 시작". 응답의 job_id를 JobProgress에 넘긴다. */
export function useCreateRegion(): M<RegionCreate, RegionCreated> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<RegionCreated>('/regions', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.regions() }),
  });
}

/**
 * PUT /regions/{id}/living-areas (updateLivingAreas) — G0-2 저장 (422 = 법정동 배정 오류). 계약 .11 F4: **202** + job_id
 * (rejudge) — 잡이 새 리비전을 판정·발행할 때까지 이전 발행 리비전이 기본(화면은 `PublishJobProgress` 로 감시).
 */
export function useUpdateLivingAreas(regionId: IdLike): M<LivingAreasUpdate, LivingAreasUpdated> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<LivingAreasUpdated>(`/regions/${enc(regionId)}/living-areas`, {
        method: 'PUT',
        body,
      }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.region(regionId), data.region);
      void qc.invalidateQueries({ queryKey: queryKeys.regions() });
    },
  });
}

/** 리비전 목록 차례마다 본 진행 중 잡(목록 배열 → 그 차례의 잡). 목록 쿼리는 structuralSharing 을 끈다(새 배열) */
const roundJobs = new WeakMap<readonly Snapshot[], RoundJobs>();
/** `/jobs` 를 읽을 수 없던(401·403) QueryClient — 다시 부르지 않는다 */
const jobsForbidden = new WeakSet<QueryClient>();

/** 진행 중 잡을 읽을 때 한 번에 받는 최대 건수(계약 Size 최대 — 기본 50건이면 잘린다, 6차 minor 23) */
export const JOBS_SCAN_SIZE = 1000;

/**
 * 진행 중 잡(queued + running) — listJobs 두 번(size = JOBS_SCAN_SIZE). 어느 목록이든 size 에 꽉 차면 잘렸을 수 있어
 * 이 지역 잡이 빠졌는지 모른다 → 'truncated'(잡으로 멈추지 않고 생성 후 30분 제한으로 폴링 — 상한 없는 폴링 금지).
 */
export async function fetchActiveJobs(signal: AbortSignal): Promise<RoundJobs> {
  const [queued, running] = await Promise.all(
    (['queued', 'running'] as const).map((status) =>
      apiFetch<JobRun[]>('/jobs', { query: { status, size: JOBS_SCAN_SIZE }, signal }),
    ),
  );
  const lists = [queued ?? [], running ?? []];
  if (lists.some((l) => l.length >= JOBS_SCAN_SIZE)) return 'truncated';
  return lists.flat();
}

/** 쿼리별 마지막 성공 때의 errorUpdateCount — 연속 오류 횟수 계산용 */
const errorBase = new WeakMap<object, number>();

/**
 * 마지막 성공(또는 첫 조회) 뒤 연속 오류 횟수. refetchInterval 콜백에서 쿼리 상태로 센다(TanStack 의
 * fetchFailureCount 는 조회마다 0 으로 돌아가 연속 횟수가 아니다).
 */
export function errorStreak(query: {
  state: Pick<QueryState, 'status' | 'errorUpdateCount'>;
}): number {
  const { status, errorUpdateCount } = query.state;
  if (status !== 'error') {
    errorBase.set(query, errorUpdateCount);
    return 0;
  }
  return Math.max(errorUpdateCount - (errorBase.get(query) ?? 0), 1);
}

/** 다시 부를 가치가 있는 일시 오류: 네트워크(상태 없음)·5xx·429. 그 밖의 4xx(없음·권한·검증)는 다시 불러도 같다 */
export function isTransientError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === null || error.status >= 500 || error.status === 429;
}

/**
 * GET /regions/{id}/snapshots (listSnapshots) — 헤더 SnapshotPicker, G8.
 * 발행 대기 리비전(building·ready)이 있으면 그 리비전을 진행할 잡이 끝날 때까지 폴링한다 — published 로 바뀌면
 * `jobWatch` 가 지역·사실 화면을 무효화해 새로 고침 없이 새 리비전이 기본이 된다(4차 리뷰 M-15). 잡이 실패해
 * 리비전이 그대로 남으면 멈춘다(5차 리뷰 minor — 30분 제한 대신 잡 기준). 직전 목록에 발행 대기 리비전이 있으면
 * 차례마다 `GET /jobs?status=queued|running` 을 **목록보다 먼저** 읽는다(그 사이 끝난 publish 는 목록에 반영).
 * `/jobs` 가 401·403(공유 링크)이면 다시 부르지 않고 생성 후 30분 제한으로 돌아간다.
 */
export function useSnapshots(regionId: IdLike | null | undefined): Q<Snapshot[]> {
  const qc = useQueryClient();
  const queryKey = queryKeys.snapshots(key(regionId));
  return useQuery({
    queryKey,
    queryFn: async ({ signal }) => {
      const prev = qc.getQueryData<Snapshot[]>(queryKey);
      let jobs: RoundJobs = jobsForbidden.has(qc) ? 'forbidden' : 'unread';
      if (jobs === 'unread' && awaitingPublish(prev).length > 0) {
        try {
          jobs = await fetchActiveJobs(signal);
        } catch (err) {
          if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
            jobsForbidden.add(qc);
            jobs = 'forbidden';
          } else if (!signal.aborted) {
            // 일시 오류(5xx·네트워크): 연속 횟수를 세어 늦춘다(6차 minor 23 — 3초 고정 무한 폴링 금지)
            jobs = failedRound(prev ? roundJobs.get(prev) : undefined);
          }
        }
      }
      const list = await apiFetch<Snapshot[]>(`/regions/${enc(key(regionId))}/snapshots`, {
        signal,
      });
      roundJobs.set(list, jobs);
      return list;
    },
    enabled: has(regionId),
    structuralSharing: false,
    refetchInterval: (q) => {
      const data = q.state.data;
      return snapshotsRefetchInterval(
        data,
        Date.now(),
        data ? (roundJobs.get(data) ?? 'forbidden') : 'forbidden',
        errorStreak(q),
      );
    },
  });
}

// ─── 스냅샷 단위 조회 ──────────────────────────────────────

/** 쿼리 키에서 (리비전, 시나리오) — 화면이 보이는 값의 정체 */
type ViewOf = (queryKey: readonly unknown[]) => readonly [unknown, unknown];

/**
 * 7차 M7(D15-8): 다음 응답을 기다리는 동안 이전 값을 두는 것(placeholder)은 **같은 리비전·같은 시나리오**의 값일 때만이다
 * (필터·정렬·생활권만 바뀐 경우). 리비전이나 시나리오가 바뀌면 이전 값을 보이지 않는다 — 새 리비전이 503
 * materialize_pending 으로 재시도하는 동안(Retry-After 마다, 최대 수십 분) 옛 리비전 값이 새 리비전 머리말 아래 보이던 것.
 */
export function keepWithinView(viewOf: ViewOf, currentKey: readonly unknown[]) {
  const [sid, scenario] = viewOf(currentKey);
  return <T>(
    previousData: T | undefined,
    previousQuery: { queryKey: readonly unknown[] } | undefined,
  ): T | undefined => {
    if (previousData === undefined || !previousQuery) return undefined;
    const [prevSid, prevScenario] = viewOf(previousQuery.queryKey);
    return prevSid === sid && (prevScenario ?? null) === (scenario ?? null)
      ? previousData
      : undefined;
  };
}

/** ['snapshots', sid, 'complexes', params] → (sid, params.scenario) */
const complexesView: ViewOf = (k) => [
  k[1],
  (k[3] as ComplexListParams | undefined)?.scenario ?? null,
];
/** ['snapshots', sid, 'market', livingArea, scenario] → (sid, scenario) */
const marketView: ViewOf = (k) => [k[1], k[4] ?? null];

/** GET /snapshots/{sid}/dashboard?scenario= (getDashboard) — G1 */
export function useDashboard(
  sid: IdLike | null | undefined,
  scenario: ScenarioKey | null,
): Q<Dashboard> {
  return useQuery({
    queryKey: queryKeys.dashboard(key(sid), scenario),
    queryFn: ({ signal }) =>
      apiFetch<Dashboard>(`/snapshots/${enc(key(sid))}/dashboard`, {
        query: { scenario },
        signal,
      }),
    enabled: has(sid),
    // M7: 키 = (리비전, 시나리오) 뿐이라 이전 값을 둘 경우가 없다(다른 리비전·시나리오 값은 보이지 않는다)
  });
}

function complexQuery(params: ComplexListParams): QueryParams {
  const { filter, ...rest } = params;
  const flat: Record<string, string> = {};
  for (const [k, v] of Object.entries(filter ?? {})) {
    if (v !== undefined && v !== null && v !== '') flat[k] = String(v);
  }
  return { ...rest, filter: flat };
}

/** GET /snapshots/{sid}/complexes (listComplexes) — G2 표 */
export function useComplexes(
  sid: IdLike | null | undefined,
  params: ComplexListParams = {},
): Q<ComplexRowPage> {
  const queryKey = queryKeys.complexes(key(sid), params);
  return useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      apiFetch<ComplexRowPage>(`/snapshots/${enc(key(sid))}/complexes`, {
        query: complexQuery(params),
        signal,
      }),
    enabled: has(sid),
    // M7: 같은 리비전·시나리오 안의 필터·정렬 변경만 이전 행을 둔다
    placeholderData: keepWithinView(complexesView, queryKey),
  });
}

export interface ComplexPagesResult {
  /** 지금까지 받은 행(items)과 서버 total. 첫 페이지 전이면 undefined */
  data: ComplexRowPage | undefined;
  error: Error | null;
  isLoading: boolean;
  /** 나머지 페이지를 받는 중 */
  loadingMore: boolean;
  /** 재시도 중인 마지막 실패 — 503 materialize_pending 이면 '준비 중'(7차 minor 18) */
  failureReason: Error | null;
  /** 지금 보이는 값이 같은 리비전·시나리오의 이전 값(필터 변경 중) */
  isPlaceholderData: boolean;
  /** 다시 시도(첫 페이지부터) */
  refetch: () => unknown;
}

/**
 * G2 목록을 점진적으로 받는다(WP9 W8·W9).
 *  1. 첫 요청 = page 1, size = firstSize(작게) — 첫 화면을 빨리 그린다.
 *  2. total 이 그보다 크면 size = params.size(기본 1000, 계약 최대) 페이지를 1부터 차례로 모두 받는다 —
 *     total 의 모든 행에 닿는다. 다 받으면 그 행들로 바꾼다(첫 페이지 행은 1페이지에 포함).
 */
export function useComplexesProgressive(
  sid: IdLike | null | undefined,
  params: ComplexListParams,
  firstSize: number,
): ComplexPagesResult {
  const pageSize = params.size ?? 1000;
  const first = useComplexes(sid, { ...params, page: 1, size: firstSize });
  const firstPage = first.isPlaceholderData ? undefined : first.data;
  const needMore = firstPage !== undefined && firstPage.total > firstPage.items.length;
  const rest = useInfiniteQuery({
    queryKey: [...queryKeys.complexes(key(sid), { ...params, size: pageSize }), 'pages'] as const,
    queryFn: ({ pageParam, signal }) =>
      apiFetch<ComplexRowPage>(`/snapshots/${enc(key(sid))}/complexes`, {
        query: complexQuery({ ...params, page: pageParam, size: pageSize }),
        signal,
      }),
    initialPageParam: 1,
    getNextPageParam: (last, all) => {
      const loaded = all.reduce((n, p) => n + p.items.length, 0);
      return last.items.length > 0 && loaded < last.total ? all.length + 1 : undefined;
    },
    enabled: has(sid) && needMore,
  });
  const { hasNextPage, isFetchingNextPage, isFetching, fetchNextPage } = rest;
  // 받은 페이지 수가 바뀔 때마다 다음 페이지(상태 플래그는 빠른 응답이면 같은 값으로 돌아온다)
  const loadedPages = rest.data?.pages.length ?? 0;
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && !isFetching) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, isFetching, fetchNextPage, loadedPages]);

  const data = useMemo<ComplexRowPage | undefined>(() => {
    const pages = needMore ? rest.data?.pages : undefined;
    if (pages && pages.length > 0) {
      const last = pages[pages.length - 1] as ComplexRowPage;
      return { ...last, page: 1, size: pageSize, items: pages.flatMap((p) => p.items) };
    }
    return first.data;
  }, [needMore, rest.data, first.data, pageSize]);

  return {
    data,
    error: first.error ?? rest.error ?? null,
    isLoading: first.isLoading,
    loadingMore: needMore && (rest.isFetching || !!rest.hasNextPage),
    failureReason: first.failureReason ?? rest.failureReason ?? null,
    isPlaceholderData: first.isPlaceholderData,
    refetch: first.refetch,
  };
}

/**
 * GET /snapshots/{sid}/complexes.csv (exportComplexesCsv) — G2 CSV(같은 필터·정렬, 페이지 없음).
 * Bearer 가 필요하므로 링크가 아니라 `download.ts`의 `useDownload`로 받는다.
 */
export function complexesCsvRequest(sid: IdLike, params: ComplexListParams = {}): FileRequest {
  const { page: _page, size: _size, ...rest } = params;
  return {
    path: `/snapshots/${enc(sid)}/complexes.csv`,
    query: complexQuery(rest),
    fallbackName: `complexes_${key(sid)}.csv`,
  };
}

/** GET /complexes/{id}?snapshot=&scenario= (getComplex) — G3 */
export function useComplexDetail(
  id: IdLike | null | undefined,
  snapshot: IdLike | null,
  scenario: ScenarioKey | null = null,
): Q<ComplexDetail> {
  return useQuery({
    queryKey: queryKeys.complex(key(id), snapshot, scenario),
    queryFn: ({ signal }) =>
      apiFetch<ComplexDetail>(`/complexes/${enc(key(id))}`, {
        query: { snapshot, scenario },
        signal,
      }),
    enabled: has(id),
  });
}

/** GET /provenance/{prov_id} (getProvenance) — 공통 출처 패널 */
export function useProvenance(
  provId: string | null | undefined,
  snapshotId: IdLike | null = null,
): Q<Provenance> {
  const scoped = provenanceSnapshot(provId, snapshotId);
  return useQuery({
    queryKey: queryKeys.provenance(provId ?? '', scoped),
    queryFn: ({ signal }) =>
      apiFetch<Provenance>(`/provenance/${enc(provId ?? '')}`, {
        query: { snapshot_id: scoped === null ? null : key(scoped) },
        signal,
      }),
    enabled: !!provId,
    staleTime: Infinity,
  });
}

/**
 * 출처 조회에 넘길 리비전. 계약 .11 F1(D14-1): 화면 응답의 `prov` 로 받은 출처는 보고 있는(그 Fact 가 나온) 리비전을 늘
 * 넘긴다 — 발행 리비전 = 발행 순간 저장본, 발행 전 = 실시간. 계약 .12 F1(D15-2): 저장본이 모든 본문의 `raw_document_id` 를
 * `rd_<id>` 서랍으로 저장하므로 화면이 만든 접수 근거 원문 출처(`rd_`)도 예외 없이 넘긴다.
 */
export function provenanceSnapshot(
  provId: string | null | undefined,
  snapshotId: IdLike | null,
): IdLike | null {
  return provId ? snapshotId : null;
}

/** GET /raw/{raw_document_id} (getRawDocument) — 원문 파일(G3·G7). `as=text`면 추출 텍스트 */
export function rawDocumentRequest(
  rawDocumentId: IdLike,
  as: 'file' | 'text' = 'file',
): FileRequest {
  return {
    path: `/raw/${enc(rawDocumentId)}`,
    query: as === 'text' ? { as } : undefined,
    fallbackName: `raw_${key(rawDocumentId)}${as === 'text' ? '.txt' : ''}`,
  };
}

/** GET /raw/{id} — 원문 파일 Blob(미리보기: 텍스트·PNG). 열 때만 받는다(enabled). */
export function useRawFile(
  rawDocumentId: IdLike | null | undefined,
  enabled = true,
): Q<FetchedFile> {
  return useQuery({
    queryKey: queryKeys.rawFile(key(rawDocumentId)),
    queryFn: ({ signal }) => fetchFile(rawDocumentRequest(key(rawDocumentId)), { signal }),
    enabled: enabled && has(rawDocumentId),
    staleTime: Infinity,
    gcTime: 60_000,
  });
}

/** GET /raw/{id}?as=text — G3 원문 하이라이트 탭(지연 로드: enabled로 켠다) */
export function useRawText(rawDocumentId: IdLike | null | undefined, enabled = true): Q<string> {
  return useQuery({
    queryKey: queryKeys.rawText(key(rawDocumentId)),
    queryFn: ({ signal }) =>
      apiFetch<string>(`/raw/${enc(key(rawDocumentId))}`, {
        query: { as: 'text' },
        signal,
        accept: 'text/plain',
      }),
    enabled: enabled && has(rawDocumentId),
    staleTime: Infinity,
  });
}

/** GET /snapshots/{sid}/compare?ids=&scenario= (getCompare) — G4 (ids 2~6개일 때만 호출) */
export function useCompare(
  sid: IdLike | null | undefined,
  ids: readonly IdLike[],
  scenario: ScenarioKey | null,
): Q<CompareView> {
  return useQuery({
    queryKey: queryKeys.compare(key(sid), ids, scenario),
    queryFn: ({ signal }) =>
      apiFetch<CompareView>(`/snapshots/${enc(key(sid))}/compare`, {
        query: { ids: ids.map(String), scenario },
        signal,
      }),
    enabled: has(sid) && ids.length >= 2 && ids.length <= 6,
  });
}

/** GET /snapshots/{sid}/sensitivity?scenario= (getSensitivity) — G4, G5 (C10) */
export function useSensitivity(
  sid: IdLike | null | undefined,
  scenario: ScenarioKey | null,
): Q<Sensitivity> {
  return useQuery({
    queryKey: queryKeys.sensitivity(key(sid), scenario),
    queryFn: ({ signal }) =>
      apiFetch<Sensitivity>(`/snapshots/${enc(key(sid))}/sensitivity`, {
        query: { scenario },
        signal,
      }),
    enabled: has(sid),
  });
}

/**
 * GET /snapshots/{sid}/market?living_area=&scenario= (getMarket) — G6.
 * 상황 토글(`?scenario=`)을 그대로 보낸다(5차 minor: 시장 화면만 시나리오가 빠졌다 — 계약 .10 Scenario 파라미터).
 */
export function useMarket(
  sid: IdLike | null | undefined,
  livingArea: string | null = null,
  scenario: ScenarioKey | null = null,
): Q<Market> {
  const queryKey = queryKeys.market(key(sid), livingArea, scenario);
  return useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      apiFetch<Market>(`/snapshots/${enc(key(sid))}/market`, {
        query: { living_area: livingArea, scenario },
        signal,
      }),
    enabled: has(sid),
    // M7: 같은 리비전·시나리오 안의 생활권 변경만 이전 값을 둔다
    placeholderData: keepWithinView(marketView, queryKey),
  });
}

/** GET /snapshots/{sid}/changes?since=&compare_snapshot=&severity= (listChanges) — G1 피드, G8 diff */
export function useChanges(
  sid: IdLike | null | undefined,
  params: ChangesParams = {},
  enabled = true,
): Q<ChangeEvent[]> {
  return useQuery({
    queryKey: queryKeys.changes(key(sid), params),
    queryFn: ({ signal }) =>
      apiFetch<ChangeEvent[]>(`/snapshots/${enc(key(sid))}/changes`, {
        query: {
          since: params.since,
          compare_snapshot: params.compare_snapshot,
          severity: params.severity,
        },
        signal,
      }),
    enabled: enabled && has(sid),
  });
}

// ─── 시나리오 ──────────────────────────────────────────────

/** GET /scenarios (listScenarios) — 헤더 ScenarioToggle, G5 */
export function useScenarios(): Q<Scenario[]> {
  return useQuery({
    queryKey: queryKeys.scenarios(),
    queryFn: ({ signal }) => apiFetch<Scenario[]>('/scenarios', { signal }),
    staleTime: 5 * 60_000,
  });
}

/** POST /scenarios (createScenario, 201) — G5 저장 */
export function useCreateScenario(): M<ScenarioCreate, Scenario> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<Scenario>('/scenarios', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.scenarios() }),
  });
}

/** GET /scenarios/{id}/preview?snapshot= (previewScenario) — G5 (판정기 호출 없음) */
export function useScenarioPreview(
  id: IdLike | null | undefined,
  snapshot: IdLike | null,
): Q<ScenarioPreview> {
  return useQuery({
    queryKey: queryKeys.scenarioPreview(key(id), snapshot),
    queryFn: ({ signal }) =>
      apiFetch<ScenarioPreview>(`/scenarios/${enc(key(id))}/preview`, {
        query: { snapshot: key(snapshot) },
        signal,
      }),
    enabled: has(id) && has(snapshot),
  });
}

// ─── 잡 ────────────────────────────────────────────────────

/** GET /jobs (listJobs) — G7 RejudgeQueue */
export function useJobs(params: JobListParams = {}): Q<JobRun[]> {
  return useQuery({
    queryKey: queryKeys.jobs(params),
    queryFn: ({ signal }) => apiFetch<JobRun[]>('/jobs', { query: { ...params }, signal }),
  });
}

/** POST /jobs (createJob, 202) — 재판정·수집 */
export function useCreateJob(): M<JobCreate, JobRun> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<JobRun>('/jobs', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs', 'list'] }),
  });
}

export const JOB_POLL_MS = 2000;

/**
 * useJob 폴링 간격: done/failed 면 멈춘다. 마지막 조회가 오류면 — 일시 오류(5xx·네트워크·429)는 늦춰 가며 다시
 * 조회하고(6차 minor 22: 한 번 오류로 영구 중단 금지) 연속 POLL_ERROR_MAX_STREAK 회를 넘으면 멈춘다. 잡 없음·권한
 * 없음 같은 4xx 는 다시 불러도 같으므로 바로 멈춘다(5차 minor: 무한 폴링 금지).
 */
export function jobRefetchInterval(
  state: {
    status: string;
    data?: (Pick<JobRun, 'status'> & Partial<Pick<JobRun, 'stats' | 'finished_at'>>) | undefined;
    error?: unknown;
  },
  pollMs: number = JOB_POLL_MS,
  streak: number = state.status === 'error' ? 1 : 0,
): number | false {
  if (state.status === 'error') {
    if (!isTransientError(state.error) || streak > POLL_ERROR_MAX_STREAK) return false;
    return backoffMs(pollMs, streak);
  }
  const data = state.data;
  const status = data?.status;
  if (status === 'done' || status === 'failed') {
    // 계약 .14 F9: 멈춘 리비전으로 미뤄진 쓰기 — 서버가 나중에 redeferred_job_id 를 달 수 있어 느리게 다시 읽는다(30분 상한)
    return data && awaitsRedeferral(data) ? Math.max(pollMs, DEFERRED_POLL_MS) : false;
  }
  return pollMs;
}

/**
 * GET /jobs/{id} (getJob) — queued/running이면 pollMs(기본 2초)마다 다시 조회, done/failed면 멈춘다.
 * 일시 오류면 늦춰 가며 다시 조회하고(그동안 JobProgress 가 오류를 보인다), 4xx·연속 오류 상한이면 멈춘다.
 */
export function useJob(id: IdLike | null | undefined, pollMs: number = JOB_POLL_MS): Q<JobRun> {
  return useQuery({
    queryKey: queryKeys.job(key(id)),
    queryFn: ({ signal }) => apiFetch<JobRun>(`/jobs/${enc(key(id))}`, { signal }),
    enabled: has(id),
    refetchInterval: (query) => jobRefetchInterval(query.state, pollMs, errorStreak(query)),
  });
}

/**
 * 발행 대기 리비전 감시가 30분 상한에서 멈췄는가(7차 minor 21) + 다시 확인. `useSnapshots` 와 같은 쿼리를 읽는다.
 */
export function usePendingWatchExpired(regionId: IdLike | null | undefined): {
  expired: boolean;
  recheck: () => void;
} {
  const query = useSnapshots(regionId);
  const data = query.data;
  // 목록을 받을 때마다(structuralSharing 끔 — 새 배열) 다시 계산한다
  const expired = data
    ? snapshotsWatchExpired(data, Date.now(), roundJobs.get(data) ?? 'forbidden')
    : false;
  const { refetch } = query;
  return { expired, recheck: () => void refetch() };
}

/**
 * 발행 유발 잡부터 stats `publish_job_id` 를 따라 이은 잡 사슬(계약 .12 F15): 쓰기 응답 job_id 잡 → (rejudge 면) 판정 뒤
 * 등록한 snapshot.publish → (후속 잡이 다른 발행에 포함됐으면) 그 발행 잡 … 각 잡은 useJob 과 같은 쿼리(2초 폴링,
 * done·failed 면 멈춤)다. 잡 목록(`GET /jobs`)은 뒤지지 않는다. 반환 = 사슬 순서의 잡(아직 못 받았으면 undefined).
 * 호출 측은 jobId 가 바뀌면 key 로 다시 마운트한다.
 */
export function usePublishChain(
  jobId: IdLike,
  pollMs: number = JOB_POLL_MS,
): (JobRun | undefined)[] {
  const [ids, setIds] = useState<string[]>(() => [key(jobId)]);
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: queryKeys.job(id),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiFetch<JobRun>(`/jobs/${enc(id)}`, { signal }),
      refetchInterval: (
        query: Parameters<typeof errorStreak>[0] & { state: QueryState<JobRun, Error> },
      ) => jobRefetchInterval(query.state, pollMs, errorStreak(query)),
    })),
  });
  const jobs = results.map((r) => r.data);
  const last = jobs[jobs.length - 1];
  const next = last ? nextPublishJobId(last) : null;
  useEffect(() => {
    if (next === null || ids.length >= PUBLISH_CHAIN_MAX) return;
    if (ids.includes(String(next))) return;
    setIds((prev) => [...prev, String(next)]);
  }, [next, ids]);
  return jobs;
}

// ─── 운영 (G7) ─────────────────────────────────────────────

/** GET /ops/sources?region_id= (listSourceStatus) */
export function useOpsSources(regionId: IdLike | null = null): Q<SourceStatus[]> {
  return useQuery({
    queryKey: queryKeys.opsSources(regionId),
    queryFn: ({ signal }) =>
      apiFetch<SourceStatus[]>('/ops/sources', { query: { region_id: regionId }, signal }),
  });
}

/** GET /ops/judgments?since=&tool=&page=&size= (getJudgmentOps) — 통계 + 봉투 목록 */
export function useOpsJudgments(params: JudgmentOpsParams = {}): Q<JudgmentOps> {
  return useQuery({
    queryKey: queryKeys.opsJudgments(params),
    queryFn: ({ signal }) =>
      apiFetch<JudgmentOps>('/ops/judgments', { query: { ...params }, signal }),
  });
}

/** GET /ops/checklist?status=&complex_id= (listChecklist) */
export function useChecklist(params: ChecklistParams = {}): Q<ChecklistItem[]> {
  return useQuery({
    queryKey: queryKeys.checklist(params),
    queryFn: ({ signal }) =>
      apiFetch<ChecklistItem[]>('/ops/checklist', {
        query: { status: params.status, complex_id: params.complex_id },
        signal,
      }),
  });
}

/**
 * GET /ops/intake-queue?region_id=&snapshot= (getIntakeQueue, 계약 .19 · D26-2) — 접수 확인 대기열. 스냅샷을 주면 그
 * 스냅샷, 없으면 지역의 최신 published(서버 기본). 사람 확인 저장 뒤 `useCreateHumanCheck` 가 무효화한다(반영 대기 표시).
 */
export function useIntakeQueue(
  regionId: IdLike | null,
  snapshot: IdLike | null,
  enabled = true,
): Q<IntakeQueue> {
  return useQuery({
    queryKey: queryKeys.intakeQueue(regionId, snapshot),
    queryFn: ({ signal }) =>
      apiFetch<IntakeQueue>('/ops/intake-queue', {
        query: { region_id: has(snapshot) ? null : regionId, snapshot },
        signal,
      }),
    enabled,
  });
}

/** PATCH /ops/checklist/{id} (updateChecklistItem) */
export function usePatchChecklistItem(): M<{ id: IdLike; patch: ChecklistPatch }, ChecklistItem> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }) =>
      apiFetch<ChecklistItem>(`/ops/checklist/${enc(id)}`, { method: 'PATCH', body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ops', 'checklist'] }),
  });
}

/**
 * POST /ops/human-checks (createHumanCheck, 201) — 저장 후 단지·스냅샷·대시보드 무효화
 * (접수 배지 즉시 갱신). 계약 .9: 서버가 재판정 잡을 자동 등록해 `rejudge_job_id` 로 돌려준다 — 화면은 그 잡
 * 진행만 보인다(`suggested_job` 을 다시 POST 하지 않는다). 잡 목록도 무효화한다.
 */
export function useCreateHumanCheck(): M<HumanCheckCreate, HumanCheck> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<HumanCheck>('/ops/human-checks', { method: 'POST', body }),
    onSuccess: () => {
      invalidateFactViews(qc);
      // 계약 .11 F6: 201 + job_id(rejudge) — 잡이 새 리비전을 판정·발행한다. 발행 대기 리비전이 목록에 보이게
      void qc.invalidateQueries({ queryKey: queryKeys.regions() });
      void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
      // 계약 .19(D26-2): 접수 확인 대기열의 '사람 확인 입력됨 — 재판정·발행 대기' 표시
      void qc.invalidateQueries({ queryKey: ['ops', 'intake-queue'] });
    },
  });
}

/** 발행을 부르는 쓰기 응답의 감시할 잡 id(계약 .11 F6 공통 이름 `job_id`, 옛 응답은 `rejudge_job_id`) */
export function humanCheckJobId(
  hc: Pick<HumanCheck, 'rejudge_job_id'> & { job_id?: number | null },
): number | null {
  return hc.job_id ?? hc.rejudge_job_id ?? null;
}

// ─── 보고서 (G8, D4: html|pdf) ─────────────────────────────

/** GET /reports?snapshot_id= (listReports) */
export function useReports(snapshotId: IdLike | null = null): Q<Report[]> {
  return useQuery({
    queryKey: queryKeys.reports(snapshotId),
    queryFn: ({ signal }) =>
      apiFetch<Report[]>('/reports', { query: { snapshot_id: snapshotId }, signal }),
  });
}

/**
 * POST /reports (createReport, 202 → JobRun; 409 publish_blocked = contradicted claim·발행 전 리비전).
 * 409 는 화면이 본 리비전 목록(contradicted 수·상태)이 낡았다는 뜻 — 리비전 목록·보고서 목록을 다시 받는다(4차 minor).
 */
export function useCreateReport(): M<ReportRequest, JobRun> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<JobRun>('/reports', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        void qc.invalidateQueries({ queryKey: queryKeys.regions() });
        void qc.invalidateQueries({ queryKey: ['reports'] });
      }
    },
  });
}

/** GET /reports/{id} (downloadReport) — 보고서 파일(Bearer → `useDownload`) */
export function reportRequest(id: IdLike, filename?: string | null): FileRequest {
  return { path: `/reports/${enc(id)}`, fallbackName: filename ?? `report_${key(id)}` };
}

// ─── 주장 수정 (G7, 계약 2026-10-09.4 · M8) ────────────────

/**
 * 사실 값이 바뀌었을 수 있을 때(주장 수정·강등·재검증 완료·사람 확인) 그 값을 보이는 캐시를 무효화한다.
 * 스냅샷 하위 전부(대시보드·리스트·비교·민감도·시장·변경·주장), 단지 상세, 출처 패널, 운영(체크리스트·소스),
 * 보고서 목록(contradicted 남음 → 생성 차단).
 */
export function invalidateFactViews(qc: QueryClient): void {
  for (const root of ['snapshots', 'complexes', 'provenance', 'ops', 'reports'] as const) {
    void qc.invalidateQueries({ queryKey: [root] });
  }
}

/** GET /snapshots/{sid}/claims?status= (listClaims) — G7 contradicted 목록 */
export function useClaims(
  sid: IdLike | null | undefined,
  params: ClaimListParams = {},
): Q<ClaimView[]> {
  return useQuery({
    queryKey: queryKeys.claims(key(sid), params),
    queryFn: ({ signal }) =>
      apiFetch<ClaimView[]>(`/snapshots/${enc(key(sid))}/claims`, {
        query: { status: params.status },
        signal,
      }),
    enabled: has(sid),
  });
}

/**
 * PATCH /claims/{id} (reviseClaim, 202 → JobRun claim.reverify) — 사람이 고친 문장으로 원자 분할 재검증.
 * 409 conflict = contradicted 아님·이미 분할됨·재검증 대기 중, 422 = 같은 대상(단지·필드)이 아님(D10-3) —
 * ApiError.detail 을 화면이 보인다. 409 는 목록이 낡았다는 뜻이므로 claims 목록을 다시 불러온다(R3 재리뷰 F3).
 * 접수되면 사실 주장의 사실이 강등되므로(D10-3·D11-3 읽기 오버레이) 그 사실을 보이는 화면 캐시를 전부
 * 무효화한다(R3 3차 minor 15): 스냅샷 하위(대시보드·리스트·비교·시장·주장)·단지 상세·출처·운영(체크리스트)·
 * 잡 목록·보고서(생성 차단 여부). 재검증 잡이 끝나면 `invalidateFactViews` 를 한 번 더 부른다(ClaimsPanel).
 */
export function useReviseClaim(): M<{ id: IdLike; patch: ClaimPatch }, JobRun> {
  const qc = useQueryClient();
  const invalidateClaims = () =>
    qc.invalidateQueries({
      predicate: (q) => q.queryKey[0] === 'snapshots' && q.queryKey[2] === 'claims',
    });
  return useMutation({
    mutationFn: ({ id, patch }) =>
      apiFetch<JobRun>(`/claims/${enc(id)}`, { method: 'PATCH', body: patch }),
    onSuccess: () => {
      invalidateFactViews(qc);
      void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) void invalidateClaims();
    },
  });
}

// ─── 호재 URL (G6, 계약 2026-10-09.4 · M6) ─────────────────

/** POST /catalysts (createCatalyst, 201) — 사람이 넣는 호재 URL. job 이 null 이면 다음 파이프라인이 분류 */
export function useCreateCatalyst(): M<CatalystCreate, CatalystCreated> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<CatalystCreated>('/catalysts', { method: 'POST', body }),
    onSuccess: () => {
      void qc.invalidateQueries({
        predicate: (q) => q.queryKey[0] === 'snapshots' && q.queryKey[2] === 'market',
      });
      void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
    },
  });
}

/**
 * PATCH /catalysts/{id} (updateCatalyst, 계약 .8, D11-5) — 사람이 호재 위치를 확인(location_confirmed + 영향
 * 생활권·단지, 선택 lat/lon·expected_ym)하면 서버가 catalyst_link 를 만든다(좌표 없는 단지는 distance_m=null·
 * weight=1·라벨 추정·reason). location_confirmed=false 면 링크를 지운다. 계약 .11(D14-5, F3): 연결이 바뀌면 **202** +
 * `job_id`(snapshot.publish — 새 리비전을 worker 가 발행), 그대로면 job_id null. 잡이 끝날 때까지 이전 발행 리비전이
 * 기본이므로 화면은 job_id 를 감시하고(`PublishJobProgress`), 끝나면 `api/jobWatch` 가 지역·리비전 목록·사실 화면을
 * 무효화한다. 여기서는 새 발행 대기 리비전이 목록에 보이도록(발행 대기 폴링) 지역·리비전 목록을 무효화한다.
 */
export function useUpdateCatalystLocation(): M<
  { id: IdLike; patch: CatalystPatch },
  CatalystUpdated
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }) =>
      apiFetch<CatalystUpdated>(`/catalysts/${enc(id)}`, { method: 'PATCH', body: patch }),
    onSuccess: (data) => {
      // 계약 .13 F3(D16-4): 200 + job_id null = 바뀐 것 없음(새 잡·리비전·출처 행 없음) — 다시 읽을 것이 없다
      if (data.job_id === null && !data.job) return;
      invalidateFactViews(qc);
      void qc.invalidateQueries({ queryKey: queryKeys.regions() });
      void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
    },
  });
}

/**
 * PATCH /regions/{id} (updateRegion, 계약 .8, D11-7) — 지역 선택 확장(selections 추가·제거, 선택 name) = RA "지역 추가".
 * 계약 .11 F5: 선택이 바뀌면 **202**(job_id = region.expand — 발행까지 이전 리비전이 기본), 이름만 바꾸면 200(job_id null).
 * 응답 = {region, change_event(critical), job_id(region.expand), added, removed}. 잡이 새 리비전에서 후보 전체
 * rerank 1회 + 보고서 §12 "지역 추가" 장을 만든다. 선택이 그대로면 409 → 지역을 다시 받는다.
 */
export function useUpdateRegionSelections(regionId: IdLike): M<RegionPatch, RegionPatched> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<RegionPatched>(`/regions/${enc(regionId)}`, { method: 'PATCH', body }),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.region(regionId), data.region);
      void qc.invalidateQueries({ queryKey: queryKeys.regions() });
      void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
    },
    // 409(선택이 그대로) = 화면이 본 지역 선택이 낡았다 — 지역을 다시 받는다(4차 minor)
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        void qc.invalidateQueries({ queryKey: queryKeys.regions() });
      }
    },
  });
}

// ─── 공유 링크 (G7, 계약 2026-10-09.4 · M9) ────────────────

/** GET /share-links (listShareLinks) — 쓰기 토큰만(읽기·공유 토큰은 403). enabled 로 쓰기 권한일 때만 부른다 */
export function useShareLinks(enabled = true): Q<ShareLink[]> {
  return useQuery({
    queryKey: queryKeys.shareLinks(),
    queryFn: ({ signal }) => apiFetch<ShareLink[]>('/share-links', { signal }),
    enabled,
  });
}

/** POST /share-links (createShareLink, 201) — 토큰은 이 응답에서 한 번만 온다 */
export function useCreateShareLink(): M<ShareLinkCreate, ShareLinkCreated> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<ShareLinkCreated>('/share-links', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.shareLinks() }),
  });
}

/** DELETE /share-links/{id} (revokeShareLink) → ShareLink(status=revoked) */
export function useRevokeShareLink(): M<IdLike, ShareLink> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => apiFetch<ShareLink>(`/share-links/${enc(id)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.shareLinks() }),
  });
}
