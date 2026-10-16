import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { useDownload } from '@/api/download';
import { reportRequest, useChanges, useCreateReport, useReports, useScenarios } from '@/api/hooks';
import { ApiError, isMaterializePending } from '@/api/client';
import type { ChangeEvent, Report, ReportFormat, Scenario, Snapshot } from '@/api/types';
import { Card, JobProgress, MetaText, ProvenanceLegend, StatusPill, Term } from '@/components';
import { snapshotText, snapshotTitle } from '@/components/SnapshotPicker';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatDate, kstDateTime } from '@/lib/format';
import { metaText } from '@/lib/meta';
import {
  changeEntityText,
  changeFieldText,
  changeValueText,
  enumText,
  QueryState,
  scenarioMadeAfterPublish,
  useGlobalSearch,
  usePageContext,
} from '../_shared';
import { HelpToggle } from '../region-new/HelpToggle';

const FORMATS: readonly ReportFormat[] = ['html', 'pdf'];

/**
 * 생성 가능 여부: contradicted claim이 남은 스냅샷은 보고서를 만들지 않는다(RA WP8·D4).
 * 발행 전(building·ready) 리비전도 만들지 않는다 — 서버가 409(conflict)로 거절한다(계약 .9 S10, 4차 M-16,
 * 5차 minor: ready 기준이면 버튼이 켜진 채 409 가 조용히 묻혔다).
 */
export function blockReason(snapshot: Snapshot | null): string | null {
  if (!snapshot) return null;
  if (snapshot.status === 'building') return t('page.G8.building');
  if (snapshot.status !== 'published') return t('page.G8.unpublished');
  const n = snapshot.contradicted_claims ?? 0;
  if (n > 0) return metaText('page.G8.blocked', { n });
  return null;
}

/**
 * POST /reports 오류 안내: 409(publish_blocked·conflict) = 만들 수 없는 리비전, 422 scenario_not_in_revision(계약 .11 F10)
 * = 그 시나리오 결과가 대상 리비전에 없다(대상 다시 고르기), 503 materialize_pending = 보고서 자료 준비 중.
 * 그 밖은 일반 오류 문구.
 */
export function createErrorText(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError && error.status === 409) {
    return t('page.G8.conflict', { detail: error.detail || error.message });
  }
  if (error instanceof ApiError && error.code === 'scenario_not_in_revision') {
    return t('page.G8.scenarioNotInRevisionServer', { detail: error.detail });
  }
  if (isMaterializePending(error)) return t('page.G8.pending');
  return t('page.G8.createError', {
    detail: error instanceof Error ? error.message : String(error),
  });
}

type RevisionOrder = Pick<Snapshot, 'id' | 'asof_date' | 'revision'>;

/**
 * a 가 b 보다 **앞선** 리비전인가 — 서버(계약 .11 F10, R3 6차 m5)와 같은 순서 (기준일, 리비전, id).
 * 비교 스냅샷은 대상보다 앞선 것만(같은 것·더 새 것은 '이전 → 현재' 표가 뒤집혀 422).
 */
export function isOlderRevision(a: RevisionOrder, b: RevisionOrder): boolean {
  if (a.asof_date !== b.asof_date) return a.asof_date < b.asof_date;
  const ra = a.revision ?? 1;
  const rb = b.revision ?? 1;
  if (ra !== rb) return ra < rb;
  return a.id < b.id;
}

/** 비교 후보: 대상과 같은 지역의 발행 리비전 중 대상보다 앞선 것 */
export function compareCandidates(
  reportable: readonly Snapshot[],
  base: Snapshot | null,
): Snapshot[] {
  if (!base) return [];
  return reportable.filter((s) => s.region_id === base.region_id && isOlderRevision(s, base));
}

/**
 * 사용자 시나리오 결과가 있을 법한 대상 리비전: 그 시나리오를 만든 뒤 발행된 리비전 중 가장 새 것. `rejected` = 서버가
 * 422 scenario_not_in_revision 으로 거절한 리비전 — 화면 계산과 달라도 서버가 맞으므로 후보에서 뺀다(7차 minor 23: 거절된
 * 리비전이 곧 추천 리비전이라 버튼이 숨었다).
 */
export function revisionWithScenario(
  reportable: readonly Snapshot[],
  scenario: Pick<Scenario, 'id' | 'code' | 'created_at' | 'is_builtin'>,
  rejected: number | null = null,
): Snapshot | null {
  const fit = reportable.filter(
    (s) => s.id !== rejected && scenarioMadeAfterPublish(scenario, s) === false,
  );
  return [...fit].sort((a, b) => (isOlderRevision(a, b) ? 1 : -1))[0] ?? null;
}

