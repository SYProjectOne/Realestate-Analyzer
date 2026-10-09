import { useId, useState } from 'react';
import { Link } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { useCreateRegion, useResolveRegion } from '@/api/hooks';
import type { RegionCandidate, RegionCreated, RegionSelection } from '@/api/types';
import { useToast } from '@/app/toast';
import { Badge, EmptyState, JobProgress } from '@/components';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatCount } from '@/lib/format';
import { enumText, Section, useDebounced } from '../_shared';

const DEBOUNCE_MS = 300;

const sameCandidate = (
  a: Pick<RegionSelection, 'kind' | 'code'>,
  b: Pick<RegionSelection, 'kind' | 'code'>,
) => a.kind === b.kind && a.code === b.code;

/**
 * G0 지역 입력 `/regions/new` (D2-5)
 * 검색창(자유 지명, 디바운스 자동완성 → GET /regions/resolve) · 후보 다중 선택 칩 · 이름 · "분석 시작"
 * → POST /regions → JobProgress(region.bootstrap 잡). 지역명은 사용자 입력·서버 응답만 쓴다.
 */
export function RegionNewPage() {
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query, DEBOUNCE_MS);
  const resolve = useResolveRegion(debounced);
  const [selected, setSelected] = useState<RegionSelection[]>([]);
  const [name, setName] = useState('');
  const create = useCreateRegion();
  const canWrite = useCanWrite();
  const [created, setCreated] = useState<RegionCreated | null>(null);
  const [done, setDone] = useState(false);
  const toast = useToast();
  const searchId = useId();
  const nameId = useId();

  const toggle = (c: RegionCandidate) =>
    setSelected((prev) =>
      prev.some((s) => sameCandidate(s, c))
        ? prev.filter((s) => !sameCandidate(s, c))
        : [...prev, { kind: c.kind, code: c.code, full_name: c.full_name }],
    );

  const canStart =
    canWrite && selected.length > 0 && name.trim().length > 0 && !create.isPending && !created;

  const start = () => {
    if (!canStart) return;
    create.mutate(
      { name: name.trim(), query_text: query.trim(), selections: selected },
      {
        onSuccess: (result) => {
          setCreated(result);
          toast({ message: t('page.G0.started') });
        },
      },
    );
  };

  const candidates = debounced.trim().length >= 2 ? (resolve.data ?? []) : [];

  return (
    <PageShell title={t('page.G0.title')}>
      <p className="text-sm text-muted">{t('page.G0.intro')}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('page.G0.candidates')}>
          <div className="flex flex-col gap-1">
            <label htmlFor={searchId} className="text-sm font-medium">
              {t('page.G0.search')}
            </label>
            <input
              id={searchId}
              type="search"
              value={query}
              autoComplete="off"
              placeholder={t('page.G0.searchPlaceholder')}
              onChange={(e) => setQuery(e.target.value)}
              className="rounded-sm border border-border bg-surface px-2 py-1.5"
            />
            <span className="text-xs text-muted">
              {resolve.isFetching ? t('page.G0.searching') : t('page.G0.searchHint')}
            </span>
          </div>
          {debounced.trim().length >= 2 && resolve.data && candidates.length === 0 ? (
            <EmptyState message={t('page.G0.noCandidates')} />
          ) : null}
          {resolve.error ? (
            <EmptyState message={t('page.common.loadError', { detail: resolve.error.message })} />
          ) : null}
          {candidates.length > 0 ? (
            <ul
              aria-label={t('page.G0.candidates')}
              className="flex flex-col divide-y divide-border"
            >
              {candidates.map((c) => {
                const checked = selected.some((s) => sameCandidate(s, c));
                return (
                  <li key={`${c.kind}-${c.code}`} className="py-1.5">
                    <label className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
                      <input type="checkbox" checked={checked} onChange={() => toggle(c)} />
                      <span className="font-medium">{c.full_name}</span>
                      <Badge tone="neutral">{enumText('page.common.candidateKind', c.kind)}</Badge>
                      <Badge tone={c.match === 'exact' ? 'strong' : 'muted'}>
                        {enumText('page.common.match', c.match)}
                      </Badge>
                      <span className="text-xs text-muted">
                        {t('page.G0.dongCount', { n: formatCount(c.legal_dong_codes.length) })}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </Section>
        <Section title={t('page.G0.selected')}>
          {selected.length === 0 ? (
            <p className="text-sm text-muted">{t('page.G0.noneSelected')}</p>
          ) : (
            <ul aria-label={t('page.G0.selected')} className="flex flex-wrap gap-1">
              {selected.map((s) => (
                <li key={`${s.kind}-${s.code}`}>
                  <button
                    type="button"
                    onClick={() => setSelected((prev) => prev.filter((x) => !sameCandidate(x, s)))}
                    aria-label={t('page.common.remove', { name: s.full_name })}
                    className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-sm"
                  >
                    {s.full_name}
                    <span aria-hidden>×</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-col gap-1">
            <label htmlFor={nameId} className="text-sm font-medium">
              {t('page.G0.name')}
            </label>
            <input
              id={nameId}
              value={name}
              placeholder={t('page.G0.namePlaceholder')}
              onChange={(e) => setName(e.target.value)}
              className="rounded-sm border border-border bg-surface px-2 py-1.5"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={start}
              disabled={!canStart}
              title={canWrite ? undefined : t('auth.readOnlyHint')}
              className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
            >
              {t('page.G0.start')}
            </button>
            {!canStart && !created ? (
              <span className="text-xs text-muted">
                {canWrite ? t('page.G0.startDisabled') : t('auth.readOnlyHint')}
              </span>
            ) : null}
          </div>
          {create.error ? (
            <p role="alert" className="text-sm text-danger">
              {t('page.common.loadError', { detail: create.error.message })}
            </p>
          ) : null}
          {created ? (
            <div className="flex flex-col gap-2">
              <JobProgress
                jobId={String(created.job_id)}
                onDone={() => {
                  setDone(true);
                  toast({ message: t('page.G0.done') });
                }}
              />
              <div className="flex gap-3 text-sm">
                {done ? (
                  <Link to={`/?region=${created.region.id}`} className="underline">
                    {t('page.G0.goDashboard')}
                  </Link>
                ) : null}
                <Link to={`/regions/${created.region.id}/living-areas`} className="underline">
                  {t('page.G0.goLivingAreas')}
                </Link>
              </div>
            </div>
          ) : null}
        </Section>
      </div>
    </PageShell>
  );
}
