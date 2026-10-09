import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { usePageContext } from '../_shared';
import { ChecklistPanel } from './Checklist';
import { HumanCheckForm } from './HumanCheckForm';
import { JudgmentStatsPanel } from './JudgmentStatsPanel';
import { RejudgeQueue } from './RejudgeQueue';
import { SourceStatusTable } from './SourceStatusTable';

/**
 * G7 데이터·운영 `/ops` (RA §7-1)
 * SourceStatusTable(재시도) · RejudgeQueue(job_run) · Checklist+Calendar · JudgmentStats(30일) · HumanCheckForm.
 * 사람 확인 저장 → 접수 배지 즉시 갱신 + 재판정 잡 제안 토스트. degraded면 전역 배너(AppLayout).
 */
export function OpsPage() {
  const { regionId, snapshotId, asof } = usePageContext();
  return (
    <PageShell title={t('page.G7.title')}>
      <HumanCheckForm snapshotId={snapshotId} />
      <SourceStatusTable regionId={regionId} asof={asof} />
      <RejudgeQueue asof={asof} />
      <ChecklistPanel asof={asof} />
      <JudgmentStatsPanel asof={asof} />
    </PageShell>
  );
}
