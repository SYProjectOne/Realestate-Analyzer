import { t } from '@/i18n';
import { useTheme } from '@/lib/theme';

/** 라이트/다크 전환 버튼(목업 "화면: 밝게 ↔ 어둡게", aria-pressed = 어둡게). 접근성 이름 = "화면: 밝게|어둡게" */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const current = theme === 'dark' ? t('header.themeDark') : t('header.themeLight');
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-pressed={theme === 'dark'}
      className="min-h-9 whitespace-nowrap rounded-[10px] border border-border-strong bg-surface px-3 py-1.5 text-[13px] font-semibold text-fg hover:border-fg-2 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
    >
      {`${t('header.theme')}: ${current}`}
    </button>
  );
}
