/** C3 벤치마크 slope(dumbbell) — 데이터 소스: Market.benchmarks[] (+ benchmark_flags, living_areas) */
import type { BenchmarkFlag, BenchmarkView, LivingAreaName } from '@/lib/contract';

export interface C03Data {
  benchmarks: BenchmarkView[];
  /** 연율 환산 기준 연도(스냅샷 asof_date의 연도). 서버 annualized_pct가 없을 때만 쓴다. null이면 생략 */
  asofYear: number | null;
  /** Market.benchmark_flags — 생활권별 표본 수(분양권 제외). 없으면 benchmarks에서 센다 */
  flags?: BenchmarkFlag[];
  /** Market.living_areas — 배지에 생활권 이름 */
  livingAreas?: LivingAreaName[];
}

/** 표본 < 3 → "표본 n, 추정" 배지 */
export const C03_MIN_SAMPLE = 3;

export const C03_EMPTY: C03Data = { benchmarks: [], asofYear: null };
