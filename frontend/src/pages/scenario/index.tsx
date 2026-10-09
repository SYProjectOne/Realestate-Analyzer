import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G5 시나리오 `/scenario` (RA §7-1) — WP6a 구현.
 * ScenarioForm(10 필드, zod), WeightPreview(합 1), RequirementPreview, RunButton(캐시 히트 → useCreateJob),
 * JobProgress(2초 폴링), DiffTable, C7, C10. escaped → 상단 배너 + 질문 텍스트.
 */
export function ScenarioPage() {
  return <PageShell title={t('page.G5.title')} />;
}
