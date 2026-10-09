/** C5 미분양 추이 — 데이터 소스: Market.unsold[] / Dashboard.unsold_series[] (월말 기준) */
import type { UnsoldPoint } from '@/lib/contract';

export interface C05Data {
  unsold: UnsoldPoint[];
  /** 최근 몇 개월을 그릴지 (기본 24) */
  months?: number;
  /** 그릴 범위(scope_code). 생략하면 자료가 가장 많은 범위 하나 */
  scope?: string | null;
}

export const C05_DEFAULT_MONTHS = 24;

export const C05_EMPTY: C05Data = { unsold: [] };
