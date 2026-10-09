/* eslint-disable @typescript-eslint/no-explicit-any -- ECharts option 유니온을 테스트에서 느슨하게 읽는다 */
/**
 * C1~C10 option 빌더 완성 테스트 — 입력은 계약 예시(contracts/examples) 그대로.
 * RA §7-2 표의 "option 핵심"·"빈·특수 상태"가 차트마다 1개 이상 고정된다.
 */
import * as C01 from './C01/buildOption';
import * as C02 from './C02/buildOption';
import * as C03 from './C03/buildOption';
import * as C04 from './C04/buildOption';
import * as C05 from './C05/buildOption';
import * as C06 from './C06/buildOption';
import * as C07 from './C07/buildOption';
import * as C08 from './C08/buildOption';
import * as C09 from './C09/buildOption';
import * as C10 from './C10/buildOption';
import {
  compare,
  complexNames,
  dashboard,
  elif,
  escapedDecision,
  kaive,
  market,
  rowsWithUnjudged,
  sensitivity,
  stableSensitivity,
} from './gallery/fixtures';
import { DEFAULT_PALETTE } from './palette';

const opt = (o: unknown) => o as Record<string, any>;
const series = (o: unknown): any[] => {
  const s = opt(o).series;
  return Array.isArray(s) ? s : [s];
};
const seriesById = (o: unknown, id: string) => series(o).find((s) => s.id === id);

describe('C01 상승 확률 사다리', () => {
  const ladder = elif().ladder;

  it('markLine 0.15 / 0.85, xAxis 0~1', () => {
    const o = C01.buildOption({ ladder, horizon: 'move_in_plus_1y' });
    const bar = series(o)[0];
    expect(bar.type).toBe('bar');
    expect(bar.markLine.data.map((d: any) => d.xAxis)).toEqual([0.15, 0.85]);
    expect(opt(o).xAxis).toMatchObject({ min: 0, max: 1 });
    // 막대 4개 = +5/+10/+20/보합·하락
    expect(bar.data).toHaveLength(4);
  });

  it('막대 라벨 = 확률 + verdict 텍스트, 부제 = 목표 시점(연도 반기)', () => {
    const data = { ladder, horizon: 'move_in_plus_1y' as const };
    const bar = series(C01.buildOption(data))[0];
    const text = bar.label.formatter({ dataIndex: 1, value: 0.45 });
    expect(text).toContain('45%');
    expect(text).toContain('불확실');
    expect(C01.subtitle(data)).toBe('목표 시점 2029 상반기');
  });

  it('review 봉투 → 회색 막대 + "미해결"', () => {
    const data = { ladder, horizon: 'asof_plus_3y' as const };
    expect(C01.emptyReason(data)).toBeNull();
    expect(C01.unresolvedBadge(data)).toBe('미해결');
    const bar = series(C01.buildOption(data))[0];
    for (const d of bar.data) expect(d.itemStyle.color).toBe(DEFAULT_PALETTE.grayed);
    expect(bar.label.formatter({ dataIndex: 0, value: 0 })).toBe('미해결');
  });

  it('horizon 행 없음 → "사다리 판정 없음"', () => {
    expect(C01.emptyReason({ ladder: kaive().ladder, horizon: 'move_in_plus_1y' })).toBe(
      '사다리 판정 없음',
    );
  });

  it('G4 overlay = 단지별 scatter(모양도 다름)', () => {
    const c = compare();
    const overlay = c.rows.map((row) => ({
      complex_id: row.complex_id,
      name: row.name,
      ladder: c.ladders[String(row.complex_id)] ?? [],
    }));
    const o = C01.buildOption({ ladder: [], horizon: 'move_in_plus_1y', overlay });
    const s = series(o);
    expect(s).toHaveLength(3);
    expect(s.every((x) => x.type === 'scatter')).toBe(true);
    expect(new Set(s.map((x) => x.symbol)).size).toBe(3);
  });
});

