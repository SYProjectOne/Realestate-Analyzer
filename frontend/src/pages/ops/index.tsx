import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { Section, usePageContext } from '../_shared';
import { BoundaryList } from './BoundaryList';
import { ChecklistPanel } from './Checklist';
import { ClaimsPanel } from './ClaimsPanel';
import { HumanCheckForm } from './HumanCheckForm';
import { JudgmentStatsPanel } from './JudgmentStatsPanel';
import { RejudgeQueue } from './RejudgeQueue';
import { SharePanel } from './SharePanel';
import { SOURCES_MIN_HEIGHT, SourceStatusTable } from './SourceStatusTable';

/**
 * G7 데이터·운영 `/ops` (RA §7-1)
 * SourceStatusTable(재시도) · RejudgeQueue(job_run) · Checklist+Calendar · JudgmentStats(30일) · HumanCheckForm
 * · ClaimsPanel(contradicted 주장 수정, M8) · SharePanel(읽기 전용 공유 링크, M9 — 쓰기 토큰만)
 * · BoundaryList(범위 경계 단지, minor 35).
 * 사람 확인 저장 → 접수 배지 즉시 갱신 + 재판정 잡 제안 토스트. degraded면 전역 배너(AppLayout).
 */
export function OpsPage() {
  const { regionId, snapshotId, asof, isLoading } = usePageContext();
  return (
    <PageShell title={t('page.G7.title')}>
      <HumanCheckForm snapshotId={snapshotId} />
      {/* 지역이 정해진 뒤 한 번만 조회(region_id가 바뀌며 표가 다시 그려지지 않게) */}
      {isLoading ? (
        <Section title={t('page.G7.sources')} className={SOURCES_MIN_HEIGHT}>
          <p role="status" className="text-sm text-muted">
            {t('app.loading')}
          </p>
        </Section>
      ) : (
        <SourceStatusTable regionId={regionId} asof={asof} />
      )}
      <RejudgeQueue asof={asof} />
      <ChecklistPanel asof={asof} />
      <JudgmentStatsPanel asof={asof} />
      {/* 새 패널(M8·minor 35·M9)은 아래 — 위 표가 늦게 커질 때 화면 안 요소가 밀리지 않게(CLS) */}
      <ClaimsPanel snapshotId={snapshotId} />
      <BoundaryList snapshotId={snapshotId} />
      <SharePanel />
    </PageShell>
  );
}
