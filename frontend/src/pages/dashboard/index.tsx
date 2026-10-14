import { useQueryClient } from '@tanstack/react-query';
import { useState, type MouseEvent, type ReactNode } from 'react';
import { Link, Navigate, useNavigate } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useChecklist, useCreateJob, useDashboard, useScenarios } from '@/api/hooks';
import type { ChangeEvent, ChecklistItem, Dashboard, ScoreRow } from '@/api/types';
import { C05Unsold, C06ScoreBreakdown } from '@/charts';
import {
  Badge,
  EmptyState,
  FactCell,
  IntakeBadge,
  JobProgress,
  MetaText,
  MetaValue,
  Term,
  TieBadge,
  UnstableBadge,
} from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatDate } from '@/lib/format';
import { useIsMobile } from '@/lib/useMediaQuery';
import { scheduleBasis, scheduleKindText, withinDays } from '../_shared/schedule';
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
/** 지금 접수 가능 링크가 거는 값(계약 IntakeStatus) */
const OPEN_NOW = '가능';

export function DashboardPage() {
  const { isEmpty } = useActiveRegion();
  const { snapshotId, scenarioKey, isLoading } = usePageContext();
  const query = useDashboard(snapshotId, scenarioKey);

  if (isEmpty) return <Navigate to="/regions/new" replace />;

  return (
    <PageShell title={t('page.G1.title')} legend>
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
  // +10% 목표 시점 = 이 상황의 p10_horizon(상황 C 는 기준일+5년 — 고정 문구로 쓰지 않는다)
  const { data: scenarios = [] } = useScenarios();
  const horizon = scenarios.find((s) => s.id === data.scenario_id)?.policy.p10_horizon ?? null;
  const target = horizon ? enumText('chart.C01.horizon', horizon) : null;
  /*
   * R9-UI P2(30-proposal §3): 1단 = 지금 할 수 있는 것(지금 접수 가능), 2단 = 상위 단지 카드, 3단 = 지역 현황·최근 변경·차트.
   * 값·라벨·출처는 그대로(FactCell) — 순서·묶음·접기만 바꾼다. 섹션 순서는 data-section 으로 테스트한다.
   */
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
      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        <OpenNowCard data={data} />
        <UpcomingCard asof={asof} />
      </div>
      <div data-section="top">
        <Section
          title={t('page.G1.top5')}
          actions={
            <span className="flex flex-wrap gap-x-1 text-xs text-muted">
              <span>{t('page.G1.top5Scenario', { name: data.scenario_name })}</span>
              <span aria-hidden>·</span>
              <span>{t('page.G1.top5Note')}</span>
            </span>
          }
        >
          {/* 카드마다 반복하지 않고 구역 머리에 한 번(P6) */}
          <p className="flex flex-wrap items-center gap-x-3 text-xs text-muted">
            <span className="inline-flex items-center">
              {t('page.G1.total')}
              <Term k="total" />
            </span>
            <span className="inline-flex items-center">
              {t('page.G1.p10')}
              <Term k="p10" />
            </span>
          </p>
          {top.length < 5 ? (
            <p data-testid="top5-fewer" className="text-sm text-muted">
              <MetaText kind="count" k="page.G1.top5Fewer" params={{ n: top.length }} />
            </p>
          ) : null}
          <ul aria-label={t('page.G1.top5')} className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {top.map((row) => (
              <Top5Card key={row.complex_id} row={row} asof={asof} target={target} />
            ))}
          </ul>
        </Section>
      </div>
      <RegionStatus data={data} />
      <ChangeFeed changes={data.changes} asof={asof} />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <C06ScoreBreakdown data={{ rows: top, weights: data.weights, orientation: 'vertical' }} />
        <C05Unsold data={{ unsold: data.unsold_series }} height={200} />
      </div>
    </div>
  );
}

