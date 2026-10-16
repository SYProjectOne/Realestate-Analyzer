import { useHealth } from '@/api/hooks';
import { Banner } from '@/components/Banner';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t } from '@/i18n';

/**
 * 판정기 장애(미판정 모드) 전역 띠 — RA G7 "degraded 플래그면 전역 배너", runbook "미판정 모드".
 * 근거: GET /health status=degraded 또는 judge=degraded(SH-2 '판정기를 지금 쓸 수 없어요'), 아니면 현재 기준일 스냅샷
 * degraded=true(SH-3 '이 기준일 자료는 미판정 모드에서 만들어졌어요') — 두 문구는 뜻이 달라 나눈다.
 */
export function DegradedBanner() {
  const { data: health } = useHealth();
  const { snapshot } = useSnapshot();
  const judgeDown = health?.status === 'degraded' || health?.judge === 'degraded';
  const snapshotDegraded = snapshot?.degraded === true;
  if (!judgeDown && !snapshotDegraded) return null;
  return (
    <Banner
      role="alert"
      tone="warn"
      icon={judgeDown}
      data-testid="degraded-banner"
      data-degraded={judgeDown ? 'judge' : 'snapshot'}
    >
      {judgeDown ? t('app.degraded') : t('app.degradedSnapshot')}
    </Banner>
  );
}
