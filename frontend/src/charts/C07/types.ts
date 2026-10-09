/** C7 판정기 확률 — 데이터 소스: CompareView.decisions[scenario] (decide prob per 후보 + escape) */
import type { DecisionSet } from '@/api/types';

export interface C07Data {
  /** 현재 시나리오의 decide 결과. null = 판정 없음 */
  decision: DecisionSet | null;
}

/** confidence < 0.6 → TieBadge "동률" (meta §2-7) */
export const C07_TIE_CONFIDENCE = 0.6;

export const C07_EMPTY: C07Data = { decision: null };
