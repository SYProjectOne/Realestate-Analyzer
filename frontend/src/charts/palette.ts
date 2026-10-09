import { useMemo } from 'react';
import { useTheme } from '@/lib/theme';
import type { ChartPalette } from './types';

/** Okabe-Ito 계열 — 색각 이상에서도 구분되는 범주 색. 라이트·다크 공용 */
const CATEGORICAL = [
  '#0072B2',
  '#E69F00',
  '#009E73',
  '#CC79A7',
  '#56B4E9',
  '#D55E00',
  '#F0E442',
  '#999999',
];

/** buildOption 기본값(테스트·SSR). index.css 라이트 토큰과 같은 값 */
export const DEFAULT_PALETTE: ChartPalette = {
  fg: 'rgb(17 24 39)',
  muted: 'rgb(75 85 99)',
  border: 'rgb(209 213 219)',
  bg: 'rgb(255 255 255)',
  strong: 'rgb(29 78 216)',
  grayed: 'rgb(156 163 175)',
  categorical: CATEGORICAL,
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
      categorical: CATEGORICAL,
    };
    // theme이 바뀌면 html.dark 토글 후 토큰을 다시 읽는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}

/** buildOption들이 공유하는 축·텍스트 기본값 */
export function baseOption(palette: ChartPalette) {
  return {
    backgroundColor: 'transparent',
    textStyle: { color: palette.fg },
    aria: { enabled: true },
    animation: false,
  } as const;
}

/** 축 공통 스타일(라이트/다크 토큰): 축선·격자 = border, 축 라벨 = muted */
export function axisStyle(palette: ChartPalette) {
  return {
    axisLine: { lineStyle: { color: palette.border } },
    axisTick: { lineStyle: { color: palette.border } },
    axisLabel: { color: palette.muted },
    splitLine: { lineStyle: { color: palette.border } },
    nameTextStyle: { color: palette.muted },
  } as const;
}

/** 툴팁 바탕·글자색을 테마 토큰으로 */
export function tooltipStyle(palette: ChartPalette) {
  return {
    backgroundColor: palette.bg,
    borderColor: palette.border,
    textStyle: { color: palette.fg },
    confine: true,
  } as const;
}

/** 범례 — 계열은 색만으로 구분하지 않는다(범례 텍스트 병기) */
export function legendStyle(palette: ChartPalette) {
  return { bottom: 0, textStyle: { color: palette.fg }, inactiveColor: palette.grayed } as const;
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