describe('C02 가격 갭', () => {
  it('점+위스커(custom) + y축 억 단위', () => {
    const o = C02.buildOption({ gap: elif().gap });
    expect(seriesById(o, 'range').type).toBe('custom');
    expect(opt(o).yAxis.axisLabel.formatter(593_000_000)).toBe('5.9억');
  });

  it('T11 대체·보정: 보정 중앙값 = 점선 테두리 점, 배지 "대체(준공년)"', () => {
    const gap = compare().gaps['4']!;
    const o = C02.buildOption({ gap });
    const adjusted = seriesById(o, 'adjusted');
    expect(adjusted.type).toBe('scatter');
    expect(adjusted.itemStyle.borderType).toBe('dashed');
    expect(adjusted.data).toHaveLength(3);
    expect(C02.compBadge(true, 2020)).toBe('대체(2020)');
    expect(C02.compBadge(false, 2025)).toBe('신축(2025)');
    // 미보정 중앙값도 함께(표)
    const table = C02.toTable({ gap });
    expect(table.columns.map((c) => c.key)).toEqual(expect.arrayContaining(['median', 'adjusted']));
  });

  it('비교군 0 → "비교군 없음(사유)" — 사유를 두 번 감싸지 않는다', () => {
    expect(C02.emptyReason({ gap: kaive().gap })).toBe(
      '비교군 없음(분양가 미공개 — 공고 후 재판정)',
    );
    expect(C02.emptyReason({ gap: null })).toBe('비교군 없음(확인 불가)');
  });
});

describe('C03 벤치마크', () => {
  const m = market();
  const data = {
    benchmarks: m.benchmarks,
    asofYear: 2026,
    flags: m.benchmark_flags,
    livingAreas: m.living_areas,
  };

  it('dumbbell(custom) + 고점 triangle + 분양권 diamond', () => {
    const o = C03.buildOption(data);
    expect(seriesById(o, 'dumbbell').type).toBe('custom');
    expect(seriesById(o, 'peak').symbol).toBe('triangle');
    const sale = seriesById(o, 'sale');
    const presaleIndex = m.benchmarks.findIndex((b) => b.is_presale);
    expect(sale.data[presaleIndex].symbol).toBe('diamond');
    expect(sale.data[0].symbol).toBe('circle');
  });

  it('행 라벨에 분양 연도, 툴팁에 연율', () => {
    const o = C03.buildOption(data);
    expect(opt(o).yAxis.data[0]).toContain('2020');
    const tip = seriesById(o, 'sale').tooltip.formatter({ dataIndex: 0 });
    expect(tip).toContain('연율 8.8%');
  });

  it('표본 < 3 → "표본 n, 추정" 배지(생활권별)', () => {
    expect(C03.sampleBadges(data)).toEqual(['계양구 표본 0, 추정']);
    const two = {
      benchmarks: m.benchmarks.filter((b) => b.living_area === 'la_2').slice(0, 2),
      asofYear: 2026,
    };
    expect(C03.sampleBadges(two)).toEqual(['표본 2, 추정']);
  });

  it('0개 → "벤치마크 없음"', () => {
    expect(C03.emptyReason({ benchmarks: [], asofYear: null })).toBe('벤치마크 없음');
  });
});

describe('C04 입주 물량', () => {
  const m = market();
  const data = { supply: m.supply, markers: m.move_in_markers, livingAreas: m.living_areas };

  it('연도 x, 생활권 stack(이름), 판정 단지 입주 markPoint', () => {
    const o = C04.buildOption(data);
    const s = series(o);
    expect(s.every((x) => x.type === 'bar' && x.stack === 'supply')).toBe(true);
    expect(s.map((x) => x.name)).toContain('김포시');
    const points = s.flatMap((x) => x.markPoint?.data ?? []);
    expect(points.length).toBeGreaterThan(0);
    // 같은 연도 단지는 핀 하나로 묶인다(이름은 쉼표로)
    expect(points.some((p: any) => String(p.name).includes('엘리프 검단 포레듀'))).toBe(true);
    const pinYears = points.map((p: any) => p.coord[0]);
    expect(new Set(pinYears).size).toBe(pinYears.length);
    // 연도는 끊김 없이
    const years = opt(o).xAxis.data as string[];
    expect(Number(years[years.length - 1]) - Number(years[0]) + 1).toBe(years.length);
  });

  it('라벨 "추정 집계", 0개 → "입주 물량 없음"', () => {
    expect(opt(C04.buildOption(data)).yAxis.name).toBe('추정 집계');
    expect(C04.emptyReason({ supply: [], markers: [] })).toBe('입주 물량 없음');
  });
});

