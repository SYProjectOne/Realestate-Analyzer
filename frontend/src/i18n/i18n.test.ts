import { t, tDynamic } from './index';

describe('t()', () => {
  it('ko.json 값을 돌려준다', () => {
    expect(t('app.disclaimer')).toBe('투자 권유 아님 · 상대 비교');
  });

  it('{param}을 치환한다', () => {
    expect(t('empty.unknownWithReason', { reason: '스캔' })).toBe('확인 불가(스캔)');
    expect(t('unit.dminus', { n: 3 })).toBe('D-3');
  });

  it('tDynamic은 없는 키에 fallback을 돌려준다', () => {
    expect(tDynamic('intake.status.가능', 'x')).toBe('접수 가능');
    expect(tDynamic('intake.status.없는값', '없는값')).toBe('없는값');
  });
});
