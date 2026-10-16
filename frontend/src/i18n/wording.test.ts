/**
 * R9-UI 문구(30-proposal §1·§13 PR 2, D28-1): 새 문구는 판단·권유를 만들지 않는다.
 *  - 금지어(평가·권유·과장)가 ko.json 어디에도 없다. "보장 아님"(부정형 고지)·"불확실"(판정기 verdict)은 허용.
 *  - +10% 값은 "상승 가능성"으로 부르고 "당첨 확률이 아님"을 함께 둔다(오해 방지, 00-baseline Q6).
 */
import ko from './ko.json';
import { t } from './index';
import { forbiddenIn } from '@/test/forbidden';

function leaves(node: unknown, path: string[] = []): [string, string][] {
  if (typeof node === 'string') return [[path.join('.'), node]];
  if (node && typeof node === 'object') {
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
      leaves(v, [...path, k]),
    );
  }
  return [];
}

describe('R9-UI 문구 금지어', () => {
  it('ko.json 모든 문구에 평가·권유·과장 금지어가 없다', () => {
    const hits = leaves(ko)
      .map(([key, text]) => ({ key, words: forbiddenIn(text) }))
      .filter((x) => x.words.length > 0);
    expect(hits).toEqual([]);
  });

  it('금지어 검사기는 실제로 잡는다(부정형은 통과)', () => {
    expect(forbiddenIn('지금이 기회입니다')).toEqual(['기회']);
    expect(forbiddenIn('추천 단지')).toEqual(['추천']);
    expect(forbiddenIn('당첨 확률이 아닙니다 · 보장 아님')).toEqual([]);
    expect(forbiddenIn('불확실')).toEqual([]);
  });
});

describe('R9-UI 문구 일괄(P2·P8·P10 문구 부분)', () => {
  it('+10% 값 이름은 "상승 가능성" — "확률" 단독 이름을 쓰지 않는다', () => {
    for (const text of [
      t('page.G1.p10'),
      t('page.G2.col.p10'),
      // G4 은 R11 목업 이름 '10% 넘게 오를 가능성'(+ 목표 시점·당첨 확률 아님) — pages/compare/compare.test 가 지킨다
      t('chart.C06.component.p10'),
    ]) {
      expect(text).toContain('상승 가능성');
      expect(text).not.toMatch(/\+10% 확률/);
    }
    expect(t('page.G1.p10Note')).toContain('당첨 확률이 아닙니다');
    expect(t('page.G3.ladder.note')).toContain('당첨 확률이 아닙니다');
  });

  it('사다리 기준선은 영어(likely/unlikely)가 아니다', () => {
    expect(t('chart.C01.threshold.likely')).toBe('가능성 높음 기준 0.85');
    expect(t('chart.C01.threshold.unlikely')).toBe('가능성 낮음 기준 0.15');
    expect(t('page.G3.ladder.proposition')).toBe('판정기에 물은 문장');
  });

  it('G3 탭 이름(7개 + 판정 기록 구획)', () => {
    expect(
      (['price', 'payment', 'events', 'gap', 'ladder', 'catalysts', 'provenance'] as const).map(
        (k) => t(`page.G3.tab.${k}`),
      ),
    ).toEqual([
      '타입별 가격',
      '내야 할 돈·일정',
      '경쟁률·추가 모집',
      '주변 시세 비교',
      '가격 전망(판정기)',
      '개발 소식(호재)',
      '근거 원문',
    ]);
    expect(t('page.G3.tab.judgments')).toBe('판정 기록(운영자용)');
  });

  it('홈·TOP·G2 필터·열 이름', () => {
    expect(t('page.G1.title')).toBe('홈');
    expect(t('page.G1.top5')).toBe('종합 점수 상위 단지');
    expect(t('page.G1.top5Note')).toBe('상대 비교 · 투자 권유 아님');
    expect(t('page.G2.filter.land_type')).toBe('택지 종류(공공·민간)');
    expect(t('page.G2.filter.resale_end_before')).toBe('이 날짜 전에 전매 종료');
    expect(t('page.G2.filter.inclusion_class')).toBe('단지 분류');
    expect(t('page.G2.filter.judge_scope')).toBe('점수 계산 범위');
    expect(t('page.G2.col.gap')).toBe('가격 갭(주변 대비)');
    expect(t('page.G2.col.total')).toBe('종합 점수(상대 비교)');
    expect(t('page.G3.header.inclusion')).toBe('단지 분류');
    expect(t('page.G3.header.scopeReason')).toBe('점수 계산 범위 사유');
  });

  it('하단 고정 문구는 그대로', () => {
    expect(t('app.disclaimer')).toBe('투자 권유 아님 · 상대 비교');
  });
});
