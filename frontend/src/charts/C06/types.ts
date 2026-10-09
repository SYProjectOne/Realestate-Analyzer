/** C6 종합 점수 분해 — 데이터 소스: ScoreRow.components + score_run.weights (Dashboard.weights / CompareView.weights) */
import type { ScoreRow, Weights } from '@/api/types';

export interface C06Data {
  rows: ScoreRow[];
  weights: Weights;
  /** G1 = vertical(단지가 x축), G4 = horizontal(가로 막대) */
  orientation?: 'vertical' | 'horizontal';
}

export const C06_EMPTY: C06Data = {
  rows: [],
  weights: { p10: 0, rerank: 0, gap: 0, benchmark: 0, supply: 0, liquidity: 0 },
};
