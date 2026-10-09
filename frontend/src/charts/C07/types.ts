/** C7 판정기 확률 — 데이터 소스: CompareView.decisions[scenario] (decide items: 후보별 prob + escape 선택지) */
import type { DecisionSet } from '@/lib/contract';

export interface C07Data {
  /** 현재 시나리오의 decide 결과. null = 판정 없음 */
  decision: DecisionSet | null;
}

/**
 * meta §2-7: confidence < 0.6 → 동률. 이 규칙은 서버(decide 정규화)가 적용해 DecisionSet.tie 로 준다 —
 * 프론트는 다시 계산하지 않는다(R3 minor 28). 문서용 상수.
 */
export const C07_TIE_CONFIDENCE = 0.6;

export const C07_EMPTY: C07Data = { decision: null };
