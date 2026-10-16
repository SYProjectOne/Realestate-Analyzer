import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { useCreateJob, useDashboard, useScenarios } from '@/api/hooks';
import type { Dashboard } from '@/api/types';
import { Banner, JobProgress, ProvenanceLegend, StatusPill } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';
import { enumText, NoSnapshot, QueryState, usePageContext } from '../_shared';
import { ChangeFeed } from './ChangeFeed';
import { ApplySoonBand, Hero, OpenNowCards } from './Hero';
import { Ranking } from './Ranking';
import { RegionMarket } from './RegionMarket';
import { UpcomingCard } from './Schedule';

/**
 * G1 홈 `/` (RA §7-1, R11 Main 보드 · D30): 알림 띠(다시 판정 SH-7 · 근처 새 아파트 실적 없음 SH-8) → 첫 줄
 * "지금 청약을 넣을 수 있는 단지는 N곳이에요"(N = 서버 KPI) → 접수 가능 카드 → 곧 청약 접수 띠 → 다가오는 일정(4주) +
 * {지역} 시장 한눈에(C05) → 점수 순서(C06 줄 막대) → 최근에 바뀐 것 → 바닥 글(라벨 뜻).
 * 상황 토글(헤더, URL ?scenario=) → dashboard 재조회. 지역이 하나도 없으면 /regions/new 로 보낸다(D2-5).
 * D10-1: 범위·순위·총점은 스냅샷 저장값 — rejudge_needed 면 '다시 판정' 띠 + rejudge 잡 제안.
 * N-M3: benchmark_absence 면 '근처 새 아파트 실적 없음(<reason>)'(종합 미계산의 이유, D9-2).
 */
export function DashboardPage() {
  const { isEmpty } = useActiveRegion();
  const { snapshotId, scenarioKey, isLoading } = usePageContext();
  const query = useDashboard(snapshotId, scenarioKey);

  if (isEmpty) return <Navigate to="/regions/new" replace />;

  const plainTitle = (
    <h1 className="text-2xl font-bold leading-tight tracking-tight text-fg sm:text-[28px]">
      {t('page.G1.title')}
    </h1>
  );
  return (
    <section className="flex flex-col gap-7">
      {/* 데이터 전(불러오는 중·오류·기준일 없음)에는 화면 이름 '홈'이 h1, 데이터가 오면 첫 줄 문장이 h1 */}
      {query.data ? null : plainTitle}
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>
          {(dashboard) => <DashboardBody data={dashboard} snapshotId={snapshotId} />}
        </QueryState>
      )}
    </section>
  );
}

function DashboardBody({ data, snapshotId }: { data: Dashboard; snapshotId: string | null }) {
  const asof = data.asof_date;
  const { region } = useActiveRegion();
  const { scenarioKey } = usePageContext();
  const regionName = region?.name ?? null;
  // +10% 목표 시점 = 이 상황의 p10_horizon(상황 C 는 기준일+5년 — 고정 문구로 쓰지 않는다)
  const { data: scenarios = [] } = useScenarios();
  const horizon = scenarios.find((s) => s.id === data.scenario_id)?.policy.p10_horizon ?? null;
  const target = horizon ? enumText('chart.C01.horizon', horizon) : null;
  return (
    <>
      {data.rejudge_needed ? <RejudgeBanner data={data} /> : null}
      {data.benchmark_absence ? (
        <Banner
          tone="note"
          role="note"
          data-testid="benchmark-absence"
          data-code={data.benchmark_absence.code}
        >
          <StatusPill tone="warn" wrap className="mr-2 align-middle">
            {t('page.G1.benchmarkAbsentBadge', { reason: data.benchmark_absence.reason })}
          </StatusPill>
          {t('page.G1.benchmarkAbsentHint')}
        </Banner>
      ) : null}
      <Hero data={data} regionName={regionName} />
      <OpenNowCards snapshotId={snapshotId} scenarioKey={scenarioKey} asof={asof} />
      <ApplySoonBand asof={asof} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <UpcomingCard asof={asof} />
        <RegionMarket data={data} regionName={regionName} />
      </div>
      <Ranking data={data} target={target} />
      <ChangeFeed changes={data.changes} asof={asof} />
      <footer className="flex flex-col gap-2 border-t border-border pt-4 text-[13px] text-muted">
        <p>{t('page.G1.footNote')}</p>
        <ProvenanceLegend />
      </footer>
    </>
  );
}

/**
 * D10-1 전역 안내(Shell SH-7): 저장된 범위 ≠ 현재 계산 범위 → '다시 판정이 필요해요' + rejudge 잡 제안(쓰기 토큰만).
 * 대상 = rejudge_needed 인 TOP 5 단지(없으면 null = 스냅샷 판정 대상 전부). 저장값은 그대로 보인다.
 * 등록 뒤 작업 진행(JobProgress), 끝나면 그 기준일 화면을 새로 부른다(고침 HM-17 #22). 휴대폰 읽기 전용이면 버튼 숨김(data-write).
 */
function RejudgeBanner({ data }: { data: Dashboard }) {
  const qc = useQueryClient();
  const canWrite = useCanWrite();
  const createJob = useCreateJob();
  const [jobId, setJobId] = useState<number | null>(null);
  const flagged = data.top5.filter((row) => row.rejudge_needed).map((row) => row.complex_id);
  const run = () => {
    createJob.mutate(
      {
        job_name: 'rejudge',
        payload: {
          snapshot_id: data.snapshot_id,
          scenario_id: null,
          complex_ids: flagged.length > 0 ? flagged : null,
          reason: t('page.G1.rejudgeReason'),
        },
      },
      { onSuccess: (job) => setJobId(job.id) },
    );
  };
  return (
    <div className="flex flex-col gap-2" data-testid="rejudge-notice" role="note">
      <Banner
        tone="info"
        title={t('page.G1.rejudgeTitle')}
        actions={
          <button
            type="button"
            data-write
            onClick={run}
            disabled={!canWrite || createJob.isPending || jobId !== null}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className="min-h-10 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
          >
            {t('page.G1.rejudgeRun')}
          </button>
        }
      >
        {t('page.G1.rejudgeNotice')}{' '}
        <StatusPill tone="outline" wrap className="align-middle">
          {t('page.G1.rejudgeStored')}
        </StatusPill>
      </Banner>
      {createJob.error ? (
        <p role="alert" className="rounded-lg bg-warn-soft px-3 py-2 text-sm text-warn-ink">
          {t('page.common.loadError', { detail: createJob.error.message })}
        </p>
      ) : null}
      {jobId !== null ? (
        <JobProgress
          jobId={jobId}
          onDone={() =>
            void qc.invalidateQueries({ queryKey: ['snapshots', String(data.snapshot_id)] })
          }
        />
      ) : null}
    </div>
  );
}
