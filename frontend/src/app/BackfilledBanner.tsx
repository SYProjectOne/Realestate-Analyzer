import { Banner } from '@/components/Banner';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t } from '@/i18n';
import { kstDay } from '@/lib/format';

/**
 * 계약 .14 F1(D17-2): 보고 있는 발행 리비전 저장본에 업그레이드 backfill 이 **새로 계산해 채운** 값이 있으면(`backfilled_at`)
 * "다시 계산한 값이 들어 있어요 — 발행 순간 값과 다를 수 있음"(SH-4) 안내. 날짜는 KST(D16-5). 키가 없으면 아무것도 없다.
 */
export function BackfilledBanner() {
  const { snapshot } = useSnapshot();
  const at = snapshot?.backfilled_at;
  if (!at) return null;
  return (
    <Banner role="note" tone="note" data-testid="backfilled-banner">
      {t('app.backfilled', { date: kstDay(at) ?? at })}
    </Banner>
  );
}
