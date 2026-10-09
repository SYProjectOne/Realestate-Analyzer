import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';

/**
 * G7 데이터·운영 `/ops` (RA §7-1) — WP6a 구현.
 * SourceStatusTable, RejudgeQueue, Checklist+Calendar, JudgmentStats, HumanCheckForm, "범위 경계" 목록(D2-6).
 * useOpsSources, useOpsJudgments, useChecklist, useCreateHumanCheck. degraded면 전역 배너.
 */
export function OpsPage() {
  return <PageShell title={t('page.G7.title')} />;
}
