/** C10 민감도 — 데이터 소스: Sensitivity.cells[] (가중치 ±10%p 12변형 × TOP 5) */
import type { Sensitivity } from '@/api/types';

export interface C10Data {
  sensitivity: Sensitivity | null;
}

export const C10_EMPTY: C10Data = { sensitivity: null };
