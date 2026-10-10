import { useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { useDownload } from '@/api/download';
import { reportRequest, useChanges, useCreateReport, useReports } from '@/api/hooks';
import { ApiError } from '@/api/client';
import type { ChangeEvent, Report, ReportFormat, Snapshot } from '@/api/types';
import { Badge, EmptyState, JobProgress, MetaText, SnapshotPicker } from '@/components';
import { snapshotText, snapshotTitle } from '@/components/SnapshotPicker';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatDate } from '@/lib/format';
import { metaText } from '@/lib/meta';
import { enumText, QueryState, Section, tdClass, thClass, usePageContext } from '../_shared';

const FORMATS: readonly ReportFormat[] = ['html', 'pdf'];

/**
 * 생성 가능 여부: contradicted claim이 남은 스냅샷은 보고서를 만들지 않는다(RA WP8·D4).
 * 생성 중(building) 리비전도 만들지 않는다 — 판정·점수가 다 쓰이지 않았다(4차 리뷰 M-16).
 */
export function blockReason(snapshot: Snapshot | null): string | null {
  if (!snapshot) return null;
  if (snapshot.status === 'building') return t('page.G8.building');
  const n = snapshot.contradicted_claims ?? 0;
  if (n > 0) return metaText('page.G8.blocked', { n });
  return null;
}

/**
 * G8 보고서 `/reports` (RA §7-1, D4 = HTML|PDF)
 * SnapshotPairPicker · FormatSelect · GenerateButton(→ JobProgress) · ReportList(다운로드) · SnapshotDiffTable
 * contradicted claim이 있으면 버튼 비활성 + 사유.
 */
export function ReportsPage() {
  const { snapshots, snapshotId } = useSnapshot();
  const { asof } = usePageContext();
  const [baseId, setBaseId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string>('');
  const [format, setFormat] = useState<ReportFormat>('html');
  const [jobId, setJobId] = useState<number | null>(null);
  const create = useCreateReport();
  const canWrite = useCanWrite();
  const qc = useQueryClient();
  const formatId = useId();
  const compareSelectId = useId();

  // M-16: 보고서 기준·비교는 리비전 단위(같은 기준일 리비전 구별), 생성 중 리비전은 고를 수 없다
  const reportable = snapshots.filter((s) => s.status !== 'building');
  const selectedId = baseId ?? snapshotId;
  const base = snapshots.find((s) => String(s.id) === selectedId) ?? null;
  const blocked = blockReason(base);
  const conflict =
    create.error instanceof ApiError && create.error.code === 'publish_blocked'
      ? create.error.detail
      : null;

  const generate = () => {
    if (!selectedId || blocked) return;
    create.mutate(
      {
        snapshot_id: Number(selectedId),
        format,
        compare_snapshot_id: compareId ? Number(compareId) : null,
      },
      { onSuccess: (job) => setJobId(job.id) },
    );
  };

  return (
    <PageShell title={t('page.G8.title')}>
      <Section title={t('page.G8.generate')}>
        <div className="flex flex-wrap items-end gap-4">
          <SnapshotPicker
            snapshots={base && base.status === 'building' ? [base, ...reportable] : reportable}
            value={selectedId}
            onChange={setBaseId}
            label={t('page.G8.snapshot')}
          />
          <span className="inline-flex items-center gap-1.5 text-sm">
            <label htmlFor={compareSelectId} className="text-muted">
              {t('page.G8.compareSnapshot')}
            </label>
            <select
              id={compareSelectId}
              value={compareId}
              onChange={(e) => setCompareId(e.target.value)}
              className="rounded-sm border border-border bg-surface px-2 py-1"
            >
              <option value="">{t('page.G8.noCompare')}</option>
              {reportable
                .filter((s) => String(s.id) !== selectedId)
                .map((s) => (
                  <option key={s.id} value={s.id} title={snapshotTitle(s)}>
                    {snapshotText(s)}
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
        {blocked || conflict ? (
          <p id="g8-blocked" role="alert" className="text-sm font-medium text-danger">
            {blocked ?? conflict}
          </p>
        ) : null}
        {base && base.status !== 'published' && !blocked ? (
          <p className="text-xs text-muted">{t('page.G8.notPublished', { status: base.status })}</p>
        ) : null}
        {jobId !== null ? (
          <JobProgress
            jobId={String(jobId)}
            onDone={() => void qc.invalidateQueries({ queryKey: ['reports'] })}
          />
        ) : null}
      </Section>
      <ReportList asof={asof} snapshots={snapshots} />
      <SnapshotDiff baseId={selectedId} compareId={compareId || null} asof={asof} />
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
            <EmptyState message={t('page.G8.none')} />
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
              <td className={tdClass}>{c.entity}</td>
              <td className={tdClass}>{c.field}</td>
              <td className={tdClass}>
                {t('page.common.arrow', {
                  old: c.old_text ?? t('page.common.none'),
                  new: c.new_text ?? t('page.common.none'),
                })}
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
