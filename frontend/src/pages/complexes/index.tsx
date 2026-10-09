import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G2 단지 리스트 `/complexes` (RA §7-1) — WP6a 구현.
 * FilterBar(URL 쿼리), ComplexTable(TanStack Table + Virtual, 열 선택 저장), CompareTray(2~6) → /compare?ids=,
 * CSV = complexesCsvUrl(같은 쿼리). useComplexes(snapshotId, params).
 */
export function ComplexesPage() {
  return <PageShell title={t('page.G2.title')} />;
}
