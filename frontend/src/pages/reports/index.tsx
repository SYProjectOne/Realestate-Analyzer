import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G8 보고서 `/reports` (RA §7-1 + D4) — WP6a 구현.
 * SnapshotPairPicker, FormatSelect(html|pdf), GenerateButton → JobProgress, ReportList, SnapshotDiffTable.
 * useCreateReport, reportDownloadUrl, useChanges. contradicted claim 있으면 버튼 비활성 + 사유.
 */
export function ReportsPage() {
  return <PageShell title={t('page.G8.title')} />;
}
