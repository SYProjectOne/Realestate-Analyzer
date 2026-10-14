import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { useDownload } from '@/api/download';
import { reportRequest, useChanges, useCreateReport, useReports, useScenarios } from '@/api/hooks';
import { ApiError, isMaterializePending } from '@/api/client';
import type { ChangeEvent, Report, ReportFormat, Scenario, Snapshot } from '@/api/types';
import { Badge, EmptyState, JobProgress, MetaText, SnapshotPicker } from '@/components';
import { snapshotText, snapshotTitle } from '@/components/SnapshotPicker';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatDate } from '@/lib/format';
import { metaText } from '@/lib/meta';
import {
  changeEntityText,
  changeFieldText,
  changeValueText,
  enumText,
  QueryState,
  scenarioMadeAfterPublish,
  Section,
  tdClass,
  thClass,
  useGlobalSearch,
  usePageContext,
} from '../_shared';

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

/**
 * G8 보고서 `/reports` (RA §7-1, D4 = HTML|PDF)
 * SnapshotPairPicker · ScenarioSelect · FormatSelect · GenerateButton(→ JobProgress) · ReportList(다운로드) · SnapshotDiffTable
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
  const scenarios = useScenarios();
  const [baseId, setBaseId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string>('');
  /** 보고서 시나리오 id(문자열). null = 전역 ?scenario= 를 따른다, '' = 기본 */
  const [scenarioChoice, setScenarioChoice] = useState<string | null>(null);
  const [format, setFormat] = useState<ReportFormat>('html');
  const [jobId, setJobId] = useState<number | null>(null);
  const create = useCreateReport();
  const canWrite = useCanWrite();
  const qc = useQueryClient();
  const formatId = useId();
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
  // 계약 .11(m5): 비교는 대상보다 앞선 발행 리비전만(자기 자신·더 새 리비전 제외)
  const candidates = compareCandidates(reportable, base);
  const compareValue =
    compareId !== '' && candidates.some((s) => String(s.id) === compareId) ? compareId : '';

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

  return (
    <PageShell title={t('page.G8.title')}>
      <Section title={t('page.G8.generate')}>
        <div className="flex flex-wrap items-end gap-4">
          <SnapshotPicker
            snapshots={base && base.status !== 'published' ? [base, ...reportable] : reportable}
            value={selectedId}
            onChange={pickBase}
            label={t('page.G8.snapshot')}
          />
          <span className="inline-flex items-center gap-1.5 text-sm">
            <label htmlFor={compareSelectId} className="text-muted">
              {t('page.G8.compareSnapshot')}
            </label>
            <select
              id={compareSelectId}
              value={compareValue}
              onChange={(e) => setCompareId(e.target.value)}
              title={t('page.G8.compareOlderOnly')}
              className="rounded-sm border border-border bg-surface px-2 py-1"
            >
              <option value="">{t('page.G8.noCompare')}</option>
              {candidates.map((s) => (
                <option key={s.id} value={s.id} title={snapshotTitle(s)}>
                  {snapshotText(s)}
                </option>
              ))}
            </select>
          </span>
          <span className="inline-flex items-center gap-1.5 text-sm">
            <label htmlFor={scenarioSelectId} className="text-muted">
              {t('page.G8.scenario')}
            </label>
            <select
              id={scenarioSelectId}
              value={scenario ? String(scenario.id) : ''}
              onChange={(e) => {
                setScenarioChoice(e.target.value);
                create.reset();
              }}
              className="rounded-sm border border-border bg-surface px-2 py-1"
            >
              <option value="">{t('page.G8.scenarioDefault')}</option>
              {scenarioList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </span>
          <fieldset className="flex items-center gap-2 text-sm">
            <legend id={formatId} className="sr-only">
              {t('page.G8.format')}
            </legend>
            <span className="text-muted" aria-hidden>
              {t('page.G8.format')}
            </span>
            {FORMATS.map((f) => (
              <label key={f} className="inline-flex items-center gap-1">
                <input
                  type="radio"
                  name="report-format"
                  value={f}
                  checked={format === f}
                  onChange={() => setFormat(f)}
                />
                {t(`page.G8.formats.${f}` as TKey)}
              </label>
            ))}
          </fieldset>
          <button
            type="button"
            onClick={generate}
            disabled={!canWrite || !selectedId || !!blocked || create.isPending}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            aria-describedby={blocked ? 'g8-blocked' : undefined}
            className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
          >
            {t('page.G8.generate')}
          </button>
        </div>
        {blocked || createError ? (
          <p id="g8-blocked" role="alert" className="text-sm font-medium text-danger">
            {blocked ?? createError}
          </p>
        ) : null}
        {suggested && String(suggested.id) !== selectedId ? (
          <button
            type="button"
            data-testid="g8-pick-scenario-revision"
            onClick={() => pickBase(String(suggested.id))}
            className="self-start text-sm underline"
          >
            {t('page.G8.scenarioPickRevision', { snapshot: snapshotText(suggested) })}
          </button>
        ) : null}
        {runInstead ? (
          <Link
            to={`/scenario${globalSearch}`}
            data-testid="g8-run-scenario"
            className="self-start text-sm underline"
          >
            {t('page.common.scenarioMissingRun')}
          </Link>
        ) : null}
        {jobId !== null ? (
          <JobProgress
            jobId={String(jobId)}
            onDone={() => void qc.invalidateQueries({ queryKey: ['reports'] })}
          />
        ) : null}
      </Section>
      <ReportList asof={asof} snapshots={snapshots} />
      <SnapshotDiff baseId={selectedId} compareId={compareValue || null} asof={asof} />
    </PageShell>
  );
}

