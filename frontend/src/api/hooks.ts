/**
 * TanStack Query 훅 — RA §4-2 + D2-3 엔드포인트마다 하나 (계약 2026-10-09.4, operationId 주석).
 *
 * 화면은 이 훅만 부른다. 반환 타입은 `./types`(생성 타입 별칭).
 * 쿼리 키는 `queryKeys`로만 만든다(무효화 일관성).
 * id 인자는 `IdLike`(number | string): URL 경로·쿼리에서 온 문자열을 그대로 넘겨도 된다.
 */
import { useEffect, useMemo } from 'react';
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiFetch, ApiError, type QueryParams } from './client';
import { fetchFile, type FetchedFile, type FileRequest } from './download';
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
  provenance: (provId: string) => ['provenance', provId] as const,
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
  market: (sid: IdLike, livingArea: string | null) =>
    ['snapshots', key(sid), 'market', livingArea] as const,
  changes: (sid: IdLike, params: ChangesParams) =>
    ['snapshots', key(sid), 'changes', params] as const,
  opsSources: (regionId: IdLike | null) => ['ops', 'sources', key(regionId)] as const,
  opsJudgments: (params: JudgmentOpsParams) => ['ops', 'judgments', params] as const,
  checklist: (params: ChecklistParams) => ['ops', 'checklist', params] as const,
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

/** PUT /regions/{id}/living-areas (updateLivingAreas) — G0-2 저장 (422 = 법정동 배정 오류) */
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

/** GET /regions/{id}/snapshots (listSnapshots) — 헤더 SnapshotPicker, G8 */
export function useSnapshots(regionId: IdLike | null | undefined): Q<Snapshot[]> {
  return useQuery({
    queryKey: queryKeys.snapshots(key(regionId)),
    queryFn: ({ signal }) =>
      apiFetch<Snapshot[]>(`/regions/${enc(key(regionId))}/snapshots`, { signal }),
    enabled: has(regionId),
  });
}

// ─── 스냅샷 단위 조회 ──────────────────────────────────────

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
    placeholderData: keepPreviousData,
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
  return useQuery({
    queryKey: queryKeys.complexes(key(sid), params),
    queryFn: ({ signal }) =>
      apiFetch<ComplexRowPage>(`/snapshots/${enc(key(sid))}/complexes`, {
        query: complexQuery(params),
        signal,
      }),
    enabled: has(sid),
    placeholderData: keepPreviousData,
  });
}

export interface ComplexPagesResult {
  /** 지금까지 받은 행(items)과 서버 total. 첫 페이지 전이면 undefined */
  data: ComplexRowPage | undefined;
  error: Error | null;
  isLoading: boolean;
  /** 나머지 페이지를 받는 중 */
  loadingMore: boolean;
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
export function useProvenance(provId: string | null | undefined): Q<Provenance> {
  return useQuery({
    queryKey: queryKeys.provenance(provId ?? ''),
    queryFn: ({ signal }) => apiFetch<Provenance>(`/provenance/${enc(provId ?? '')}`, { signal }),
    enabled: !!provId,
    staleTime: Infinity,
  });
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

/** GET /snapshots/{sid}/market?living_area= (getMarket) — G6 */
export function useMarket(
  sid: IdLike | null | undefined,
  livingArea: string | null = null,
): Q<Market> {
  return useQuery({
    queryKey: queryKeys.market(key(sid), livingArea),
    queryFn: ({ signal }) =>
      apiFetch<Market>(`/snapshots/${enc(key(sid))}/market`, {
        query: { living_area: livingArea },
        signal,
      }),
    enabled: has(sid),
    placeholderData: keepPreviousData,
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

/** GET /jobs/{id} (getJob) — queued/running이면 pollMs(기본 2초)마다 다시 조회, done/failed면 멈춘다. */
export function useJob(id: IdLike | null | undefined, pollMs: number = JOB_POLL_MS): Q<JobRun> {
  return useQuery({
    queryKey: queryKeys.job(key(id)),
    queryFn: ({ signal }) => apiFetch<JobRun>(`/jobs/${enc(key(id))}`, { signal }),
    enabled: has(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'done' || status === 'failed' ? false : pollMs;
    },
  });
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
 * (접수 배지 즉시 갱신). 응답의 `suggested_job`은 화면이 "재판정 잡 제안" 토스트로 쓴다.
 */
export function useCreateHumanCheck(): M<HumanCheckCreate, HumanCheck> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<HumanCheck>('/ops/human-checks', { method: 'POST', body }),
    onSuccess: () => invalidateFactViews(qc),
  });
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

/** POST /reports (createReport, 202 → JobRun; 409 publish_blocked = contradicted claim) */
export function useCreateReport(): M<ReportRequest, JobRun> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<JobRun>('/reports', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
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
 * weight=1·라벨 추정·reason). location_confirmed=false 면 링크를 지운다. 응답 `job` = 연결이 바뀌었을 때의 rejudge 잡
 * (그대로면 null). 단지 상세(호재 탭)·시장·점수 입력이 바뀌므로 사실 화면 캐시와 잡 목록을 무효화한다.
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
      invalidateFactViews(qc);
      if (data.job) void qc.invalidateQueries({ queryKey: ['jobs', 'list'] });
    },
  });
}

/**
 * PATCH /regions/{id} (updateRegion, 계약 .8, D11-7) — 지역 선택 확장(selections 추가·제거, 선택 name) = RA "지역 추가".
 * 응답 = {region, change_event(critical), job_id(region.expand), added, removed}. 잡이 새 리비전에서 후보 전체
 * rerank 1회 + 보고서 §12 "지역 추가" 장을 만든다. 선택이 그대로면 409.
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
