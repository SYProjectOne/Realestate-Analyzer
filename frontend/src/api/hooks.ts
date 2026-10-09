/**
 * TanStack Query 훅 — RA §4-2 + D2-3 엔드포인트마다 하나.
 *
 * 시그니처가 계약이다: WP6a 화면은 이 훅만 부른다. 반환 타입은 `./types`(임시)에서 오며,
 * 계약 머지 후 types.ts만 생성 타입 별칭으로 바꾸면 여기는 그대로 둔다.
 * 쿼리 키는 `queryKeys`로만 만든다(무효화 일관성).
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiFetch, apiUrl } from './client';
import type {
  ChangeEvent,
  ChecklistItem,
  ChecklistPatch,
  CompareView,
  ComplexDetail,
  ComplexListParams,
  ComplexRow,
  Dashboard,
  Health,
  HumanCheck,
  Id,
  JobCreateRequest,
  JobRun,
  JudgmentStats,
  LivingAreasUpdateRequest,
  Market,
  Page,
  Provenance,
  Region,
  RegionCandidate,
  RegionCreateRequest,
  RegionCreateResponse,
  ReportCreateRequest,
  Scenario,
  ScenarioCreateRequest,
  ScenarioPreview,
  Sensitivity,
  Snapshot,
  SourceStatus,
} from './types';

type Q<T> = UseQueryResult<T, Error>;
type M<TVars, TData> = UseMutationResult<TData, Error, TVars>;

const enc = encodeURIComponent;

export const queryKeys = {
  health: () => ['health'] as const,
  regions: () => ['regions'] as const,
  region: (id: Id) => ['regions', id] as const,
  regionResolve: (q: string) => ['regions', 'resolve', q] as const,
  snapshots: (regionId: Id) => ['regions', regionId, 'snapshots'] as const,
  dashboard: (sid: Id, scenario: Id | null) => ['snapshots', sid, 'dashboard', scenario] as const,
  complexes: (sid: Id, params: ComplexListParams) => ['snapshots', sid, 'complexes', params] as const,
  complex: (id: Id, snapshot: Id | null) => ['complexes', id, snapshot] as const,
  provenance: (provId: string) => ['provenance', provId] as const,
  compare: (sid: Id, ids: readonly Id[], scenario: Id | null) =>
    ['snapshots', sid, 'compare', [...ids], scenario] as const,
  sensitivity: (sid: Id, scenario: Id | null) => ['snapshots', sid, 'sensitivity', scenario] as const,
  scenarios: () => ['scenarios'] as const,
  scenarioPreview: (id: Id, snapshot: Id | null) => ['scenarios', id, 'preview', snapshot] as const,
  job: (id: Id) => ['jobs', id] as const,
  market: (sid: Id) => ['snapshots', sid, 'market'] as const,
  changes: (sid: Id, since: string | null) => ['snapshots', sid, 'changes', since] as const,
  opsSources: () => ['ops', 'sources'] as const,
  opsJudgments: (since: string | null) => ['ops', 'judgments', since] as const,
  checklist: () => ['ops', 'checklist'] as const,
};

// ─── 공통 ───────────────────────────────────────────────────

/** GET /health */
export function useHealth(): Q<Health> {
  return useQuery({ queryKey: queryKeys.health(), queryFn: ({ signal }) => apiFetch<Health>('/health', { signal }) });
}

// ─── 지역 (D2-3) ───────────────────────────────────────────

/** GET /regions — 헤더 RegionPicker, G1 "지역 없음 → G0" 판단 */
export function useRegions(): Q<Region[]> {
  return useQuery({
    queryKey: queryKeys.regions(),
    queryFn: ({ signal }) => apiFetch<Region[]>('/regions', { signal }),
  });
}

/** GET /regions/{id} — G0-2 */
export function useRegion(id: Id | null | undefined): Q<Region> {
  return useQuery({
    queryKey: queryKeys.region(id ?? ''),
    queryFn: ({ signal }) => apiFetch<Region>(`/regions/${enc(id ?? '')}`, { signal }),
    enabled: !!id,
  });
}

/** GET /regions/resolve?q= — G0 자동완성. 디바운스는 호출 측(G0)이 한다. 2자 미만이면 호출하지 않는다. */
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

/** POST /regions — G0 "분석 시작". 응답의 job_id를 JobProgress에 넘긴다. */
export function useCreateRegion(): M<RegionCreateRequest, RegionCreateResponse> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<RegionCreateResponse>('/regions', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.regions() }),
  });
}

/** PUT /regions/{id}/living-areas — G0-2 저장 (422 = 법정동 배정 오류) */
export function useUpdateLivingAreas(regionId: Id): M<LivingAreasUpdateRequest, Region> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      apiFetch<Region>(`/regions/${enc(regionId)}/living-areas`, { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.regions() }),
  });
}