describe('C05 미분양 추이', () => {
  const unsold = market().unsold;

  it('line 2개(합계·준공 후), connectNulls=false', () => {
    const o = C05.buildOption({ unsold });
    expect(seriesById(o, 'total').connectNulls).toBe(false);
    expect(seriesById(o, 'post').connectNulls).toBe(false);
    expect(series(o).every((s) => s.type === 'line')).toBe(true);
  });

  it('결측 월은 null로 남긴다(월 축은 끊김 없음), 최근 24개월', () => {
    const sparse = unsold.filter((u) => u.ym !== '2026-04' && u.ym !== '2026-05');
    const o = C05.buildOption({ unsold: sparse });
    const months = opt(o).xAxis.data as string[];
    expect(months).toContain('2026-04');
    expect(months.length).toBeLessThanOrEqual(24);
    const i = months.indexOf('2026-04');
    expect(seriesById(o, 'total').data[i]).toBeNull();
  });

  it('범위(scope)가 여럿이면 자료가 가장 많은 범위 하나, 부제에 범위명', () => {
    expect(C05.selectScope(unsold)).toBe('41570');
    expect(C05.subtitle({ unsold })).toContain('김포시');
    expect(C05.subtitle({ unsold })).toContain('월말 기준');
  });
});

describe('C06 종합 점수 분해', () => {
  const d = dashboard();

  it('기여 합 = 종합 점수 ±0.01 (모든 TOP 5 행)', () => {
    for (const row of d.top5) {
      const sum = Object.values(C06.contributions(row)).reduce<number>(
        (acc, v) => acc + (v ?? 0),
        0,
      );
      expect(Math.abs(sum - Number(row.total.v))).toBeLessThanOrEqual(0.01);
    }
  });

  it('stacked 6 시리즈, 정렬 = 종합 내림차순, 툴팁 = formula_text + 원값', () => {
    const o = C06.buildOption({ rows: [...d.top5].reverse(), weights: d.weights });
    const s = series(o);
    expect(s).toHaveLength(6);
    expect(s.every((x) => x.stack === 'score')).toBe(true);
    const names = opt(o).xAxis.data as string[];
    expect(names[0]).toContain('더샵 송도그란테르');
    const tip = opt(o).tooltip.formatter({ dataIndex: 1, seriesIndex: 0 });
    expect(tip).toContain('10 × 0.45 = 4.5');
    expect(tip).toContain('45%');
  });

  it('제목 부제 = 가중치', () => {
    expect(C06.weightsSubtitle(d.weights)).toContain('+10% 확률 0.35');
  });

  it('null component → 빗금(decal) + "미판정"', () => {
    const o = C06.buildOption({ rows: rowsWithUnjudged(), weights: d.weights });
    const liquidity = series(o)[5];
    const hatched = liquidity.data.find((x: any) => typeof x === 'object' && x?.itemStyle?.decal);
    expect(hatched).toBeDefined();
    expect(hatched.label.formatter).toBe('미판정');
  });

  it('minor 26: 미판정 막대는 스택 길이 0 — w×10 으로 부풀리지 않는다(빗금·라벨로만 표시)', () => {
    const rows = rowsWithUnjudged();
    const o = C06.buildOption({ rows, weights: d.weights });
    const s = series(o);
    const valueOf = (x: any) => (typeof x === 'object' && x !== null ? x.value : x) as number;
    // 미판정 항목은 값 0 + 빗금 + 라벨
    const hatchedAll = s.flatMap((x) =>
      x.data.filter((v: any) => typeof v === 'object' && v?.itemStyle?.decal),
    );
    expect(hatchedAll.length).toBeGreaterThan(0);
    for (const h of hatchedAll) {
      expect(h.value).toBe(0);
      expect(h.label.show).toBe(true);
    }
    // 행마다 스택 합 = 서버 기여 합(미판정 = 0)
    const sorted = C06.sortedRows(rows);
    sorted.forEach((row, i) => {
      const stack = s.reduce((acc, x) => acc + (valueOf(x.data[i]) ?? 0), 0);
      const expected = Object.values(
        C06.contributions(row, C06.componentKeys({ rows, weights: d.weights })),
      ).reduce<number>((acc, v) => acc + (v ?? 0), 0);
      expect(stack).toBeCloseTo(expected, 6);
    });
  });

  it('상황 A·D의 move_in 성분도 키로 받는다', () => {
    const row = structuredCloneRow(d.top5[0]!);
    row.components.move_in = row.components.liquidity;
    delete row.components.liquidity;
    const weights = { ...d.weights, liquidity: undefined, move_in: 0.1 };
    expect(C06.componentKeys({ rows: [row], weights })).toContain('move_in');
    expect(C06.componentKeys({ rows: [row], weights })).not.toContain('liquidity');
  });
});

