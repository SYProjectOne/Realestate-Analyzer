/** C9 호재 단계 — 데이터 소스: Market.catalysts[] (G6) / ComplexDetail.catalysts[] (G3 작게) */
import type { Catalyst, CatalystStage } from '@/api/types';

export interface C09Data {
  catalysts: Catalyst[];
  /** G3 작게: 보드만, 타임라인 숨김 */
  compact?: boolean;
}

/** 보드 열 순서 (HTML 그리드 5열) */
export const C09_STAGES: readonly CatalystStage[] = ['확정', '계획', '추진', '언론', '미확정'];
/** 회색으로 그릴 단계 */
export const C09_GRAYED: readonly CatalystStage[] = ['언론', '미확정'];

export const C09_EMPTY: C09Data = { catalysts: [] };