/** 1단: 지금 접수 가능 N곳(FactCell — 출처 패널 그대로) + G2 접수 가능 목록 링크 */
function OpenNowCard({ data }: { data: Dashboard }) {
  const search = useGlobalSearch();
  const params = new URLSearchParams(search);
  params.set('intake_status', OPEN_NOW);
  const title = t('page.G1.openNow.title');
  return (
    <section
      aria-label={title}
      data-section="openNow"
      className="flex flex-col gap-2 rounded-sm border border-border bg-surface p-3"
    >
      <h2 className="text-base font-semibold">
        {title}
        <Term k="intake_status" className="ml-1 align-middle" />
      </h2>
      <p className="flex flex-wrap items-baseline gap-1 text-2xl font-semibold">
        <FactCell wrap fact={data.kpis.intake_open_count} unit="count" />
        <span className="text-base font-normal">{t('page.G1.openNow.unit')}</span>
      </p>
      <Link to={`/complexes?${params.toString()}`} className="self-start text-sm underline">
        {t('page.G1.openNow.link')}
      </Link>
      <p className="text-xs text-muted">{t('page.G1.openNow.hint')}</p>
    </section>
  );
}

/** 모바일(≤768px)은 접어 둔다(펼침 1클릭), 데스크톱은 펼친 구역 */
function Collapsible({
  title,
  section,
  children,
}: {
  title: string;
  section: string;
  children: ReactNode;
}) {
  const isMobile = useIsMobile();
  if (isMobile) {
    return (
      <details data-section={section} className="rounded-sm border border-border bg-surface p-3">
        <summary className="cursor-pointer text-base font-semibold">{title}</summary>
        <div className="mt-2">{children}</div>
      </details>
    );
  }
  return (
    <div data-section={section}>
      <Section title={title}>{children}</Section>
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

/** 3단 지역 현황(예전 핵심 지표 4칸): 판정 대상·미분양·입주가 가장 많은 해·마지막 수집 — 값·라벨 그대로 */
function RegionStatus({ data }: { data: Dashboard }) {
  const { kpis, asof_date: asof } = data;
  const tiles = [
    {
      key: 'judged',
      title: (
        <>
          {t('page.G1.kpi.judged')}
          <Term k="judge_scope" />
        </>
      ),
      body: <FactCell wrap fact={kpis.judged_count} unit="count" />,
    },
    {
      key: 'unsold',
      title: t('page.G1.kpi.unsold'),
      body: <FactCell wrap fact={kpis.unsold.total} unit="households" />,
      sub: (
        <>
          <span>{t('page.G1.kpi.unsoldSub', { ym: kpis.unsold.ym ?? t('empty.unknown') })}</span>{' '}
          <FactCell wrap fact={kpis.unsold.post_completion} unit="households" />
          {kpis.unsold.breakdown && kpis.unsold.breakdown.length > 0 ? (
            // 계약 .20 F4: 지역 합계 내역(시군구별 원천 Fact — 출처 1클릭)
            <details className="mt-1">
              <summary className="cursor-pointer">{t('page.G1.kpi.unsoldBreakdown')}</summary>
              <span data-testid="unsold-breakdown" className="mt-1 flex flex-col gap-0.5">
                {kpis.unsold.breakdown.map((part) => (
                  <span key={part.scope_code ?? part.scope_name} className="flex flex-wrap gap-1">
                    <span>{part.scope_name}</span>
                    <FactCell wrap fact={part.total} unit="households" />
                  </span>
                ))}
              </span>
            </details>
          ) : null}
        </>
      ),
    },
    {
      key: 'movePeak',
      title: t('page.G1.kpi.movePeak'),
      body: <FactCell wrap fact={kpis.move_in_peak.year} unit="text" />,
      sub: <FactCell wrap fact={kpis.move_in_peak.units} unit="households" />,
    },
    {
      key: 'freshness',
      title: t('page.G1.kpi.freshness'),
      body: <FactCell wrap fact={kpis.data_freshness.last_success_at} unit="date" asof={asof} />,
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
    <Collapsible title={t('page.G1.region')} section="region">
      <ul aria-label={t('page.G1.region')} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((tile) => (
          <li key={tile.key} className="flex min-w-0 flex-col gap-0.5 text-sm" data-kpi={tile.key}>
            <span className="text-xs text-muted">{tile.title}</span>
            <span className="font-medium">{tile.body}</span>
            {tile.sub ? <span className="text-xs text-muted">{tile.sub}</span> : null}
          </li>
        ))}
      </ul>
    </Collapsible>
  );
}

/**
 * TOP 카드(R9-UI P2, D28-4 '사실 먼저·점수 아래'): 이름·생활권·접수 → 현재 구매가·전매 종료·가격 갭(계약 .20 F8 — ScoreRow 의
 * 같은 리비전 목록 행 Fact, 결정 14(b)) → 종합 점수·+10% 상승 가능성(목표 시점·당첨 확률 아님). rerank 변화는 G3 점수 줄·G4·G5.
 * .20 이전 발행 저장본(키 없음)은 '확인 불가(이 기준일 자료에 없음)'.
 */
function Top5Card({ row, asof, target }: { row: ScoreRow; asof: string; target: string | null }) {
  const navigate = useNavigate();
  const search = useGlobalSearch();
  const to = `/complexes/${row.complex_id}${search}`;
  // 카드 빈 곳 클릭 → G3. 안쪽 버튼(숫자 셀 = 출처 패널)·링크 클릭은 그대로 둔다.
  const onClick = (event: MouseEvent<HTMLLIElement>) => {
    if ((event.target as HTMLElement).closest('button, a, summary')) return;
    navigate(to);
  };
  const missing = t('page.G1.noListRow');
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
      <dl data-card="facts" className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm">
        <dt className="text-muted">{t('page.G1.card.price')}</dt>
        <dd className="flex flex-wrap items-center gap-1">
          <FactCell wrap fact={row.price_low ?? null} unit="eok" emptyReason={missing} />
          <span aria-hidden>~</span>
          <FactCell wrap fact={row.price_high ?? null} unit="eok" emptyReason={missing} />
        </dd>
        <dt className="text-muted">{t('page.G1.card.resaleEnd')}</dt>
        <dd>
          <FactCell
            wrap
            fact={row.resale_end ?? null}
            unit="date"
            asof={asof}
            emptyReason={missing}
          />
        </dd>
        <dt className="text-muted">{t('page.G1.card.gap')}</dt>
        <dd>
          <FactCell wrap fact={row.gap_pct ?? null} unit="pct" emptyReason={missing} />
        </dd>
      </dl>
      <dl
        data-card="score"
        className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 border-t border-border pt-2 text-sm"
      >
        <dt className="text-muted">{t('page.G1.total')}</dt>
        <dd>
          <FactCell wrap fact={row.total} unit="score" />
        </dd>
        <dt className="text-muted">{t('page.G1.p10')}</dt>
        <dd className="flex flex-col">
          <FactCell wrap fact={row.p10} unit="prob" />
          {target ? (
            <span className="text-xs text-muted">{t('page.G1.p10Target', { target })}</span>
          ) : null}
          <span className="text-xs text-muted">{t('page.G1.p10Note')}</span>
        </dd>
      </dl>
    </li>
  );
}

/** 다가오는 일정 최대 건수·기간(일) */
const UPCOMING_MAX = 5;
const UPCOMING_DAYS = 28;

/**
 * 1단 다가오는 일정(4주, R9-UI P2·갭 #15): 체크리스트 기한(계약·중도금·전매 가능 시작·공고 예상)을 기준일부터 4주 안만 날짜순.
 * 청약 접수일은 아직 일정에 없다(계약 .20 요청 Q3) — 정직하게 적는다. 공유 링크(읽기 전용 공유 토큰)는 /ops 가 403.
 */
function UpcomingCard({ asof }: { asof: string }) {
  const query = useChecklist();
  const search = useGlobalSearch();
  const title = t('page.G1.upcoming.title');
  const items = (query.data ?? [])
    .filter(
      (i): i is ChecklistItem & { due_date: string } =>
        i.status === 'open' && !!i.due_date && withinDays(i.due_date, asof, UPCOMING_DAYS),
    )
    .sort((a, b) => a.due_date.localeCompare(b.due_date))
    .slice(0, UPCOMING_MAX);
  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  return (
    <section
      aria-label={title}
      data-section="upcoming"
      className="flex flex-col gap-2 rounded-sm border border-border bg-surface p-3"
    >
      <h2 className="text-base font-semibold">{title}</h2>
      {forbidden ? (
        <p className="text-sm text-muted">{t('page.G1.upcoming.noAccess')}</p>
      ) : query.error ? (
        <EmptyState inline message={t('page.common.loadError', { detail: query.error.message })} />
      ) : query.isLoading ? (
        <p role="status" className="text-sm text-muted">
          {t('app.loading')}
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{t('page.G1.upcoming.none')}</p>
      ) : (
        <ul aria-label={title} className="flex flex-col gap-1 text-sm">
          {items.map((item) => {
            const basis = scheduleBasis(item);
            return (
              <li
                key={item.id}
                data-due={item.due_date}
                className="flex flex-wrap items-center gap-x-2"
                title={item.title}
              >
                <span data-testid="schedule-kind">
                  <Badge tone="neutral">{scheduleKindText(item)}</Badge>
                </span>
                <span className="tabular-nums">{formatDate(item.due_date, asof)}</span>
                {item.complex_id ? (
                  <Link to={`/complexes/${item.complex_id}${search}`} className="underline">
                    {item.complex_name ?? item.title}
                  </Link>
                ) : (
                  <span>{item.title}</span>
                )}
                {basis ? (
                  <span className="w-full text-xs text-muted">
                    {t('page.common.scheduleBasis', { basis })}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-xs text-muted">{t('page.G1.upcoming.noApply')}</p>
      <Link to={`/ops${search}`} className="self-start text-sm underline">
        {t('page.G1.upcoming.all')}
      </Link>
    </section>
  );
}

/** 처음 보이는 변경 수 — 나머지는 '변경 더 보기'(1클릭) */
const CHANGES_SHOWN = 3;

/**
 * 3단 최근 변경(D25-2: 변경 기록이지 사실이 아니다). 한 줄 = 중요도 · 단지 · "{필드} 변경" · 감지일, 바뀐 값(해시 등 원문)은
 * '바뀐 값 보기' 펼침(1클릭). 지역 첫 적재(first_load)는 요약 문장 그대로.
 */
function ChangeFeed({ changes, asof }: { changes: ChangeEvent[]; asof: string }) {
  const search = useGlobalSearch();
  const [all, setAll] = useState(false);
  const shown = all ? changes : changes.slice(0, CHANGES_SHOWN);
  return (
    <Collapsible title={t('page.G1.changes')} section="changes">
      {changes.length === 0 ? (
        <EmptyState message={t('page.G1.noChanges')} />
      ) : (
        <div className="flex flex-col gap-1">
          <ul aria-label={t('page.G1.changes')} className="flex flex-col divide-y divide-border">
            {shown.map((change) => {
              // 계약 .20 F5: 서버 summary 한 줄 — hash·json 이면 원값은 '바뀐 값 보기' 안, plain 은 summary 에 값이 있다
              const serverSummary = change.summary ?? null;
              const summaryOnly =
                serverSummary !== null
                  ? change.value_kind !== 'hash' && change.value_kind !== 'json'
                  : change.field === 'first_load' && change.old_text === null;
              const head = (
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
                    {serverSummary !== null ? (
                      <span title={change.field_label}>{serverSummary}</span>
                    ) : summaryOnly ? (
                      <>
                        <span>{changeFieldText(change.field)}</span>{' '}
                        <span>{changeValueText(change)}</span>
                      </>
                    ) : (
                      t('page.G1.changeSentence', { field: changeFieldText(change.field) })
                    )}
                  </span>
                  <span className="text-xs text-muted">{formatDate(change.detected_at, asof)}</span>
                </>
              );
              return (
                <li key={change.id} className="flex flex-col gap-0.5 py-2">
                  {change.complex_id ? (
                    <Link
                      to={`/complexes/${change.complex_id}${search}${change.tab ? `#${change.tab}` : ''}`}
                      className="flex flex-col gap-0.5 hover:underline"
                    >
                      {head}
                    </Link>
                  ) : (
                    <div className="flex flex-col gap-0.5">{head}</div>
                  )}
                  {summaryOnly ? null : (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-muted">
                        {t('page.G1.changeShowValue')}
                      </summary>
                      <span data-testid="change-value" className="break-all">
                        {changeValueText(change)}
                      </span>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
          {changes.length > CHANGES_SHOWN ? (
            <button
              type="button"
              aria-expanded={all}
              onClick={() => setAll((x) => !x)}
              className="self-start text-sm underline"
            >
              {all ? t('page.G1.changesLess') : t('page.G1.changesMore')}
            </button>
          ) : null}
        </div>
      )}
    </Collapsible>
  );
}
