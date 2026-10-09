import { REGISTERED_SERIES } from './EChartRuntime';

/**
 * 트리 셰이킹한 ECharts 런타임(EChartRuntime.tsx)에 등록하지 않은 계열을 buildOption 이 쓰면
 * 화면에서 조용히 빈 차트가 된다. buildOption 소스의 `type: '…'` 리터럴을 모아 대조한다.
 */
const NON_SERIES_TYPES = new Set([
  // 축
  'category',
  'value',
  'time',
  'log',
  // 선 모양·graphic 요소·custom renderItem 도형
  'solid',
  'dashed',
  'dotted',
  'circle',
  'rect',
  'text',
  'group',
  'polyline',
  // tooltip axisPointer
  'shadow',
  'cross',
]);

describe('EChartRuntime 등록 목록', () => {
  it('buildOption 이 쓰는 series.type 은 전부 등록되어 있다', () => {
    const sources = import.meta.glob<string>('./C*/buildOption.ts', {
      query: '?raw',
      import: 'default',
      eager: true,
    });
    expect(Object.keys(sources)).toHaveLength(10);
    const used = new Set<string>();
    for (const src of Object.values(sources)) {
      for (const m of src.matchAll(/\btype:\s*'([a-zA-Z]+)'/g)) used.add(m[1]!);
    }
    const unknown = [...used].filter(
      (type) =>
        !NON_SERIES_TYPES.has(type) && !(REGISTERED_SERIES as readonly string[]).includes(type),
    );
    expect(unknown).toEqual([]);
    expect(used.has('bar')).toBe(true);
  });
});
