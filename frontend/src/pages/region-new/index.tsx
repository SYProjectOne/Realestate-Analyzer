import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G0 지역 입력 `/regions/new` (D2-5) — WP6a 구현.
 * 검색창(디바운스 → useResolveRegion), 후보 다중 선택 칩, 이름 입력, "분석 시작"(useCreateRegion) → JobProgress.
 */
export function RegionNewPage() {
  return <PageShell title={t('page.G0.title')} />;
}
