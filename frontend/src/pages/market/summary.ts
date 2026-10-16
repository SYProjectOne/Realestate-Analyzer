/**
 * G6 한눈에 보기·표 보조(목업 MK-1·MK-8·MK-9) — **줄을 세거나 같은 값인지 보기만** 한다(D25-3 개수 세기). 값을 더하거나
 * 가장 큰 곳·가장 몰리는 해를 고르지 않는다(AGENTS 규칙 3·5). 문구는 화면이 ko.json 으로 붙인다.
 */
import type { Market } from '@/api/types';

type RegulationItem = Market['regulation']['items'][number];
type RegulationKey = RegulationItem['key'];

/** 계약 RegulationItem.key enum 8종 — 화면은 이 순서로 모두 보인다(목업 MK-8) */
export const REGULATION_KINDS: readonly RegulationKey[] = [
  'regulated_area',
  'price_cap',
  'resale',
  'residency',
  'loan',
  'tax',
  'land_permit',
  'other',
];

/** 입주 핀(입주 연월이 있는 판정 단지)을 해마다 센다 — 연도 오름차순 */
export function moveInByYear(
  markers: readonly { move_in_ym: string }[],
): { year: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const m of markers) {
    const year = m.move_in_ym.slice(0, 4);
    counts.set(year, (counts.get(year) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, count]) => ({ year, count }));
}

/** 값이 모두 같으면 그 값, 하나라도 다르거나 비었으면 null */
export function sharedValue(values: readonly (string | null | undefined)[]): string | null {
  if (values.length === 0) return null;
  const first = values[0];
  if (!first) return null;
  return values.every((v) => v === first) ? first : null;
}

/** 실거래 중간 값이 있는 생활권 줄 수 + 모든 줄의 거래 기간이 같으면 그 기간(서버 문자열) */
export function areaPriceSummary(rows: Market['living_area_prices']): {
  withValue: number;
  window: string | null;
} {
  return {
    withValue: rows.filter((r) => r.median_won.v !== null && r.median_won.v !== undefined).length,
    window: sharedValue(rows.map((r) => r.trade_window)),
  };
}

/**
 * 한 규제 종류의 항목을 서버 값(글자) 별로 센다 — "'비규제' 9곳". 처음 나온 순서. 값이 없는 항목은 세지 않는다
 * (그 줄은 아래 규제 칸에서 '확인 불가(사유)'로 보인다).
 */
export function regulationGroups(
  items: readonly RegulationItem[],
  key: RegulationKey,
): { value: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    if (item.key !== key) continue;
    const v = item.value.v;
    if (v === null || v === undefined || v === '') continue;
    const text = String(v);
    counts.set(text, (counts.get(text) ?? 0) + 1);
  }
  return [...counts.entries()].map(([value, count]) => ({ value, count }));
}

/** 미분양 범위(시군구) 목록 — 처음 나온 순서, 같은 코드는 한 번 */
export function unsoldScopes(rows: Market['unsold']): { code: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const r of rows) {
    const code = r.scope_code;
    if (!code || seen.has(code)) continue;
    seen.set(code, r.scope_name ?? code);
  }
  return [...seen.entries()].map(([code, name]) => ({ code, name }));
}
