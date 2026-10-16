// @vitest-environment node
/**
 * R5-FE2: 첫 화면 번들 규칙(scripts/lib/bundle-guards.ts) — 진입 청크의 정적 닫힘에 echarts·zrender·msw 가 없고 크기 예산 안.
 * 실제 빌드는 vite.config.ts 의 `entry-chunk-guard` 가 같은 함수로 검사해 어기면 `npm run build` 가 실패한다.
 */
import { describe, expect, it } from 'vitest';
import config from '../vite.config';
import {
  ENTRY_CLOSURE_BUDGET_KB,
  entryViolations,
  isLazyOnly,
  LAZY_ONLY_CHUNKS,
  staticClosure,
  type ChunkLike,
} from './lib/bundle-guards';

function chunk(
  fileName: string,
  opts: { name?: string; isEntry?: boolean; imports?: string[]; kb?: number } = {},
): ChunkLike {
  return {
    type: 'chunk',
    fileName,
    name: opts.name ?? fileName.replace(/-.*$/, ''),
    isEntry: opts.isEntry ?? false,
    imports: opts.imports ?? [],
    code: 'x'.repeat(Math.round((opts.kb ?? 1) * 1000)),
  };
}

describe('staticClosure', () => {
  it('정적 import 를 끝까지 따라가고 순환은 한 번만', () => {
    const chunks = [
      chunk('index-a.js', { isEntry: true, imports: ['vendor-b.js'] }),
      chunk('vendor-b.js', { imports: ['helper-c.js', 'index-a.js'] }),
      chunk('helper-c.js'),
      chunk('page-d.js', { imports: ['index-a.js'] }),
    ];
    expect(
      staticClosure(chunks, chunks[0] as ChunkLike)
        .map((c) => c.fileName)
        .sort(),
    ).toEqual(['helper-c.js', 'index-a.js', 'vendor-b.js']);
  });
});

describe('entryViolations', () => {
  it('지연 로드 전용 청크가 진입에서 정적으로 닿으면 위반(R5-FE2 이전 모양: 진입 → zrender·msw)', () => {
    const before = [
      chunk('index-Da.js', { isEntry: true, imports: ['zrender-Cg.js', 'msw-ck.js'], kb: 300 }),
      chunk('zrender-Cg.js', { name: 'zrender', kb: 196 }),
      chunk('msw-ck.js', { name: 'msw', kb: 1 }),
      chunk('echarts-Bp.js', { name: 'echarts', imports: ['zrender-Cg.js'], kb: 444 }),
    ];
    const problems = entryViolations(before);
    expect(problems).toHaveLength(2);
    expect(problems[0]).toContain('zrender-Cg.js');
    expect(problems[0]).toContain('msw-ck.js');
    expect(problems[1]).toContain('예산');
  });

  it('차트 엔진은 동적 청크에서만 닿으면 통과', () => {
    const after = [
      chunk('index-a.js', { isEntry: true, imports: ['vendor-v.js'], kb: 100 }),
      chunk('vendor-v.js', { name: 'vendor', kb: 250 }),
      chunk('EChartRuntime-r.js', { imports: ['echarts-e.js', 'vendor-v.js'] }),
      chunk('echarts-e.js', { name: 'echarts', imports: ['zrender-z.js', 'vendor-v.js'], kb: 444 }),
      chunk('zrender-z.js', { name: 'zrender', imports: ['vendor-v.js'], kb: 196 }),
    ];
    expect(entryViolations(after)).toEqual([]);
  });

  it('예산은 진입 정적 닫힘 합계', () => {
    const chunks = [
      chunk('index-a.js', { isEntry: true, imports: ['vendor-v.js'], kb: 200 }),
      chunk('vendor-v.js', { name: 'vendor', kb: 200 }),
    ];
    expect(entryViolations(chunks, 400)).toEqual([]);
    expect(entryViolations(chunks, 399)).toHaveLength(1);
  });

  it('R11-I18N: 문자열 이름공간 청크(ko-*)가 진입에서 정적으로 닿으면 위반, 동적이면 통과', () => {
    const bad = [
      chunk('index-a.js', { isEntry: true, imports: ['ko-page-G3-x.js'], kb: 100 }),
      chunk('ko-page-G3-x.js', { name: 'ko-page-G3', kb: 10 }),
    ];
    expect(entryViolations(bad)).toHaveLength(1);
    expect(entryViolations(bad)[0]).toContain('ko-page-G3-x.js');
    const ok = [
      chunk('index-a.js', { isEntry: true, kb: 100 }),
      chunk('index-p.js', { imports: ['ko-chart-y.js'] }),
      chunk('ko-chart-y.js', { name: 'ko-chart', kb: 10 }),
    ];
    expect(entryViolations(ok)).toEqual([]);
    expect(isLazyOnly('ko-glossary')).toBe(true);
    expect(isLazyOnly('index')).toBe(false);
  });

  it('지연 전용 = echarts·zrender·msw, 예산 450kB(R5-FE2 실측 401kB + 여유, 이전 651kB)', () => {
    expect([...LAZY_ONLY_CHUNKS].sort()).toEqual(['echarts', 'msw', 'zrender']);
    expect(ENTRY_CLOSURE_BUDGET_KB).toBe(450);
  });
});

describe('vite.config.ts', () => {
  it('빌드에 entry-chunk-guard 를 건다', () => {
    const resolved = config({ mode: 'production', command: 'build' });
    const names = (resolved.plugins ?? [])
      .flat()
      .map((p) => (p && typeof p === 'object' && 'name' in p ? p.name : null));
    expect(names).toContain('entry-chunk-guard');
    expect(names).toContain('max-chunk-guard');
    expect(names).toContain('ko-split');
  });

  it('R11-I18N: ko 가상 모듈 — 이름공간은 ko-* 청크, core 는 vendor 로 끌려가지 않는다', () => {
    const resolved = config({ mode: 'production', command: 'build' });
    const output = resolved.build?.rollupOptions?.output;
    const manual = (Array.isArray(output) ? output[0] : output)?.manualChunks;
    expect(typeof manual).toBe('function');
    const fn = manual as (id: string) => string | undefined;
    expect(fn('\0virtual:ko/ns/page/G3')).toBe('ko-page-G3');
    expect(fn('\0virtual:ko/ns/chart')).toBe('ko-chart');
    expect(fn('\0virtual:ko/core')).toBeUndefined();
    expect(fn('\0vite/preload-helper.js')).toBe('vendor');
  });
});
