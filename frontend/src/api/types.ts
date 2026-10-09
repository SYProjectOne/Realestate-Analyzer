/**
 * API 도메인 타입 — 계약 2026-10-09.1 생성 타입(`./schema.d.ts`)의 별칭.
 *
 * `schema.d.ts`는 `npm run gen:api`가 `contracts/openapi.bundled.yaml`에서 만든다(손으로 고치지 않음).
 * 화면·차트·훅은 반드시 이 파일(`@/api/types`)에서만 타입을 가져온다.
 *
 * 이름 규칙: 계약 스키마 이름 그대로 export 하고, WP0-C 임시 타입 시절의 이름은 호환 별칭으로 남긴다
 * (예: `Benchmark` = `BenchmarkView`). 모양은 항상 생성 타입이 맞다.
 */
import type { components, operations } from './schema';

type S = components['schemas'];

/**
 * openapi-typescript는 속성 없는 `{type: object}`를 `Record<string, never>`로 만든다(읽을 수 없는 타입).
 * 계약 의미는 "임의 객체"이므로 그 필드만 `Record<string, unknown>`으로 되돌린다.
 */
type Obj = Record<string, unknown>;
type Loosen<T, K extends keyof T, Nullable extends boolean = false> = Omit<T, K> & {
  [P in K]: Nullable extends true ? Obj | null : Obj;
};

/** 계약의 행 id는 정수다(스냅샷·단지·잡·보고서…). 생활권 id(`la_1`)·출처 id(`fp_…`)는 문자열. */
export type Id = number;
/** ISO 날짜 `YYYY-MM-DD` */
export type IsoDate = string;
/** ISO 일시 */
export type IsoDateTime = string;
/** `YYYY-MM` */
export type YearMonth = string;

// ─── §4-1 공통 타입 ─────────────────────────────────────────────

export type Label = S['Label'];
export const LABELS = [
  '확인됨',
  '추정',
  '비공식',
  '재가공',
  '확인 불가',
] as const satisfies readonly Label[];

/**
 * 수치·날짜는 맨값으로 나가지 않는다. 화면은 `prov`로 출처 패널을 연다.
 * `human`은 스키마상 선택(기본 false)인데 openapi-typescript가 default 때문에 필수로 만든다 →
 * 실제 응답(계약 예시)에는 없으므로 선택으로 되돌린다. 생성 Fact는 이 타입에 그대로 대입된다.
 */
export type Fact = Omit<S['Fact'], 'human'> & { human?: boolean };
export type FactUnitHint = NonNullable<Fact['unit']>;
/** 호환 별칭 — v의 타입은 계약상 number | string | null 하나다 */
export type NumFact = Fact;
export type DateFact = Fact;

export type Intake = S['Intake'];
export type IntakeStatus = Intake['status'];
export const INTAKE_STATUSES = [
  '가능',
  '미정',
  '확인 불가',
  '불가',
] as const satisfies readonly IntakeStatus[];
export type IntakePath = Intake['path'];
export const INTAKE_PATHS = [
  'human_check',
  'official_popup',
  'headless_shot',
  'unofficial_ref',
] as const satisfies readonly IntakePath[];

export type JudgeTool = S['JudgeTool'];
export type JudgmentEnvelope = Loosen<S['JudgmentEnvelope'], 'result' | 'raw'>;
export type EnvelopeStatus = JudgmentEnvelope['status'];
/** 점수·추천에 쓰지 않는(회색 "미해결") 봉투 상태 */
export const UNRESOLVED_STATUSES = [
  'review',
  'escaped',
  'blocked',
  'error',
] as const satisfies readonly EnvelopeStatus[];

export type ApiErrorBody = S['Error'];
export type ApiErrorCode = ApiErrorBody['code'];
export const API_ERROR_CODES = [
  'unauthorized',
  'forbidden',
  'not_found',
  'validation_error',
  'conflict',
  'publish_blocked',
  'intake_unknown',
  'judge_unavailable',
  'contract_violation',
  'internal',
] as const satisfies readonly ApiErrorCode[];

