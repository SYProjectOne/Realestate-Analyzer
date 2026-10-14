/** R9-UI 문구 금지어 검사(30-proposal §1) — 테스트 전용 */
/** 30-proposal §1 문구 금지어 */
export const FORBIDDEN = [
  '추천',
  '유리',
  '불리',
  '좋음',
  '나쁨',
  '싸다',
  '비싸다',
  '저렴',
  '알짜',
  '기회',
  '사세요',
  '넣으세요',
  '당첨 가능',
  '확실',
  '보장',
] as const;

/** 허용되는 부정형·판정기 표기 — 지운 뒤 금지어를 찾는다 */
const ALLOWED = ['보장 아님', '보장이 아닙니다', '보장도 아닙니다', '불확실'];

export function forbiddenIn(text: string): string[] {
  let rest = text;
  for (const ok of ALLOWED) rest = rest.split(ok).join('');
  return FORBIDDEN.filter((w) => rest.includes(w));
}
