/**
 * 비수치 메타 — 사실(Fact)이 **아닌** 숫자를 문자열로 만드는 곳 (R3c, no-raw-number-render 9·10).
 *
 * 화면의 숫자는 둘 중 하나다:
 *  1. 사실(가격·세대수·점수·확률 …) → `<FactCell fact>` (값 + 라벨 배지 + 출처). 라벨 없는 사실 숫자 금지.
 *  2. 비수치 메타(목록 개수·순위·소요 시간·HTTP 상태·판정 로그 번호·입력 칸 값·진행률 …) — 출처·라벨이
 *     없는 화면·운영 정보 → `<MetaValue>`·`<MetaText>`(JSX, `data-meta` 표시) 또는 이 파일의 함수(속성·문구).
 *
 * `src/lib/format.ts` 의 숫자 포맷 함수(formatCount·formatRank …)는 FactCell·MetaValue·이 파일·차트
 * buildOption 만 부른다(ESLint). 사실 값(`fact.v`)을 메타로 넘기면 lint 가 막는다(10).
 */
import { t, type TKey } from '@/i18n';
import { formatConfidence, formatCount, formatNumber, formatValue, type FactUnit } from './format';

/** 메타 숫자 포맷: FactUnit + 판정기 신뢰도(0~1 → "0.48") + plain(천 단위 구분 없는 정수: HTTP 상태·번호) */
export type MetaFormat = FactUnit | 'confidence' | 'plain';

/** 메타 숫자 하나: 그냥 숫자(정수 → 천 단위, 소수 → 둘째 자리) 또는 포맷 지정 */
export type MetaNum = number | { n: number; as?: MetaFormat; digits?: number };

/** metaText 파라미터: 문자열(이미 만든 문구·이름) 또는 메타 숫자 */
export type MetaParam = string | MetaNum;

/** 메타 숫자 → 문자열 */
export function metaNumber(value: MetaNum): string {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? formatCount(value) : formatNumber(value, 2);
  }
  const { n, as = 'number', digits } = value;
  if (as === 'confidence') return formatConfidence(n);
  if (as === 'plain') return Number.isFinite(n) ? String(Math.round(n)) : formatNumber(n);
  return formatValue(n, as, { digits });
}

/** ko.json 문구 + 메타 숫자 파라미터 → 문자열 (속성·토스트·폼 오류처럼 JSX 자식이 아닌 자리) */
export function metaText(key: TKey, params: Record<string, MetaParam>): string {
  const out: Record<string, string> = {};
  for (const [name, value] of Object.entries(params)) {
    out[name] = typeof value === 'string' ? value : metaNumber(value);
  }
  return t(key, out);
}
