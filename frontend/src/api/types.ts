/**
 * API 도메인 타입 — **임시(계약 머지 전)**.
 *
 * RA §4-1·§4-2 + DECISIONS D2를 손으로 옮긴 것이다. `contracts/openapi.yaml`(WP0-A)이 머지되면
 * 각 타입을 생성물 별칭으로 바꾼다:
 *
 *   import type { components } from './schema';
 *   export type Fact = components['schemas']['Fact'];
 *
 * 화면·차트·훅은 반드시 이 파일(`@/api/types`)에서만 타입을 가져온다. 그래야 교체가 이 파일 하나로 끝난다.
 */

export type Id = string;
/** ISO 날짜 `YYYY-MM-DD` */
export type IsoDate = string;
/** ISO 일시 */
export type IsoDateTime = string;
/** `YYYY-MM` */
export type YearMonth = string;

// ─── §4-1 공통 타입 ─────────────────────────────────────────────

export const LABELS = ['확인됨', '추정', '비공식', '재가공', '확인 불가'] as const;
export type Label = (typeof LABELS)[number];

/** 수치·날짜는 맨값으로 나가지 않는다. 화면은 `prov`로 출처 패널을 연다. */
export interface Fact<V extends number | string = number | string> {
  v: V | null;
  label: Label;
  /** field_provenance id (예: "fp_01HX…"). 없으면 출처 패널을 열 수 없다. */
  prov: string | null;
  checked_at: IsoDate | null;
  /** label이 "확인 불가"일 때 사유(예: "스캔"). 임시 필드 — 계약 확인 필요 */
  reason?: string | null;
  /** 사람 확인(human_check) 경로로 확정된 값이면 true → 배지 "사람 확인됨". 임시 필드 */
  human?: boolean;
}
export type NumFact = Fact<number>;
export type DateFact = Fact<IsoDate>;

export const INTAKE_STATUSES = ['가능', '미정', '확인 불가', '불가'] as const;
export type IntakeStatus = (typeof INTAKE_STATUSES)[number];
export const INTAKE_PATHS = [
  'human_check',
  'official_popup',
  'headless_shot',
  'unofficial_ref',
] as const;
export type IntakePath = (typeof INTAKE_PATHS)[number];

export interface Intake {
  status: IntakeStatus;
  path: IntakePath;
  evidence_url: string | null;
  checked_at: IsoDateTime | null;
  http_status: number | null;
}

export type JudgeTool =
  'screen' | 'extract' | 'audit' | 'classify' | 'compare' | 'noul' | 'rerank' | 'decide' | 'verify';
export type EnvelopeStatus = 'ok' | 'review' | 'escaped' | 'blocked' | 'error';

export interface JudgmentEnvelope {
  tool: JudgeTool;
  purpose: string;
  input_hash: string;
  status: EnvelopeStatus;
  confidence: number | null;
  cached: boolean;
  result: Record<string, unknown>;
  raw: Record<string, unknown>;
  duration_ms: number | null;
  judgment_seq: number;
  created_at: IsoDateTime;
}

export type ApiErrorCode =
  'intake_unknown' | 'judge_unavailable' | 'contract_violation' | 'not_found';
export interface ApiErrorBody {
  code: ApiErrorCode;
  detail: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  snapshot_id: Id;
  asof_date: IsoDate;
}

// ─── 지역 (D2) ─────────────────────────────────────────────────

export type RegionCandidateKind = 'sido' | 'sigungu' | 'admin_dong' | 'legal_dong';
export interface RegionCandidate {
  kind: RegionCandidateKind;
  code: string;
  full_name: string;
  legal_dong_codes: string[];
  match: 'exact' | 'prefix' | 'partial';
}
export interface RegionSelection {
  kind: RegionCandidateKind;
  code: string;
  full_name: string;
}
export interface LivingArea {
  id: string;
  name: string;
  legal_dong_codes: string[];
  households: NumFact | null;
}
export type RegionStatus = 'resolving' | 'bootstrapping' | 'ready' | 'failed';
export interface Region {
  id: Id;
  name: string;
  query_text: string;
  selections: RegionSelection[];
  living_areas: LivingArea[];
  status: RegionStatus;
  latest_snapshot_id: Id | null;
  created_at: IsoDateTime;
}
export interface RegionCreateRequest {
  name: string;
  query_text: string;
  selections: RegionSelection[];
}
export interface RegionCreateResponse {
  region: Region;
  job_id: Id;
}
export interface LivingAreasUpdateRequest {
  living_areas: { name: string; legal_dong_codes: string[] }[];
}

export type SnapshotStatus = 'building' | 'ready' | 'published';
export interface Snapshot {
  id: Id;
  region_id: Id;
  asof_date: IsoDate;
  status: SnapshotStatus;
  created_at: IsoDateTime;
}

// ─── 점수·대시보드 ─────────────────────────────────────────────

export const SCORE_COMPONENTS = [
  'p10',
  'rerank',
  'gap',
  'benchmark',
  'supply',
  'liquidity',
] as const;
export type ScoreComponent = (typeof SCORE_COMPONENTS)[number];
export type Weights = Record<ScoreComponent, number>;