function structuredCloneRow<T>(row: T): T {
  return JSON.parse(JSON.stringify(row)) as T;
}

describe('C07 판정기 확률', () => {
  const c = compare();

  it('decide prob per 후보 + escape 선택지, confidence 텍스트', () => {
    const data = { decision: c.decisions.base! };
    const o = C07.buildOption(data);
    const bar = series(o)[0];
    expect(bar.type).toBe('bar');
    expect(opt(o).yAxis.data).toContain('사용자에게 질문');
    expect(C07.confidenceText(data)).toMatch(/^신뢰도 /);
    expect(C07.hasMismatch(data)).toBe(true);
  });

  it('T2 상황 B: confidence 0.48 < 0.6 → 동률', () => {
    const data = { decision: c.decisions.B! };
    expect(C07.isTie(data)).toBe(true);
    expect(C07.confidenceText(data)).toBe('신뢰도 0.48');
  });

  it('minor 28: 동률은 서버 tie 만 — confidence 로 브라우저가 다시 계산하지 않는다', () => {
    const decision = structuredCloneRow(c.decisions.base!);
    decision.tie = false;
    decision.confidence = { ...(decision.confidence as any), v: 0.3 };
    expect(C07.isTie({ decision })).toBe(false);
    decision.tie = true;
    decision.confidence = { ...(decision.confidence as any), v: 0.9 };
    expect(C07.isTie({ decision })).toBe(true);
  });

  it('minor 28: 봉투 review·blocked·error·escaped 면 동률 표시 없음(전체·항목 모두)', () => {
    for (const status of ['review', 'blocked', 'error', 'escaped'] as const) {
      const decision = structuredCloneRow(c.decisions.B!);
      decision.status = status;
      expect(decision.tie).toBe(true);
      expect(C07.isTie({ decision })).toBe(false);
      const o = C07.buildOption({ decision });
      const labels = decision.items.map((_, i) =>
        series(o)[0].label.formatter({ dataIndex: i, value: 0.5 }),
      );
      expect(labels.some((l: string) => l.includes('동률'))).toBe(false);
      expect(C07.toTable({ decision }).rows.some((r) => String(r.flags).includes('동률'))).toBe(
        false,
      );
    }
  });

  it('minor 28: ok 봉투의 항목 동률·선택은 서버 값 그대로', () => {
    const decision = c.decisions.B!;
    const o = C07.buildOption({ decision });
    decision.items.forEach((item, i) => {
      const label = series(o)[0].label.formatter({ dataIndex: i, value: 0.5 }) as string;
      expect(label.includes('동률')).toBe(item.tie);
      expect(label.includes('선택')).toBe(item.chosen);
    });
  });

  it('계약 .5 가상 후보 모집공고 대기(wait_new): 선택 강조 + "가상 후보", 질문 남김 아님', () => {
    const decision = structuredCloneRow(c.decisions.B!);
    decision.tie = false;
    decision.items = decision.items.map((item) => ({ ...item, chosen: false, tie: false }));
    const base = decision.items[0]!;
    decision.items.push({
      ...base,
      id: 999,
      option_key: 'wait_new',
      complex_id: null,
      label: '모집공고 대기',
      chosen: true,
      tie: false,
      mismatch: false,
    });
    const i = decision.items.length - 1;
    const o = C07.buildOption({ decision });
    const label = series(o)[0].label.formatter({ dataIndex: i, value: 0.94 }) as string;
    expect(label).toContain('선택');
    expect(label).not.toContain('질문 남김');
    expect(series(o)[0].data[i].itemStyle.color).toBe(DEFAULT_PALETTE.strong);
    const row = C07.toTable({ decision }).rows[i]!;
    expect(row.name).toBe('모집공고 대기');
    expect(String(row.flags)).toContain('가상 후보');
    expect(String(row.flags)).not.toContain('질문 남김');
  });

  it('escaped → 막대 대신 질문 텍스트', () => {
    const reason = C07.emptyReason({ decision: escapedDecision() });
    expect(reason).toContain('질문 남김');
    expect(reason).toContain('잔금대출 한도');
    expect(C07.emptyReason({ decision: null })).toBe('판정 없음');
  });

  it('툴팁의 서버 문자열은 HTML 이스케이프', () => {
    const decision = escapedDecision();
    decision.status = 'ok';
    decision.items[0]!.label = '<img src=x onerror=alert(1)>';
    const o = C07.buildOption({ decision });
    const tip = opt(o).tooltip.formatter({ dataIndex: 0 });
    expect(tip).not.toContain('<img');
    expect(tip).toContain('&lt;img');
  });
});