/** 목업 Reports 공용 모양(.kick·.what·.warn·.stepno·.sel) */
const KICK = 'text-[13px] font-bold text-accent';
const WARN_BOX =
  'flex flex-col gap-2.5 rounded-xl border border-warn-border bg-warn-soft px-3.5 py-3 text-sm leading-relaxed text-warn-ink';
const SELECT =
  'min-h-11 w-full rounded-[10px] border border-border-strong bg-surface px-3 py-2 text-[15px] tabular-nums disabled:bg-subtle disabled:text-grayed';
const LINK_BUTTON =
  'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-[10px] border border-border-strong bg-surface px-4 text-sm font-semibold text-fg hover:border-accent hover:text-accent-ink';

/** 구역 머리: 작은 윗글(kicker) + 질문형 h2 + '이게 뭐예요?' 한 줄 */
function SectionHead({
  id,
  kicker,
  title,
  what,
  aside,
}: {
  id?: string;
  kicker: string;
  title: string;
  what: string;
  aside?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex min-w-0 flex-[1_1_480px] flex-col gap-1.5">
        <p className={KICK}>{kicker}</p>
        <h2 id={id} className="text-lg font-bold tracking-tight sm:text-[22px]">
          {title}
        </h2>
        <p className="text-sm leading-relaxed text-muted">
          <b className="mr-1.5 inline-block rounded-md bg-accent-soft px-1.5 text-xs font-bold text-accent-ink">
            {t('page.G8.what')}
          </b>
          {what}
        </p>
      </div>
      {aside}
    </div>
  );
}

/** 단계 번호(목업 .stepno — 진한 동그라미) */
function StepBadge({ n }: { n: string }) {
  return (
    <span
      aria-hidden
      className="inline-flex size-[26px] shrink-0 items-center justify-center rounded-full bg-fg text-[13px] font-bold text-surface"
    >
      {n}
    </span>
  );
}

/**
 * G8 보고서 `/reports` (RA §7-1, D4 = HTML|PDF · 목업 Reports: 만들기 4단계 → 막힌 이유(고칠 곳 링크) → 만든 보고서 → 바뀐 항목)
 * 기준 리비전 · 비교 리비전 · 시나리오 · 형식 → 보고서 만들기(→ JobProgress) · ReportList(Bearer 다운로드) · SnapshotDiff
 * contradicted claim이 있으면 버튼 비활성 + 사유. 계약 .11 F10: 사용자 시나리오가 대상 리비전 발행 뒤에 만들어졌으면
 * 생성 전에 막고(그 시나리오는 시나리오 실행이 만든 리비전에서) 결과가 있을 리비전으로 바꾸는 버튼을 준다 — 서버
 * 422 scenario_not_in_revision 도 같은 안내. 비교 후보는 대상보다 앞선 발행 리비전만.
 */
export function ReportsPage() {
  // 7차 minor 22: 지역을 바꾸면 고른 값·생성 오류·잡 진행을 모두 버린다(이전 지역 것이 새 지역 화면에 남았다)
  // 처음 지역을 알게 될 때(없음 → 지역)는 그대로 둔다 — 지역 목록보다 먼저 누른 생성이 지워지지 않게
  const regionId = useActiveRegion().region?.id ?? null;
  const [scope, setScope] = useState({ region: regionId, n: 0 });
  if (regionId !== null && regionId !== scope.region) {
    setScope({ region: regionId, n: scope.region === null ? scope.n : scope.n + 1 });
  }
  return <ReportsBody key={scope.n} />;
}

