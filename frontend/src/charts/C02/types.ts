/**
 * C2 가격 갭 — 데이터 소스: ComplexDetail.gap / CompareView.gaps[id]
 *   gap{price_low, price_high, price_mid, comps[]: {name, low, median, high, adjusted_median, substitute}}
 * G4 "나란히"는 C02를 단지 수만큼 렌더한다.
 */
import type { Gap } from '@/api/types';

export interface C02Data {
  /** null = 갭 계산 없음(비교군 없음 사유는 gap.empty_reason) */
  gap: Gap | null;
}

export const C02_EMPTY: C02Data = { gap: null };
