/** C5 미분양 추이 — 데이터 소스: Market.unsold[] (월말 기준) */
import type { UnsoldRow } from '@/api/types';

export interface C05Data {
  unsold: UnsoldRow[];
  /** 최근 몇 개월을 그릴지 (기본 24) */
  months?: number;
}

export const C05_DEFAULT_MONTHS = 24;

export const C05_EMPTY: C05Data = { unsold: [] };
