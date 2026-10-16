/**
 * 차트 갤러리(개발 전용) — 차트 10개 × 정상·빈·특수 상태를 한 화면에. 데이터는 계약 예시(./fixtures).
 * WP6a가 `/__charts`(dev) 라우트에 등록한다. 등록 전에는 테스트 전용 엔트리(./gallery.html)로 연다.
 */
import type { ReactNode } from 'react';
import { t } from '@/i18n';
import { useTheme } from '@/lib/theme';
import { C01Ladder } from '../C01';
import { C01_EMPTY } from '../C01/types';
import { C02Gap } from '../C02';
import { C03Benchmark } from '../C03';
import { C04Supply } from '../C04';
import { C05Unsold } from '../C05';
import { C06ScoreBreakdown } from '../C06';
import { C07Decision } from '../C07';
import { C08Timeline } from '../C08';
import { C09Catalyst } from '../C09';
import { C10Sensitivity } from '../C10';
import type { ChartId } from '../types';
import {
  ASOF,
  compare,
  complexNames,
  decisionWithWaitNew,
  dashboard,
  elif,
  escapedDecision,
  kaive,
  market,
  rowsWithUnjudged,
  sensitivity,
  stableSensitivity,
  supplyManyAreas,
} from './fixtures';

export type GalleryState = 'normal' | 'empty' | 'special' | 'escaped';

export interface GalleryCase {
  chart: ChartId;
  state: GalleryState;
  /** 상태 설명(개발자용 주석 — 화면에 그리지 않는다. 화면 문자열은 ko.json) */
  note: string;
  render: () => ReactNode;
}

const m = market();
const d = dashboard();
const c = compare();
const detail = elif();

const overlay = c.rows.map((row) => ({
  complex_id: row.complex_id,
  name: row.name,
  ladder: c.ladders[String(row.complex_id)] ?? [],
}));

/** 지역명이 아니라 예시 데이터의 생활권 id로 고른다 */
const firstArea = m.living_areas[1]?.id ?? null;

