import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G0-2 생활권 편집 `/regions/:id/living-areas` (D2-5) — WP6a 구현.
 * 생활권 카드 + 법정동 이동, 추가·이름 변경·삭제(빈 경우만), 세대수(FactCell), 저장 → useUpdateLivingAreas(422 표시).
 */
export function LivingAreasPage() {
  return <PageShell title={t('page.G0_2.title')} />;
}
