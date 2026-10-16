import { useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { invalidateFactViews, useClaims, useReviseClaim } from '@/api/hooks';
import type { ClaimView } from '@/api/types';
import { Badge, JobProgress, MetaText, MetaValue, useOpenProvenance } from '@/components';
import { t } from '@/i18n';
import { enumText, idText, QueryState, useGlobalSearch } from '../_shared';
import { HUMAN_CHECK_ANCHOR, humanCheckSearch } from './HumanCheckForm';
import { humanCheckFieldOf } from './humanCheckRules';
import { OpsSection } from './sections';

/**
 * G7 ClaimsPanel (M8, 계약 2026-10-09.4) — 지금 스냅샷의 contradicted 주장 목록.
 * remaining(분할 재검증 없는 contradicted)은 스냅샷 publish·보고서 생성을 막는다(RA §10).
 * 문장을 고치면 PATCH /claims/{id} → claim.reverify 잡(202) → JobProgress.
 * 읽기 전용 토큰·재검증 대기 중(pending_job_id)·이미 분할됨(child_count>0)이면 수정을 끈다.
 */
export function ClaimsPanel({ snapshotId }: { snapshotId: string | null }) {
  // 계약 .22 A5(D30-5): 상태 필터 없이 전체 목록을 받아 상태별 줄 수를 세고(D25-3), 모순 줄만 아래에 보인다
  const query = useClaims(snapshotId);
  return (
    <OpsSection k="claims">
      {snapshotId === null ? (
        <p className="text-sm text-muted">{t('app.noSnapshot')}</p>
      ) : (
        <QueryState query={query}>
          {(all) => {
            const rows = contradictedClaims(all);
            return (
              <div className="flex flex-col gap-3">
                <ClaimSummary all={all} contradicted={rows.length} />
                {rows.length === 0 ? null : (
                  <ul aria-label={t('page.G7.claims.title')} className="flex flex-col gap-3">
                    {rows.map((claim) => (
                      <ClaimItem key={claim.id} claim={claim} />
                    ))}
                  </ul>
                )}
              </div>
            );
          }}
        </QueryState>
      )}
    </OpsSection>
  );
}

/** 모순(contradicted) 줄만 — 서버 verify_status 그대로(판단하지 않는다) */
export function contradictedClaims(rows: readonly ClaimView[]): ClaimView[] {
  return rows.filter((c) => c.verify_status === 'contradicted');
}

/** 검증 상태 표시 순서(계약 verify_status enum + 검증 전 null) */
const CLAIM_STATUSES = ['verified', 'contradicted', 'unsupported', 'review'] as const;

/** 상태별 줄 수(검증 전 = null 포함) — 개수 세기만(D25-3) */
export function claimStatusCounts(rows: readonly ClaimView[]): { key: string; n: number }[] {
  const counts = CLAIM_STATUSES.map((key) => ({
    key,
    n: rows.filter((c) => c.verify_status === key).length,
  }));
  const none = rows.filter((c) => c.verify_status === null).length;
  return none > 0 ? [...counts, { key: 'none', n: none }] : counts;
}

/** 목업 OP-9: "모순 주장 n건(목록 줄 수)" + 상태별 줄 수. 남은 주장이 없으면 "남은 모순 주장이 없어요" */
function ClaimSummary({ all, contradicted }: { all: readonly ClaimView[]; contradicted: number }) {
  return (
    <div
      className="flex flex-col gap-1 rounded-xl border border-border bg-subtle px-4 py-3 text-sm"
      data-testid="claims-summary"
    >
      <b className="font-semibold text-fg">
        {contradicted === 0 ? (
          t('page.G7.claims.none')
        ) : (
          <MetaText kind="count" k="page.G7.claims.summary" params={{ n: contradicted }} />
        )}
      </b>
      {all.length > 0 ? (
        <p className="text-xs text-muted" data-testid="claims-breakdown">
          {t('page.G7.claims.breakdown')}:{' '}
          {claimStatusCounts(all).map((s, i) => (
            <span key={s.key} data-status={s.key}>
              {i > 0 ? ' · ' : ''}
              {s.key === 'none'
                ? t('page.G7.claims.statusNone')
                : enumText('page.G7.claims.status', s.key)}{' '}
              <MetaValue kind="count" value={s.n} />
            </span>
          ))}
        </p>
      ) : null}
    </div>
  );
}

function ClaimItem({ claim }: { claim: ClaimView }) {
  const canWrite = useCanWrite();
  const openProvenance = useOpenProvenance();
  const search = useGlobalSearch();
  const revise = useReviseClaim();
  const qc = useQueryClient();
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
      className="flex flex-col gap-2 rounded-xl border border-border p-4 text-sm"
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
            <MetaText kind="count" k="page.G7.claims.split" params={{ n: claim.child_count }} />
          </Badge>
        ) : null}
        {claim.field_name ? (
          <span data-testid="claim-field" className="text-xs text-muted">
            {t('page.G7.claims.field', { name: claim.field_name })}
          </span>
        ) : null}
        <DemotionBadge demotion={claim.demotion} />
        {canWrite ? <RestoreByHumanLink claim={claim} /> : null}
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
        {claim.field !== null ? (
          <p className="text-xs text-muted">{t('page.G7.claims.demoteHint')}</p>
        ) : null}
        <textarea
          id={textId}
          value={text}
          rows={2}
          disabled={locked}
          onChange={(e) => setText(e.target.value)}
          className="w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm disabled:opacity-60"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="submit"
            disabled={!canSubmit}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className="rounded-sm bg-accent px-3 py-1 text-sm text-accent-fg disabled:opacity-50"
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
          {/* 재검증이 끝나면 강등·복원이 반영된 사실을 다시 읽는다(R3 3차 minor 15) */}
          <JobProgress jobId={jobId} onDone={() => invalidateFactViews(qc)} />
        </div>
      ) : null}
    </li>
  );
}

