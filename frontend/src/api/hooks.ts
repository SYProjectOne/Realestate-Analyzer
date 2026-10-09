/**
 * TanStack Query 훅 — RA §4-2 + D2-3 엔드포인트마다 하나 (계약 2026-10-09.1, operationId 주석).
 *
 * 화면은 이 훅만 부른다. 반환 타입은 `./types`(생성 타입 별칭).
 * 쿼리 키는 `queryKeys`로만 만든다(무효화 일관성).
 * id 인자는 `IdLike`(number | string): URL 경로·쿼리에서 온 문자열을 그대로 넘겨도 된다.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiFetch, apiUrl, type QueryParams } from './client';
import type {
  ChangeEvent,
  ChangeSeverity,
  ChecklistItem,
  ChecklistPatch,
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
  Report,
  ReportRequest,
  Scenario,
  ScenarioCreate,
  ScenarioPreview,
  Sensitivity,
  Snapshot,
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
const has = (v: IdLike | null | undefined): v is IdLike => v !== null && v !== undefined && v !== '';

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
};

// ─── 공통 ───────────────────────────────────────────────────

/** GET /health (getHealth) — status=degraded면 전역 배너 */
export function useHealth(): Q<Health> {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => apiFetch<Health>('/health', { signal }),
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

/** GET /snapshots/{sid}/complexes.csv (exportComplexesCsv) — G2 CSV 링크(같은 필터·정렬, 페이지 없음) */
export function complexesCsvUrl(sid: IdLike, params: ComplexListParams = {}): string {
  const { page: _page, size: _size, ...rest } = params;
  return apiUrl(`/snapshots/${enc(sid)}/complexes.csv`, complexQuery(rest));
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

/** GET /raw/{raw_document_id} (getRawDocument) — 원문 파일 링크(G3·G7). `as=text`면 추출 텍스트 */
export function rawDocumentUrl(rawDocumentId: IdLike, as: 'file' | 'text' = 'file'): string {
  return apiUrl(`/raw/${enc(rawDocumentId)}`, as === 'text' ? { as } : undefined);
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['complexes'] });
      void qc.invalidateQueries({ queryKey: ['snapshots'] });
      void qc.invalidateQueries({ queryKey: ['ops'] });
    },
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

/** GET /reports/{id} (downloadReport) — 파일 다운로드 링크 */
export function reportDownloadUrl(id: IdLike): string {
  return apiUrl(`/reports/${enc(id)}`);
}
