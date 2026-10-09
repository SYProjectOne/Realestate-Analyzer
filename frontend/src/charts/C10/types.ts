/** C10 민감도 — 데이터 소스: GET /sensitivity → Sensitivity.cells[] (가중치 ±0.10 변형 12개 × TOP 5) */
import type { Sensitivity } from '@/lib/contract';

export interface C10Data {
  sensitivity: Sensitivity | null;
  /** complex_id → 단지명 (Sensitivity에는 id만 있다 — Dashboard.top5·CompareView.rows에서 만든다) */
  names?: Record<string, string>;
}

export const C10_EMPTY: C10Data = { sensitivity: null };
