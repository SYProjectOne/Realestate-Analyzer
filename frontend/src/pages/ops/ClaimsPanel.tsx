import { useId, useState } from 'react';
import { Link } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useClaims, useReviseClaim } from '@/api/hooks';
import type { ClaimView } from '@/api/types';
import { Badge, JobProgress, useOpenProvenance } from '@/components';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import { enumText, idText, QueryState, Section, useGlobalSearch } from '../_shared';

/**
 * G7 ClaimsPanel (M8, 계약 2026-10-09.4) — 지금 스냅샷의 contradicted 주장 목록.
 * remaining(분할 재검증 없는 contradicted)은 스냅샷 publish·보고서 생성을 막는다(RA §10).
 * 문장을 고치면 PATCH /claims/{id} → claim.reverify 잡(202) → JobProgress.
 * 읽기 전용 토큰·재검증 대기 중(pending_job_id)·이미 분할됨(child_count>0)이면 수정을 끈다.
 */
export function ClaimsPanel({ snapshotId }: { snapshotId: string | null }) {
  const query = useClaims(snapshotId, { status: 'contradicted' });
  return (
    <Section title={t('page.G7.claims.title')}>
      <p className="text-xs text-muted">{t('page.G7.claims.intro')}</p>
      {snapshotId === null ? (
        <p className="text-sm text-muted">{t('app.noSnapshot')}</p>
      ) : (
        <QueryState
          query={query}
          empty={(rows) => (rows.length === 0 ? t('page.G7.claims.none') : null)}
        >
          {(rows) => (
            <ul aria-label={t('page.G7.claims.title')} className="flex flex-col gap-3">
              {rows.map((claim) => (
                <ClaimItem key={claim.id} claim={claim} />
              ))}
            </ul>
          )}
        </QueryState>
      )}
    </Section>
  );
}

function ClaimItem({ claim }: { claim: ClaimView }) {
  const canWrite = useCanWrite();
  const openProvenance = useOpenProvenance();
  const search = useGlobalSearch();
  const revise = useReviseClaim();
  const textId = useId();
  const [text, setText] = useState(claim.text);
  const [jobId, setJobId] = useState<number | null>(null);

  const pending = claim.pending_job_id !== null;
  const split = claim.child_count > 0;
  const locked = !canWrite || pending || split;
  const trimmed = text.trim();
  const canSubmit = !locked && !revise.isPending && trimmed !== '' && trimmed !== claim.text;

  const error =
    revise.error instanceof ApiError
      ? revise.error.detail
      : revise.error
        ? revise.error.message
        : null;

  return (
    <li
      data-testid={`claim-${claim.id}`}
      className="flex flex-col gap-2 rounded border border-border p-2 text-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        {claim.complex_id !== null ? (
          <Link to={`/complexes/${claim.complex_id}${search}`} className="font-medium underline">
            {claim.complex_name ?? idText(claim.complex_id)}
          </Link>
        ) : (
          <span className="font-medium">{claim.complex_name ?? claim.section}</span>
        )}
        <Badge tone="strong">{enumText('page.G7.claims.status', claim.verify_status)}</Badge>
        {claim.remaining ? (
          <span data-testid="claim-remaining">
            <Badge tone="strong">{t('page.G7.claims.remaining')}</Badge>
          </span>
        ) : null}
        {pending ? (
          <Badge tone="muted">
            {t('page.G7.claims.pending', { job: idText(claim.pending_job_id) })}
          </Badge>
        ) : null}
        {split ? (
          <Badge tone="muted">
            {t('page.G7.claims.split', { n: formatCount(claim.child_count) })}
          </Badge>
        ) : null}
        {claim.prov && openProvenance ? (
          <button
            type="button"
            className="text-xs underline"
            data-prov={claim.prov}
            onClick={() => openProvenance(claim.prov as string)}
          >
            {t('page.G7.claims.prov')}
          </button>
        ) : null}
      </div>
      <blockquote className="whitespace-pre-wrap border-l-2 border-border pl-2">
        {claim.text}
      </blockquote>
      {claim.evidence_text ? (
        <p className="whitespace-pre-wrap text-xs text-muted">
          <span className="font-medium">{t('page.G7.claims.evidence')}</span> {claim.evidence_text}
        </p>
      ) : null}
      <form
        className="flex flex-col gap-1"
        data-write
        onSubmit={(e) => {
          e.preventDefault();
          if (!canSubmit) return;
          revise.mutate(
            { id: claim.id, patch: { text: trimmed } },
            { onSuccess: (job) => setJobId(job.id) },
          );
        }}
      >
        <label htmlFor={textId} className="text-xs text-muted">
          {t('page.G7.claims.revise')}
        </label>
        <textarea
          id={textId}
          value={text}
          rows={2}
          disabled={locked}
          onChange={(e) => setText(e.target.value)}
          className="w-full rounded border border-border bg-surface px-2 py-1 text-sm disabled:opacity-60"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={!canSubmit}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className="rounded bg-accent px-3 py-1 text-sm text-accent-fg disabled:opacity-50"
          >
            {t('page.G7.claims.submit')}
          </button>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {t('page.G7.claims.error', { detail: error })}
            </p>
          ) : null}
        </div>
      </form>
      {jobId !== null ? (
        <div data-testid="claim-job">
          <JobProgress jobId={jobId} />
        </div>
      ) : null}
    </li>
  );
}