export interface ScoreRowDecision {
  prob: number | null;
  chosen: boolean;
  tie: boolean;
  mismatch: boolean;
}
export interface ScoreRow {
  complex_id: Id;
  name: string;
  total: NumFact;
  rank: number;
  tie_group: string | null;
  unstable: boolean;
  p10: NumFact;
  components: Record<ScoreComponent, NumFact>;
  /** component별 산출식(툴팁). 임시 필드 — 계약 확인 필요 */
  formula_text?: Partial<Record<ScoreComponent, string>>;
  intake: Intake | null;
  decision?: ScoreRowDecision | null;
}

export type ChangeSeverity = 'info' | 'notice' | 'critical';
export interface ChangeEvent {
  id: Id;
  snapshot_id: Id;
  entity: string;
  entity_id: Id;
  field: string;
  old_text: string | null;
  new_text: string | null;
  detected_at: IsoDateTime;
  severity: ChangeSeverity;
  triggers_rejudge: boolean;
}

export interface DashboardKpis {
  judged_count: NumFact;
  intake_open_count: NumFact;
  unsold_total: NumFact;
  move_in_peak_year: NumFact;
  data_freshness: DateFact;
}
export interface Dashboard {
  snapshot_id: Id;
  asof_date: IsoDate;
  scenario_id: Id;
  weights: Weights;
  kpis: DashboardKpis;
  top5: ScoreRow[];
  changes: ChangeEvent[];
}

// ─── 단지 ──────────────────────────────────────────────────────

export type InclusionClass = '포함' | '제외' | '범위 경계' | '미정';
export interface ComplexRow {
  complex_id: Id;
  name: string;
  living_area: string | null;
  intake: Intake | null;
  price_low: NumFact;
  price_high: NumFact;
  resale_end: DateFact;
  move_in: Fact<YearMonth>;
  gap_pct: NumFact;
  total: NumFact;
  inclusion_class: InclusionClass;
  last_change_at: IsoDateTime | null;
}
export interface ComplexListParams {
  page?: number;
  size?: number;
  sort?: string;
  filter?: Record<string, string>;
  scenario?: string | null;
}

export type LadderHorizon = 'move_in_plus_1y' | 'asof_plus_3y' | 'asof_plus_5y';
export type LadderBar = 'p5' | 'p10' | 'p20' | 'p_flat';
export interface LadderRow {
  horizon: LadderHorizon;
  target_ym: YearMonth;
  p5: NumFact;
  p10: NumFact;
  p20: NumFact;
  p_flat: NumFact;
  verdicts: Partial<Record<LadderBar, string>>;
  annualized?: Partial<Record<LadderBar, number>> | null;
  status: EnvelopeStatus;
  judgment_seq: number | null;
}

export interface GapComp {
  name: string;
  completed_year: number | null;
  low: NumFact;
  median: NumFact;
  high: NumFact;
  adjusted_median: NumFact | null;
  substitute: boolean;
}
export interface Gap {
  price_low: NumFact;
  price_high: NumFact;
  price_mid: NumFact;
  comps: GapComp[];
  /** 비교군 0일 때 사유 */
  empty_reason?: string | null;
}

export type RemainingKind = '본청약' | '무순위' | '임의' | '선착순';
export interface RemainingEvent {
  kind: RemainingKind;
  notice_no: string | null;
  notice_date: DateFact;
  units: NumFact | null;
  ratio_text: string | null;
  result_text: string | null;
}

export type CatalystKind = '교통' | '개발' | '학교' | '상업';
export type CatalystStage = '확정' | '계획' | '추진' | '언론' | '미확정';
export interface Catalyst {
  id: Id;
  name: string;
  kind: CatalystKind;
  stage: CatalystStage;
  stage_prob: number | null;
  expected_ym: YearMonth | null;
  location_confirmed: boolean;
  distance_m?: number | null;
}

export interface ComplexType {
  type_code: string;
  area_m2: NumFact;
  units: NumFact;
  max_price: NumFact;
  floor_sample_price: NumFact | null;
  floor_sample_text: string | null;
  balcony: NumFact | null;
  options_required: NumFact | null;
}
export interface PaymentTerm {
  notice_no: string;
  effective_from: DateFact;
  down_payment_pct: NumFact;
  down_payment_first: NumFact | null;
  interim_pct: NumFact;
  interim_terms_text: string | null;
  balance_pct: NumFact;
}
export interface ComplexHeader {
  complex_id: Id;
  name: string;
  address: string | null;
  living_area: string | null;
  price_low: NumFact;
  price_high: NumFact;
  resale_end: DateFact;
  move_in: Fact<YearMonth>;
  inclusion_class: InclusionClass;
}
export interface ComplexDetail {
  header: ComplexHeader;
  types: ComplexType[];
  payment: PaymentTerm[];
  events: RemainingEvent[];
  intake: Intake[];
  ladder: LadderRow[];
  gap: Gap | null;
  catalysts: Catalyst[];
  judgments: JudgmentEnvelope[];
}