/** 목록 응답 래퍼(RA §4-2). 계약에는 G2용 `ComplexRowPage` 하나뿐이다. */
export type ComplexRowPage = S['ComplexRowPage'];
export type Page<T> = Omit<ComplexRowPage, 'items'> & { items: T[] };

export type Health = S['Health'];

// ─── 지역 (D2) ─────────────────────────────────────────────────

export type RegionCandidate = S['RegionCandidate'];
export type RegionCandidateKind = RegionCandidate['kind'];
export type RegionSelection = S['RegionSelection'];
export type LivingArea = S['LivingArea'];
export type LivingAreaInput = S['LivingAreaInput'];
export type Region = Loosen<S['Region'], 'applyhome_query'>;
export type RegionStatus = Region['status'];
export type AgePremiumCoef = S['AgePremiumCoef'];
export type RegionCreate = S['RegionCreate'];
export type RegionCreated = Omit<S['RegionCreated'], 'region'> & { region: Region };
export type LivingAreasUpdate = S['LivingAreasUpdate'];
export type LivingAreasUpdated = Omit<S['LivingAreasUpdated'], 'region'> & { region: Region };
/** 호환 별칭 */
export type RegionCreateRequest = RegionCreate;
export type RegionCreateResponse = RegionCreated;
export type LivingAreasUpdateRequest = LivingAreasUpdate;

export type Snapshot = S['Snapshot'];
export type SnapshotStatus = Snapshot['status'];

// ─── 점수·대시보드 ─────────────────────────────────────────────

export type ComponentKey = S['ComponentKey'];
/** 성분 7키(liquidity·move_in은 시나리오가 둘 중 하나만 쓴다 → 한 행에는 6개) */
export const COMPONENT_KEYS = [
  'p10',
  'rerank',
  'gap',
  'benchmark',
  'supply',
  'liquidity',
  'move_in',
] as const satisfies readonly ComponentKey[];
/** 호환 별칭 */
export type ScoreComponent = ComponentKey;
export const SCORE_COMPONENTS = COMPONENT_KEYS;
export type ComponentView = S['ComponentView'];
export type Components = S['Components'];
export type Weights = S['Weights'];

export type DecisionBadge = S['DecisionBadge'];
/** 호환 별칭 */
export type ScoreRowDecision = DecisionBadge;
export type ScoreRow = S['ScoreRow'];
export type JudgeScope = S['JudgeScope'];

export type ChangeEvent = S['ChangeEvent'];
export type ChangeSeverity = ChangeEvent['severity'];
export type ChangeTab = NonNullable<ChangeEvent['tab']>;

export type Kpis = S['Kpis'];
/** 호환 별칭 */
export type DashboardKpis = Kpis;
export type UnsoldPoint = S['UnsoldPoint'];
export type Dashboard = S['Dashboard'];

// ─── 단지 ──────────────────────────────────────────────────────

export type InclusionClass = S['InclusionClass'];
export type ComplexRow = S['ComplexRow'];
export type ComplexFilter = components['parameters']['ComplexFilter'];
/** GET /snapshots/{sid}/complexes 쿼리(page·size·sort·filter[...]·scenario) */
export type ComplexListParams = NonNullable<operations['listComplexes']['parameters']['query']>;

export type LadderRow = S['LadderRow'];
export type LadderHorizon = LadderRow['horizon'];
export type LadderBar = keyof LadderRow['verdicts'];
export type Verdict3 = S['Verdict3'];

export type GapComp = S['GapComp'];
export type Gap = S['Gap'];

export type RemainingEvent = S['RemainingEvent'];
export type RemainingKind = RemainingEvent['kind'];
export type Competition = S['Competition'];