export const GALLERY_CASES: GalleryCase[] = [
  {
    chart: 'C01',
    state: 'normal',
    note: 'ComplexDetail.ladder · 입주+1년',
    render: () => <C01Ladder data={{ ladder: detail.ladder, horizon: 'move_in_plus_1y' }} />,
  },
  {
    chart: 'C01',
    state: 'empty',
    note: 'ladder []',
    render: () => <C01Ladder data={{ ...C01_EMPTY, ladder: kaive().ladder }} />,
  },
  {
    chart: 'C01',
    state: 'special',
    note: 'status=review → 회색 + 미해결',
    render: () => <C01Ladder data={{ ladder: detail.ladder, horizon: 'asof_plus_3y' }} />,
  },
  {
    chart: 'C01',
    state: 'special',
    note: 'G4 overlay(점)',
    render: () => <C01Ladder data={{ ladder: [], horizon: 'move_in_plus_1y', overlay }} />,
  },
  {
    chart: 'C02',
    state: 'normal',
    note: 'ComplexDetail.gap',
    render: () => <C02Gap data={{ gap: detail.gap }} />,
  },
  {
    chart: 'C02',
    state: 'empty',
    note: 'comps 0 → 비교군 없음(사유)',
    render: () => <C02Gap data={{ gap: kaive().gap }} />,
  },
  {
    chart: 'C02',
    state: 'special',
    note: 'T11 대체·보정(점선 점)',
    render: () => <C02Gap data={{ gap: c.gaps['4'] ?? null }} />,
  },
  {
    chart: 'C03',
    state: 'normal',
    note: 'Market.benchmarks',
    render: () => (
      <C03Benchmark
        data={{
          benchmarks: m.benchmarks,
          asofYear: 2026,
          flags: m.benchmark_flags,
          livingAreas: m.living_areas,
        }}
      />
    ),
  },
  {
    chart: 'C03',
    state: 'empty',
    note: '0개',
    render: () => <C03Benchmark data={{ benchmarks: [], asofYear: null }} />,
  },
  {
    chart: 'C03',
    state: 'special',
    note: '표본 < 3 배지',
    render: () => (
      <C03Benchmark
        data={{
          benchmarks: m.benchmarks.filter((b) => b.living_area === firstArea).slice(0, 2),
          asofYear: 2026,
        }}
      />
    ),
  },
  {
    chart: 'C04',
    state: 'normal',
    note: 'Market.supply + 입주 마커',
    render: () => (
      <C04Supply
        data={{ supply: m.supply, markers: m.move_in_markers, livingAreas: m.living_areas }}
      />
    ),
  },
  {
    chart: 'C04',
    state: 'empty',
    note: '0개',
    render: () => <C04Supply data={{ supply: [], markers: [] }} />,
  },
  {
    chart: 'C04',
    state: 'special',
    note: 'G3: 생활권 하나 + 단지 1개 마커',
    render: () => {
      const area = m.supply[0]?.living_area ?? null;
      return (
        <C04Supply
          data={{
            supply: m.supply.filter((s) => s.living_area === area),
            markers: m.move_in_markers.filter((x) => x.living_area === area).slice(0, 1),
            livingAreas: m.living_areas,
          }}
        />
      );
    },
  },
  {
    chart: 'C04',
    state: 'special',
    note: '생활권 8곳 → 큰 5곳 + 나머지 3곳 + 확인 불가(생활권 모름)',
    render: () => (
      <C04Supply data={{ supply: supplyManyAreas(), markers: m.move_in_markers.slice(0, 1) }} />
    ),
  },
  {
    chart: 'C05',
    state: 'normal',
    note: 'Dashboard.unsold_series',
    render: () => <C05Unsold data={{ unsold: d.unsold_series }} />,
  },
  { chart: 'C05', state: 'empty', note: '0개', render: () => <C05Unsold data={{ unsold: [] }} /> },
  {
    chart: 'C05',
    state: 'special',
    note: '결측 월 connectNulls=false',
    render: () => <C05Unsold data={{ unsold: m.unsold }} />,
  },
  {
    chart: 'C06',
    state: 'normal',
    note: 'Dashboard.top5 · 기여 합 = 종합',
    render: () => <C06ScoreBreakdown data={{ rows: d.top5, weights: d.weights }} />,
  },
  {
    chart: 'C06',
    state: 'empty',
    note: '0행',
    render: () => <C06ScoreBreakdown data={{ rows: [], weights: d.weights }} />,
  },
  {
    chart: 'C06',
    state: 'special',
    note: 'null 성분 → 빗금 + 미판정, 가로(G4)',
    render: () => (
      <C06ScoreBreakdown
        data={{ rows: rowsWithUnjudged(), weights: d.weights, orientation: 'horizontal' }}
      />
    ),
  },
  {
    chart: 'C07',
    state: 'normal',
    note: 'CompareView.decisions.base · MismatchBadge · 가상 후보 wait_new',
    render: () => <C07Decision data={{ decision: decisionWithWaitNew() }} />,
  },
  {
    chart: 'C07',
    state: 'empty',
    note: 'null',
    render: () => <C07Decision data={{ decision: null }} />,
  },
  {
    chart: 'C07',
    state: 'special',
    note: 'T2 상황 B: confidence 0.48 → 동률',
    render: () => <C07Decision data={{ decision: c.decisions.B ?? null }} />,
  },
  {
    chart: 'C07',
    state: 'escaped',
    note: 'escaped → 질문 텍스트',
    render: () => <C07Decision data={{ decision: escapedDecision() }} />,
  },
  {
    chart: 'C08',
    state: 'normal',
    note: 'ComplexDetail.events (월만 확인 포함)',
    render: () => <C08Timeline data={{ events: detail.events }} asof={ASOF} />,
  },
  {
    chart: 'C08',
    state: 'empty',
    note: '0개 → 본청약만',
    render: () => <C08Timeline data={{ events: [] }} />,
  },
  {
    chart: 'C08',
    state: 'special',
    note: '세대 수 확인 불가 이벤트만',
    render: () => (
      <C08Timeline data={{ events: detail.events.filter((e) => e.units.v === null) }} asof={ASOF} />
    ),
  },
  {
    chart: 'C09',
    state: 'normal',
    note: 'Market.catalysts (보드 + 확정 타임라인)',
    render: () => <C09Catalyst data={{ catalysts: m.catalysts }} />,
  },
  {
    chart: 'C09',
    state: 'empty',
    note: '0개',
    render: () => <C09Catalyst data={{ catalysts: [] }} />,
  },
  {
    chart: 'C09',
    state: 'special',
    note: 'G3 compact · 위치 미확정',
    render: () => (
      <C09Catalyst
        data={{
          catalysts: m.catalysts
            .filter((x) => !x.location_confirmed || x.stage === '확정')
            .slice(0, 6),
          compact: true,
        }}
      />
    ),
  },
  {
    chart: 'C10',
    state: 'normal',
    note: 'Sensitivity · 순위 불안정',
    render: () => <C10Sensitivity data={{ sensitivity: sensitivity(), names: complexNames() }} />,
  },
  {
    chart: 'C10',
    state: 'empty',
    note: 'null',
    render: () => <C10Sensitivity data={{ sensitivity: null }} />,
  },
  {
    chart: 'C10',
    state: 'special',
    note: '변동 없음 → 전 행 회색',
    render: () => (
      <C10Sensitivity data={{ sensitivity: stableSensitivity(), names: complexNames() }} />
    ),
  },
];

/** 같은 차트·상태가 여럿이면 두 번째부터 testid에 번호를 붙인다(gallery-C01-special-2) */
function testIds(cases: GalleryCase[]): string[] {
  const seen = new Map<string, number>();
  return cases.map((item) => {
    const base = `gallery-${item.chart}-${item.state}`;
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    return n === 1 ? base : `${base}-${n}`;
  });
}

function ThemeSwitch() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      aria-pressed={theme === 'dark'}
      onClick={toggleTheme}
      className="rounded-sm border border-border px-2 py-1 text-sm"
    >
      {`${t('header.theme')}: ${theme === 'dark' ? t('header.themeDark') : t('header.themeLight')}`}
    </button>
  );
}

export function ChartGallery() {
  const ids = testIds(GALLERY_CASES);
  const charts = [...new Set(GALLERY_CASES.map((item) => item.chart))];
  return (
    <div className="mx-auto flex max-w-(--breakpoint-2xl) flex-col gap-6 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">{t('chart.gallery.title')}</h1>
        <p className="text-sm text-muted">{t('chart.gallery.note')}</p>
        <span className="ml-auto">
          <ThemeSwitch />
        </span>
      </header>
      {charts.map((chart) => (
        <section key={chart} aria-label={chart} className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-muted">{chart}</h2>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 2xl:grid-cols-3">
            {GALLERY_CASES.map((item, index) =>
              item.chart === chart ? (
                <div
                  key={ids[index]}
                  data-testid={ids[index]}
                  data-state={item.state}
                  className="flex min-w-0 flex-col gap-1"
                >
                  <p className="text-xs text-muted">{t(`chart.gallery.state.${item.state}`)}</p>
                  {item.render()}
                </div>
              ) : null,
            )}
          </div>
        </section>
      ))}
    </div>
  );
}