function ReportsBody() {
  const { snapshots, snapshotId } = useSnapshot();
  const { asof, scenarioKey } = usePageContext();
  const { region } = useActiveRegion();
  const scenarios = useScenarios();
  const reports = useReports();
  const [baseId, setBaseId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string>('');
  /** 보고서 시나리오 id(문자열). null = 전역 ?scenario= 를 따른다, '' = 기본 */
  const [scenarioChoice, setScenarioChoice] = useState<string | null>(null);
  const [format, setFormat] = useState<ReportFormat>('html');
  const [jobId, setJobId] = useState<number | null>(null);
  const create = useCreateReport();
  const canWrite = useCanWrite();
  const qc = useQueryClient();
  const formId = useId();
  const baseSelectId = useId();
  const compareSelectId = useId();
  const scenarioSelectId = useId();

  // M-16: 보고서 기준·비교는 리비전 단위(같은 기준일 리비전 구별). 발행 리비전만 고를 수 있다(서버: 발행 전 409,
  // 비교 스냅샷도 발행·같은 지역만 — 5차 M5)
  const reportable = snapshots.filter((s) => s.status === 'published');
  // 6차 minor 21: 고른 값은 **지금 지역** 리비전 목록에 있을 때만 쓴다 — 지역을 바꾸면 이전 지역에서 고른 기준·비교는
  // 버려지고 새 지역 기본 리비전으로 돌아간다.
  const selectedId =
    baseId !== null && snapshots.some((s) => String(s.id) === baseId) ? baseId : snapshotId;
  const base = snapshots.find((s) => String(s.id) === selectedId) ?? null;
  const baseOptions = base && base.status !== 'published' ? [base, ...reportable] : reportable;
  // 계약 .11(m5): 비교는 대상보다 앞선 발행 리비전만(자기 자신·더 새 리비전 제외)
  const candidates = compareCandidates(reportable, base);
  const compareValue =
    compareId !== '' && candidates.some((s) => String(s.id) === compareId) ? compareId : '';
  const compareSnapshot = candidates.find((s) => String(s.id) === compareValue) ?? null;

  // 보고서 시나리오: 고른 값 → 없으면 전역 ?scenario=(code·id) → 기본
  const scenarioList = scenarios.data ?? [];
  const globalScenario =
    scenarioKey === null
      ? null
      : (scenarioList.find((s) => (s.code ?? String(s.id)) === scenarioKey) ?? null);
  const scenario =
    scenarioChoice === null
      ? globalScenario
      : (scenarioList.find((s) => String(s.id) === scenarioChoice) ?? null);
  const scenarioMissing =
    scenario && base ? scenarioMadeAfterPublish(scenario, base) === true : false;
  const serverScenarioMissing =
    create.error instanceof ApiError && create.error.code === 'scenario_not_in_revision';
  /** 서버가 거절한 대상 리비전(그 요청의 snapshot_id) */
  const [rejectedId, setRejectedId] = useState<number | null>(null);
  const suggested =
    scenario && (scenarioMissing || serverScenarioMissing)
      ? revisionWithScenario(reportable, scenario, serverScenarioMissing ? rejectedId : null)
      : null;
  // 결과가 있을 리비전이 없다 — 숨기지 않고 시나리오 실행(그 시나리오 결과 리비전을 만든다)으로 안내
  const runInstead = !!scenario && (scenarioMissing || serverScenarioMissing) && suggested === null;
  const globalSearch = useGlobalSearch();

  const blocked =
    blockReason(base) ??
    (scenarioMissing && scenario
      ? t('page.G8.scenarioNotInRevision', { name: scenario.name })
      : null);
  const createError = createErrorText(create.error);
  // 막힌 이유가 남은 모순 주장이면 고칠 곳(데이터·운영 화면 모순 주장)으로 가는 링크를 붙인다(목업 N10)
  const claimsBlocked =
    (blocked !== null && base?.status === 'published' && (base.contradicted_claims ?? 0) > 0) ||
    (create.error instanceof ApiError && create.error.code === 'publish_blocked');
  const canMake = !!base && base.status === 'published' && blocked === null;

  const generate = () => {
    if (!selectedId || blocked) return;
    setRejectedId(Number(selectedId));
    create.mutate(
      {
        snapshot_id: Number(selectedId),
        format,
        compare_snapshot_id: compareValue ? Number(compareValue) : null,
        ...(scenario ? { scenario_id: scenario.id } : {}),
      },
      { onSuccess: (job) => setJobId(job.id) },
    );
  };

  const pickBase = (id: string) => {
    setBaseId(id);
    // 비교로 고른 리비전을 기준으로 바꾸면 비교는 없음(나중에 기준을 되돌려도 되살아나지 않게)
    if (id === compareId) setCompareId('');
    create.reset();
  };

  const selection = [
    base ? snapshotText(base) : null,
    compareSnapshot
      ? t('page.G8.selectionCompare', { snapshot: snapshotText(compareSnapshot) })
      : null,
    scenario ? scenario.name : t('page.G8.scenarioDefault'),
    t(`page.G8.formats.${format}` as TKey),
  ]
    .filter((x): x is string => !!x)
    .join(' · ');

  return (
    <div className="flex flex-col gap-2">
      {region ? (
        <MetaText
          kind="count"
          className="text-sm text-muted"
          k="page.G8.summary"
          params={{
            region: region.name,
            snapshots: reportable.length,
            reports: reports.data?.length ?? 0,
          }}
        />
      ) : null}
      <PageShell title={t('page.G8.title')} intro={t('page.G8.intro')}>
        <Card
          as="section"
          aria-labelledby={`${formId}-h`}
          padding="lg"
          className="flex flex-col gap-5"
        >
          <SectionHead
            id={`${formId}-h`}
            kicker={t('page.G8.createKicker')}
            title={t('page.G8.createTitle')}
            what={t('page.G8.createWhat')}
          />
          <div className="grid gap-x-6 gap-y-5 lg:grid-cols-2">
            {/* 1 기준일 */}
            <div className="flex flex-col gap-2">
              <span className="flex items-center gap-2.5">
                <StepBadge n="1" />
                <label htmlFor={baseSelectId} className="text-[15px] font-bold">
                  {t('page.G8.snapshot')}
                </label>
                <HelpToggle label={t('page.G8.snapshotHelp')}>
                  {t('page.G8.snapshotHelpBody')}
                </HelpToggle>
              </span>
              <select
                id={baseSelectId}
                value={selectedId ?? ''}
                disabled={baseOptions.length === 0}
                onChange={(e) => pickBase(e.target.value)}
                className={SELECT}
              >
                {baseOptions.length === 0 ? (
                  <option value="">{t('header.snapshotNone')}</option>
                ) : null}
                {baseOptions.map((s) => (
                  <option key={s.id} value={s.id} title={snapshotTitle(s)}>
                    {snapshotText(s)}
                  </option>
                ))}
              </select>
              <span className="text-[13px] leading-normal text-muted">
                {t('page.G8.snapshotHint')}
              </span>
            </div>
            {/* 2 비교 */}
            <div className="flex flex-col gap-2">
              <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <StepBadge n="2" />
                <label htmlFor={compareSelectId} className="text-[15px] font-bold">
                  {t('page.G8.compareSnapshot')}
                </label>
                <span className="text-[15px] text-muted">{t('page.G8.compareOptional')}</span>
              </span>
              <select
                id={compareSelectId}
                value={compareValue}
                onChange={(e) => setCompareId(e.target.value)}
                title={t('page.G8.compareOlderOnly')}
                className={SELECT}
              >
                <option value="">{t('page.G8.noCompare')}</option>
                {candidates.map((s) => (
                  <option key={s.id} value={s.id} title={snapshotTitle(s)}>
                    {snapshotText(s)}
                  </option>
                ))}
              </select>
              <span className="text-[13px] leading-normal text-muted">
                {t('page.G8.compareHint')}
              </span>
            </div>
            {/* 3 상황(시나리오) */}
            <div className="flex flex-col gap-2">
              <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <StepBadge n="3" />
                <label htmlFor={scenarioSelectId} className="text-[15px] font-bold">
                  {t('page.G8.scenario')}
                </label>
                <span className="text-[15px] text-muted">{t('page.G8.scenarioTag')}</span>
                <Term k="scenario" />
              </span>
              <select
                id={scenarioSelectId}
                value={scenario ? String(scenario.id) : ''}
                onChange={(e) => {
                  setScenarioChoice(e.target.value);
                  create.reset();
                }}
                className={SELECT}
              >
                <option value="">{t('page.G8.scenarioDefault')}</option>
                {scenarioList.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <span className="text-[13px] leading-normal text-muted">
                {t('page.G8.scenarioHint')}
              </span>
            </div>
            {/* 4 형식 */}
            <fieldset className="flex min-w-0 flex-col gap-2">
              <legend className="mb-2 flex items-center gap-2.5 text-[15px] font-bold">
                <StepBadge n="4" />
                {t('page.G8.format')}
              </legend>
              <div className="grid grid-cols-2 gap-2.5">
                {FORMATS.map((f) => {
                  const on = format === f;
                  return (
                    <label
                      key={f}
                      className={`flex min-h-11 cursor-pointer items-start gap-2.5 rounded-xl px-3.5 py-3 ${
                        on
                          ? 'border-2 border-accent bg-accent-soft/50'
                          : 'border border-border-strong bg-surface'
                      }`}
                    >
                      <input
                        type="radio"
                        name="report-format"
                        value={f}
                        checked={on}
                        onChange={() => setFormat(f)}
                        aria-labelledby={`${formId}-${f}`}
                        aria-describedby={`${formId}-${f}-hint`}
                        className="mt-1 accent-accent"
                      />
                      <span className="flex flex-col gap-0.5">
                        <span id={`${formId}-${f}`} className="text-[15px] font-bold">
                          {t(`page.G8.formats.${f}` as TKey)}
                        </span>
                        <span id={`${formId}-${f}-hint`} className="text-[13px] text-muted">
                          {t(`page.G8.formatHint.${f}` as TKey)}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          </div>

          <div className="flex flex-wrap items-center gap-3.5 border-t border-subtle pt-[18px]">
            <button
              type="button"
              onClick={generate}
              disabled={!canWrite || !selectedId || !!blocked || create.isPending}
              title={canWrite ? undefined : t('auth.readOnlyHint')}
              aria-describedby={blocked || createError ? 'g8-blocked' : undefined}
              className="inline-flex min-h-12 items-center gap-1.5 rounded-[10px] bg-accent px-6 text-base font-semibold text-accent-fg hover:bg-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg
                aria-hidden
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                <path d="M14 3v6h6" />
                <path d="M12 18v-6" />
                <path d="m9 15 3 3 3-3" />
              </svg>
              {t('page.G8.generate')}
            </button>
            <span className="text-sm tabular-nums text-fg-2" data-testid="g8-selection">
              {selection}
            </span>
            {canMake ? (
              <span
                data-testid="g8-ready"
                className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent-ink"
              >
                <svg
                  aria-hidden
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                >
                  <path d="m5 12 5 5 9-10" />
                </svg>
                <MetaText
                  kind="count"
                  k="page.G8.ready"
                  params={{ n: base?.contradicted_claims ?? 0 }}
                />
              </span>
            ) : null}
          </div>

          {/* 막힌 이유·오류: 버튼 바로 아래(aria-describedby), 고칠 곳 링크·바꾸기 버튼을 같이 */}
          {blocked || createError ? (
            <div className={WARN_BOX} data-testid="g8-block">
              <p id="g8-blocked" role="alert" className="font-medium">
                {blocked ?? createError}
                {claimsBlocked ? (
                  <Link
                    to={`/ops${globalSearch}#claims`}
                    data-testid="g8-fix-claims"
                    className="ml-1.5 font-semibold text-accent underline-offset-2 hover:underline"
                  >
                    {t('page.G8.blockedFix')}
                  </Link>
                ) : null}
              </p>
              {(suggested && String(suggested.id) !== selectedId) || runInstead ? (
                <span className="flex flex-wrap gap-2">
                  {suggested && String(suggested.id) !== selectedId ? (
                    <button
                      type="button"
                      data-testid="g8-pick-scenario-revision"
                      onClick={() => pickBase(String(suggested.id))}
                      className={LINK_BUTTON}
                    >
                      {t('page.G8.scenarioPickRevision', { snapshot: snapshotText(suggested) })}
                    </button>
                  ) : null}
                  {runInstead ? (
                    <Link
                      to={`/scenario${globalSearch}`}
                      data-testid="g8-run-scenario"
                      className={LINK_BUTTON}
                    >
                      {t('page.common.scenarioMissingRun')}
                    </Link>
                  ) : null}
                </span>
              ) : null}
            </div>
          ) : null}

          {jobId !== null ? (
            <JobProgress
              jobId={String(jobId)}
              onDone={() => void qc.invalidateQueries({ queryKey: ['reports'] })}
            />
          ) : (
            <div
              className="flex flex-col gap-1 rounded-[14px] border border-dashed border-grayed p-4"
              data-testid="g8-progress-slot"
            >
              <p className="text-sm font-bold">{t('page.G8.progressSlot')}</p>
              <p className="text-[13px] text-muted">{t('page.G8.progressSlotHint')}</p>
            </div>
          )}
        </Card>

        <ReportList asof={asof} snapshots={snapshots} />
        <SnapshotDiff
          baseId={selectedId}
          compareId={compareValue || null}
          base={base}
          compare={compareSnapshot}
          asof={asof}
        />
        <footer className="flex flex-col gap-2 border-t border-border pt-4 text-[13px] leading-relaxed text-muted">
          <p>{t('page.G8.footnote')}</p>
          <ProvenanceLegend />
          <p>{t('page.G8.legendNote')}</p>
        </footer>
      </PageShell>
    </div>
  );
}

const LIST_COLS = ['created', 'snapshot', 'compare', 'format', 'status', 'size', 'file'] as const;
const TH =
  'whitespace-nowrap border-b border-border px-3 py-2.5 text-left text-[13px] font-medium text-muted';
const TD = 'border-b border-subtle px-3 py-3 text-left align-top';

function ReportList({ asof, snapshots }: { asof: string | null; snapshots: Snapshot[] }) {
  const query = useReports();
  const headingId = useId();
  // 같은 기준일 리비전을 구별해 보인다(M-16)
  const dateOf = (id: number | null) => {
    if (id === null) return '';
    const s = snapshots.find((x) => x.id === id);
    return s ? snapshotText(s) : t('page.G8.snapshotId', { id: String(id) });
  };
  return (
    <Card
      as="section"
      aria-label={t('page.G8.list')}
      padding="lg"
      className="flex flex-col gap-[18px]"
    >
      <SectionHead
        id={headingId}
        kicker={t('page.G8.listKicker')}
        title={t('page.G8.list')}
        what={t('page.G8.listWhat')}
      />
      <QueryState query={query}>
        {(reports) =>
          reports.length === 0 ? (
            // R9-UI(30-proposal §11-1): 빈 상태가 보고서가 무엇을 담는지·어떻게 만드는지 말한다
            <div className="flex flex-wrap items-start gap-[18px] rounded-[14px] bg-subtle p-6">
              <span
                aria-hidden
                className="inline-flex size-14 shrink-0 items-center justify-center rounded-2xl border border-border bg-surface text-accent"
              >
                <svg
                  width="28"
                  height="28"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                  <path d="M14 3v6h6" />
                  <path d="M8 13h8" />
                  <path d="M8 17h5" />
                </svg>
              </span>
              <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-1.5 text-sm leading-relaxed text-fg-2">
                <p className="text-lg font-bold text-fg">{t('page.G8.emptyTitle')}</p>
                <p>{t('page.G8.emptyBody')}</p>
                <p>{t('page.G8.emptyHow')}</p>
                <p>{t('page.G8.emptyProgress')}</p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table aria-label={t('page.G8.list')} className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    {LIST_COLS.map((k) => (
                      <th key={k} scope="col" className={TH}>
                        {t(`page.G8.col.${k}` as TKey)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => (
                    <ReportRow key={r.id} report={r} asof={asof} dateOf={dateOf} />
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </QueryState>
    </Card>
  );
}

/** 보고서 상태 알약(대기·실행 중·완료·실패) — 의미는 글자, 색은 눈에 띄는 정도만 */
const REPORT_STATUS_TONE: Record<string, string> = {
  queued: 'bg-chip text-muted',
  running: 'bg-accent-soft text-accent-ink',
  done: 'bg-chip text-fg-2',
  failed: 'bg-fg text-surface',
};

function ReportRow({
  report,
  asof,
  dateOf,
}: {
  report: Report;
  asof: string | null;
  dateOf: (id: number | null) => string;
}) {
  const file = useDownload();
  const qc = useQueryClient();
  // 409(아직 완료되지 않음 등) = 목록이 낡았다 — 보고서 목록을 다시 받는다(4차 minor)
  const conflict = file.error instanceof ApiError && file.error.status === 409;
  useEffect(() => {
    if (conflict) void qc.invalidateQueries({ queryKey: ['reports'] });
  }, [conflict, qc]);
  const compare = dateOf(report.compare_snapshot_id);
  return (
    <tr>
      <td className={`${TD} whitespace-nowrap tabular-nums`}>
        {formatDate(report.created_at, asof)}
      </td>
      <td className={`${TD} tabular-nums`}>{dateOf(report.snapshot_id)}</td>
      <td className={`${TD} tabular-nums ${compare ? '' : 'text-grayed'}`}>{compare || '—'}</td>
      <td className={TD}>{t(`page.G8.formats.${report.format}` as TKey)}</td>
      <td className={TD}>
        <span
          data-status={report.status}
          className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            REPORT_STATUS_TONE[report.status] ?? 'bg-chip text-fg-2'
          }`}
        >
          {enumText('job.status', report.status)}
        </span>
        {report.blocked_reason ? (
          <span className="mt-1 block text-xs text-warn-ink">{report.blocked_reason}</span>
        ) : null}
      </td>
      <td className={`${TD} whitespace-nowrap`}>
        {report.size_bytes === null ? null : (
          <MetaText
            kind="size"
            className="tabular-nums"
            k="page.G8.sizeKb"
            params={{ kb: { n: report.size_bytes / 1024, as: 'number' } }}
          />
        )}
      </td>
      <td className={TD}>
        {report.status === 'done' ? (
          <button
            type="button"
            disabled={file.pending}
            onClick={() => void file.download(reportRequest(report.id, report.filename))}
            className="inline-flex min-h-9 items-center gap-1.5 break-all rounded-[10px] border border-border-strong bg-surface px-3 text-left text-[13px] font-semibold text-fg hover:border-accent hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            {file.pending ? null : (
              <svg
                aria-hidden
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                className="shrink-0"
              >
                <path d="M12 4v11" />
                <path d="m7 10 5 5 5-5" />
                <path d="M5 20h14" />
              </svg>
            )}
            {file.pending ? t('download.pending') : (report.filename ?? t('page.common.download'))}
          </button>
        ) : null}
        {file.error ? (
          <span role="alert" className="mt-1 block text-xs text-warn-ink">
            {t('download.error', { detail: file.error.message })}
          </span>
        ) : null}
      </td>
    </tr>
  );
}

const DIFF_COLS = ['complex', 'entity', 'field', 'change', 'severity', 'detected'] as const;

/** 중요도 알약: 중요 = 주의, 알림 = 테두리, 정보 = 회색 */
const SEVERITY_TONE = { critical: 'warn', notice: 'outline', info: 'muted' } as const;

function SnapshotDiff({
  baseId,
  compareId,
  base,
  compare,
  asof,
}: {
  baseId: string | null;
  compareId: string | null;
  base: Snapshot | null;
  compare: Snapshot | null;
  asof: string | null;
}) {
  const query = useChanges(baseId, { compare_snapshot: compareId }, compareId !== null);
  const headingId = useId();
  return (
    <Card
      as="section"
      aria-label={t('page.G8.diff')}
      padding="lg"
      className="flex flex-col gap-[18px]"
    >
      <SectionHead
        id={headingId}
        kicker={t('page.G8.diffKicker')}
        title={t('page.G8.diff')}
        what={t('page.G8.diffWhat')}
        aside={
          base && compare ? (
            <StatusPill tone="neutral" size="md" data-testid="g8-diff-pair">
              {t('page.G8.diffPair', {
                base: snapshotText(base),
                compare: snapshotText(compare),
              })}
            </StatusPill>
          ) : null
        }
      />
      {compareId === null ? (
        <p className="rounded-xl border border-dashed border-grayed p-3.5 text-sm text-muted">
          {t('page.G8.diffHint')}
        </p>
      ) : (
        <QueryState
          query={query}
          empty={(rows) => (rows.length === 0 ? t('page.G8.noDiff') : null)}
        >
          {(rows) => (
            <>
              <DiffSummary rows={rows} />
              <DiffTable rows={rows} asof={asof} />
            </>
          )}
        </QueryState>
      )}
    </Card>
  );
}

const fieldLabel = (c: ChangeEvent) => c.field_label ?? changeFieldText(c.field);

/**
 * 바뀐 항목 요약 칸 4개(목업 N12) — 서버 행을 세기만 한다(D25-3): 건수·단지 수, 중요도별 수, 항목 가짓수, 감지 시각.
 * 원인을 짐작하는 문장은 만들지 않는다(RP-4).
 */
function DiffSummary({ rows }: { rows: ChangeEvent[] }) {
  const complexes = new Set(
    rows.map((r) => r.complex_id ?? r.complex_name ?? null).filter((x) => x !== null),
  ).size;
  const bySeverity = (s: ChangeEvent['severity']) => rows.filter((r) => r.severity === s).length;
  const fields = [...new Set(rows.map(fieldLabel))];
  const times = rows.map((r) => r.detected_at).sort();
  const latest = times[times.length - 1] ?? '';
  const earliest = times[0] ?? '';
  const tile = 'flex flex-col gap-1 rounded-xl border p-3.5';
  return (
    <div
      className="grid grid-cols-[repeat(auto-fit,minmax(min(180px,100%),1fr))] gap-3"
      data-testid="g8-diff-summary"
    >
      <div className={`${tile} border-border`}>
        <span className="text-[13px] text-muted">{t('page.G8.tile.count')}</span>
        <MetaText
          kind="count"
          className="text-[26px] font-bold tabular-nums"
          k="page.G8.tile.countValue"
          params={{ n: rows.length }}
        />
        <MetaText
          kind="count"
          className="text-xs text-muted"
          k="page.G8.tile.complexes"
          params={{ n: complexes }}
        />
      </div>
      <div className={`${tile} border-warn-border bg-warn-soft`}>
        <span className="text-[13px] text-warn-ink">{t('page.G8.tile.critical')}</span>
        <MetaText
          kind="count"
          className="text-[26px] font-bold tabular-nums"
          k="page.G8.tile.countValue"
          params={{ n: bySeverity('critical') }}
        />
        <MetaText
          kind="count"
          className="text-xs text-muted"
          k="page.G8.tile.criticalRest"
          params={{ notice: bySeverity('notice'), info: bySeverity('info') }}
        />
      </div>
      <div className={`${tile} border-border`}>
        <span className="text-[13px] text-muted">{t('page.G8.tile.field')}</span>
        {fields.length === 1 ? (
          <>
            <span className="text-[17px] font-bold leading-snug">{fields[0]}</span>
            <MetaText
              kind="count"
              className="text-xs text-muted"
              k="page.G8.tile.fieldSame"
              params={{ n: rows.length }}
            />
          </>
        ) : (
          <>
            <MetaText
              kind="count"
              className="text-[17px] font-bold leading-snug"
              k="page.G8.tile.fieldKinds"
              params={{ n: fields.length }}
            />
            <span className="text-xs text-muted">{fields.slice(0, 3).join(' · ')}</span>
          </>
        )}
      </div>
      <div className={`${tile} border-border`}>
        <span className="text-[13px] text-muted">{t('page.G8.tile.detected')}</span>
        <span className="text-[22px] font-bold tabular-nums">{kstDateTime(latest)}</span>
        {earliest === latest ? (
          <MetaText
            kind="count"
            className="text-xs text-muted"
            k="page.G8.tile.detectedSame"
            params={{ n: rows.length }}
          />
        ) : (
          <span className="text-xs text-muted">
            {t('page.G8.tile.detectedFirst', { at: kstDateTime(earliest) })}
          </span>
        )}
      </div>
    </div>
  );
}

function DiffTable({ rows, asof }: { rows: ChangeEvent[]; asof: string | null }) {
  const search = useGlobalSearch();
  return (
    <div className="overflow-x-auto">
      <table aria-label={t('page.G8.diff')} className="w-full border-collapse text-sm">
        <caption className="pb-2 text-left text-[13px] text-muted">
          {t('page.G8.diffCaption')}
        </caption>
        <thead>
          <tr>
            {DIFF_COLS.map((k) => (
              <th key={k} scope="col" className={TH}>
                {t(`page.G8.diffCol.${k}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <th scope="row" className={`${TD} font-semibold`}>
                {c.complex_id !== null && c.complex_id !== undefined && c.complex_name ? (
                  <Link
                    to={`/complexes/${c.complex_id}${search}`}
                    className="text-accent hover:underline"
                  >
                    {c.complex_name}
                  </Link>
                ) : (
                  (c.complex_name ?? '')
                )}
              </th>
              <td className={TD}>{changeEntityText(c.entity)}</td>
              {/* 계약 .20 F5: 사람이 읽는 필드 이름(원래 field 는 title), 해시·JSON 원값은 펼침 안 */}
              <td className={TD} title={c.field}>
                {fieldLabel(c)}
              </td>
              <td className={`${TD} tabular-nums`}>
                {c.summary && (c.value_kind === 'hash' || c.value_kind === 'json') ? (
                  <details>
                    <summary className="min-h-8 cursor-pointer">{c.summary}</summary>
                    <span className="mt-1.5 block text-xs leading-relaxed text-muted">
                      {c.value_kind === 'hash' ? (
                        <span className="block">{t('page.G8.hashNote')}</span>
                      ) : null}
                      <span className="break-all font-mono">{changeValueText(c)}</span>
                    </span>
                  </details>
                ) : (
                  changeValueText(c)
                )}
              </td>
              <td className={TD}>
                <StatusPill tone={SEVERITY_TONE[c.severity]}>
                  {enumText('page.common.severity', c.severity)}
                </StatusPill>
              </td>
              <td
                className={`${TD} whitespace-nowrap tabular-nums`}
                title={formatDate(c.detected_at, asof)}
              >
                {kstDateTime(c.detected_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
