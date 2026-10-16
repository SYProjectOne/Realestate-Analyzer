import type { Config } from 'tailwindcss';

// 색은 전부 CSS 변수 토큰(src/index.css)을 거친다. 라이트/다크는 html.dark 클래스로 전환.
const token = (name: string) => `rgb(var(--color-${name}) / <alpha-value>)`;

/** 토큰 이름(src/index.css :root 의 --color-*). tokens.test.ts 가 index.css 와 같은지 본다. */
export const COLOR_TOKENS = [
  'bg',
  'surface',
  'surface-2',
  'subtle',
  'chip',
  'fg',
  'fg-2',
  'muted',
  'grayed',
  'border',
  'border-strong',
  'accent',
  'accent-fg',
  'accent-soft',
  'accent-ink',
  'warn',
  'warn-soft',
  'warn-ink',
  'warn-border',
  'info-soft',
  'info-ink',
  'info-border',
  'est',
  'est-border',
  'danger',
  'mark',
  'toast',
  'toast-fg',
  'overlay',
] as const;

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: Object.fromEntries(COLOR_TOKENS.map((name) => [name, token(name)])),
      fontFamily: {
        // D30-3: IBM Plex Sans KR(자가 호스팅) → 시스템 한글 글꼴
        sans: [
          "'IBM Plex Sans KR'",
          "'Apple SD Gothic Neo'",
          "'Malgun Gothic'",
          'system-ui',
          '-apple-system',
          "'Segoe UI'",
          'sans-serif',
        ],
      },
      screens: {
        // D7: 모바일 = 768px 이하
        mobile: { max: '768px' },
      },
    },
  },
  plugins: [],
} satisfies Config;
