import { Link } from 'react-router';
import { t } from '@/i18n';

/**
 * 화면 머리 위 현재 위치 줄(목업 RegionNew·LivingAreas: "홈 › 새 지역 추가", "홈 › 인천 › 생활권 나누기").
 * 지역 이름은 서버 값만 받는다. R11-SETUP(G0·G0-2) 공용.
 */
export function Crumbs({ items }: { items: readonly string[] }) {
  return (
    <nav aria-label={t('page.G0.crumbLabel')} className="text-sm text-muted">
      <Link to="/" className="text-accent hover:underline">
        {t('page.G0.crumbHome')}
      </Link>
      {items.map((item, i) => (
        <span key={`${i}-${item}`}>
          <span aria-hidden className="mx-1.5">
            ›
          </span>
          {item}
        </span>
      ))}
    </nav>
  );
}
