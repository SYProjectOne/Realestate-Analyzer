/**
 * API 도메인 타입 — 계약 2026-10-09.2 생성 타입(`./schema.d.ts`)의 별칭.
 *
 * `schema.d.ts`는 `npm run gen:api`가 `contracts/openapi.bundled.yaml`에서 만든다(손으로 고치지 않음).
 * 화면·차트·훅은 반드시 이 파일(`@/api/types`)에서만 타입을 가져온다.
 *
 * 이름 규칙: 계약 스키마 이름 그대로 export 하고, WP0-C 임시 타입 시절의 이름은 호환 별칭으로 남긴다
 * (예: `Benchmark` = `BenchmarkView`). 모양은 항상 생성 타입이 맞다.
 */
import type { components, operations } from './schema';

type S = components['schemas'];

/*
 * 계약 2026-10-09.2부터 보정 코드가 없다: 임의 객체 필드(payload·result·raw·applyhome_query …)는 스키마가
 * `additionalProperties: true`라 `Record<string, unknown>`으로, `default`가 있는 선택 필드(Fact.human 등)는
 * gen:api의 `defaultNonNullable: false`로 선택 필드 그대로 생성된다.
 */

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

/** 수치·날짜는 맨값으로 나가지 않는다. 화면은 `prov`로 출처 패널을 연다. */
export type Fact = S['Fact'];
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
export type JudgmentEnvelope = S['JudgmentEnvelope'];
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
  // 계약 .11(D14-3·D14-4·D14-9)
  'scenario_not_in_revision',
  'stored_view_mismatch',
  'materialize_pending',
  // 계약 .12 F14(D15-7): 사람 확인 checked_at 422
  'checked_at_format',
  'checked_at_future',
  'checked_at_before_source',
  // 계약 .14 F3(R3i m2): 사람 확인 할인 값
  'discount_format',
  'discount_not_below_price',
] as const satisfies readonly ApiErrorCode[];

/** 계약 enum 에 새 code 가 생기면 여기서 타입 오류 — 목록이 빠지면 zod 가 그 오류를 'http' 로 떨어뜨린다 */
type MissingErrorCode = Exclude<ApiErrorCode, (typeof API_ERROR_CODES)[number]>;
export const API_ERROR_CODES_COMPLETE: [MissingErrorCode] extends [never]
  ? true
  : MissingErrorCode = true;

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
export type Region = S['Region'];
export type RegionStatus = Region['status'];
export type AgePremiumCoef = S['AgePremiumCoef'];
export type RegionCreate = S['RegionCreate'];
/** 청약홈 조회 파라미터(계약 .15 F3: POST /regions 선택 필드 `applyhome_query` — from_ym·to_ym 'YYYY-MM', areas) */
export type ApplyhomeQuery = S['ApplyhomeQuery'];
export type RegionCreated = S['RegionCreated'];
/** PATCH /regions/{id} 본문(계약 .8, D11-7): 바뀐 뒤 선택 전체 + 이름(선택) */
export type RegionPatch = S['RegionPatch'];
/** PATCH /regions/{id} 응답: 지역 + change_event(critical) + region.expand 잡 id + 추가·제거 선택 */
export type RegionPatched = S['RegionPatched'];
export type LivingAreasUpdate = S['LivingAreasUpdate'];
export type LivingAreasUpdated = S['LivingAreasUpdated'];
/** 호환 별칭 */
export type RegionCreateRequest = RegionCreate;
export type RegionCreateResponse = RegionCreated;
export type LivingAreasUpdateRequest = LivingAreasUpdate;

/** 기준일 스냅샷 — 계약 .8 리비전(`revision`·`revision_of`·`revision_reason`, D11-1) 포함 */
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
/**
 * 판정 범위(meta §1-3-4, D9-1). 화면 표시 문구는 ko.json `page.common.judgeScope` —
 * 보류 '보류 — 공고 후 재판정', 참고 '참고 후보(순위만)', 미해결 '미해결(분류 판정 미해결)'(계약 2026-10-09.4).
 */
