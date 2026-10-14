/**
 * R8-JITTER: G2 가상 스크롤 범위 히스테리시스(nextHeldRange) — 실측 → 범위 → 열 너비 → 실측 되먹임이 고정점에 닿는다.
 * 실제 떨림 재현·회귀는 e2e/pages/jitter.spec.ts(실 브라우저). 여기서는 규칙만 본다.
 */
import { describe, expect, it } from 'vitest';
import { nextHeldRange, RANGE_HOLD, type HeldRange } from './ComplexTable';

const r = (startIndex: number, endIndex: number, count = 101, overscan = 2) => ({
  startIndex,
  endIndex,
  overscan,
  count,
});
const span = (h: HeldRange) => [h.start, h.end];

describe('nextHeldRange (R8-JITTER)', () => {
  it('처음에는 기본 범위(창 ± overscan, 0..count-1 로 자름)', () => {
    expect(span(nextHeldRange(null, r(0, 9)))).toEqual([0, 11]);
    expect(span(nextHeldRange(null, r(95, 100)))).toEqual([93, 100]);
  });

  it('맨 위 행이 그대로면 실측으로 줄어든 끝을 붙잡는다 — 12행 ↔ 13행 진동이 13행에서 멈춘다', () => {
    let held = nextHeldRange(null, r(0, 10)); // 0..12 (13행)
    const seen = new Set<string>();
    // 진동하던 입력: 창 끝이 10 ↔ 9 를 오간다
    for (let i = 0; i < 10; i += 1) {
      held = nextHeldRange(held, r(0, i % 2 === 0 ? 9 : 10));
      seen.add(span(held).join('-'));
    }
    expect([...seen]).toEqual(['0-12']);
  });

  it('붙잡는 폭은 앞뒤 RANGE_HOLD 행까지', () => {
    const wide = nextHeldRange(null, r(20, 30)); // 18..32
    const shrunk = nextHeldRange(wide, r(20, 24)); // 기본 18..26
    expect(span(shrunk)).toEqual([18, 26 + RANGE_HOLD]);
  });

  it('넓어지는 건 바로 따른다', () => {
    const held = nextHeldRange(null, r(0, 9));
    expect(span(nextHeldRange(held, r(0, 12)))).toEqual([0, 14]);
  });

  it('맨 위 행이 바뀌면(사용자 스크롤) 붙잡은 범위를 버린다 — 스크롤 중 그리는 행 수 그대로', () => {
    const held = nextHeldRange(null, r(20, 30)); // 18..32
    expect(span(nextHeldRange(held, r(22, 28)))).toEqual([20, 30]);
  });

  it('끝(마지막 행이 창 안)에서는 맨 위 행이 바뀌어도(anchorTo end 보정) 붙잡는다', () => {
    const held = nextHeldRange(null, r(93, 100)); // 91..100
    const next = nextHeldRange(held, r(94, 100)); // 기본 92..100
    expect(span(next)).toEqual([91, 100]);
    expect(span(nextHeldRange(next, r(93, 100)))).toEqual([91, 100]);
  });

  it('행 수가 바뀌면(이어 받기·필터) 기본 범위부터', () => {
    const held = nextHeldRange(null, r(0, 12, 100));
    expect(span(nextHeldRange(held, r(0, 9, 101)))).toEqual([0, 11]);
  });

  it('빈 목록은 빈 범위', () => {
    const empty = nextHeldRange(null, r(0, 0, 0));
    expect(empty.end).toBeLessThan(empty.start);
  });
});
