/**
 * G0 '청약홈 조회 기간(고급)' 입력 규칙 — 계약 .15 F3(D20-1) `POST /regions` 선택 필드 `applyhome_query`.
 * 형식은 계약 `region.json` `ApplyhomeQuery.from_ym`·`to_ym` 패턴과 같다(서버가 같은 패턴으로 422). MSW 목도 이 규칙을 쓴다.
 * 비우면 키를 보내지 않는다 → 서버 기본 창(지난 24개월 + 향후 12개월, F4).
 */
import type { ApplyhomeQuery } from '@/api/types';

/** 계약 region.json ApplyhomeQuery.from_ym·to_ym pattern */
export const YM_PATTERN = /^[0-9]{4}-(0[1-9]|1[0-2])$/;

export type WindowField = 'from_ym' | 'to_ym';

export interface WindowCheck {
  /** 형식이 틀린 칸 */
  invalid: WindowField[];
  /** 두 칸이 모두 맞는데 시작월 > 끝월 */
  reversed: boolean;
  /** 보낼 값 — 입력한 칸만. 둘 다 비면 null(키를 보내지 않음) */
  query: ApplyhomeQuery | null;
}

/** 입력 두 칸(앞뒤 공백 무시) → 형식 검사 + 보낼 applyhome_query */
export function checkWindow(fromYm: string, toYm: string): WindowCheck {
  const from = fromYm.trim();
  const to = toYm.trim();
  const invalid: WindowField[] = [];
  if (from && !YM_PATTERN.test(from)) invalid.push('from_ym');
  if (to && !YM_PATTERN.test(to)) invalid.push('to_ym');
  const reversed = invalid.length === 0 && from !== '' && to !== '' && from > to;
  const query: ApplyhomeQuery = {};
  if (from) query.from_ym = from;
  if (to) query.to_ym = to;
  return { invalid, reversed, query: from || to ? query : null };
}

/** 서버 422 field_errors 중 applyhome_query 칸 오류(목·서버 같은 loc: ['body','applyhome_query',<키>]) */
export function isApplyhomeQueryLoc(loc: readonly (string | number)[]): boolean {
  return loc.includes('applyhome_query');
}
