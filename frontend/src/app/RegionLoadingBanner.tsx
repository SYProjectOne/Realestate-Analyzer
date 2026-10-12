import { Link } from 'react-router';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';

/**
 * 지역 첫 적재 상태 안내(계약 .18 F3·D23-4). 서버 `region.status` 를 그대로 따른다(화면이 판단하지 않는다):
 *  - `bootstrapping`: region.bootstrap 잡이 아직 끝나지 않았다 — 청약홈 API 빈 데이터셋이면 판정·발행 없이 30분 뒤 다시
 *    수집하므로(최대 6회) 몇 시간 이어질 수 있다. 발행 리비전이 없어 화면은 '적재 중'
 *  - `failed`: 첫 적재가 실패(재시도 상한 초과 등) — 잡 목록에서 오류 확인
 * 그 밖(ready·resolving)은 아무것도 그리지 않는다.
 */
export function RegionLoadingBanner() {
  const { region } = useActiveRegion();
  const status = region?.status;
  if (!region || (status !== 'bootstrapping' && status !== 'failed')) return null;
  return (
    <div
      role="status"
      data-testid="region-loading-banner"
      data-region-status={status}
      className={`border-b border-border bg-surface px-4 py-1.5 text-sm ${
        status === 'failed' ? 'font-medium text-danger' : 'text-muted'
      }`}
    >
      {status === 'failed' ? t('app.regionFailed') : t('app.regionBootstrapping')}{' '}
      <Link to={{ pathname: '/ops', search: `?region=${String(region.id)}` }} className="underline">
        {t('nav.G7')}
      </Link>
    </div>
  );
}
