import { useQueryClient } from '@tanstack/react-query';
import { useState, type MouseEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { useCreateJob, useDashboard } from '@/api/hooks';
import type { ChangeEvent, Dashboard, ScoreRow } from '@/api/types';
import { C05Unsold, C06ScoreBreakdown } from '@/charts';
import {
  Badge,
  EmptyState,
  FactCell,
  IntakeBadge,
  JobProgress,
  MetaText,
  MetaValue,
  TieBadge,
  UnstableBadge,
} from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatDate } from '@/lib/format';
import {
  changeEntityText,
  changeFieldText,
  changeValueText,
  enumText,
  JudgeScopeBadge,
  NoSnapshot,
  QueryState,
  RejudgeNeededBadge,
  Section,
  useGlobalSearch,
  usePageContext,
} from '../_shared';

/**
 * G1 홈 대시보드 `/` (RA §7-1) — KpiTiles(5), Top5Cards, ChangeFeed, C5 작게, C6.
 * 상황 토글(헤더, URL ?scenario=) → dashboard 재조회. 카드 클릭 → G3, 피드 항목 → G3 해당 탭.
 * 지역이 하나도 없으면 /regions/new 로 보낸다(D2-5).
 * D10-1: 범위·순위·총점은 스냅샷 저장값 — rejudge_needed 면 '재판정 필요' 배지·안내 + rejudge 잡 제안.
 * N-M3: benchmark_absence 면 '벤치마크 없음(<reason>)'(종합 미계산의 이유, D9-2).
 * 계약 .15: 피드의 대상·필드 이름은 ko.json(`changeEntity`·`changeField`), 지역 첫 적재(`first_load`, F7)는 요약 문장 한 줄,
 * 트랙 A 공고 예정 후보(`track`)·후보와 청약홈 공고 합침(`applyhome_id`, F5)은 그 이름으로.
 */
export function DashboardPage() {
  const { isEmpty } = useActiveRegion();
  const { snapshotId, scenarioKey, isLoading } = usePageContext();
  const query = useDashboard(snapshotId, scenarioKey);

  if (isEmpty) return <Navigate to="/regions/new" replace />;

  return (
    <PageShell title={t('page.G1.title')}>
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>{(dashboard) => <DashboardBody data={dashboard} />}</QueryState>
      )}
    </PageShell>
  );
}

function DashboardBody({ data }: { data: Dashboard }) {
  const asof = data.asof_date;
  const top = data.top5.filter((row) => row.rank === null || row.rank <= 5);
  return (
    <div className="flex flex-col gap-4">
      {data.rejudge_needed ? <RejudgeNotice data={data} /> : null}
      {data.benchmark_absence ? (
        <p
          role="note"
          data-testid="benchmark-absence"
          data-code={data.benchmark_absence.code}
          className="flex flex-wrap items-center gap-2 rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        >
          <Badge tone="muted">
            {t('page.common.benchmarkAbsent', { reason: data.benchmark_absence.reason })}
          </Badge>
          <span className="text-xs text-muted">{t('page.G1.benchmarkAbsentHint')}</span>
        </p>
      ) : null}
      <KpiTiles data={data} />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Section
          title={t('page.G1.top5')}
          actions={
            <span className="text-xs text-muted">
              {t('page.G1.top5Scenario', { name: data.scenario_name })}
            </span>
          }
        >
          <ul aria-label={t('page.G1.top5')} className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {top.map((row) => (
              <Top5Card key={row.complex_id} row={row} asof={asof} />
            ))}
          </ul>
        </Section>
        <ChangeFeed changes={data.changes} asof={asof} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <C06ScoreBreakdown data={{ rows: top, weights: data.weights, orientation: 'vertical' }} />
        <C05Unsold data={{ unsold: data.unsold_series }} height={200} />
      </div>
    </div>
  );
}

/**
 * D10-1 전역 안내: 저장된 범위 ≠ 현재 계산 범위 → '재판정 필요' + rejudge 잡 제안(쓰기 토큰만).
 * 대상 = rejudge_needed 인 TOP 5 단지(없으면 null = 스냅샷 판정 대상 전부). 저장값은 그대로 보인다.
 */