/** GET /regions/{id}/snapshots — 헤더 SnapshotPicker, G8 */
export function useSnapshots(regionId: Id | null | undefined): Q<Snapshot[]> {
  return useQuery({
    queryKey: queryKeys.snapshots(regionId ?? ''),
    queryFn: ({ signal }) => apiFetch<Snapshot[]>(`/regions/${enc(regionId ?? '')}/snapshots`, { signal }),
    enabled: !!regionId,
  });
}

// ─── 스냅샷 단위 조회 ──────────────────────────────────────

/** GET /snapshots/{sid}/dashboard?scenario= — G1 */
export function useDashboard(sid: Id | null | undefined, scenario: Id | null): Q<Dashboard> {
  return useQuery({
    queryKey: queryKeys.dashboard(sid ?? '', scenario),
    queryFn: ({ signal }) =>
      apiFetch<Dashboard>(`/snapshots/${enc(sid ?? '')}/dashboard`, { query: { scenario }, signal }),
    enabled: !!sid,
    placeholderData: keepPreviousData,
  });
}

/** GET /snapshots/{sid}/complexes — G2 표 */
export function useComplexes(sid: Id | null | undefined, params: ComplexListParams = {}): Q<Page<ComplexRow>> {
  return useQuery({
    queryKey: queryKeys.complexes(sid ?? '', params),
    queryFn: ({ signal }) =>
      apiFetch<Page<ComplexRow>>(`/snapshots/${enc(sid ?? '')}/complexes`, {
        query: { ...params, filter: params.filter },
        signal,
      }),
    enabled: !!sid,
    placeholderData: keepPreviousData,
  });
}

/** GET /snapshots/{sid}/complexes.csv — G2 CSV 다운로드 링크(같은 필터) */
export function complexesCsvUrl(sid: Id, params: ComplexListParams = {}): string {
  return apiUrl(`/snapshots/${enc(sid)}/complexes.csv`, { ...params, filter: params.filter });
}

/** GET /complexes/{id}?snapshot= — G3 */
export function useComplexDetail(id: Id | null | undefined, snapshot: Id | null): Q<ComplexDetail> {
  return useQuery({
    queryKey: queryKeys.complex(id ?? '', snapshot),
    queryFn: ({ signal }) =>
      apiFetch<ComplexDetail>(`/complexes/${enc(id ?? '')}`, { query: { snapshot }, signal }),
    enabled: !!id,
  });
}

/** GET /provenance/{prov_id} — 공통 출처 패널 */
export function useProvenance(provId: string | null | undefined): Q<Provenance> {
  return useQuery({
    queryKey: queryKeys.provenance(provId ?? ''),
    queryFn: ({ signal }) => apiFetch<Provenance>(`/provenance/${enc(provId ?? '')}`, { signal }),
    enabled: !!provId,
    staleTime: Infinity,
  });
}

/** GET /raw/{raw_document_id} — 원문 파일 링크(G3·G7). 파일이므로 훅이 아니라 URL. */
export function rawDocumentUrl(rawDocumentId: Id): string {
  return apiUrl(`/raw/${enc(rawDocumentId)}`);
}

/** GET /snapshots/{sid}/compare?ids=&scenario= — G4 (ids 2~6개일 때만 호출) */
export function useCompare(sid: Id | null | undefined, ids: readonly Id[], scenario: Id | null): Q<CompareView> {
  return useQuery({
    queryKey: queryKeys.compare(sid ?? '', ids, scenario),
    queryFn: ({ signal }) =>
      apiFetch<CompareView>(`/snapshots/${enc(sid ?? '')}/compare`, { query: { ids, scenario }, signal }),
    enabled: !!sid && ids.length >= 2 && ids.length <= 6,
  });
}

/** GET /snapshots/{sid}/sensitivity?scenario= — G4, G5 (C10) */
export function useSensitivity(sid: Id | null | undefined, scenario: Id | null): Q<Sensitivity> {
  return useQuery({
    queryKey: queryKeys.sensitivity(sid ?? '', scenario),
    queryFn: ({ signal }) =>
      apiFetch<Sensitivity>(`/snapshots/${enc(sid ?? '')}/sensitivity`, { query: { scenario }, signal }),
    enabled: !!sid,
  });
}

/** GET /snapshots/{sid}/market — G6 */
export function useMarket(sid: Id | null | undefined): Q<Market> {
  return useQuery({
    queryKey: queryKeys.market(sid ?? ''),
    queryFn: ({ signal }) => apiFetch<Market>(`/snapshots/${enc(sid ?? '')}/market`, { signal }),
    enabled: !!sid,
  });
}

