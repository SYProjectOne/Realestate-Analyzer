/**
 * 계약 타입 별칭 (계약 2026-10-09.1) — 원본은 `src/api/types.ts`(생성물 `src/api/schema.d.ts`의 별칭)다.
 * 이 파일은 차트·공통 컴포넌트(WP6b)가 쓰던 이름을 그대로 re-export 하고, props용 `*Like` 구조 타입만 따로 둔다.
 */
import type { IntakePath, IntakeStatus, Label, Market } from '@/api/types';

export type {
  BenchmarkView,
  CatalystStage,
  CatalystView,
  CompareView,
  ComplexDetail,
  ComponentKey,
  ComponentView,
  Dashboard,
  Decision,
  DecisionSet,
  EnvelopeStatus,
  Fact,
  FactUnitHint,
  Gap,
  GapComp,
  Intake,
  IntakePath,
  IntakeStatus,
  JobRun,
  Label,
  LadderHorizon,
  LadderRow,
  Market,
  Provenance,
  ProvenanceConflict,
  Region,
  RemainingEvent,
  RemainingKind,
  ScoreRow,
  Sensitivity,
  SensitivityCell,
  Snapshot,
  SupplyPoint,
  UnsoldPoint,
  Verdict3,
  Weights,
} from '@/api/types';
export { COMPONENT_KEYS } from '@/api/types';

export type BenchmarkFlag = Market['benchmark_flags'][number];
export type MoveInMarker = Market['move_in_markers'][number];

/** 생활권 id → 이름 (Market.living_areas / Region.living_areas) */
export interface LivingAreaName {
  id: string;
  name: string;
}

// ─── 컴포넌트 props용 구조 타입(임시·계약 타입 모두 대입 가능) ───────────

/** Fact의 표시에 필요한 최소 모양. 계약 Fact·임시 Fact 모두 대입된다. */
export interface FactLike {
  v: number | string | null;
  label: Label;
  prov: string | null;
  checked_at: string | null;
  reason?: string | null;
  human?: boolean;
  unit?: string;
}

/** IntakeBadge 입력 */
export interface IntakeLike {
  status: IntakeStatus;
  path: IntakePath;
  checked_at?: string | null;
  reason?: string | null;
  evidence_url?: string | null;
  http_status?: number | null;
}

/** RegionPicker 옵션 */
export interface RegionLike {
  id: string | number;
  name: string;
}

/** SnapshotPicker 옵션 */
export interface SnapshotLike {
  id: string | number;
  asof_date: string;
  status?: string;
  degraded?: boolean;
  /** 같은 기준일 리비전 번호(계약 .8, D11-1). 옛 응답엔 없다(= 1) */
  revision?: number;
  /** 리비전을 만든 사유(리비전 1 은 null) */
  revision_reason?: string | null;
}

/** JobProgressView 입력 */
export interface JobLike {
  id: string | number;
  job_name: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  error_text: string | null;
  progress?: { done: number; total: number; step?: string | null } | null;
}
