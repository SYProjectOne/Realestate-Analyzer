import { t } from '@/i18n';
import { useTheme } from '@/lib/theme';

/** 라이트/다크 전환 버튼. 접근성 이름 = "테마: 라이트|다크" */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const current = theme === 'dark' ? t('header.themeDark') : t('header.themeLight');
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-pressed={theme === 'dark'}
      className="rounded-sm border border-border px-2 py-1 text-sm"
    >
      {`${t('header.theme')}: ${current}`}
    </button>
  );
}
