/** buildOption 공용 도우미 — 순수 함수만. */
import type { Fact, Label } from '@/api/types';

/** Fact → 숫자 또는 null (문자열 숫자도 허용) */
export function num(fact: Fact | null | undefined): number | null {
  if (!fact || fact.v === null || fact.v === undefined) return null;
  const n = typeof fact.v === 'number' ? fact.v : Number(fact.v);
  return Number.isFinite(n) ? n : null;
}

/** 데이터에 쓰인 라벨 모음(ChartFrame 배지용) */
export function collectLabels(facts: (Fact | null | undefined)[]): Label[] {
  const out = new Set<Label>();
  for (const fact of facts) if (fact) out.add(fact.label);
  return [...out];
}
