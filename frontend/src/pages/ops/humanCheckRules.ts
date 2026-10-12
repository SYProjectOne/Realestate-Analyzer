/**
 * 사람 확인 값 규칙(계약 2026-10-09.8 HumanCheckField · 서버 `app/api/demotion.py` parse_human_value 와 같은 범위).
 * 서버는 같은 검사로 422 를 낸다 — 화면은 POST 전에 같은 규칙으로 막는다(절삭·반올림 없음, 3차 리뷰 minor 11).
 */
import { HUMAN_CHECK_FIELDS, type HumanCheckField } from '@/api/types';
import type { MetaFormat } from '@/lib/meta';

/** 사람 확인 폼 앵커·미리 채우기 URL 파라미터(ClaimsPanel '사람 확인으로 복원'·G3 '추정' 할인 링크가 쓴다) */
export const HUMAN_CHECK_ANCHOR = 'human-check';
export const HC_PARAM = { complex: 'hc_complex', field: 'hc_field', entity: 'hc_entity' } as const;

/** HumanCheckCreate.value_text·note 길이 상한(계약 .8) */
export const HUMAN_CHECK_VALUE_MAX = 200;
export const HUMAN_CHECK_NOTE_MAX = 500;

export interface HumanCheckRule {
  kind: 'int' | 'number' | 'ym';
  min?: number;
  max?: number;
  /** number: 소수 자릿수 상한 */
  decimals?: number;
  /** 범위 오류 문구의 숫자 포맷(원 → '1,000만') */
  unit?: MetaFormat;
}

/**
 * 사실 필드 값 형·범위(서버 허용 범위). 접수 상태·기타는 규칙 없음(길이만). 할인(`discount`)은 계약 .14 F3 부터 서버와 같은
 * 엄격한 규칙으로 화면도 검사한다(기준 타입 차감 바탕 이상 `discount_not_below_price` 는 서버만 안다 — 422 를 값 칸에).
 */
export const HUMAN_CHECK_RULES: Partial<Record<HumanCheckField, HumanCheckRule>> = {
  /** 원 단위 정수, 1,000만 ~ 1,000억 */
  max_price_won: { kind: 'int', min: 10_000_000, max: 100_000_000_000, unit: 'won' },
  /** YYYY-MM, 2000-01 ~ 2100-12 */
  move_in_ym: { kind: 'ym', min: 2000, max: 2100 },
  resale_months: { kind: 'int', min: 0, max: 240 },
  residency_months: { kind: 'int', min: 0, max: 240 },
  /** 0 ~ 100, 소수 둘째 자리까지 */
  down_payment_pct: { kind: 'number', min: 0, max: 100, decimals: 2 },
  /** 원 단위 정수 0 ~ 1,000억(0 = 할인 없음 확인), 기준 타입 할인(계약 .13 F1·.14 F3) */
  discount: { kind: 'int', min: 0, max: 100_000_000_000, unit: 'won' },
};

/**
 * 숫자 필드가 받는 단위 접미어(서버 `parse_human_value` allowed 와 같다). 개월 필드의 '년'은 ×12. 없으면 단위 없음.
 */
export const HUMAN_NUMBER_UNITS: Partial<Record<HumanCheckField, readonly string[]>> = {
  resale_months: ['개월', '년'],
  residency_months: ['개월', '년'],
  max_price_won: ['원'],
  discount: ['원'],
  down_payment_pct: ['%'],
};

/**
 * 계약 .14 F3·F4(R3i m2) 서버 `_STRICT_NUMBER_RE` 와 같은 꼴: ASCII 숫자, 쉼표는 세 자리 묶음만, 숫자 사이 공백 없음,
 * 단위 앞 공백은 한 칸까지(할인은 공백 없음). 앞뒤 공백은 뗀 값에 쓴다.
 */
const STRICT_NUMBER = /^(-)?((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)( ?)([^\s0-9]*)$/;

/** 엄격한 숫자 읽기 결과 — 형식 오류 / 음수 / 값(단위 반영, '년' ×12)과 소수 자릿수 */
export type StrictNumber =
  { ok: false; reason: 'format' | 'negative' } | { ok: true; value: number; decimals: number };

/**
 * 사람 확인 숫자 값을 서버와 같은 규칙으로 읽는다(고쳐 쓰지 않는다 — 쉼표를 지워 '1,0'을 10으로 읽던 .13 동작 금지).
 */
export function parseStrictNumber(field: HumanCheckField, raw: string): StrictNumber {
  const m = STRICT_NUMBER.exec(raw.trim());
  if (!m) return { ok: false, reason: 'format' };
  const [, neg, num = '', sp, unit = ''] = m;
  const allowed = HUMAN_NUMBER_UNITS[field] ?? [];
  if ((unit && !allowed.includes(unit)) || (field === 'discount' && sp) || (sp && !unit)) {
    return { ok: false, reason: 'format' };
  }
  if (neg) return { ok: false, reason: 'negative' };
  const digits = num.replace(/,/g, '');
  return {
    ok: true,
    value: Number(digits) * (unit === '년' ? 12 : 1),
    decimals: digits.split('.')[1]?.length ?? 0,
  };
}

/**
 * 강등(FactDemotion.field)·주장 대상 필드 → 사람 확인 필드. 가격 강등은 점수·화면이 쓰는
 * `payment_terms.price_by_type`(D11-3)에 걸리고(출처 필드 경로 `price_by_type.<타입>.max_price_won` — 서버
 * `facts_view.logical_field`) 사람 확인은 `max_price_won` 으로 넣는다. 매핑 없으면 null.
 */
export function humanCheckFieldOf(field: string | null | undefined): HumanCheckField | null {
  if (!field) return null;
  // 계약 .13 F1: 타입별 할인 칸(`discount_by_type.<타입>`)·가격 범위 할인은 사람 확인 `discount`
  if (field === 'discount' || field.startsWith('discount_by_type')) return 'discount';
  const logical = field.startsWith('price_by_type.')
    ? field.slice(field.lastIndexOf('.') + 1)
    : field;
  if ((HUMAN_CHECK_FIELDS as readonly string[]).includes(logical)) {
    return logical as HumanCheckField;
  }
  if (field === 'price_by_type' || field === 'price_won' || field === 'max_price') {
    return 'max_price_won';
  }
  return null;
}
