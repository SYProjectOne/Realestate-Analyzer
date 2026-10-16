import { chartRegistry } from './registry';

const IDS = ['C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09', 'C10'] as const;

describe('차트 C01~C10 buildOption', () => {
  it('레지스트리에 10개가 순서대로 있다', () => {
    expect(chartRegistry.map((c) => c.id)).toEqual(IDS);
  });

  it.each(IDS)('%s: 빈 데이터에서 throw 없이 option 객체를 돌려준다', (id) => {
    const entry = chartRegistry.find((c) => c.id === id);
    expect(entry).toBeDefined();
    const option = entry!.buildOption(entry!.empty);
    expect(option).toBeTypeOf('object');
    expect(option).not.toBeNull();
    // ECharts option은 직렬화 가능해야 한다(보고서 HTML 인라인, 스냅샷 테스트)
    expect(() => JSON.stringify(option)).not.toThrow();
  });

  it.each(IDS)('%s: 빈 데이터의 빈 상태 사유가 있다', (id) => {
    const entry = chartRegistry.find((c) => c.id === id)!;
    expect(entry.emptyReason(entry.empty)).toEqual(expect.any(String));
  });

  it.each(IDS)('%s: toTable(빈 데이터)은 열 정의를 가진 표를 돌려준다', (id) => {
    const entry = chartRegistry.find((c) => c.id === id)!;
    const table = entry.toTable(entry.empty);
    expect(table.columns.length).toBeGreaterThan(0);
    expect(table.rows).toEqual([]);
  });
});

describe('R11 범례(차트 위 HTML)', () => {
  it.each(IDS)('%s: 빈 데이터면 범례 항목이 없다(빈 상태 문구만)', (id) => {
    const entry = chartRegistry.find((c) => c.id === id)!;
    expect(entry.legendItems(entry.empty)).toEqual([]);
  });

  it.each(IDS)('%s: ECharts 범례는 그리지 않는다(show:false — 범례는 차트 위 HTML)', (id) => {
    const entry = chartRegistry.find((c) => c.id === id)!;
    const legend = (entry.buildOption(entry.empty) as { legend?: { show?: boolean } }).legend;
    expect(legend?.show ?? false).toBe(false);
  });
});
