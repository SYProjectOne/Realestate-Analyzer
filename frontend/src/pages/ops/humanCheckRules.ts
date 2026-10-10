/**
 * 사람 확인 값 규칙(계약 2026-10-09.8 HumanCheckField · 서버 `app/api/demotion.py` parse_human_value 와 같은 범위).
 * 서버는 같은 검사로 422 를 낸다 — 화면은 POST 전에 같은 규칙으로 막는다(절삭·반올림 없음, 3차 리뷰 minor 11).
 */
import { HUMAN_CHECK_FIELDS, type HumanCheckField } from '@/api/types';
import type { MetaFormat } from '@/lib/meta';

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

/** 사실 필드 값 형·범위(서버 허용 범위). 접수 상태·기타는 규칙 없음(길이만) */
export const HUMAN_CHECK_RULES: Partial<Record<HumanCheckField, HumanCheckRule>> = {
  /** 원 단위 정수, 1,000만 ~ 1,000억 */
  max_price_won: { kind: 'int', min: 10_000_000, max: 100_000_000_000, unit: 'won' },
  /** YYYY-MM, 2000-01 ~ 2100-12 */
  move_in_ym: { kind: 'ym', min: 2000, max: 2100 },
  resale_months: { kind: 'int', min: 0, max: 240 },
  residency_months: { kind: 'int', min: 0, max: 240 },
  /** 0 ~ 100, 소수 둘째 자리까지 */
  down_payment_pct: { kind: 'number', min: 0, max: 100, decimals: 2 },
};

/**
 * 강등(FactDemotion.field)·주장 대상 필드 → 사람 확인 필드. 가격 강등은 점수·화면이 쓰는
 * `payment_terms.price_by_type`(D11-3)에 걸리고(출처 필드 경로 `price_by_type.<타입>.max_price_won` — 서버
 * `facts_view.logical_field`) 사람 확인은 `max_price_won` 으로 넣는다. 매핑 없으면 null.
 */
export function humanCheckFieldOf(field: string | null | undefined): HumanCheckField | null {
  if (!field) return null;
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
