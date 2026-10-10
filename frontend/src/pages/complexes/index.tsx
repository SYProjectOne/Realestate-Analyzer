import { useCallback, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useDownload } from '@/api/download';
import { complexesCsvRequest, useComplexesProgressive } from '@/api/hooks';
import { EmptyState, MetaText } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';
import { specialErrorText } from '@/lib/errorText';
import { PageShell } from '@/layout/PageShell';
import { NoSnapshot, QueryState, useGlobalSearch, usePageContext } from '../_shared';
import { ComplexTable } from './ComplexTable';
import { FilterBar } from './FilterBar';
import {
  FILTER_KEYS,
  FIRST_PAGE_SIZE,
  readFilters,
  readSort,
  toListParams,
  type FilterKey,
} from './params';

const MAX_COMPARE = 6;
const MIN_COMPARE = 2;

/**
 * G2 단지 리스트 `/complexes` (RA §7-1)
 * FilterBar(URL 쿼리) · ComplexTable(TanStack Table + 가상 스크롤, 열 선택 저장) · CompareTray(2~6 → /compare?ids=)
 * CSV는 같은 필터·정렬로 서버가 만든다(complexesCsvRequest → Bearer fetch → 저장).
 * 목록은 첫 페이지(작게)를 먼저 그리고 나머지 페이지를 이어 받는다(useComplexesProgressive, W8·W9).
 */
export function ComplexesPage() {
  const { snapshotId, scenarioKey, asof, readOnly, isLoading } = usePageContext();
  const { region } = useActiveRegion();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const sort = readSort(params);
  const listParams = useMemo(
    () => toListParams(filters, sort, scenarioKey),
    [filters, sort, scenarioKey],
  );
  const query = useComplexesProgressive(snapshotId, listParams, FIRST_PAGE_SIZE);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const globalSearch = useGlobalSearch();

  const setFilter = useCallback(
    (key: FilterKey, value: string) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) next.set(key, value);
          else next.delete(key);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
  const resetFilters = useCallback(
    () =>
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        for (const key of FILTER_KEYS) next.delete(key);
        next.delete('sort');
        return next;
      }),
    [setParams],
  );
  const setSort = useCallback(
    (value: string) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('sort', value);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
  const toggle = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < MAX_COMPARE) next.add(id);
      return next;
    });
  }, []);

  const csv = useDownload();

  return (
    <PageShell
      title={t('page.G2.title')}
      actions={
        snapshotId ? (
          <span className="inline-flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={csv.pending}
              onClick={() => void csv.download(complexesCsvRequest(snapshotId, listParams))}
              className="rounded-sm border border-border px-2 py-1 text-sm disabled:opacity-50"
            >
              {csv.pending ? t('download.pending') : t('page.G2.csv')}
            </button>
            {csv.error ? (
              <span role="alert" className="text-xs text-danger">
                {specialErrorText(csv.error) ?? t('download.error', { detail: csv.error.message })}
              </span>
            ) : null}
          </span>
        ) : null
      }
    >
      <FilterBar
        values={filters}
        livingAreas={region?.living_areas ?? []}
        onChange={setFilter}
        onReset={resetFilters}
      />
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>
          {(page) => (
            <>
              <p className="text-sm text-muted" aria-live="polite">
                <MetaText
                  kind="count"
                  k="page.G2.count"
                  params={{ shown: page.items.length, total: page.total }}
                />
                {query.loadingMore ? (
                  <span role="status" className="ml-2">
                    {t('page.G2.loadingMore')}
                  </span>
                ) : null}
              </p>
              {page.items.length === 0 ? (
                <EmptyState message={t('page.G2.empty')} />
              ) : (
                <ComplexTable
                  rows={page.items}
                  total={page.total}
                  asof={asof ?? page.asof_date}
                  sort={sort}
                  onSort={setSort}
                  selected={selected}
                  onToggle={toggle}
                  maxSelected={MAX_COMPARE}
                  readOnly={readOnly}
                  linkSearch={globalSearch}
                />
              )}
            </>
          )}
        </QueryState>
      )}
      {!readOnly ? (
        <CompareTray
          ids={[...selected]}
          names={new Map((query.data?.items ?? []).map((r) => [r.complex_id, r.name]))}
          onRemove={toggle}
          onClear={() => setSelected(new Set())}
          search={globalSearch}
        />
      ) : null}
    </PageShell>
  );
}

function CompareTray({
  ids,
  names,
  onRemove,
  onClear,
  search,
}: {
  ids: number[];
  names: Map<number, string>;
  onRemove: (id: number) => void;
  onClear: () => void;
  search: string;
}) {
  const ok = ids.length >= MIN_COMPARE && ids.length <= MAX_COMPARE;
  const href = `/compare${search ? `${search}&` : '?'}ids=${ids.join(',')}`;
  return (
    <aside
      aria-label={t('page.G2.tray')}
      data-write
      className="sticky bottom-10 flex flex-wrap items-center gap-2 rounded-sm border border-border bg-surface p-2 shadow-sm"
    >
      <span className="text-sm font-medium">{t('page.G2.tray')}</span>
      <MetaText
        kind="count"
        className="text-sm text-muted"
        k="page.G2.trayCount"
        params={{ n: ids.length }}
      />
      {ids.map((id) => {
        const name = names.get(id) ?? `#${id}`;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onRemove(id)}
            className="rounded-sm border border-border px-1.5 py-0.5 text-xs"
            aria-label={t('page.common.remove', { name })}
          >
            {name} ×
          </button>
        );
      })}
      <span className="text-xs text-muted">
        {ids.length >= MAX_COMPARE ? t('page.G2.trayMax') : t('page.G2.trayHint')}
      </span>
      <span className="ml-auto flex gap-2">
        {ids.length > 0 ? (
          <button
            type="button"
            onClick={onClear}
            className="rounded-sm border border-border px-2 py-1 text-sm"
          >
            {t('page.G2.clearSelection')}
          </button>
        ) : null}
        {ok ? (
          <Link to={href} className="rounded-sm bg-accent px-3 py-1 text-sm text-accent-fg">
            {t('page.G2.compare')}
          </Link>
        ) : (
          <button
            type="button"
            disabled
            className="rounded-sm bg-accent px-3 py-1 text-sm text-accent-fg opacity-50"
          >
            {t('page.G2.compare')}
          </button>
        )}
      </span>
    </aside>
  );
}
