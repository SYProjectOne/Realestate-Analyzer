/** buildOption 공용 도우미 — 순수 함수만. */
import type { FactLike, Label } from '@/lib/contract';

/** Fact → 숫자 또는 null (문자열 숫자도 허용) */
export function num(fact: FactLike | null | undefined): number | null {
  if (!fact || fact.v === null || fact.v === undefined) return null;
  const n = typeof fact.v === 'number' ? fact.v : Number(fact.v);
  return Number.isFinite(n) ? n : null;
}

/** Fact → 문자열 값 또는 null */
export function str(fact: FactLike | null | undefined): string | null {
  if (!fact || fact.v === null || fact.v === undefined || fact.v === '') return null;
  return String(fact.v);
}

/** 데이터에 쓰인 라벨 모음(ChartFrame 배지용) */
export function collectLabels(facts: (FactLike | null | undefined)[]): Label[] {
  const out = new Set<Label>();
  for (const fact of facts) if (fact) out.add(fact.label);
  return [...out];
}

/**
 * ECharts 툴팁(renderMode html)은 formatter 문자열을 innerHTML로 넣는다 →
 * 서버 문자열(단지명·질문·산출식)은 반드시 이스케이프한다.
 */
export function escapeHtml(text: string | null | undefined): string {
  if (text === null || text === undefined) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 'YYYY-MM' 또는 'YYYY-MM-DD…' → 'YYYY-MM-DD' (월만 확인된 값은 1일로). 아니면 null */
export function toIsoDay(value: string | null | undefined): string | null {
  if (!value) return null;
  const day = /^\d{4}-\d{2}-\d{2}/.exec(value);
  if (day) return day[0];
  const month = /^(\d{4})-(\d{2})$/.exec(value);
  return month ? `${month[1]}-${month[2]}-01` : null;
}

const monthIndex = (ym: string): number | null => {
  const m = /^(\d{4})-(\d{2})/.exec(ym);
  return m ? Number(m[1]) * 12 + Number(m[2]) - 1 : null;
};

/** 'YYYY-MM' 범위를 끊김 없이 나열 (양 끝 포함) */
export function monthRange(from: string, to: string): string[] {
  const a = monthIndex(from);
  const b = monthIndex(to);
  if (a === null || b === null || b < a) return [];
  const out: string[] = [];
  for (let i = a; i <= b; i += 1) {
    out.push(`${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`);
  }
  return out;
}

/** 생활권 id → 이름 (모르면 id 그대로) */
export function livingAreaName(
  id: string | null | undefined,
  areas: readonly { id: string; name: string }[] | undefined,
): string | null {
  if (!id) return null;
  return areas?.find((a) => a.id === id)?.name ?? id;
}
