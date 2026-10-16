import { useCanWrite } from '@/api/auth';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { usePageContext } from '../_shared';
import { BoundaryList } from './BoundaryList';
import { ChecklistPanel } from './Checklist';
import { ClaimsPanel } from './ClaimsPanel';
import { HumanCheckForm } from './HumanCheckForm';
import { IntakeQueuePanel } from './IntakeQueuePanel';
import { JudgmentStatsPanel } from './JudgmentStatsPanel';
import { OpsMenu } from './OpsMenu';
import { RejudgeQueue } from './RejudgeQueue';
import { OpsSection } from './sections';
import { SharePanel } from './SharePanel';
import { SOURCES_MIN_HEIGHT, SourceStatusTable } from './SourceStatusTable';
import { TodayTiles } from './TodayTiles';

/**
 * G7 데이터·운영 `/ops` (RA §7-1 · R11 목업 Ops.dc.html)
 * 머리 "오늘 확인할 것부터 볼까요?" → '오늘 확인할 것' 타일 4장(서버 수·줄 개수만, D25-3) → 데스크톱은 왼쪽 묶음 메뉴 +
 * 오른쪽 묶음 9개(휴대폰은 메뉴가 위로 쌓여 옆으로 민다): ① 일정·체크리스트(+달력) ② 접수 확인 대기열(#intake-queue)
 * ③ 사람 확인 입력(#human-check) ④ 수집 상태(재시도) ⑤ 작업 대기열 ⑥ 판정기 호출 통계(30일) ⑦ 모순 주장(수정, M8)
 * ⑧ 범위 경계 단지 ⑨ 공유 링크(쓰기 토큰만, M9). 묶음마다 "이게 뭐예요?" 한 줄.
 * 사람 확인 저장 → 접수 배지 즉시 갱신 + 재판정 자동 등록. degraded면 전역 배너(AppLayout).
 */
export function OpsPage() {
  const { regionId, snapshotId, asof, isLoading } = usePageContext();
  const { region } = useActiveRegion();
  const canWrite = useCanWrite();
  const kicker = region
    ? asof
      ? t('page.G7.kicker', { region: region.name, asof })
      : t('page.G7.kickerNoAsof', { region: region.name })
    : null;
  return (
    <PageShell
      title={t('page.G7.title')}
      intro={
        <>
          {/* 지역을 받기 전에도 줄 높이를 잡아 둔다(CLS) */}
          <span className="mb-1 block min-h-5 text-sm text-muted" data-testid="ops-kicker">
            {kicker ?? ''}
          </span>
          {t('page.G7.intro')}
        </>
      }
    >
      <TodayTiles regionId={regionId} snapshotId={snapshotId} asof={asof} enabled={!isLoading} />
      <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <OpsMenu
          regionId={regionId}
          snapshotId={snapshotId}
          enabled={!isLoading}
          showShare={canWrite}
        />
        <div className="flex min-w-0 flex-col gap-6">
          <ChecklistPanel asof={asof} />
          <IntakeQueuePanel regionId={regionId} snapshotId={snapshotId} asof={asof} />
          <HumanCheckForm snapshotId={snapshotId} />
          {/* 지역이 정해진 뒤 한 번만 조회(region_id가 바뀌며 표가 다시 그려지지 않게) */}
          {isLoading ? (
            <OpsSection k="sources" className={SOURCES_MIN_HEIGHT}>
              <p role="status" className="text-sm text-muted">
                {t('app.loading')}
              </p>
            </OpsSection>
          ) : (
            <SourceStatusTable regionId={regionId} asof={asof} />
          )}
          <RejudgeQueue asof={asof} />
          <JudgmentStatsPanel asof={asof} />
          <ClaimsPanel snapshotId={snapshotId} />
          <BoundaryList snapshotId={snapshotId} />
          <SharePanel />
        </div>
      </div>
    </PageShell>
  );
}
