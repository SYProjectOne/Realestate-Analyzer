/** C3 벤치마크 slope(dumbbell) — 데이터 소스: Market.benchmarks[] */
import type { Benchmark } from '@/api/types';

export interface C03Data {
  benchmarks: Benchmark[];
  /** 연율 환산 기준 연도(스냅샷 asof_date의 연도). null이면 툴팁에 연율 생략 */
  asofYear: number | null;
}

/** 표본 < 3 → "표본 n, 추정" 배지 */
export const C03_MIN_SAMPLE = 3;

export const C03_EMPTY: C03Data = { benchmarks: [], asofYear: null };
