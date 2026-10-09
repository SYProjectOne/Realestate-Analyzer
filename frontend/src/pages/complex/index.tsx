import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G3 단지 상세 `/complexes/:id` (RA §7-1) — WP6a 구현.
 * ComplexHeader + 탭 8개(URL 해시): PriceTable, PaymentTerms, C8, C1, C2, CatalystList(+C9), ProvenanceTab, JudgmentLogTab.
 * useComplexDetail(id, snapshotId). review/escaped 봉투는 회색 + "미해결".
 */
export function ComplexPage() {
  return <PageShell title={t('page.G3.title')} />;
}
