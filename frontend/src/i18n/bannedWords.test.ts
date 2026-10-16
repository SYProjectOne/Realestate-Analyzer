/**
 * R11(D30, R11_PLAN 완료 기준 3): ko.json 값에 평가·권유·과장 금지어가 없다.
 * 금지어: 추천·유리·불리·좋음·나쁨·싸다·비싸다·저렴·알짜·기회·사세요·넣으세요·당첨 가능·확실·보장.
 * 허용(부정형·인용 이름만): "보장 아님"(부정형 고지), "불확실"(판정기 verdict 분류 이름 `chart.C01.verdict.uncertain` —
 * '확실하다'는 주장이 아니라 판정기가 낸 등급 이름을 그대로 보이는 것). 그 밖의 예외는 두지 않는다
 * (예전 검사기 `@/test/forbidden` 이 허용하던 '보장이 아닙니다'·'보장도 아닙니다'도 여기서는 금지).
 */
import ko from './ko.json';

export const BANNED = [
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

/** 허용 표현 — 지운 뒤 금지어를 찾는다 */
export const BANNED_EXCEPT = ['보장 아님', '불확실'] as const;

export function bannedIn(text: string): string[] {
  let rest = text;
  for (const ok of BANNED_EXCEPT) rest = rest.split(ok).join('');
  return BANNED.filter((w) => rest.includes(w));
}

function leaves(node: unknown, path: string[] = []): [string, string][] {
  if (typeof node === 'string') return [[path.join('.'), node]];
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
      leaves(v, [...path, k]),
    );
  }
  return [];
}

describe('R11 금지어(ko.json 값 전체)', () => {
  it('ko.json 어떤 값에도 금지어가 없다(허용: "보장 아님"·판정기 등급 "불확실")', () => {
    const hits = leaves(ko)
      .map(([key, text]) => ({ key, words: bannedIn(text) }))
      .filter((x) => x.words.length > 0);
    expect(hits).toEqual([]);
  });

  it('검사기는 금지어를 잡고, 허용 표현만 통과시킨다', () => {
    expect(bannedIn('지금이 기회예요')).toEqual(['기회']);
    expect(bannedIn('추천 단지')).toEqual(['추천']);
    expect(bannedIn('분양가가 저렴해요')).toEqual(['저렴']);
    expect(bannedIn('당첨 가능 단지')).toEqual(['당첨 가능']);
    expect(bannedIn('확실히 올라요')).toEqual(['확실']);
    expect(bannedIn('보장도 아니에요')).toEqual(['보장']);
    expect(bannedIn('보장이 아닙니다')).toEqual(['보장']);
    expect(bannedIn('당첨 확률이 아닙니다 · 보장 아님')).toEqual([]);
    expect(bannedIn('불확실')).toEqual([]);
  });

  it('금지어 목록은 R11 지시서 15개 그대로', () => {
    expect(BANNED).toHaveLength(15);
    expect(new Set(BANNED).size).toBe(15);
  });
});