export interface ProvenanceConflict {
  prov: string;
  value_text: string;
  url: string | null;
  label: Label;
  chosen: boolean;
}
export interface Provenance {
  id: string;
  url: string | null;
  checked_at: IsoDate | null;
  label: Label;
  excerpt: string | null;
  raw_document_id: Id | null;
  conflicts: ProvenanceConflict[];
}

// ─── 비교·시나리오 ─────────────────────────────────────────────

export interface DecisionRow {
  complex_id: Id;
  name: string;
  prob: number | null;
  chosen: boolean;
  tie: boolean;
  mismatch: boolean;
  confidence: number | null;
  status: EnvelopeStatus;
}
export interface DecisionSet {
  scenario_id: Id;
  rows: DecisionRow[];
  /** escape hatch 확률과 판정기가 남긴 질문 */
  escape: { prob: number | null; question: string | null } | null;
  confidence: number | null;
  status: EnvelopeStatus;
}
export interface CompareView {
  rows: ScoreRow[];
  weights: Weights;
  ladders: Record<Id, LadderRow[]>;
  gaps: Record<Id, Gap | null>;
  terms: Record<Id, Record<string, Fact>>;
  decisions: DecisionSet[];
}

export interface SensitivityCell {
  /** 예: "gap+10" */
  variant: string;
  component: ScoreComponent;
  delta_pp: number;
  top5: { complex_id: Id; name: string; rank: number }[];
  changed: boolean;
}
export interface Sensitivity {
  baseline_top5: { complex_id: Id; name: string; rank: number }[];
  cells: SensitivityCell[];
  unstable: boolean;
}

export interface Scenario {
  id: Id;
  name: string;
  is_builtin: boolean;
  params: Record<string, unknown>;
  weights: Weights;
  requirements: Record<string, unknown>;
}
export type ScenarioCreateRequest = Omit<Scenario, 'id' | 'is_builtin'>;
export interface RequirementPre {
  status: '충족' | '미충족';
  basis: string;
}
export interface ScenarioPreview {
  weights: Weights;
  requirements_pre: Record<
    Id,
    { access: RequirementPre; regulation: RequirementPre; funds: RequirementPre }
  >;
  cache_hits: number;
}

// ─── 잡·시장·운영·보고서 ──────────────────────────────────────

export type JobStatus = 'queued' | 'running' | 'done' | 'failed';
export interface JobRun {
  id: Id;
  job_name: string;
  kind: 'scheduled' | 'manual' | 'rejudge';
  payload: Record<string, unknown>;
  scheduled_at: IsoDateTime | null;
  started_at: IsoDateTime | null;
  finished_at: IsoDateTime | null;
  status: JobStatus;
  stats: Record<string, unknown> | null;
  error_text: string | null;
}
export interface JobCreateRequest {
  job_name: string;
  payload: Record<string, unknown>;
}

export interface Benchmark {
  id: Id;
  name: string;
  living_area: string | null;
  completed_year: number | null;
  sale_year: number | null;
  sale_period: string | null;
  sale_price_84: NumFact;
  trade_low: NumFact;
  trade_median: NumFact;
  trade_high: NumFact;
  trade_window: string | null;
  peak: NumFact | null;
  peak_ym: YearMonth | null;
  is_presale: boolean;
}
export interface SupplyRow {
  living_area: string;
  year: number;
  units: NumFact;
  label: Label;
}
export interface UnsoldRow {
  ym: YearMonth;
  total: NumFact;
  post_completion: NumFact;
  source_label: Label;
}
export interface Market {
  benchmarks: Benchmark[];
  supply: SupplyRow[];
  unsold: UnsoldRow[];
  catalysts: Catalyst[];
  regulation: Record<string, Fact | string | null>;
}

export interface SourceStatus {
  source_kind: string;
  last_fetched_at: IsoDateTime | null;
  success_count: number;
  failure_count: number;
  last_http_status: number | null;
  last_error: string | null;
}
export interface JudgmentStats {
  since: IsoDate;
  total: number;
  failed: number;
  by_tool: Partial<Record<JudgeTool, number>>;
  avg_duration_ms: number | null;
  items: JudgmentEnvelope[];
}
export interface ChecklistItem {
  id: Id;
  complex_id: Id | null;
  kind: '법적 확인' | '중도금' | '만료' | '공고 예상';
  title: string;
  due_date: IsoDate | null;
  status: 'open' | 'done' | 'na';
  note: string | null;
}
export type ChecklistPatch = Partial<Pick<ChecklistItem, 'status' | 'note' | 'due_date'>>;
export interface HumanCheck {
  id?: Id;
  complex_id: Id;
  field: string;
  value_text: string;
  kind: 'phone' | 'visit' | 'email';
  checked_at: IsoDateTime;
  entered_by: string;
  note: string | null;
}

export type ReportFormat = 'html' | 'pdf';
export interface ReportCreateRequest {
  snapshot_id: Id;
  format: ReportFormat;
  compare_snapshot_id?: Id | null;
}

export interface Health {
  status: 'ok' | 'degraded';
  version: string;
}
