import { useHealth } from '@/api/hooks';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t } from '@/i18n';

/**
 * 판정기 장애(미판정 모드) 전역 배너 — RA G7 "degraded 플래그면 전역 배너", runbook "미판정 모드".
 * 근거: GET /health status=degraded 또는 judge=degraded, 또는 현재 기준일 스냅샷 degraded=true.
 */
export function DegradedBanner() {
  const { data: health } = useHealth();
  const { snapshot } = useSnapshot();
  const judgeDown = health?.status === 'degraded' || health?.judge === 'degraded';
  const snapshotDegraded = snapshot?.degraded === true;
  if (!judgeDown && !snapshotDegraded) return null;
  return (
    <div
      role="alert"
      data-testid="degraded-banner"
      className="border-b border-danger bg-surface px-4 py-1.5 text-sm font-medium text-danger"
    >
      {judgeDown ? t('app.degraded') : t('app.degradedSnapshot')}
    </div>
  );
}
