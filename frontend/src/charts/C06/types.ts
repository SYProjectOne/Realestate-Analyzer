/**
 * C6 종합 점수 분해 — 데이터 소스: ScoreRow.components(ComponentView) + score_run.weights
 * (Dashboard.top5·weights / CompareView.rows·components.weights·keys)
 */
import type { ComponentKey, ScoreRow, Weights } from '@/lib/contract';

export interface C06Data {
  rows: ScoreRow[];
  weights: Weights;
  /** G1 = vertical(단지가 x축), G4 = horizontal(가로 막대) */
  orientation?: 'vertical' | 'horizontal';
  /** 성분 키 순서(CompareView.components.keys). 생략하면 weights·rows에서 고른다(A·D는 liquidity 대신 move_in) */
  keys?: ComponentKey[];
}

export const C06_EMPTY: C06Data = {
  rows: [],
  weights: { p10: 0, rerank: 0, gap: 0, benchmark: 0, supply: 0, liquidity: 0 },
};
