/* eslint-disable @typescript-eslint/no-explicit-any -- ECharts option 유니온을 테스트에서 느슨하게 읽는다 */
/**
 * R11-CHARTS — 목업 보드(50-mockup: Main·DetailTabs·Compare·Scenario·Market·Shell §8·§11)대로 다시 그린 차트의 테스트.
 * coverage-*.md 차트 줄의 `테스트` 칸이 이 파일의 테스트 이름을 가리킨다.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { t } from '@/i18n';
import { renderWithProviders } from '@/test/render';
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
import { C02Gap, adjustedBadges } from './C02';
import { C07Decision } from './C07';
import { C09Catalyst } from './C09';
import { C10Sensitivity } from './C10';
import { ChartFrame, sourceLine } from './ChartFrame';
import {
  compare,
  complexNames,
  dashboard,
  elif,
  market,
  rowsWithUnjudged,
  sensitivity,
  stableSensitivity,
  supplyManyAreas,
} from './gallery/fixtures';
import { GALLERY_CASES } from './gallery/ChartGallery';
import {
  CATEGORICAL_DARK,
  CATEGORICAL_LIGHT,
  DEFAULT_PALETTE,
  legendStyle,
  seriesColor,
} from './palette';
import { chartRegistry } from './registry';

vi.mock('./EChart', () => ({
  EChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div data-testid="echart" role="img" aria-label={ariaLabel} />
  ),
}));

const opt = (o: unknown) => o as Record<string, any>;
const series = (o: unknown): any[] => {
  const s = opt(o).series;
  return Array.isArray(s) ? s : [s];
};
const axes = (v: unknown): any[] => (Array.isArray(v) ? v : v ? [v] : []);
const overlayOf = () => {
  const c = compare();
  return c.rows.map((row) => ({
    complex_id: row.complex_id,
    name: row.name,
    ladder: c.ladders[String(row.complex_id)] ?? [],
  }));
};

describe('R11 팔레트(목업 파랑·주황, 라이트·다크)', () => {
  it('팔레트: 계열 색은 파랑 → 주황 순서로 시작하고 라이트·다크가 따로 있다', () => {
    expect(CATEGORICAL_LIGHT[0]).toBe('#2350D8');
    expect(CATEGORICAL_LIGHT[1]).toBe('#D97A1E');
    expect(CATEGORICAL_DARK).toHaveLength(CATEGORICAL_LIGHT.length);
    expect(CATEGORICAL_DARK).not.toEqual(CATEGORICAL_LIGHT);
    expect(DEFAULT_PALETTE.secondary).toBe(CATEGORICAL_LIGHT[1]);
  });

  it('팔레트: 계열 색은 돌려 쓰지 않는다(넘치면 마지막 색)', () => {
    const n = DEFAULT_PALETTE.categorical.length;
    expect(seriesColor(DEFAULT_PALETTE, n + 3)).toBe(DEFAULT_PALETTE.categorical[n - 1]);
  });

  it('범례 위치: ECharts 범례는 숨기고(show:false) HTML 범례를 차트 위에 둔다', () => {
    expect(legendStyle(DEFAULT_PALETTE).show).toBe(false);
  });
});

describe('R11 라벨이 사라지지 않는다', () => {
  it('라벨 사라짐 없음: 모든 갤러리 데이터의 축 라벨은 잘라 숨기지 않는다(overflow truncate 없음)', () => {
    const d = dashboard();
    const m = market();
    const cases: [string, unknown][] = [
      ['C01', { ladder: elif().ladder, horizon: 'move_in_plus_1y' }],
      ['C01', { ladder: [], horizon: 'move_in_plus_1y', overlay: overlayOf() }],
      ['C02', { gap: elif().gap }],
      ['C03', { benchmarks: m.benchmarks, asofYear: 2026 }],
      ['C04', { supply: supplyManyAreas(), markers: m.move_in_markers }],
      ['C05', { unsold: m.unsold }],
      ['C06', { rows: d.top5, weights: d.weights }],
      ['C06', { rows: d.top5, weights: d.weights, orientation: 'horizontal' }],
      ['C07', { decision: compare().decisions.base }],
      ['C08', { events: elif().events }],
      ['C09', { catalysts: m.catalysts }],
      ['C10', { sensitivity: sensitivity(), names: complexNames() }],
    ];
    for (const [id, data] of cases) {
      const entry = chartRegistry.find((c) => c.id === id)!;
      const o = opt(entry.buildOption(data));
      for (const axis of [...axes(o.xAxis), ...axes(o.yAxis)]) {
        expect(axis.axisLabel?.overflow, `${id} 축 라벨`).not.toBe('truncate');
      }
    }
  });

  it('축 눈금: 값 축·범주 축 모두 눈금(axisTick)을 그린다', () => {
    const o = opt(C04.buildOption({ supply: market().supply, markers: [] }));
    expect(o.xAxis.axisTick.show).toBe(true);
    expect(o.yAxis.axisTick.show).toBe(true);
  });

  it('갤러리: C04 특수 2 = 생활권 8곳(나머지·확인 불가)', () => {
    expect(
      GALLERY_CASES.filter((c) => c.chart === 'C04' && c.state === 'special').length,
    ).toBeGreaterThanOrEqual(2);
  });
});

describe('R11 ChartFrame(Shell §8)', () => {
  it('ChartFrame: 제목·라벨 배지·부제 → 범례(위) → 차트 → 바닥줄 "자료: 출처 · 기준일" + 표로 보기', () => {
    renderWithProviders(
      <ChartFrame
        title="T"
        subtitle="S"
        labels={['추정']}
        legend={[{ name: 'L1', color: '#000', symbol: 'square' }]}
        table={{ columns: [{ key: 'a', header: 'A' }], rows: [{ a: 'x' }] }}
        source="SRC"
        asof="2026-10-14"
      >
        <div data-testid="body" />
      </ChartFrame>,
    );
    const figure = screen.getByRole('figure');
    const legend = within(figure).getByTestId('chart-legend');
    const body = within(figure).getByTestId('body');
    // 범례가 차트 본문보다 앞(위)
    expect(legend.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(figure).getByTestId('chart-source')).toHaveTextContent(
      t('chart.sourceAsof', { source: 'SRC', asof: '2026-10-14' }),
    );
    expect(within(figure).getByTestId('chart-subtitle')).toHaveTextContent('S');
    expect(within(figure).getAllByTestId('label-badge').length).toBe(1);
  });

  it('ChartFrame 표로 보기: 캡션 "{제목} 데이터", 펼치면 표 닫기, 줄이 없으면 열 머리 아래 "데이터 없음" 한 줄', async () => {
    renderWithProviders(
      <ChartFrame title="T" table={{ columns: [{ key: 'a', header: 'A' }], rows: [] }}>
        <div />
      </ChartFrame>,
    );
    const button = screen.getByRole('button', { name: t('table.show') });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(button);
    expect(screen.getByRole('button', { name: t('table.hide') })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    const table = screen.getByRole('table', { name: t('table.caption', { title: 'T' }) });
    expect(within(table).getByRole('columnheader', { name: 'A' })).toBeInTheDocument();
    expect(within(table).getByTestId('chart-table-empty')).toHaveTextContent(t('empty.noData'));
  });

  it('ChartFrame 빈 상태: 차트·범례 대신 빈 상태 문구, 바닥줄은 남는다', () => {
    renderWithProviders(
      <ChartFrame
        title="T"
        emptyReason="E"
        legend={[{ name: 'L1', color: '#000', symbol: 'square' }]}
        source="SRC"
      >
        <div data-testid="body" />
      </ChartFrame>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('E');
    expect(screen.queryByTestId('body')).toBeNull();
    expect(screen.queryByTestId('chart-legend')).toBeNull();
    expect(screen.getByTestId('chart-source')).toHaveTextContent(
      t('chart.source', { source: 'SRC' }),
    );
  });

  it('ChartFrame 바닥줄 글자: 출처·기준일 있는 것만', () => {
    expect(sourceLine(null, null)).toBeNull();
    expect(sourceLine(null, '2026-10-14')).toBe(t('chart.asofOnly', { asof: '2026-10-14' }));
    expect(sourceLine('S', null)).toBe(t('chart.source', { source: 'S' }));
  });

  it.each(chartRegistry.map((c) => c.id))(
    '%s 출처: ko chart.<id>.source 기본 출처 설명이 있다',
    (id) => {
      expect(t(`chart.${id}.source` as Parameters<typeof t>[0])).not.toBe(`chart.${id}.source`);
    },
  );
});

describe('R11 C01 가능성 사다리', () => {
  const ladder = elif().ladder;

  it('C01 눈금: 가능성 축 0~100%(20%p 간격), 축 이름 "가능성"', () => {
    const o = opt(C01.buildOption({ ladder, horizon: 'move_in_plus_1y' }));
    expect(o.xAxis).toMatchObject({ min: 0, max: 1, interval: 0.2, name: t('chart.axis.prob') });
    expect(o.xAxis.axisLabel.formatter(1)).toBe('100%');
  });

  it('C01 쉬운 말: 막대 이름 "10% 넘게 오를 가능성"(+ 점수에 씀), 점수 막대만 강조색', () => {
    const o = opt(C01.buildOption({ ladder, horizon: 'move_in_plus_1y' }));
    expect(o.yAxis.data[1]).toContain(t('chart.C01.bar.p10'));
    expect(o.yAxis.data[1]).toContain('점수에 씀');
    const colors = series(o)[0].data.map((d: any) => d.itemStyle.color);
    expect(colors[1]).toBe(DEFAULT_PALETTE.strong);
    expect(colors.filter((c: string) => c === DEFAULT_PALETTE.strong)).toHaveLength(1);
  });

  it('C01 목표 시점: 겹쳐 보기 부제에 단지마다 목표 시점을 보인다', () => {
    const overlay = overlayOf();
    const sub = C01.subtitle({ ladder: [], horizon: 'move_in_plus_1y', overlay }) ?? '';
    for (const o of overlay) expect(sub).toContain(o.name);
    expect(sub.startsWith('목표 시점')).toBe(true);
  });

  it('C01 겹쳐 보기: 막대 묶음 · 기준선 0.15/0.85 · 막대 위 확률 글자', () => {
    const o = opt(
      C01.buildOption({ ladder: [], horizon: 'move_in_plus_1y', overlay: overlayOf() }),
    );
    const s = series(o);
    expect(s[0].markLine.data.map((d: any) => d.yAxis)).toEqual([0.15, 0.85]);
    expect(s[0].label.formatter({ value: 0.53 })).toBe('53%');
    expect(o.yAxis.interval).toBe(0.25);
  });

  it('C01 툴팁: 막대 이름 · 확률 · 판정 + 필요한 연 상승률', () => {
    const o = opt(C01.buildOption({ ladder, horizon: 'move_in_plus_1y' }));
    const tip = o.tooltip.formatter({ dataIndex: 1 }) as string;
    expect(tip).toContain(t('chart.C01.bar.p10'));
    expect(tip).toContain('필요한 연 상승률');
  });
});

describe('R11 C02 가격 갭', () => {
  it('C02 축 이름: 비교 단지 이름 + 신축/대체 배지, 첫 줄은 이 단지', () => {
    const gap = compare().gaps['4']!;
    const o = opt(C02.buildOption({ gap }));
    expect(o.yAxis.data[0]).toBe(t('chart.C02.current'));
    expect(o.yAxis.data[1]).toContain(gap.comps[0]!.name);
    expect(o.yAxis.data[1]).toContain(C02.compBadge(true, gap.comps[0]!.completed_year));
    expect(o.yAxis.inverse).toBe(true);
  });

  it('C02 보정 가운데값: 점선 빈 점 계열 + 범례(대체 단지가 있을 때만)', () => {
    const adjusted = C02.legendItems({ gap: compare().gaps['4']! });
    expect(adjusted.map((x) => x.name)).toContain(t('chart.C02.adjusted'));
    const plain = C02.legendItems({ gap: elif().gap });
    expect(plain.map((x) => x.name)).not.toContain(t('chart.C02.adjusted'));
  });

  it('C02 주변 전체 중간값 선 없음(서버에 없는 값 — 고침 CP-2)', () => {
    const o = opt(C02.buildOption({ gap: elif().gap }));
    for (const s of series(o)) expect(s.markLine).toBeUndefined();
  });

  it('C02 툴팁: 이름·배지 / 가장 낮은 값 ~ 가장 높은 값 / 가운데값(보정 안 함)', () => {
    const gap = elif().gap;
    const o = opt(C02.buildOption({ gap }));
    const tip = series(o)[0].tooltip.formatter({ value: [1] }) as string;
    expect(tip).toContain(gap.comps[0]!.name);
    expect(tip).toContain('가장 낮은 값');
    expect(tip).toContain(t('chart.C02.unadjusted'));
  });
});

describe('R11 C03 근처 새 아파트', () => {
  it('C03 범례: 분양가 · 실거래 범위 · 중간 값 · 고점 · 분양권(있을 때)', () => {
    const m = market();
    const names = C03.legendItems({ benchmarks: m.benchmarks, asofYear: 2026 }).map((x) => x.name);
    expect(names).toEqual(
      expect.arrayContaining([
        t('chart.C03.sale'),
        t('chart.C03.range'),
        t('chart.C03.median'),
        t('chart.C03.peak'),
        t('chart.C03.presaleLegend'),
      ]),
    );
  });

  it('C03 축 이름: "84㎡ 기준 가격", 억 단위 눈금', () => {
    const o = opt(C03.buildOption({ benchmarks: market().benchmarks, asofYear: 2026 }));
    expect(o.xAxis.name).toBe(t('chart.axis.price84'));
    expect(o.xAxis.axisLabel.formatter(800_000_000)).toBe('8.0억');
  });
});

describe('R11 C04 입주 물량', () => {
  const data = { supply: supplyManyAreas(), markers: market().move_in_markers.slice(0, 1) };

  it('C04 생활권 묶기: 큰 5곳 + 나머지 n곳 + 확인 불가(생활권 모름)', () => {
    const g = C04.areaGroups(data);
    expect(g.top).toHaveLength(5);
    expect(g.rest).toHaveLength(3);
    expect(g.unknown).toBe(true);
    expect(C04.restName(data, g)).toContain('나머지 3곳');
  });

  it('C04 나머지: 계열은 생활권마다 따로(서버 값 그대로), 이름·색만 하나', () => {
    const s = series(C04.buildOption(data));
    const rest = s.filter((x) => x.name.startsWith('나머지'));
    expect(rest).toHaveLength(3);
    expect(new Set(rest.map((x) => x.itemStyle.color)).size).toBe(1);
    expect(rest[0].itemStyle.color).toBe(DEFAULT_PALETTE.rest);
    // 값은 생활권 행 그대로(합치지 않는다)
    const one = data.supply.find((r) => r.living_area === rest[0].id && r.year === 2027)!;
    expect(rest[0].data[0]).toBe(one.units.v);
    const unknown = s.find((x) => x.id === C04.UNKNOWN_AREA);
    expect(unknown.name).toBe(t('chart.C04.unknownArea'));
    expect(unknown.itemStyle.decal).toBeDefined();
  });

  it('C04 범례(위): 큰 생활권 · 나머지 · 점수 매긴 단지 입주 · 확인 불가', () => {
    const items = C04.legendItems(data);
    expect(items.map((x) => x.symbol)).toEqual([
      'square',
      'square',
      'square',
      'square',
      'square',
      'square',
      'pin',
      'hatch',
    ]);
    expect(items[5]!.name).toContain('나머지');
    expect(items[7]!.name).toBe(t('chart.C04.unknownArea'));
  });

  it('C04 툴팁: 생활권마다 세대(묶은 생활권도 제 이름으로), 합계 줄 없음', () => {
    const o = opt(C04.buildOption(data));
    const ids = series(o).map((x) => x.id);
    const tip = o.tooltip.formatter(
      ids.map((id: string) => ({ seriesId: id, value: 100, axisValue: '2028' })),
    ) as string;
    expect(tip).toContain('생활권 아'); // 나머지로 묶인 생활권
    expect(tip).toContain(t('chart.C04.unknownArea'));
    expect(tip).not.toContain('합계');
  });

  it('C04 표: 생활권 모르는 줄은 "확인 불가"', () => {
    const rows = C04.toTable(data).rows;
    expect(rows.some((r) => r.living_area === t('empty.unknown'))).toBe(true);
  });
});

describe('R11 C05 미분양', () => {
  it('C05 범례: 실선 ● 합계 · 점선 ■ 준공 후(주황)', () => {
    const items = C05.legendItems({ unsold: market().unsold });
    expect(items.map((x) => x.symbol)).toEqual(['line', 'dashedLine']);
    expect(items[1]!.color).toBe(DEFAULT_PALETTE.secondary);
  });

  it('C05 툴팁: 그 달의 두 값, 빈 달은 확인 불가', () => {
    const o = opt(C05.buildOption({ unsold: market().unsold }));
    const tip = o.tooltip.formatter([
      { seriesId: 'total', value: 103, axisValue: '2025-12' },
      { seriesId: 'post', value: null, axisValue: '2025-12' },
    ]) as string;
    expect(tip).toContain(`${t('chart.C05.totalShort')} 103`);
    expect(tip).toContain(`${t('chart.C05.postShort')} ${t('empty.unknown')}`);
    expect(o.yAxis.name).toBe(t('chart.axis.households'));
  });
});

describe('R11 C06 점수 분해', () => {
  const d = dashboard();

  it('C06 비중: 범례마다 "비중 n%"(가중치 0.35 → 35%)', () => {
    const items = C06.legendItems({ rows: d.top5, weights: d.weights });
    expect(items[0]!.note).toBe(t('chart.C06.weightPct', { pct: '35' }));
    expect(items.every((x) => x.note?.startsWith('비중'))).toBe(true);
  });

  it('C06 색은 기준을 따른다(되팔기 쉬움·입주 시기는 같은 자리)', () => {
    expect(C06.componentColor(DEFAULT_PALETTE, 'liquidity')).toBe(
      C06.componentColor(DEFAULT_PALETTE, 'move_in'),
    );
    const o = series(C06.buildOption({ rows: d.top5, weights: d.weights }));
    expect(o[0].itemStyle.color).toBe(C06.componentColor(DEFAULT_PALETTE, 'p10'));
    // 칸 사이 바탕색 틈
    expect(o[0].itemStyle.borderColor).toBe(DEFAULT_PALETTE.bg);
  });

  it('C06 미판정 범례: 빗금 "미판정" 항목(미판정 칸이 있을 때만)', () => {
    const withUnjudged = C06.legendItems({ rows: rowsWithUnjudged(), weights: d.weights });
    expect(withUnjudged.at(-1)).toMatchObject({ name: t('badge.unjudged'), symbol: 'hatch' });
    const none = C06.legendItems({ rows: d.top5, weights: d.weights });
    expect(none.some((x) => x.symbol === 'hatch')).toBe(false);
  });

  it('C06 값 축: 축 이름 "점수"', () => {
    const o = opt(C06.buildOption({ rows: d.top5, weights: d.weights }));
    expect(o.yAxis.name).toBe(t('chart.axis.score'));
  });
});

describe('R11 C07 판정기가 고를 확률', () => {
  it('C07 보류 선택지: 단지가 아닌 선택지 막대는 회색 + "판정기 보류 선택지"', () => {
    const decision = compare().decisions.base!;
    const o = opt(C07.buildOption({ decision }));
    const i = decision.items.findIndex((x) => x.option_key !== 'complex');
    expect(i).toBeGreaterThanOrEqual(0);
    expect(series(o)[0].label.formatter({ dataIndex: i, value: 0.02 })).toContain(
      t('chart.C07.hold'),
    );
    expect(series(o)[0].data[i].itemStyle.color).toBe(DEFAULT_PALETTE.grayed);
  });

  it('C07 눈금: 0·25·50·75·100%, 축 이름 "고를 확률"', () => {
    const o = opt(C07.buildOption({ decision: compare().decisions.base! }));
    expect(o.xAxis).toMatchObject({ min: 0, max: 1, interval: 0.25 });
    expect(o.xAxis.name).toBe(t('chart.axis.choiceProb'));
  });

  it('C07 범례: 판정기 선택 · 다른 후보 · 보류 선택지', () => {
    const names = C07.legendItems({ decision: compare().decisions.base! }).map((x) => x.name);
    expect(names).toEqual([t('chart.chosen'), t('chart.C07.other'), t('chart.C07.holdLegend')]);
  });
});

describe('R11 C08 다시 모집 이력', () => {
  it('C08 기준일: 시간축에 기준일 세로 점선(서버 기준일 그대로)', () => {
    const o = opt(C08.buildOption({ events: elif().events, asof: '2026-10-14' }));
    const line = series(o).find((s) => s.markLine)?.markLine;
    expect(line.data[0].xAxis).toBe('2026-10-14');
    expect(line.label.formatter).toBe(t('chart.C08.asof', { date: '2026-10-14' }));
    expect(series(C08.buildOption({ events: elif().events })).some((s) => s.markLine)).toBe(false);
  });

  it('C08 범례: 모집 종류 4가지 — 모양이 다르고 본청약만 진한 색', () => {
    const items = C08.legendItems({ events: elif().events });
    expect(new Set(items.map((x) => x.symbol)).size).toBe(4);
    expect(items[0]!.color).toBe(DEFAULT_PALETTE.fg);
    expect(items.slice(1).every((x) => x.color === DEFAULT_PALETTE.strong)).toBe(true);
  });
});

describe('R11 C09 개발 소식 단계', () => {
  it('C09 단계 보드: 칸마다 개수(목록 세기) + 빈 칸은 "없음"', () => {
    const catalysts = market().catalysts.filter((c) => c.stage === '확정');
    renderWithProviders(<C09Catalyst data={{ catalysts, compact: true }} />);
    const board = screen.getByTestId('catalyst-board');
    const planned = within(board).getByRole('region', { name: t('chart.C09.stage.계획') });
    expect(planned).toHaveTextContent(t('chart.C09.none'));
    expect(planned.querySelector('[data-meta="count"]')).toHaveTextContent('0건');
    const confirmed = within(board).getByRole('region', { name: t('chart.C09.stage.확정') });
    expect(confirmed.querySelector('[data-meta="count"]')).toHaveTextContent(
      `${catalysts.length}건`,
    );
  });

  it('C09 일정표 비었을 때: 확정 + 예정 시기 소식이 없으면 안내 문구(G3 compact는 없음)', () => {
    const catalysts = market().catalysts.filter((c) => c.stage !== '확정');
    const { unmount } = renderWithProviders(<C09Catalyst data={{ catalysts }} />);
    expect(screen.getByTestId('catalyst-timeline-empty')).toHaveTextContent(
      t('chart.C09.timelineEmpty'),
    );
    unmount();
    renderWithProviders(<C09Catalyst data={{ catalysts, compact: true }} />);
    expect(screen.queryByTestId('catalyst-timeline-empty')).toBeNull();
  });

  it('C09 쉬운 단계 이름: 언론 → 언론 보도만, 미확정 → 아직 정해지지 않음', () => {
    expect(C09.stageLabel('언론')).toBe('언론 보도만');
    expect(C09.stageLabel('미확정')).toBe('아직 정해지지 않음');
  });
});

describe('R11 C10 민감도(재설계)', () => {
  const data = { sensitivity: sensitivity(), names: complexNames() };

  it('C10 재설계 표: 기준 6줄 × (줄이면/늘리면) — 서버 변형을 짝지어 놓기만 한다', () => {
    const rows = C10.criterionRows(data);
    expect(rows).toHaveLength(6);
    for (const row of rows) {
      expect(row.down?.delta).toBeLessThan(0);
      expect(row.up?.delta).toBeGreaterThan(0);
    }
    expect(rows[0]!.name).toBe(t('chart.C06.component.p10'));
    expect(rows[0]!.weightPct).toBe('35');
  });

  it('C10 x축: 아래 줄 줄이면/늘리면, 그 아래 기준 이름(두 칸씩)', () => {
    const o = opt(C10.buildOption(data));
    const [dir, group] = o.xAxis;
    expect(dir.data.slice(0, 2)).toEqual([t('chart.C10.down'), t('chart.C10.up')]);
    expect(dir.data).toHaveLength(12);
    expect(group.data).toHaveLength(6);
    expect(group.data[0]).toBe(t('chart.C10.short.p10'));
    // 선의 점 순서도 같은 순서(서버 변형을 기준 × 방향으로 정렬)
    const cells = C10.orderedCells(data);
    expect(cells[0]!.component).toBe('p10');
    expect(cells[0]!.delta).toBeLessThan(0);
  });

  it('C10 상위 5곳 밖 띠: 순위가 5위보다 크면 주황 띠(markArea) + 범례', () => {
    const o = opt(C10.buildOption(data));
    const area = series(o)[0].markArea;
    expect(area.data[0][0].yAxis).toBe(5.5);
    expect(C10.legendItems(data).at(-1)?.name).toBe(t('chart.C10.outsideBand'));
  });

  it('C10 결과 개수: 순위 변동 있음/없음을 센다(서버 changed)', () => {
    const counts = C10.changeCounts(data);
    expect(counts.changed + counts.unchanged).toBe(12);
    expect(C10.changeCounts({ sensitivity: stableSensitivity() })).toEqual({
      changed: 0,
      unchanged: 12,
    });
  });

  it('C10 이름: names 없으면 서버 complex_names', () => {
    expect(C10.nameOf({ sensitivity: sensitivity() }, 1)).toBe(sensitivity().complex_names?.['1']);
  });

  it('C10 툴팁: 비중 바꾼 항목 / 단지별 순위(상위 5곳 밖 표시, 없으면 확인 불가)', () => {
    const o = opt(C10.buildOption(data));
    const tip = o.tooltip.formatter([
      { seriesName: 'A', value: 7, dataIndex: 0 },
      { seriesName: 'B', value: null, dataIndex: 0 },
    ]) as string;
    expect(tip).toContain(C10.variantLabel(C10.orderedCells(data)[0]!));
    expect(tip).toContain(t('chart.C10.outside'));
    expect(tip).toContain(`B ${t('empty.unknown')}`);
  });

  it('C10 패널: 결과 줄 · 표(칸마다 1~5위 + 순위 변동) · 변동 없는 칸 회색', () => {
    renderWithProviders(<C10Sensitivity data={data} />);
    expect(screen.getByTestId('c10-summary')).toHaveTextContent('순위 변동(상위 5곳 바뀜)');
    expect(screen.getAllByTestId('c10-changed')).toHaveLength(12);
    const table = screen.getAllByRole('table')[0]!;
    expect(within(table).getByText(t('chart.C10.downCol'))).toBeInTheDocument();
    expect(table.querySelectorAll('td[data-stable="true"]').length).toBe(
      C10.changeCounts(data).unchanged,
    );
  });
});

describe('R11 보충', () => {
  it('차트 이름(aria-label) = 제목: 갤러리 정상 카드마다 차트 img 이름이 제목(또는 일정표 이름)', () => {
    for (const item of GALLERY_CASES.filter((c) => c.state === 'normal')) {
      const { unmount } = renderWithProviders(<>{item.render()}</>);
      const names = screen.getAllByRole('img').map((el) => el.getAttribute('aria-label'));
      const title = t(`chart.${item.chart}.title` as Parameters<typeof t>[0]);
      expect(names, item.chart).toEqual(
        expect.arrayContaining([item.chart === 'C09' ? t('chart.C09.timeline') : title]),
      );
      unmount();
    }
  });

  it('C01 표: 시점 · 목표 시점 · 막대 4개(짧은 이름) · 상태, 겹쳐 보기면 이름 열', () => {
    const single = C01.toTable({ ladder: elif().ladder, horizon: 'move_in_plus_1y' });
    expect(single.columns.map((c) => c.header)).toEqual([
      t('chart.col.horizon'),
      t('chart.col.target'),
      t('chart.C01.barShort.p5'),
      t('chart.C01.barShort.p10'),
      t('chart.C01.barShort.p20'),
      t('chart.C01.barShort.p_flat'),
      t('chart.col.status'),
    ]);
    const overlay = C01.toTable({ ladder: [], horizon: 'move_in_plus_1y', overlay: overlayOf() });
    expect(overlay.columns[0]!.header).toBe(t('chart.col.name'));
    expect(overlay.rows).toHaveLength(overlayOf().length);
  });

  it('C02 제목: G4는 단지 이름을 제목으로(title prop)', () => {
    renderWithProviders(<C02Gap data={{ gap: elif().gap }} title="단지 가" />);
    expect(screen.getByRole('heading', { level: 3, name: '단지 가' })).toBeInTheDocument();
  });

  it('C02 보정 배지: 대체·보정 비교군이면 "추정(대체·보정 c=…)" 배지', () => {
    const texts = adjustedBadges({ gap: compare().gaps['4']! });
    expect(texts.length).toBeGreaterThan(0);
    expect(texts[0]).toContain('대체·보정');
    expect(adjustedBadges({ gap: elif().gap })).toEqual([]);
  });

  it('C07 미해결: 봉투 review면 배지 "판정 미해결" + 막대 회색 + 값 옆 "미해결"', () => {
    const decision = { ...compare().decisions.base!, status: 'review' as const };
    renderWithProviders(<C07Decision data={{ decision }} />);
    expect(screen.getByTestId('unresolved-badge')).toHaveTextContent(t('chart.C07.unresolved'));
    const o = opt(C07.buildOption({ decision }));
    expect(series(o)[0].data.every((d: any) => d.itemStyle.color === DEFAULT_PALETTE.grayed)).toBe(
      true,
    );
    expect(series(o)[0].label.formatter({ dataIndex: 0, value: 0.5 })).toContain(
      t('badge.unresolved'),
    );
  });

  it('C08 툴팁: 종류 · 공고일 / 공고 번호 / 세대 · 경쟁률 / 결과', () => {
    const events = elif().events;
    const o = opt(C08.buildOption({ events }));
    const kind = events[1]!.kind;
    const tip = o.tooltip.formatter({ seriesId: kind, dataIndex: 0 }) as string;
    expect(tip).toContain(t(`chart.C08.kind.${kind}` as Parameters<typeof t>[0]));
    if (events[1]!.notice_no) expect(tip).toContain(events[1]!.notice_no);
  });

  it('C10 진입 굵게: 새로 들어온 단지 이름은 굵게', () => {
    const data = { sensitivity: sensitivity(), names: complexNames() };
    const entered = C10.variantRows(data).find((r) => r.entered.length > 0)!;
    expect(entered).toBeDefined();
    renderWithProviders(<C10Sensitivity data={data} />);
    const bold = [...document.querySelectorAll('li.font-semibold')].map((li) => li.textContent);
    expect(bold.some((text) => text?.includes(entered.entered[0]!))).toBe(true);
  });

  it('C10 범례: 기준 TOP 5 단지(색 + 모양, 서버 base_top5 순서)', () => {
    const data = { sensitivity: sensitivity(), names: complexNames() };
    const items = C10.legendItems(data);
    const base = sensitivity().base_top5;
    expect(items.slice(0, base.length).map((x) => x.name)).toEqual(
      base.map((id) => C10.nameOf(data, id)),
    );
    expect(new Set(items.slice(0, 4).map((x) => x.symbol)).size).toBe(4);
  });
});