/**
 * D10-3 사실 강등 상태(계약 2026-10-09.6 FactDemotion): 강등 = 라벨+사유 그대로 '확인 불가(검증 모순)',
 * 복원 = '복원됨(사람 확인|새 원문)'. 강등 없음(null)이면 그리지 않는다.
 */
function DemotionBadge({ demotion }: { demotion: ClaimView['demotion'] }) {
  if (!demotion) return null;
  const text =
    demotion.status === 'demoted'
      ? t('label.withReason', { label: demotion.label, reason: demotion.reason })
      : demotion.restored_by
        ? t('page.G7.claims.restored', {
            by: enumText('page.G7.claims.restoredBy', demotion.restored_by),
          })
        : t('page.G7.claims.restoredPlain');
  return (
    <span data-testid="claim-demotion" data-status={demotion.status}>
      <Badge tone={demotion.status === 'demoted' ? 'muted' : 'neutral'}>{text}</Badge>
    </span>
  );
}

/**
 * 강등된(검증 모순) 사실을 사람 확인으로 복원하는 바로가기(M-5, D11-3): 같은 화면의 사람 확인 폼을
 * 단지·필드·사실 행(entity_id)으로 미리 채우고 폼으로 스크롤한다. 사람 확인 필드로 옮길 수 없는 강등이면 그리지 않는다.
 */
function RestoreByHumanLink({ claim }: { claim: ClaimView }) {
  const [params] = useSearchParams();
  const demotion = claim.demotion;
  if (!demotion || demotion.status !== 'demoted') return null;
  const field = humanCheckFieldOf(demotion.field) ?? humanCheckFieldOf(claim.field);
  if (!field) return null;
  const search = humanCheckSearch(params, {
    complexId: claim.complex_id,
    field,
    entityId: demotion.entity_id,
  });
  return (
    <Link
      to={{ search, hash: HUMAN_CHECK_ANCHOR }}
      data-testid="claim-restore-human"
      className="text-xs underline"
      onClick={() => {
        // 라우터는 해시로 스크롤하지 않는다 — 폼으로 직접 옮긴다
        requestAnimationFrame(() => {
          const form = document.getElementById(HUMAN_CHECK_ANCHOR);
          if (form && typeof form.scrollIntoView === 'function') {
            form.scrollIntoView({ block: 'start' });
          }
        });
      }}
    >
      {t('page.G7.claims.restoreByHuman')}
    </Link>
  );
}
