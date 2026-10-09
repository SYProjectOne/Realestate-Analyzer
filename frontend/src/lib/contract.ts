/**
 * 계약 타입 별칭 (계약 2026-10-09.1) — 생성물 `src/api/schema.d.ts`(contracts/openapi.bundled.yaml)에서 직접 온다.
 *
 * 차트·공통 컴포넌트(WP6b)는 응답 모양을 이 파일로만 본다. `src/api/types.ts`는 계약 머지 전 임시 타입이라
 * 모양이 다르고(id 문자열, Benchmark ↔ BenchmarkView 등) WP6a가 생성 타입 별칭으로 바꾸는 중이다.
 * 컴포넌트 props는 아래 `*Like` 구조 타입으로 받아 임시 타입·계약 타입 어느 쪽이 와도 컴파일된다.
 */
import type { components } from '@/api/schema';

type Schemas = components['schemas'];

// ─── 공통 ───────────────────────────────────────────────────
export type Label = Schemas['Label'];
export type Fact = Schemas['Fact'];
export type FactUnitHint = NonNullable<Fact['unit']>;
export type Intake = Schemas['Intake'];
export type EnvelopeStatus = Schemas['LadderRow']['status'];

// ─── 화면 응답 ──────────────────────────────────────────────
export type ComplexDetail = Schemas['ComplexDetail'];
export type Market = Schemas['Market'];
export type Dashboard = Schemas['Dashboard'];
export type CompareView = Schemas['CompareView'];
export type Provenance = Schemas['Provenance'];
export type ProvenanceConflict = Schemas['ProvenanceConflict'];
export type JobRun = Schemas['JobRun'];
export type Snapshot = Schemas['Snapshot'];
export type Region = Schemas['Region'];

// ─── 차트 입력 ──────────────────────────────────────────────
export type LadderRow = Schemas['LadderRow'];
export type LadderHorizon = LadderRow['horizon'];
export type Verdict3 = Schemas['Verdict3'];
export type Gap = Schemas['Gap'];
export type GapComp = Schemas['GapComp'];
export type BenchmarkView = Schemas['BenchmarkView'];
export type BenchmarkFlag = Market['benchmark_flags'][number];
export type SupplyPoint = Schemas['SupplyPoint'];
export type MoveInMarker = Market['move_in_markers'][number];
export type UnsoldPoint = Schemas['UnsoldPoint'];
export type ScoreRow = Schemas['ScoreRow'];
export type ComponentKey = Schemas['ComponentKey'];
export type ComponentView = Schemas['ComponentView'];
export type Weights = Schemas['Weights'];
export type DecisionSet = Schemas['DecisionSet'];
export type Decision = Schemas['Decision'];
export type RemainingEvent = Schemas['RemainingEvent'];
export type RemainingKind = RemainingEvent['kind'];
export type CatalystView = Schemas['CatalystView'];
export type CatalystStage = CatalystView['stage'];
export type Sensitivity = Schemas['Sensitivity'];
export type SensitivityCell = Schemas['SensitivityCell'];

/** 성분 표시 순서(ScoreRow.components·Weights 키). move_in은 상황 A·D에서 liquidity 대신 온다 */
export const COMPONENT_KEYS: readonly ComponentKey[] = [
  'p10',
  'rerank',
  'gap',
  'benchmark',
  'supply',
  'liquidity',
  'move_in',
];

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

export type IntakeStatus = Intake['status'];
export type IntakePath = Intake['path'];

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
}

/** JobProgressView 입력 */
export interface JobLike {
  id: string | number;
  job_name: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  error_text: string | null;
  progress?: { done: number; total: number; step?: string | null } | null;
}
