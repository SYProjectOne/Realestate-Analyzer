import type { Fact } from '@/api/types';
import {
  formatArea,
  formatCount,
  formatDate,
  formatDday,
  formatEok,
  formatFactValue,
  formatHalfYear,
  formatNumber,
  formatPercent,
  formatProb,
  formatRank,
  formatRatio,
  formatScore,
  formatWon,
} from './format';

describe('formatWon (억·만)', () => {
  it.each([
    [749_000_000, '7억 4,900만원'],
    [1_500_000_000, '15억원'],
    [35_000_000, '3,500만원'],
    [5_000, '5,000원'],
    [0, '0원'],
    [-120_000_000, '-1억 2,000만원'],
    [749_512_345, '7억 4,951만원'],
    [12_345_678_900, '123억 4,568만원'],
  ])('%d → %s', (won, expected) => {
    expect(formatWon(won)).toBe(expected);
  });

  it('유한수가 아니면 확인 불가', () => {
    expect(formatWon(Number.NaN)).toBe('확인 불가');
  });
});

describe('formatEok (차트 축)', () => {
  it('억 단위 소수', () => {
    expect(formatEok(749_000_000)).toBe('7.49억');
    expect(formatEok(1_500_000_000, 1)).toBe('15.0억');
  });
});

describe('퍼센트·확률·면적·점수', () => {
  it('formatPercent: 이미 % 값', () => {
    expect(formatPercent(12.345)).toBe('12.3%');
    expect(formatPercent(5, 0)).toBe('5%');
  });
  it('formatProb: 0~1 → %', () => {
    expect(formatProb(0.48)).toBe('48%');
    expect(formatProb(0.485, 1)).toBe('48.5%');
  });
  it('formatArea: ㎡ 소수 2자리', () => {
    expect(formatArea(84.97)).toBe('84.97㎡');
    expect(formatArea(59)).toBe('59.00㎡');
  });
  it('formatScore: 소수 2자리', () => {
    expect(formatScore(7.256)).toBe('7.26');
  });
  it('formatNumber·formatCount·formatRank·formatRatio', () => {
    expect(formatNumber(1234567)).toBe('1,234,567');
    expect(formatCount(1234)).toBe('1,234');
    expect(formatCount(1234, 'households')).toBe('1,234세대');
    expect(formatRank(1)).toBe('1위');
    expect(formatRatio(12.34)).toBe('12.3:1');
  });
});

describe('날짜 D±', () => {
  it('기준일 대비 D-n / D+n / D-day', () => {
    expect(formatDday('2026-10-11', '2026-10-08')).toBe('D-3');
    expect(formatDday('2026-10-05', '2026-10-08')).toBe('D+3');
    expect(formatDday('2026-10-08', '2026-10-08')).toBe('D-day');
  });
  it('formatDate는 기준일이 있으면 D±를 붙인다', () => {
    expect(formatDate('2026-10-11', '2026-10-08')).toBe('2026-10-11 (D-3)');
    expect(formatDate('2026-10-11')).toBe('2026-10-11');
  });
  it('일시 문자열도 날짜 부분만 쓴다', () => {
    expect(formatDate('2026-10-11T06:10:00+09:00', '2026-10-08')).toBe('2026-10-11 (D-3)');
  });
  it('formatHalfYear: 연도 반기', () => {
    expect(formatHalfYear('2028-03')).toBe('2028년 상반기');
    expect(formatHalfYear('2028-07')).toBe('2028년 하반기');
  });
});

describe('formatFactValue', () => {
  const fact = (v: number | string | null): Fact => ({ v, label: '추정', prov: 'fp_1', checked_at: '2026-10-08' });

  it('단위별로 디스패치한다', () => {
    expect(formatFactValue(fact(749_000_000), 'won')).toBe('7억 4,900만원');
    expect(formatFactValue(fact(0.48), 'prob')).toBe('48%');
    expect(formatFactValue(fact(84.97), 'm2')).toBe('84.97㎡');
    expect(formatFactValue(fact('2026-10-11'), 'date', { asof: '2026-10-08' })).toBe('2026-10-11 (D-3)');
    expect(formatFactValue(fact('원문 그대로'), 'text')).toBe('원문 그대로');
  });

  it('v가 null이면 null (호출 측이 "확인 불가(사유)")', () => {
    expect(formatFactValue(fact(null), 'won')).toBeNull();
  });

  it('숫자 단위인데 v가 숫자 문자열이면 숫자로 해석한다', () => {
    expect(formatFactValue(fact('35000000'), 'won')).toBe('3,500만원');
  });
});