/** GET /snapshots/{sid}/changes?since= — G1 피드, G8 */
export function useChanges(sid: Id | null | undefined, since: string | null = null): Q<ChangeEvent[]> {
  return useQuery({
    queryKey: queryKeys.changes(sid ?? '', since),
    queryFn: ({ signal }) =>
      apiFetch<ChangeEvent[]>(`/snapshots/${enc(sid ?? '')}/changes`, { query: { since }, signal }),
    enabled: !!sid,
  });
}

// ─── 시나리오 ──────────────────────────────────────────────

/** GET /scenarios — 헤더 ScenarioToggle, G5 */
export function useScenarios(): Q<Scenario[]> {
  return useQuery({
    queryKey: queryKeys.scenarios(),
    queryFn: ({ signal }) => apiFetch<Scenario[]>('/scenarios', { signal }),
    staleTime: 5 * 60_000,
  });
}

/** POST /scenarios — G5 저장 */
export function useCreateScenario(): M<ScenarioCreateRequest, Scenario> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<Scenario>('/scenarios', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.scenarios() }),
  });
}

/** GET /scenarios/{id}/preview?snapshot= — G5 (판정기 호출 없음) */
export function useScenarioPreview(id: Id | null | undefined, snapshot: Id | null): Q<ScenarioPreview> {
  return useQuery({
    queryKey: queryKeys.scenarioPreview(id ?? '', snapshot),
    queryFn: ({ signal }) =>
      apiFetch<ScenarioPreview>(`/scenarios/${enc(id ?? '')}/preview`, { query: { snapshot }, signal }),
    enabled: !!id,
  });
}

// ─── 잡 ────────────────────────────────────────────────────

/** POST /jobs — 재판정·수집·보고서 (202) */
export function useCreateJob(): M<JobCreateRequest, JobRun> {
  return useMutation({
    mutationFn: (body) => apiFetch<JobRun>('/jobs', { method: 'POST', body }),
  });
}

export const JOB_POLL_MS = 2000;

/** GET /jobs/{id} — queued/running이면 pollMs(기본 2초)마다 다시 조회, done/failed면 멈춘다. */
export function useJob(id: Id | null | undefined, pollMs: number = JOB_POLL_MS): Q<JobRun> {
  return useQuery({
    queryKey: queryKeys.job(id ?? ''),
    queryFn: ({ signal }) => apiFetch<JobRun>(`/jobs/${enc(id ?? '')}`, { signal }),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'done' || status === 'failed' ? false : pollMs;
    },
  });
}

// ─── 운영 (G7) ─────────────────────────────────────────────

/** GET /ops/sources */
export function useOpsSources(): Q<SourceStatus[]> {
  return useQuery({
    queryKey: queryKeys.opsSources(),
    queryFn: ({ signal }) => apiFetch<SourceStatus[]>('/ops/sources', { signal }),
  });
}

/** GET /ops/judgments?since= */
export function useOpsJudgments(since: string | null = null): Q<JudgmentStats> {
  return useQuery({
    queryKey: queryKeys.opsJudgments(since),
    queryFn: ({ signal }) => apiFetch<JudgmentStats>('/ops/judgments', { query: { since }, signal }),
  });
}

/** GET /ops/checklist */
export function useChecklist(): Q<ChecklistItem[]> {
  return useQuery({
    queryKey: queryKeys.checklist(),
    queryFn: ({ signal }) => apiFetch<ChecklistItem[]>('/ops/checklist', { signal }),
  });
}

/** PATCH /ops/checklist/{id} */
export function usePatchChecklistItem(): M<{ id: Id; patch: ChecklistPatch }, ChecklistItem> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }) =>
      apiFetch<ChecklistItem>(`/ops/checklist/${enc(id)}`, { method: 'PATCH', body: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.checklist() }),
  });
}

/** POST /ops/human-checks — 저장 후 단지·대시보드 무효화(접수 배지 즉시 갱신) */
export function useCreateHumanCheck(): M<HumanCheck, HumanCheck> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => apiFetch<HumanCheck>('/ops/human-checks', { method: 'POST', body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['complexes'] });
      void qc.invalidateQueries({ queryKey: ['snapshots'] });
    },
  });
}

// ─── 보고서 (G8, D4: html|pdf) ─────────────────────────────

/** POST /reports → JobRun */
export function useCreateReport(): M<ReportCreateRequest, JobRun> {
  return useMutation({
    mutationFn: (body) => apiFetch<JobRun>('/reports', { method: 'POST', body }),
  });
}

/** GET /reports/{id} — 파일 다운로드 링크 */
export function reportDownloadUrl(id: Id): string {
  return apiUrl(`/reports/${enc(id)}`);
}
