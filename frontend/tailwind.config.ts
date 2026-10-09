import type { Config } from 'tailwindcss';

// 색은 전부 CSS 변수 토큰(src/index.css)을 거친다. 라이트/다크는 html.dark 클래스로 전환.
const token = (name: string) => `rgb(var(--color-${name}) / <alpha-value>)`;

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        surface: token('surface'),
        fg: token('fg'),
        muted: token('muted'),
        border: token('border'),
        accent: token('accent'),
        'accent-fg': token('accent-fg'),
        danger: token('danger'),
        grayed: token('grayed'),
      },
      screens: {
        // D7: 모바일 = 768px 이하
        mobile: { max: '768px' },
      },
    },
  },
  plugins: [],
} satisfies Config;
