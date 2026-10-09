/** C10 민감도 — 데이터 소스: Sensitivity.cells[] (가중치 ±10%p 12변형 × TOP 5) */
import type { Sensitivity } from '@/api/types';

export interface C10Data {
  sensitivity: Sensitivity | null;
  /** complex_id → 단지명 (Sensitivity는 id만 준다; 화면이 ScoreRow 등에서 채운다) */
  names?: Record<string, string>;
}

export function c10Name(data: C10Data, id: number): string {
  return data.names?.[String(id)] ?? `#${id}`;
}

export const C10_EMPTY: C10Data = { sensitivity: null };
