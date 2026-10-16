import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router';
import { t } from '@/i18n';
import { GLOSSARY, type NavItem } from './Header';

/** D30-4: 휴대폰 하단 고정 메뉴 3개 — 홈·단지 찾기·용어 사전(모바일 읽기 전용 지원 화면 + 용어, D7) */
export const NAV_MOBILE: NavItem[] = [
  { to: '/', key: 'nav.G1', end: true },
  { to: '/complexes', key: 'nav.G2' },
  GLOSSARY,
];

const ICON_PATHS: Record<string, ReactNode> = {
  '/': (
    <>
      <path d="M3 10.5 12 4l9 6.5" />
      <path d="M5 9.5V20h14V9.5" />
      <path d="M10 20v-5h4v5" />
    </>
  ),
  '/complexes': (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ),
  '/glossary': (
    <>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z" />
      <path d="M4 19.5V21h16" />
    </>
  ),
};

/**
 * 휴대폰(≤768px) 하단 고정 바(D30-4). 메뉴 이동에도 지역·기준일·상황 쿼리가 따라간다(#22). 아이콘은 장식이고 이름은 글자.
 * 바닥 문구(투자 권유 아님 · 상대 비교)는 이 바 바로 위에 붙는다(AppLayout).
 */
export function BottomNav() {
  const location = useLocation();
  return (
    <nav
      aria-label={t('nav.label')}
      data-testid="bottom-nav"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="mx-auto grid max-w-lg grid-cols-3">
        {NAV_MOBILE.map((item) => (
          <li key={item.to}>
            <NavLink
              to={{ pathname: item.to, search: location.search }}
              end={item.end}
              className={({ isActive }) =>
                `flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs focus:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${
                  isActive ? 'font-semibold text-accent-ink' : 'text-muted'
                }`
              }
            >
              <svg
                aria-hidden
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                {ICON_PATHS[item.to]}
              </svg>
              {t(item.key)}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
