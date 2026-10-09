import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G4 비교 `/compare?ids=` (RA §7-1) — WP6a 구현.
 * CompareGrid, C6 가로, C1 overlay, C2 나란히, TermsTable, DecisionPanel(C7·MismatchBadge·TieBadge), C10.
 * useCompare(snapshotId, ids, scenarioId), useSensitivity. ids 2~6 검사.
 */
export function ComparePage() {
  return <PageShell title={t('page.G4.title')} />;
}
