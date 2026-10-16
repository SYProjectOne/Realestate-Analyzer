import { useMemo } from 'react';
import { useTheme, type Theme } from '@/lib/theme';
import type { ChartPalette } from './types';

/**
 * 계열 색(목업 팔레트 — 파랑·주황이 먼저, 밝기가 서로 다르다). 순서 고정, 돌려 쓰지 않는다(계열은 단지·생활권 순서를 따른다).
 * 라이트·다크를 따로 골라 dataviz 검증기(scripts/validate_palette.js: 밝기 띠·채도·색각 이상 ΔE·대비)를 통과시켰다:
 *   라이트(바탕 #FFFFFF) / 다크(카드 #161B22) 모두 ALL CHECKS PASS (2026-10-16, R11-CHARTS).
 * 색만으로 뜻을 전하지 않는다 — 범례 글자·마커 모양·표로 보기가 함께 간다.
 */
export const CATEGORICAL_LIGHT = ['#2350D8', '#D97A1E', '#008C82', '#8E5CC9', '#D4508A', '#6E7F1A'];
export const CATEGORICAL_DARK = ['#4F8EF7', '#D9782A', '#14A89A', '#9670E0', '#E0609E', '#8A9A2E'];

/** 테마별 고정 색(CSS 토큰에 없는 차트 전용 값). 목업 보드 값(Compare·Market·Shell §11) */
const FIXED: Record<
  Theme,
  Omit<ChartPalette, 'fg' | 'muted' | 'border' | 'bg' | 'strong' | 'grayed'>
> = {
  light: {
    categorical: CATEGORICAL_LIGHT,
    secondary: CATEGORICAL_LIGHT[1]!,
    strongSoft: '#9DB4F2',
    rest: '#B8C0CC',
    grid: '#EEF1F4',
    band: 'rgba(217, 122, 30, 0.12)',
  },
  dark: {
    categorical: CATEGORICAL_DARK,
    secondary: CATEGORICAL_DARK[1]!,
    strongSoft: '#3B5C99',
    rest: '#4B5563',
    grid: '#252C36',
    band: 'rgba(217, 120, 42, 0.20)',
  },
};

/** buildOption 기본값(테스트·SSR). index.css 라이트 토큰과 같은 값 */
export const DEFAULT_PALETTE: ChartPalette = {
  fg: 'rgb(17 24 39)',
  muted: 'rgb(75 85 99)',
  border: 'rgb(209 213 219)',
  bg: 'rgb(255 255 255)',
  strong: 'rgb(29 78 216)',
  grayed: 'rgb(156 163 175)',
  ...FIXED.light,
};

function readToken(style: CSSStyleDeclaration, name: string, fallback: string): string {
  const raw = style.getPropertyValue(`--color-${name}`).trim();
  return raw ? `rgb(${raw})` : fallback;
}

/** 현재 테마의 CSS 토큰을 읽어 차트 팔레트를 만든다. 테마가 바뀌면 다시 계산. */
export function useChartPalette(): ChartPalette {
  const { theme } = useTheme();
  return useMemo(() => {
    if (typeof window === 'undefined') return DEFAULT_PALETTE;
    const style = window.getComputedStyle(document.documentElement);
    return {
      fg: readToken(style, 'fg', DEFAULT_PALETTE.fg),
      muted: readToken(style, 'muted', DEFAULT_PALETTE.muted),
      border: readToken(style, 'border', DEFAULT_PALETTE.border),
      bg: readToken(style, 'surface', DEFAULT_PALETTE.bg),
      strong: readToken(style, 'accent', DEFAULT_PALETTE.strong),
      grayed: readToken(style, 'grayed', DEFAULT_PALETTE.grayed),
      ...FIXED[theme],
    };
    // theme이 바뀌면 html.dark 토글 후 토큰을 다시 읽는다
  }, [theme]);
}

/** 계열 색 i번째(범위를 넘으면 마지막 색 — 6개를 넘는 계열은 '나머지'로 묶거나 표로 본다) */
export function seriesColor(palette: ChartPalette, index: number): string {
  const list = palette.categorical;
  return list[Math.min(index, list.length - 1)] ?? palette.strong;
}

/** buildOption들이 공유하는 축·텍스트 기본값 */
export function baseOption(palette: ChartPalette) {
  return {
    backgroundColor: 'transparent',
    textStyle: { color: palette.fg, fontSize: 12 },
    aria: { enabled: true },
    animation: false,
  } as const;
}

/**
 * 축 공통 스타일(라이트/다크 토큰): 축선 = border, 눈금 표시(바깥쪽 4px), 격자 = 옅은 grid, 축 라벨 = muted.
 * 축 이름(name)은 쉬운 말 + 단위(ko.json `chart.axis.*`)만 쓴다.
 */
export function axisStyle(palette: ChartPalette) {
  return {
    axisLine: { show: true, lineStyle: { color: palette.border } },
    axisTick: { show: true, length: 4, lineStyle: { color: palette.border } },
    axisLabel: { color: palette.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: palette.grid } },
    nameTextStyle: { color: palette.muted, fontSize: 11 },
  } as const;
}

/** 툴팁 바탕·글자색을 테마 토큰으로 */
export function tooltipStyle(palette: ChartPalette) {
  return {
    backgroundColor: palette.bg,
    borderColor: palette.border,
    textStyle: { color: palette.fg, fontSize: 12 },
    extraCssText: 'border-radius:8px;box-shadow:0 6px 18px rgba(20,24,31,0.16);',
    confine: true,
  } as const;
}

/**
 * 범례 — ECharts 범례는 그리지 않는다(show:false). 범례는 차트 **위**에 HTML(ChartLegend)로 그린다:
 * 줄바꿈이 자유로워 축 라벨과 겹치지 않는다(C04 겹침 결함). `data`는 계열 이름 목록으로 남겨 둔다.
 */
export function legendStyle(palette: ChartPalette) {
  return {
    show: false,
    top: 0,
    textStyle: { color: palette.fg },
    inactiveColor: palette.grayed,
  } as const;
}

/** null 성분·미판정 막대의 빗금(decal) — 색이 아니라 무늬로 구분 */
export function hatchDecal(palette: ChartPalette) {
  return {
    symbol: 'rect',
    color: palette.bg,
    dashArrayX: [1, 0],
    dashArrayY: [2, 4],
    rotation: Math.PI / 4,
  };
}
