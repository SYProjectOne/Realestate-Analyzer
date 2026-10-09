import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G6 지역 시장 `/market` (RA §7-1) — WP6a 구현.
 * C3, C4, C5, C9 보드+타임라인, RegulationCard, LivingAreaCompare. useMarket(snapshotId). 생활권 필터.
 */
export function MarketPage() {
  return <PageShell title={t('page.G6.title')} />;
}
