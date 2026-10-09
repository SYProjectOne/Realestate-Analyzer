import { useId, useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import type { RegionPatched } from '@/api/contract8';
import { useResolveRegion, useUpdateRegionSelections } from '@/api/hooks';
import type { Region, RegionCandidate, RegionSelection } from '@/api/types';
import { useToast } from '@/app/toast';
import { Badge, EmptyState, JobProgress, MetaText } from '@/components';
import { t } from '@/i18n';
import { enumText, Section, useDebounced } from '../_shared';

const DEBOUNCE_MS = 300;

const key = (s: Pick<RegionSelection, 'kind' | 'code'>) => `${s.kind}:${s.code}`;

/** 저장 전 바뀐 점: 추가·제거된 선택 */
export function selectionDiff(
  before: readonly RegionSelection[],
  after: readonly RegionSelection[],
): { added: RegionSelection[]; removed: RegionSelection[] } {
  const was = new Set(before.map(key));
  const now = new Set(after.map(key));
  return {
    added: after.filter((s) => !was.has(key(s))),
    removed: before.filter((s) => !now.has(key(s))),
  };
}

/**
 * G0-2 지역 범위 확장 (D11-7, 계약 .8 초안 PATCH /regions/{id} {selections}) = RA "지역 추가".
 * 지금 선택(시도·시군구·읍면동)에 후보를 더하거나 빼고 저장하면, 서버가 새 리비전에서 후보 전체 rerank 를 1회 돌리고
 * 보고서 §12 "지역 추가" 장(이전 리비전과 비교)을 만든다. 마지막 선택 하나는 뺄 수 없다. 지역명은 서버 값만 쓴다.
 */
export function RegionExpandPanel({ region }: { region: Region }) {
  const canWrite = useCanWrite();
  const toast = useToast();
  const update = useUpdateRegionSelections(region.id);
  const [selections, setSelections] = useState<RegionSelection[]>(region.selections);
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query, DEBOUNCE_MS);
  const resolve = useResolveRegion(debounced);
  const [saved, setSaved] = useState<RegionPatched | null>(null);
  const searchId = useId();
  const diff = selectionDiff(region.selections, selections);
  const dirty = diff.added.length + diff.removed.length > 0;
  const candidates = debounced.trim().length >= 2 ? (resolve.data ?? []) : [];

  const add = (c: RegionCandidate) =>
    setSelections((prev) =>
      prev.some((s) => key(s) === key(c))
        ? prev
        : [...prev, { kind: c.kind, code: c.code, full_name: c.full_name }],
    );
  const remove = (s: RegionSelection) =>
    setSelections((prev) => (prev.length <= 1 ? prev : prev.filter((x) => key(x) !== key(s))));

  const save = () => {
    if (!dirty || !canWrite) return;
    update.mutate(
      { selections },
      {
        onSuccess: (result) => {
          setSaved(result);
          setSelections(result.region.selections);
          toast({ message: t('page.G0_2.expand.saved') });
        },
      },
    );
  };

  const serverError =
    update.error instanceof ApiError ? update.error.detail : (update.error?.message ?? null);

  return (
    <Section title={t('page.G0_2.expand.title')}>
      <p className="text-xs text-muted">{t('page.G0_2.expand.intro')}</p>
      <ul aria-label={t('page.G0_2.expand.current')} className="flex flex-wrap gap-1.5">
        {selections.map((s) => {
          const added = diff.added.some((a) => key(a) === key(s));
          return (
            <li
              key={key(s)}
              className="inline-flex items-center gap-1 text-sm"
              data-added={added || undefined}
            >
              <Badge tone={added ? 'strong' : 'neutral'}>
                {s.full_name} · {enumText('page.common.candidateKind', s.kind)}
              </Badge>
              <button
                type="button"
                data-write
                disabled={!canWrite || selections.length <= 1}
                onClick={() => remove(s)}
                aria-label={t('page.G0_2.expand.remove', { name: s.full_name })}
                className="rounded-sm border border-border px-1 text-xs disabled:opacity-50"
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-col gap-1" data-write>
        <label htmlFor={searchId} className="text-sm font-medium">
          {t('page.G0_2.expand.search')}
        </label>
        <input
          id={searchId}
          type="search"
          value={query}
          autoComplete="off"
          placeholder={t('page.G0.searchPlaceholder')}
          onChange={(e) => setQuery(e.target.value)}
          className="rounded-sm border border-border bg-surface px-2 py-1.5 text-sm"
        />
        {debounced.trim().length >= 2 && resolve.data && candidates.length === 0 ? (
          <EmptyState message={t('page.G0.noCandidates')} />
        ) : null}
        {candidates.length > 0 ? (
          <ul aria-label={t('page.G0_2.expand.candidates')} className="flex flex-col gap-1">
            {candidates.map((c) => {
              const have = selections.some((s) => key(s) === key(c));
              return (
                <li key={key(c)} className="flex flex-wrap items-center gap-2 text-sm">
                  <span>{c.full_name}</span>
                  <MetaText
                    kind="count"
                    className="text-xs text-muted"
                    k="page.G0.dongCount"
                    params={{ n: c.legal_dong_codes.length }}
                  />
                  <button
                    type="button"
                    disabled={have || !canWrite}
                    onClick={() => add(c)}
                    className="rounded-sm border border-border px-2 py-0.5 text-xs disabled:opacity-50"
                  >
                    {have ? t('page.G0_2.expand.have') : t('page.G0_2.expand.add')}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
      {dirty ? (
        <p className="text-xs text-muted" data-testid="expand-diff">
          <MetaText
            kind="count"
            k="page.G0_2.expand.diff"
            params={{ added: diff.added.length, removed: diff.removed.length }}
          />
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2" data-write>
        <button
          type="button"
          onClick={save}
          disabled={!dirty || !canWrite || update.isPending}
          title={canWrite ? undefined : t('auth.readOnlyHint')}
          className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
        >
          {t('page.G0_2.expand.submit')}
        </button>
        {serverError ? (
          <p role="alert" className="text-sm text-danger">
            {t('page.common.loadError', { detail: serverError })}
          </p>
        ) : null}
      </div>
      {saved ? (
        <div data-testid="expand-job">
          <p className="text-xs text-muted">{t('page.G0_2.expand.jobHint')}</p>
          <JobProgress jobId={saved.job.id} />
        </div>
      ) : null}
    </Section>
  );
}
