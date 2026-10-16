/** C10 민감도 — 데이터 소스: GET /sensitivity → Sensitivity.cells[] (가중치 ±0.10 변형 12개 × TOP 5) */
import type { Sensitivity } from '@/lib/contract';

export interface C10Data {
  sensitivity: Sensitivity | null;
  /** complex_id → 단지명 (Sensitivity에는 id만 있다 — Dashboard.top5·CompareView.rows에서 만든다) */
  names?: Record<string, string>;
}

/** '상위 5곳'(TOP 5) — 서버 top5 의 뜻. 순위가 이보다 크면 상위 5곳 밖(주황 띠) */
export const C10_TOP = 5;

export const C10_EMPTY: C10Data = { sensitivity: null };