describe('C08 잔여 이력', () => {
  const events = elif().events;

  it('시간축 scatter, 마커 모양 = kind 4종', () => {
    const o = C08.buildOption({ events });
    expect(opt(o).xAxis.type).toBe('time');
    const symbols = Object.fromEntries(series(o).map((s) => [s.id, s.symbol]));
    expect(symbols).toEqual({
      본청약: 'circle',
      무순위: 'rect',
      임의: 'triangle',
      선착순: 'diamond',
    });
  });

  it('월만 확인된 공고일(YYYY-MM)도 그린다, 라벨 = 잔여 세대·경쟁률', () => {
    expect(C08.eventDate(events[1]!)).toBe('2025-10-01');
    const o = C08.buildOption({ events });
    const s = series(o).find((x) => x.id === '무순위');
    expect(s.data[0].value[0]).toBe('2025-10-01');
    expect(s.data[0].label.formatter).toContain('185세대');
  });

  it('이벤트 0 → "본청약만"', () => {
    expect(C08.emptyReason({ events: [] })).toBe('본청약만');
  });
});

describe('C09 호재 단계', () => {
  const catalysts = market().catalysts;

  it('타임라인은 확정 + 예정 연월 있는 것만', () => {
    const o = C09.buildOption({ catalysts });
    const items = series(o)[0].data as any[];
    const confirmed = catalysts.filter((c) => c.stage === '확정' && c.expected_ym.v);
    expect(items).toHaveLength(confirmed.length);
    expect(opt(o).xAxis.type).toBe('time');
  });

  it('보드 5열 묶음 + 언론·미확정 회색 + 위치 미확정 표시', () => {
    const groups = C09.groupByStage(catalysts);
    expect(Object.keys(groups)).toEqual(['확정', '계획', '추진', '언론', '미확정']);
    expect(groups['언론']).toHaveLength(1);
    const table = C09.toTable({ catalysts });
    expect(table.rows.some((r) => r.location === '위치 미확정 · 단지 연결 없음')).toBe(true);
    expect(C09.emptyReason({ catalysts: [] })).toBe('호재 없음');
  });
});

describe('C10 민감도', () => {
  const names = complexNames();

  it('표 = 12 변형 × TOP 5(이름), 변동 표시', () => {
    const table = C10.toTable({ sensitivity: sensitivity(), names });
    expect(table.rows).toHaveLength(12);
    expect(String(table.rows[0]!.top5)).toContain('더샵 송도그란테르');
    expect(table.rows.some((r) => r.changed === '예')).toBe(true);
  });

  it('작은 선: 기준 TOP 5 단지별 순위, y축 뒤집힘(1위 위)', () => {
    const o = C10.buildOption({ sensitivity: sensitivity(), names });
    const s = series(o);
    expect(s.length).toBe(sensitivity().base_top5.length);
    expect(s[0].name).toBe('더샵 송도그란테르');
    expect(opt(o).yAxis.inverse).toBe(true);
    expect(s.every((x) => x.connectNulls === false)).toBe(true);
  });

  it('변동 없는 가중치 행 = stable', () => {
    const rows = C10.variantRows({ sensitivity: stableSensitivity(), names });
    expect(rows.every((r) => r.stable)).toBe(true);
    expect(C10.emptyReason({ sensitivity: null })).toBe('민감도 없음');
  });
});