const LIST_COLS = ['created', 'snapshot', 'compare', 'format', 'status', 'size', 'file'] as const;

function ReportList({ asof, snapshots }: { asof: string | null; snapshots: Snapshot[] }) {
  const query = useReports();
  // 같은 기준일 리비전을 구별해 보인다(M-16)
  const dateOf = (id: number | null) => {
    if (id === null) return '';
    const s = snapshots.find((x) => x.id === id);
    return s ? snapshotText(s) : t('page.G8.snapshotId', { id: String(id) });
  };
  return (
    <Section title={t('page.G8.list')}>
      <QueryState query={query}>
        {(reports) =>
          reports.length === 0 ? (
            // R9-UI(30-proposal §11-1): 빈 상태가 보고서가 무엇을 담는지·어떻게 만드는지 말한다
            <EmptyState message={t('page.G8.emptyTitle')}>
              <p>{t('page.G8.emptyBody')}</p>
              <p>{t('page.G8.emptyHow')}</p>
              <p>{t('page.G8.emptyProgress')}</p>
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table aria-label={t('page.G8.list')} className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    {LIST_COLS.map((k) => (
                      <th key={k} scope="col" className={thClass}>
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
    </Section>
  );
}

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
  return (
    <tr>
      <td className={tdClass}>{formatDate(report.created_at, asof)}</td>
      <td className={tdClass}>{dateOf(report.snapshot_id)}</td>
      <td className={tdClass}>{dateOf(report.compare_snapshot_id)}</td>
      <td className={tdClass}>{t(`page.G8.formats.${report.format}` as TKey)}</td>
      <td className={tdClass}>
        <Badge
          tone={
            report.status === 'done' ? 'neutral' : report.status === 'failed' ? 'strong' : 'muted'
          }
        >
          {enumText('job.status', report.status)}
        </Badge>
        {report.blocked_reason ? (
          <span className="block text-xs text-danger">{report.blocked_reason}</span>
        ) : null}
      </td>
      <td className={tdClass}>
        {report.size_bytes === null ? null : (
          <MetaText
            kind="size"
            k="page.G8.sizeKb"
            params={{ kb: { n: report.size_bytes / 1024, as: 'number' } }}
          />
        )}
      </td>
      <td className={tdClass}>
        {report.status === 'done' ? (
          <button
            type="button"
            disabled={file.pending}
            onClick={() => void file.download(reportRequest(report.id, report.filename))}
            className="text-left underline disabled:opacity-50"
          >
            {file.pending ? t('download.pending') : (report.filename ?? t('page.common.download'))}
          </button>
        ) : null}
        {file.error ? (
          <span role="alert" className="block text-xs text-danger">
            {t('download.error', { detail: file.error.message })}
          </span>
        ) : null}
      </td>
    </tr>
  );
}

const DIFF_COLS = ['complex', 'entity', 'field', 'change', 'severity', 'detected'] as const;

function SnapshotDiff({
  baseId,
  compareId,
  asof,
}: {
  baseId: string | null;
  compareId: string | null;
  asof: string | null;
}) {
  const query = useChanges(baseId, { compare_snapshot: compareId }, compareId !== null);
  return (
    <Section title={t('page.G8.diff')}>
      {compareId === null ? (
        <p className="text-sm text-muted">{t('page.G8.diffHint')}</p>
      ) : (
        <QueryState
          query={query}
          empty={(rows) => (rows.length === 0 ? t('page.G8.noDiff') : null)}
        >
          {(rows) => <DiffTable rows={rows} asof={asof} />}
        </QueryState>
      )}
    </Section>
  );
}

function DiffTable({ rows, asof }: { rows: ChangeEvent[]; asof: string | null }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label={t('page.G8.diff')} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {DIFF_COLS.map((k) => (
              <th key={k} scope="col" className={thClass}>
                {t(`page.G8.diffCol.${k}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td className={tdClass}>{c.complex_name ?? ''}</td>
              <td className={tdClass}>{changeEntityText(c.entity)}</td>
              {/* 계약 .20 F5: 사람이 읽는 필드 이름(원래 field 는 title), 해시·JSON 원값은 펼침 안 */}
              <td className={tdClass} title={c.field}>
                {c.field_label ?? changeFieldText(c.field)}
              </td>
              <td className={tdClass}>
                {c.summary && (c.value_kind === 'hash' || c.value_kind === 'json') ? (
                  <details>
                    <summary className="cursor-pointer">{c.summary}</summary>
                    <span className="break-all text-xs">{changeValueText(c)}</span>
                  </details>
                ) : (
                  changeValueText(c)
                )}
              </td>
              <td className={tdClass}>
                <Badge tone={c.severity === 'critical' ? 'strong' : 'muted'}>
                  {enumText('page.common.severity', c.severity)}
                </Badge>
              </td>
              <td className={tdClass}>{formatDate(c.detected_at, asof)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
