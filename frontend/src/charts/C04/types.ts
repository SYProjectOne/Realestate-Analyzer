/** C4 입주 물량 — 데이터 소스: Market.supply[] (+ Market.move_in_markers = 판정 단지 입주월 마커) */
import type { FactLike, LivingAreaName, SupplyPoint } from '@/lib/contract';

/** 판정 단지 입주월 마커. Market.move_in_markers 그대로(move_in_ym = Fact) 또는 'YYYY-MM' 문자열 */
export interface C04Marker {
  complex_id: number | string;
  name: string;
  move_in_ym: FactLike | string;
}

export interface C04Data {
  supply: SupplyPoint[];
  /** 판정 단지 입주월 markPoint (G3에서는 해당 단지 1개) */
  markers: C04Marker[];
  /** Market.living_areas — 스택 계열 이름 */
  livingAreas?: LivingAreaName[];
}

/** 따로 색을 주는 큰 생활권 수 — 나머지는 '나머지 n곳'(목업 Market: 5곳 + 나머지) */
export const C04_TOP_AREAS = 5;

export const C04_EMPTY: C04Data = { supply: [], markers: [] };