export type CatalystView = S['CatalystView'];
/** 호환 별칭 */
export type Catalyst = CatalystView;
export type CatalystKind = CatalystView['kind'];
export type CatalystStage = CatalystView['stage'];

export type ComplexType = S['ComplexType'];
export type PaymentTerms = S['PaymentTerms'];
/** 호환 별칭 */
export type PaymentTerm = PaymentTerms;
export type PriceRange = S['PriceRange'];
export type ScheduleItem = S['ScheduleItem'];
export type Complex = S['Complex'];
/** 호환 별칭 — ComplexDetail.header는 Complex 전체다 */
export type ComplexHeader = Complex;
export type ComplexDetail = Omit<S['ComplexDetail'], 'judgments'> & {
  judgments: JudgmentEnvelope[];
};

export type Provenance = S['Provenance'];
export type ProvenanceConflict = S['ProvenanceConflict'];
export type SourceKind = S['SourceKind'];

// ─── 비교·시나리오 ─────────────────────────────────────────────

export type Decision = S['Decision'];
/** 호환 별칭 */
export type DecisionRow = Decision;
export type DecisionSet = S['DecisionSet'];
export type RequirementCheck = S['RequirementCheck'];
export type RequirementChecks = S['RequirementChecks'];
export type TermsRow = S['TermsRow'];
export type CompareView = S['CompareView'];

export type SensitivityCell = S['SensitivityCell'];
export type Sensitivity = S['Sensitivity'];

export type Scenario = S['Scenario'];
export type ScenarioParams = S['ScenarioParams'];
export type ScenarioPolicy = S['ScenarioPolicy'];
export type ScenarioCreate = S['ScenarioCreate'];
/** 호환 별칭 */
export type ScenarioCreateRequest = ScenarioCreate;
export type Requirements = S['Requirements'];
export type RequirementRule = S['RequirementRule'];
export type RequirementPre = S['RequirementPre'];
export type RequirementPreSet = S['RequirementPreSet'];
export type ScenarioPreview = S['ScenarioPreview'];
export type ScenarioPreviewRow = ScenarioPreview['requirements_pre'][number];

// ─── 잡·시장·운영·보고서 ──────────────────────────────────────

export type JobName = S['JobName'];
export type JobRun = Loosen<S['JobRun'], 'payload' | 'stats'>;
export type JobStatus = JobRun['status'];
export type JobCreate = Loosen<S['JobCreate'], 'payload'>;
/** 호환 별칭 */
export type JobCreateRequest = JobCreate;
export type JobListParams = NonNullable<operations['listJobs']['parameters']['query']>;

export type BenchmarkView = S['BenchmarkView'];
/** 호환 별칭 */
export type Benchmark = BenchmarkView;
export type SupplyPoint = S['SupplyPoint'];
/** 호환 별칭 */
export type SupplyRow = SupplyPoint;
/** 호환 별칭 */
export type UnsoldRow = UnsoldPoint;
export type RegulationSummary = S['RegulationSummary'];
export type Market = S['Market'];

export type SourceStatus = Omit<S['SourceStatus'], 'retry'> & {
  retry: { job_name: JobName; payload: Obj } | null;
};
export type JudgmentStats = S['JudgmentStats'];
export type JudgmentOps = Omit<S['JudgmentOps'], 'items'> & { items: JudgmentEnvelope[] };
export type JudgmentOpsParams = NonNullable<operations['getJudgmentOps']['parameters']['query']>;
export type ChecklistItem = S['ChecklistItem'];
export type ChecklistPatch = S['ChecklistPatch'];
export type HumanCheck = Omit<S['HumanCheck'], 'suggested_job'> & {
  suggested_job?: JobCreate | null;
};
export type HumanCheckCreate = S['HumanCheckCreate'];

export type ReportFormat = S['ReportRequest']['format'];
export type ReportRequest = S['ReportRequest'];
/** 호환 별칭 */
export type ReportCreateRequest = ReportRequest;
export type Report = S['Report'];
