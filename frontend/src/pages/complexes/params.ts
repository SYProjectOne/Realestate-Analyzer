/** G2 필터·정렬 ↔ URL 쿼리 ↔ API 쿼리(filter[...] deepObject) */
import type { ComplexFilter, ComplexListParams } from '@/api/types';

/** URL 쿼리 키 = API filter 키. 가격은 URL에서 억 단위(읽기 쉬움), API로는 원 */
export const FILTER_KEYS = [
  'living_area',
  'intake_status',
  'land_type',
  'resale_end_before',
  'price_min',
  'price_max',
  'move_in_year',
  'inclusion_class',
  'judge_scope',
  'q',
] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];
export type FilterValues = Partial<Record<FilterKey, string>>;

export const SORT_KEYS = [
  'total',
  'rank',
  'name',
  'price_mid',
  'price_low',
  'move_in_ym',
  'resale_end',
  'gap_pct',
  'p10',
  'living_area',
  'last_change',
  // 계약 .20 F10: 접수 상태(가능 → 미정 → 확인 불가 → 불가, 같은 상태 안 마감 임박)
  'intake',
] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export const DEFAULT_SORT = '-total';
/**
 * G2 목록 페이지 크기(계약 size 최대 1000). 첫 화면은 FIRST_PAGE_SIZE 로 먼저 그리고(W8 — T16 첫 렌더 1초),
 * 나머지는 PAGE_SIZE 페이지를 이어 받아 같은 가상 스크롤 표에 붙인다(W9 — total 의 모든 행에 닿는다).
 */
export const PAGE_SIZE = 1000;
export const FIRST_PAGE_SIZE = 100;

const EOK = 100_000_000;

export function readFilters(params: URLSearchParams): FilterValues {
  const out: FilterValues = {};
  for (const key of FILTER_KEYS) {
    const v = params.get(key);
    if (v) out[key] = v;
  }
  return out;
}

export function readSort(params: URLSearchParams): string {
  const sort = params.get('sort');
  if (!sort) return DEFAULT_SORT;
  const key = sort.replace(/^-/, '');
  return (SORT_KEYS as readonly string[]).includes(key) ? sort : DEFAULT_SORT;
}

export function toApiFilter(values: FilterValues): ComplexFilter {
  const filter: ComplexFilter = {};
  if (values.living_area) filter.living_area = values.living_area;
  if (values.intake_status) filter.intake_status = values.intake_status;
  if (values.land_type) filter.land_type = values.land_type;
  if (values.inclusion_class) filter.inclusion_class = values.inclusion_class;
  if (values.judge_scope) filter.judge_scope = values.judge_scope;
  if (values.resale_end_before) filter.resale_end_before = values.resale_end_before;
  if (values.q) filter.q = values.q;
  const min = Number(values.price_min);
  if (values.price_min && Number.isFinite(min)) filter.price_min = Math.round(min * EOK);
  const max = Number(values.price_max);
  if (values.price_max && Number.isFinite(max)) filter.price_max = Math.round(max * EOK);
  const year = Number(values.move_in_year);
  if (values.move_in_year && Number.isInteger(year)) filter.move_in_year = year;
  return filter;
}

export function toListParams(
  values: FilterValues,
  sort: string,
  scenario: string | null,
): ComplexListParams {
  return {
    page: 1,
    size: PAGE_SIZE,
    sort,
    ...(scenario ? { scenario } : {}),
    filter: toApiFilter(values),
  };
}

/** 처음 누르면 오름차순인 키 — intake 는 오름차순이 '접수 가능 먼저'(서버 INTAKE_ORDER) */
const ASC_FIRST: ReadonlySet<SortKey> = new Set(['intake']);

/** 헤더 클릭: 같은 키면 방향을 뒤집고, 새 키면 내림차순부터(접수 상태는 가능 먼저) */
export function nextSort(current: string, key: SortKey): string {
  if (ASC_FIRST.has(key)) return current === key ? `-${key}` : key;
  if (current === `-${key}`) return key;
  return `-${key}`;
}
