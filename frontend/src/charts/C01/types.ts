/** C1 상승 확률 사다리 — 데이터 소스: ComplexDetail.ladder[horizon] (p5, p10, p20, p_flat) / CompareView.ladders[id] */
import type { LadderHorizon, LadderRow } from '@/lib/contract';

export type LadderBar = 'p5' | 'p10' | 'p20' | 'p_flat';

export interface C01OverlaySeries {
  complex_id: number | string;
  name: string;
  ladder: LadderRow[];
}

export interface C01Data {
  /** G3: 한 단지의 사다리 행(horizon 3종) */
  ladder: LadderRow[];
  /** 표시할 horizon (탭 3개 중 선택) */
  horizon: LadderHorizon;
  /** G4: 단지별 사다리를 점(scatter)으로 겹쳐 그림. 있으면 overlay 모드 */
  overlay?: C01OverlaySeries[];
}

export const C01_BARS: readonly LadderBar[] = ['p5', 'p10', 'p20', 'p_flat'];
export const C01_HORIZONS: readonly LadderHorizon[] = [
  'move_in_plus_1y',
  'asof_plus_3y',
  'asof_plus_5y',
];
/** markLine 임계: likely 0.85 / unlikely 0.15 (meta §2-7) */
export const C01_THRESHOLDS = { likely: 0.85, unlikely: 0.15 } as const;
/** overlay 단지별 마커 모양 — 색만으로 단지를 구분하지 않는다 */
export const C01_OVERLAY_SYMBOLS = ['circle', 'rect', 'triangle', 'diamond', 'pin', 'roundRect'];

export const C01_EMPTY: C01Data = { ladder: [], horizon: 'move_in_plus_1y' };
