/** C8 잔여 이력 타임라인 — 데이터 소스: ComplexDetail.events[] (kind, notice_date, units, ratio_text) */
import type { RemainingEvent, RemainingKind } from '@/lib/contract';

export interface C08Data {
  events: RemainingEvent[];
  /** 기준일(스냅샷 asof, 'YYYY-MM-DD') — 시간축에 세로 점선. 생략하면 선 없음 */
  asof?: string | null;
}

/** 마커 모양 = kind 4종 (색만으로 구분하지 않는다) */
export const C08_SYMBOLS: Record<RemainingKind, string> = {
  본청약: 'circle',
  무순위: 'rect',
  임의: 'triangle',
  선착순: 'diamond',
};

export const C08_EMPTY: C08Data = { events: [] };