function RejudgeNotice({ data }: { data: Dashboard }) {
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
    <div
      role="note"
      data-testid="rejudge-notice"
      className="flex flex-col gap-2 rounded-sm border border-border bg-surface px-3 py-2 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span>{t('page.G1.rejudgeNotice')}</span>
        <button
          type="button"
          data-write
          onClick={run}
          disabled={!canWrite || createJob.isPending || jobId !== null}
          title={canWrite ? undefined : t('auth.readOnlyHint')}
          className="rounded-sm bg-accent px-3 py-1 text-sm text-accent-fg disabled:opacity-50"
        >
          {t('page.G1.rejudgeRun')}
        </button>
      </div>
      {createJob.error ? (
        <p role="alert" className="text-sm text-danger">
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

function KpiTiles({ data }: { data: Dashboard }) {
  const { kpis, asof_date: asof } = data;
  const tiles = [
    {
      key: 'judged',
      title: t('page.G1.kpi.judged'),
      body: <FactCell fact={kpis.judged_count} unit="count" />,
    },
    {
      key: 'intakeOpen',
      title: t('page.G1.kpi.intakeOpen'),
      body: <FactCell fact={kpis.intake_open_count} unit="count" />,
    },
    {
      key: 'unsold',
      title: t('page.G1.kpi.unsold'),
      body: <FactCell fact={kpis.unsold.total} unit="households" />,
      sub: (
        <>
          <span>{t('page.G1.kpi.unsoldSub', { ym: kpis.unsold.ym ?? t('empty.unknown') })}</span>{' '}
          <FactCell fact={kpis.unsold.post_completion} unit="households" />
        </>
      ),
    },
    {
      key: 'movePeak',
      title: t('page.G1.kpi.movePeak'),
      body: <FactCell fact={kpis.move_in_peak.year} unit="text" />,
      sub: <FactCell fact={kpis.move_in_peak.units} unit="households" />,
    },
    {
      key: 'freshness',
      title: t('page.G1.kpi.freshness'),
      body: <FactCell fact={kpis.data_freshness.last_success_at} unit="date" asof={asof} />,
      // 수집 대상 개수 — 운영 메타(사실 아님)
      sub: (
        <MetaText
          kind="count"
          k="page.G1.kpi.freshnessSub"
          params={{
            failing: kpis.data_freshness.failing_sources,
            stale: kpis.data_freshness.stale_sources,
          }}
        />
      ),
    },
  ];
  return (
    <ul aria-label={t('page.G1.kpis')} className="grid grid-cols-2 gap-2 md:grid-cols-5">
      {tiles.map((tile) => (
        <li
          key={tile.key}
          className="flex flex-col gap-1 rounded-sm border border-border bg-surface p-3"
          data-kpi={tile.key}
        >
          <span className="text-xs text-muted">{tile.title}</span>
          <span className="text-lg font-semibold">{tile.body}</span>
          {tile.sub ? <span className="text-xs text-muted">{tile.sub}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function Top5Card({ row, asof }: { row: ScoreRow; asof: string }) {
  const navigate = useNavigate();
  const search = useGlobalSearch();
  const to = `/complexes/${row.complex_id}${search}`;
  // 카드 빈 곳 클릭 → G3. 안쪽 버튼(숫자 셀 = 출처 패널)·링크 클릭은 그대로 둔다.
  const onClick = (event: MouseEvent<HTMLLIElement>) => {
    if ((event.target as HTMLElement).closest('button, a')) return;
    navigate(to);
  };
  return (
    <li
      onClick={onClick}
      className="flex cursor-pointer flex-col gap-2 rounded-sm border border-border p-3 hover:border-accent"
      data-complex-id={row.complex_id}
    >
      <div className="flex items-start justify-between gap-2">
        <Link
          to={to}
          className="font-medium hover:underline"
          aria-label={t('page.G1.open', { name: row.name })}
        >
          {row.name}
        </Link>
        {row.rank !== null ? (
          <Badge tone="strong">
            <MetaValue kind="rank" value={row.rank} as="rank" />
          </Badge>
        ) : null}
      </div>
      {row.living_area_name ? (
        <span className="text-xs text-muted">{row.living_area_name}</span>
      ) : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm">
        <dt className="text-muted">{t('page.G1.total')}</dt>
        <dd>
          <FactCell fact={row.total} unit="score" />
        </dd>
        <dt className="text-muted">{t('page.G1.p10')}</dt>
        <dd>
          <FactCell fact={row.p10} unit="prob" />
        </dd>
        {row.delta_rerank ? (
          <>
            <dt className="text-muted">{t('page.common.deltaRerank')}</dt>
            <dd data-testid="top5-delta-rerank">
              <FactCell fact={row.delta_rerank} unit="score" />
            </dd>
          </>
        ) : null}
      </dl>
      <div className="flex flex-wrap gap-1">
        <IntakeBadge intake={row.intake} asof={asof} />
        <TieBadge
          tie={row.tie_group !== null || row.decision?.tie === true}
          confidence={row.decision?.tie ? (row.decision.confidence ?? null) : null}
        />
        <UnstableBadge unstable={row.unstable} />
        <JudgeScopeBadge scope={row.judge_scope} hideTarget />
        <RejudgeNeededBadge needed={row.rejudge_needed} />
      </div>
    </li>
  );
}

function ChangeFeed({ changes, asof }: { changes: ChangeEvent[]; asof: string }) {
  const search = useGlobalSearch();
  return (
    <Section title={t('page.G1.changes')}>
      {changes.length === 0 ? (
        <EmptyState message={t('page.G1.noChanges')} />
      ) : (
        <ul aria-label={t('page.G1.changes')} className="flex flex-col divide-y divide-border">
          {changes.map((change) => {
            const body = (
              <>
                <span className="flex flex-wrap items-center gap-1">
                  <Badge tone={change.severity === 'critical' ? 'strong' : 'muted'}>
                    {enumText('page.common.severity', change.severity)}
                  </Badge>
                  {change.triggers_rejudge ? (
                    <Badge tone="muted">{t('page.G1.rejudge')}</Badge>
                  ) : null}
                  <span className="font-medium">
                    {change.complex_name ?? changeEntityText(change.entity)}
                  </span>
                </span>
                <span className="text-sm">
                  <span>{changeFieldText(change.field)}</span>{' '}
                  <span>{changeValueText(change)}</span>
                </span>
                <span className="text-xs text-muted">{formatDate(change.detected_at, asof)}</span>
              </>
            );
            return (
              <li key={change.id} className="py-2">
                {change.complex_id ? (
                  <Link
                    to={`/complexes/${change.complex_id}${search}${change.tab ? `#${change.tab}` : ''}`}
                    className="flex flex-col gap-0.5 hover:underline"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="flex flex-col gap-0.5">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
