import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { usePageContext } from '../_shared';
import { ChecklistPanel } from './Checklist';
import { ClaimsPanel } from './ClaimsPanel';
import { HumanCheckForm } from './HumanCheckForm';
import { JudgmentStatsPanel } from './JudgmentStatsPanel';
import { RejudgeQueue } from './RejudgeQueue';
import { SourceStatusTable } from './SourceStatusTable';

/**
 * G7 데이터·운영 `/ops` (RA §7-1)
 * SourceStatusTable(재시도) · RejudgeQueue(job_run) · Checklist+Calendar · JudgmentStats(30일) · HumanCheckForm
 * · ClaimsPanel(contradicted 주장 수정, M8).
 * 사람 확인 저장 → 접수 배지 즉시 갱신 + 재판정 잡 제안 토스트. degraded면 전역 배너(AppLayout).
 */
export function OpsPage() {
  const { regionId, snapshotId, asof, isLoading } = usePageContext();
  return (
    <PageShell title={t('page.G7.title')}>
      <HumanCheckForm snapshotId={snapshotId} />
      {/* 지역이 정해진 뒤 한 번만 조회(region_id가 바뀌며 표가 다시 그려지지 않게) */}
      {isLoading ? null : <SourceStatusTable regionId={regionId} asof={asof} />}
      <ClaimsPanel snapshotId={snapshotId} />
      <RejudgeQueue asof={asof} />
      <ChecklistPanel asof={asof} />
      <JudgmentStatsPanel asof={asof} />
    </PageShell>
  );
}
