/** C4 입주 물량 — 데이터 소스: Market.supply[] (+ 판정 단지 입주월 마커) */
import type { Id, SupplyRow, YearMonth } from '@/api/types';

export interface C04Marker {
  complex_id: Id;
  name: string;
  move_in_ym: YearMonth;
}

export interface C04Data {
  supply: SupplyRow[];
  /** 판정 단지 입주월 markPoint (G3에서는 해당 단지 1개) */
  markers: C04Marker[];
}

export const C04_EMPTY: C04Data = { supply: [], markers: [] };