export type JudgeScope = S['JudgeScope'];
export const JUDGE_SCOPES = [
  '판정 대상',
  '보류',
  '참고',
  '미해결',
  '제외',
] as const satisfies readonly JudgeScope[];

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
/** PATCH /catalysts/{id} 본문(계약 .8, D11-5) */
export type CatalystPatch = S['CatalystPatch'];
/** catalyst_link 1행(좌표 없는 단지 → distance_m null·weight 1·라벨 추정, reason 필수) */
export type CatalystLinkView = S['CatalystLinkView'];
/** PATCH /catalysts/{id} 응답: 호재 + 연결 + rejudge 잡(연결이 그대로면 null) */
export type CatalystUpdated = S['CatalystUpdated'];

export type ComplexType = S['ComplexType'];
export type PaymentTerms = S['PaymentTerms'];
/** 호환 별칭 */
export type PaymentTerm = PaymentTerms;
export type PriceRange = S['PriceRange'];
export type ScheduleItem = S['ScheduleItem'];
export type Complex = S['Complex'];
/** 호환 별칭 — ComplexDetail.header는 Complex 전체다 */
export type ComplexHeader = Complex;
export type ComplexDetail = S['ComplexDetail'];

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
/** POST /jobs 로 넣을 수 있는 잡 이름 — claim.reverify 제외(계약 2026-10-09.6, PATCH /claims 전용) */
export type JobCreateName = S['JobCreateName'];
export type JobRun = S['JobRun'];
export type JobStatus = JobRun['status'];
export type JobCreate = S['JobCreate'];
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

export type SourceStatus = S['SourceStatus'];
export type JudgmentStats = S['JudgmentStats'];
export type JudgmentOps = S['JudgmentOps'];
export type JudgmentOpsParams = NonNullable<operations['getJudgmentOps']['parameters']['query']>;
export type ChecklistItem = S['ChecklistItem'];
export type ChecklistKind = ChecklistItem['kind'];
/** 체크리스트 종류(계약 2026-10-09.4 '계약', 2026-10-09.6 '사실 재확인' — D10-3 강등 사실 재확인). 표시 = ko.json `page.G7.checkKind` */
export const CHECKLIST_KINDS = [
  '법적 확인',
  '중도금',
  '만료',
  '공고 예상',
  '계약',
  '사실 재확인',
] as const satisfies readonly ChecklistKind[];
export type ChecklistPatch = S['ChecklistPatch'];
export type HumanCheck = S['HumanCheck'];
export type HumanCheckCreate = S['HumanCheckCreate'];
/**
 * 사람 확인 대상 필드(계약 .8 HumanCheckField): 강등 가능한 사실 5개 + 할인(계약 .13 F1·D16-1 — 기준 타입 할인 원, 사람
 * 확인만 '확인됨' 차감을 만든다) + 접수 상태 + 기타(기록만)
 */
export type HumanCheckField = S['HumanCheckField'];
export const HUMAN_CHECK_FIELDS = [
  'intake_status',
  'max_price_won',
  'move_in_ym',
  'resale_months',
  'residency_months',
  'down_payment_pct',
  'discount',
  'other',
] as const satisfies readonly HumanCheckField[];
/** 사람 확인 입력자 = 역할만(계약 2026-10-09.4 EnteredByRole, RA §10 보안 2 — 사람 이름 자유 입력 금지) */
export type EnteredByRole = S['EnteredByRole'];
export const ENTERED_BY_ROLES = ['운영자', '검토자'] as const satisfies readonly EnteredByRole[];

// ─── 계약 2026-10-09.4: 주장 수정·호재 URL·공유 링크 ─────────────

/** G7 주장 목록 행(GET /snapshots/{sid}/claims) — remaining = publish 를 막는 contradicted */
export type ClaimView = S['ClaimView'];
export type ClaimVerifyStatus = NonNullable<ClaimView['verify_status']>;
export type ClaimPatch = S['ClaimPatch'];
export type ClaimListParams = NonNullable<operations['listClaims']['parameters']['query']>;
/** 사람이 넣는 호재 URL(POST /catalysts) */
export type CatalystCreate = S['CatalystCreate'];
export type CatalystCreated = S['CatalystCreated'];
/** 읽기 전용 공유 링크(GET·POST /share-links, DELETE /share-links/{id}) */
export type ShareLink = S['ShareLink'];
export type ShareLinkStatus = ShareLink['status'];
export type ShareLinkCreate = S['ShareLinkCreate'];
export type ShareLinkCreated = S['ShareLinkCreated'];

export type ReportFormat = S['ReportRequest']['format'];
export type ReportRequest = S['ReportRequest'];
/** 호환 별칭 */
export type ReportCreateRequest = ReportRequest;
export type Report = S['Report'];
