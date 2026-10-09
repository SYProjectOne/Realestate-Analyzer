import { Navigate } from 'react-router';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G1 홈 대시보드 `/` (RA §7-1) — WP6a 구현.
 * KpiTiles(5), Top5Cards(ScoreRow), ChangeFeed, C5 작게, C6 — useDashboard(snapshotId, scenarioId), useChanges.
 * 지역이 하나도 없으면 /regions/new 로 보낸다(D2-5).
 */
export function DashboardPage() {
  const { isEmpty } = useActiveRegion();
  if (isEmpty) return <Navigate to="/regions/new" replace />;
  return <PageShell title={t('page.G1.title')} />;
}
