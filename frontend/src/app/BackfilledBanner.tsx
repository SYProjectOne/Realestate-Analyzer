import { useSnapshot } from '@/hooks/useSnapshot';
import { t } from '@/i18n';
import { kstDay } from '@/lib/format';

/**
 * 계약 .14 F1(D17-2): 보고 있는 발행 리비전 저장본에 업그레이드 backfill 이 **새로 계산해 채운** 값이 있으면(`backfilled_at`)
 * "업그레이드 때 다시 계산한 값 포함(발행 순간 값이 아닐 수 있음)" 안내. 날짜는 KST(D16-5). 키가 없으면 아무것도 없다.
 */
export function BackfilledBanner() {
  const { snapshot } = useSnapshot();
  const at = snapshot?.backfilled_at;
  if (!at) return null;
  return (
    <p
      role="note"
      data-testid="backfilled-banner"
      className="border-b border-border bg-surface px-4 py-1 text-xs text-muted"
    >
      {t('app.backfilled', { date: kstDay(at) ?? at })}
    </p>
  );
}
