/**
 * D30-3 디자인 토큰: 라이트 = 50-mockup 팔레트, 다크 = 기존 다크 토큰(유지), 글자색은 자기 바탕 위에서 4.5:1 이상.
 * index.css 의 :root / :root.dark 값을 읽어 잰다(색을 바꾸면 이 표가 대비를 다시 확인한다).
 * vitest 는 `css: false` 라 CSS 를 import 하면 빈 문자열 — 파일을 node fs 로 직접 읽는다(앱 tsconfig 에 node 타입이
 * 없어 모듈 이름을 문자열로 만들어 동적 import 한다).
 */
import tailwindConfig from '../../tailwind.config.ts?raw';

const fsModule = 'node:' + 'fs';
const { readFileSync } = (await import(/* @vite-ignore */ fsModule)) as {
  readFileSync: (path: string, encoding: 'utf-8') => string;
};
/** vitest 는 frontend/ 에서 돈다(package.json scripts) */
const cwd = (globalThis as unknown as { process: { cwd: () => string } }).process.cwd();
const css = readFileSync(`${cwd}/src/index.css`, 'utf-8');

type Rgb = [number, number, number];

function block(selector: string): Record<string, Rgb> {
  const start = css.indexOf(`${selector} {`);
  expect(start).toBeGreaterThanOrEqual(0);
  const body = css.slice(start, css.indexOf('}', start));
  const out: Record<string, Rgb> = {};
  for (const m of body.matchAll(/--color-([a-z0-9-]+):\s*(\d+)\s+(\d+)\s+(\d+);/g)) {
    out[m[1] as string] = [Number(m[2]), Number(m[3]), Number(m[4])];
  }
  return out;
}

const LIGHT = block(':root');
const DARK = block(':root.dark');

function lum([r, g, b]: Rgb): number {
  const f = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const hex = (h: string): Rgb => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];

/** [글자 토큰, 바탕 토큰] — 화면에서 실제로 겹치는 짝 */
const TEXT_PAIRS: [string, string][] = [
  ...['fg', 'fg-2', 'muted', 'grayed'].flatMap((fg) =>
    ['bg', 'surface', 'surface-2', 'subtle', 'chip'].map((bg): [string, string] => [fg, bg]),
  ),
  ['accent', 'surface'],
  ['accent', 'bg'],
  ['accent', 'surface-2'],
  ['accent', 'info-soft'],
  ['accent', 'warn-soft'],
  ['accent-fg', 'accent'],
  ['accent-ink', 'accent-soft'],
  ['warn-ink', 'warn-soft'],
  ['warn', 'surface'],
  ['info-ink', 'info-soft'],
  ['est', 'surface'],
  ['est', 'bg'],
  ['est', 'subtle'],
  ['est', 'warn-soft'],
  ['danger', 'surface'],
  ['danger', 'bg'],
  ['danger', 'warn-soft'],
  ['fg', 'mark'],
  ['toast-fg', 'toast'],
  ['fg-2', 'warn-soft'],
  ['muted', 'warn-soft'],
  ['fg-2', 'info-soft'],
  ['bg', 'fg'],
];

describe('D30-3 디자인 토큰', () => {
  it('라이트 값은 목업 팔레트(배경 #F3F5F7 · 카드 #FFFFFF · 주색 #2350D8 · 주의 #A3470A/#FFF1E6)', () => {
    expect(LIGHT.bg).toEqual(hex('#F3F5F7'));
    expect(LIGHT.surface).toEqual(hex('#FFFFFF'));
    expect(LIGHT.accent).toEqual(hex('#2350D8'));
    expect(LIGHT.warn).toEqual(hex('#A3470A'));
    expect(LIGHT['warn-soft']).toEqual(hex('#FFF1E6'));
    expect(LIGHT.fg).toEqual(hex('#14181F'));
    expect(LIGHT.border).toEqual(hex('#E3E7EC'));
    expect(LIGHT['accent-soft']).toEqual(hex('#E8EEFF'));
  });

  it('다크 모드는 유지 — 기존 다크 토큰(바탕 #0D1117 · 카드 #161B22 · 글자 #E6EDF3 · 강조 #60A5FA)', () => {
    expect(DARK.bg).toEqual(hex('#0D1117'));
    expect(DARK.surface).toEqual(hex('#161B22'));
    expect(DARK.fg).toEqual(hex('#E6EDF3'));
    expect(DARK.accent).toEqual(hex('#60A5FA'));
  });

  it('라이트·다크가 같은 토큰 이름을 모두 정의하고, tailwind.config.ts 가 모두 참조한다', () => {
    expect(Object.keys(DARK).sort()).toEqual(Object.keys(LIGHT).sort());
    for (const name of Object.keys(LIGHT)) {
      expect({ name, inTailwind: tailwindConfig.includes(`'${name}'`) }).toEqual({
        name,
        inTailwind: true,
      });
    }
  });

  it.each([
    ['light', LIGHT],
    ['dark', DARK],
  ] as const)('%s: 글자색 토큰은 자기 바탕 위에서 4.5:1 이상', (_name, tokens) => {
    const low = TEXT_PAIRS.map(([fg, bg]) => {
      const a = tokens[fg];
      const b = tokens[bg];
      expect({ fg, bg, defined: !!a && !!b }).toEqual({ fg, bg, defined: true });
      return { pair: `${fg}/${bg}`, ratio: Math.round(contrast(a as Rgb, b as Rgb) * 100) / 100 };
    }).filter((x) => x.ratio < 4.5);
    expect(low).toEqual([]);
  });

  it('대비 계산기는 WCAG 공식(흰/검 21:1)', () => {
    expect(Math.round(contrast([255, 255, 255], [0, 0, 0]))).toBe(21);
  });
});
