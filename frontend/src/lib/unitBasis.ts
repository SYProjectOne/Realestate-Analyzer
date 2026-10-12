/**
 * 계약 .16 F6(D21-1): 공고문 금액 표를 '(단위: 천원)'·'만원' 표에서 읽어 원으로 환산한 가격 출처 행은 발췌 끝에
 * `\n[단위 근거] <표 머리 줄>` 한 줄이 붙는다(백엔드 `normalize/notice_parser._unit_kw`). 화면은 그 줄을 발췌 본문과 나눠
 * '단위 근거'로 따로 보이고, 원문 하이라이트는 본문(금액 행)으로 찾는다. 표식 문자열은 계약 데이터 모양이라 여기 둔다
 * (화면 문구 아님 — 화면 문구는 ko.json `provenance.unitBasis`).
 */
const UNIT_BASIS_MARK = '[단위 근거] ';

export interface UnitBasisParts {
  /** 발췌 본문(단위 근거 줄을 뗀 것). 발췌가 없으면 null */
  body: string | null;
  /** 단위 근거 줄의 표 머리(표식 뒤). 없으면 null */
  unitBasis: string | null;
}

export function splitUnitBasis(excerpt: string | null | undefined): UnitBasisParts {
  if (excerpt === null || excerpt === undefined) return { body: null, unitBasis: null };
  const at = excerpt.lastIndexOf(`\n${UNIT_BASIS_MARK}`);
  if (at < 0) return { body: excerpt, unitBasis: null };
  const unitBasis = excerpt.slice(at + 1 + UNIT_BASIS_MARK.length).trim();
  return { body: excerpt.slice(0, at), unitBasis: unitBasis || null };
}
