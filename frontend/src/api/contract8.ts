/**
 * 계약 2026-10-09.8 **초안** 타입 (R3C_FIX.md "계약 .8 초안" + CORE 진행본 human_check·snapshot 스키마).
 *
 * CORE 가 계약 .8 을 main 에 머지하면 `npm run gen:api && npm run gen:msw` 로 생성 타입이 생긴다 — 그때 이 파일의
 * 타입을 `./types`(생성 별칭)로 옮기고 이 파일을 지운다. 화면은 여기 이름만 쓰므로 바꿀 곳은 import 한 줄씩이다.
 * 생성물(schema.d.ts·handlers.gen.ts)은 손으로 고치지 않는다 — 초안 동작은 handlers.extra.ts(MSW)가 흉내 낸다.
 */
import type { CatalystView, JobRun, Label, Region, Snapshot } from './types';

// ─── M-5 / D11-3: 사람 확인 대상 필드 ─────────────────────────

/** 사람 확인 대상: 강등 가능한 사실 필드 5개 + 접수 상태 + 기타(기록만) — 계약 .8 HumanCheckField */
export const HUMAN_CHECK_FIELDS = [
  'intake_status',
  'max_price_won',
  'move_in_ym',
  'resale_months',
  'residency_months',
  'down_payment_pct',
  'other',
] as const;
export type HumanCheckField = (typeof HUMAN_CHECK_FIELDS)[number];

/** HumanCheckCreate.value_text·note 길이 상한(계약 .8) */
export const HUMAN_CHECK_VALUE_MAX = 200;
export const HUMAN_CHECK_NOTE_MAX = 500;

/** 사실 필드 값 형·범위(계약 .8 HumanCheckField 설명) — 서버도 같은 검사로 422 */
export const HUMAN_CHECK_RULES: Partial<
  Record<HumanCheckField, { kind: 'int' | 'number' | 'ym'; min?: number; max?: number }>
> = {
  max_price_won: { kind: 'int', min: 1 },
  move_in_ym: { kind: 'ym' },
  resale_months: { kind: 'int', min: 0, max: 240 },
  residency_months: { kind: 'int', min: 0, max: 240 },
  down_payment_pct: { kind: 'number', min: 0, max: 100 },
};

/**
 * 강등(FactDemotion.field)·주장 대상 필드 → 사람 확인 필드. 가격 강등은 점수·화면이 쓰는
 * `payment_terms.price_by_type`(D11-3)에 걸리고 사람 확인은 `max_price_won` 으로 넣는다. 매핑 없으면 null.
 */
export function humanCheckFieldOf(field: string | null | undefined): HumanCheckField | null {
  if (!field) return null;
  if ((HUMAN_CHECK_FIELDS as readonly string[]).includes(field)) return field as HumanCheckField;
  if (field === 'price_by_type' || field === 'price_won' || field === 'max_price') {
    return 'max_price_won';
  }
  return null;
}

/** HumanCheckCreate(계약 .8): field enum + entity_id(사실 행 지정, 선택) */
export interface HumanCheckCreate8 {
  complex_id: number;
  field: HumanCheckField;
  entity_id?: number | null;
  value_text: string;
  kind: 'phone' | 'visit' | 'email';
  checked_at: string;
  entered_by: '운영자' | '검토자';
  note?: string | null;
}

// ─── D11-1: 스냅샷 리비전 ─────────────────────────────────────

/** Snapshot + 리비전(계약 .8). 옛 응답(.7)엔 없을 수 있어 선택 필드로 읽는다 */
export type SnapshotRev = Snapshot & {
  revision?: number;
  revision_of?: number | null;
  revision_reason?: string | null;
};

// ─── D11-5: 호재 위치 확인 → catalyst_link ────────────────────

/** '호재 아님'(D10-6·D11-2) 포함 단계 */
export type CatalystStage8 = CatalystView['stage'] | '호재 아님';

/** PATCH /catalysts/{id} 본문(계약 .8 초안) */
export interface CatalystPatch {
  location_confirmed: boolean;
  lat?: number | null;
  lon?: number | null;
  living_area_ids?: string[];
  complex_ids?: number[];
}

/** catalyst_link 1행: 단지 좌표가 없으면 distance_m=null·weight=1(같은 생활권)·라벨 추정(D11-5) */
export interface CatalystLink {
  complex_id: number;
  distance_m: number | null;
  weight: number;
  label: Label;
}

/** PATCH /catalysts/{id} 응답 = Catalyst + links */
export interface CatalystPatched {
  catalyst: CatalystView;
  links: CatalystLink[];
}

// ─── D11-7: 지역 선택 확장 ────────────────────────────────────

/** PATCH /regions/{id} 본문: 선택 전체(추가·제거 반영) — 새 리비전에서 후보 전체 rerank 1회 */
export interface RegionPatch {
  selections: Region['selections'];
}

/** PATCH /regions/{id} 응답 = Region + 잡(region.expand → 새 리비전 rejudge) */
export interface RegionPatched {
  region: Region;
  job: JobRun;
}
