import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useDownload } from '@/api/download';
import { complexesCsvRequest, useComplexesProgressive, useScenarios } from '@/api/hooks';
import { Card, MetaText, ProvenanceLegend } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { scenarioKey as keyOfScenario } from '@/hooks/useScenario';
import { t, type TKey } from '@/i18n';
import { specialErrorText } from '@/lib/errorText';
import { enumText, NoSnapshot, QueryState, useGlobalSearch, usePageContext } from '../_shared';
import { ComplexCards } from './ComplexCards';
import { ComplexTable } from './ComplexTable';
import { FilterBar } from './FilterBar';
import {
  FILTER_KEYS,
  FIRST_PAGE_SIZE,
  isSortPreset,
  readFilters,
  readSort,
  readView,
  toListParams,
  VIEW_KEY,
  VIEW_STORAGE_KEY,
  type FilterKey,
  type ViewMode,
} from './params';

const MAX_COMPARE = 6;
const MIN_COMPARE = 2;
/** 창 아래 비워 둘 높이: 고정 문구(약 30) + 트레이 bottom-10(40) + 트레이 한 줄(약 46) + 여유 */
const TRAY_RESERVE = 124;

/** 정렬 키 → 열 이름(개수 줄 "정렬 …") */
const SORT_COL: Record<string, TKey> = {
  total: 'page.G2.col.total',
  name: 'page.G2.col.name',
  price_mid: 'page.G2.col.price',
  price_low: 'page.G2.col.price',
  move_in_ym: 'page.G2.col.move_in',
  resale_end: 'page.G2.col.resale_end',
  gap_pct: 'page.G2.col.gap',
  p10: 'page.G2.col.p10',
  living_area: 'page.G2.col.living_area',
  last_change: 'page.G2.col.last_change',
  intake: 'page.G2.col.intake',
};

/** 개수 줄의 정렬 이름(ListTable 새로 더한 것 #13): 정렬 상자 이름이 있으면 그것, 아니면 "{열} 큰 값부터/작은 값부터" */
export function sortLabel(sort: string): string {
  if (isSortPreset(sort)) return t(`page.G2.sort.${sort}`);
  const key = sort.replace(/^-/, '');
  if (key === 'rank') return t('page.G2.sort.rank');
  const col = SORT_COL[key];
  if (!col) return sort;
  return t(sort.startsWith('-') ? 'page.G2.sortDesc' : 'page.G2.sortAsc', { col: t(col) });
}

function loadView(): string | null {
  try {
    return window.localStorage.getItem(VIEW_STORAGE_KEY);
  } catch {
    return null;
  }
}

function saveView(view: ViewMode): void {
  try {
    window.localStorage.setItem(VIEW_STORAGE_KEY, view);
  } catch {
    // 저장소 없음 — 무시(URL 이 기억한다)
  }
}

/**
 * G2 단지 찾기 `/complexes` (RA §7-1, R11 List·ListTable 보드)
 * 머리(h1 "{지역} 분양 단지 {n}곳" · 카드/표 · CSV) → FilterBar(URL 쿼리) → 표(TanStack Table + 가상 스크롤, 열 선택 저장)
 * 또는 카드(D30-10 점수 줄 포함) → 비교 바구니(2~6 → /compare?ids=). 기본 정렬 = 종합 점수(-total, D28-4).
 * 보기 방식은 URL `?view=`(바꿀 때 replace) + 이 브라우저에 기억. 휴대폰(읽기 전용)은 늘 카드.
 * CSV는 같은 필터·정렬로 서버가 만든다(complexesCsvRequest → Bearer fetch → 저장).
 * 목록은 첫 페이지(작게)를 먼저 그리고 나머지 페이지를 이어 받는다(useComplexesProgressive, W8·W9).
 */
export function ComplexesPage() {
  const { snapshotId, scenarioKey, asof, readOnly, isLoading } = usePageContext();
  const { region } = useActiveRegion();
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const sort = readSort(params);
  const view: ViewMode = readOnly ? 'cards' : readView(params, loadView());
  const listParams = useMemo(
    () => toListParams(filters, sort, scenarioKey),
    [filters, sort, scenarioKey],
  );
  const query = useComplexesProgressive(snapshotId, listParams, FIRST_PAGE_SIZE);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const globalSearch = useGlobalSearch();
  // '+10% 오를 가능성'의 목표 시점 = 지금 상황의 p10_horizon(고정 문구로 쓰지 않는다)
  const { data: scenarios = [] } = useScenarios();
  const scenario =
    scenarios.find((s) => String(keyOfScenario(s)) === scenarioKey) ?? scenarios[0] ?? null;
  const horizon = scenario?.policy.p10_horizon ?? null;
  const p10Target = horizon ? enumText('chart.C01.horizon', horizon) : null;

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
  const setView = useCallback(
    (value: ViewMode) => {
      saveView(value);
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set(VIEW_KEY, value);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  // URL 로 들어온 보기도 이 브라우저에 기억한다
  useEffect(() => {
    const fromUrl = params.get(VIEW_KEY);
    if (!readOnly && (fromUrl === 'cards' || fromUrl === 'table')) saveView(fromUrl);
  }, [params, readOnly]);
  const toggle = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < MAX_COMPARE) next.add(id);
      return next;
    });
  }, []);

  const csv = useDownload();
  const total = query.data?.total;
  const regionName = region?.name ?? null;

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <div className="flex min-w-0 flex-[1_1_480px] flex-col">
          <h1 className="text-xl font-bold leading-tight tracking-tight text-fg sm:text-[30px]">
            {total !== undefined && regionName ? (
              <>
                <span className="sr-only">{t('page.G2.title')} </span>
                <MetaText
                  kind="count"
                  k="page.G2.heading"
                  params={{ region: regionName, n: total }}
                />
              </>
            ) : (
              t('page.G2.title')
            )}
          </h1>
        </div>
        <span className="flex flex-wrap items-center gap-2">
          {readOnly ? null : <ViewToggle value={view} onChange={setView} />}
          {snapshotId ? (
            <span className="inline-flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={csv.pending}
                onClick={() => void csv.download(complexesCsvRequest(snapshotId, listParams))}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-border-strong bg-surface px-3.5 py-1.5 text-sm font-semibold text-fg disabled:opacity-50"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden
                >
                  <path d="M12 4v11" />
                  <path d="m7 10 5 5 5-5" />
                  <path d="M5 20h14" />
                </svg>
                {csv.pending ? t('download.pending') : t('page.G2.csv')}
              </button>
              {csv.error ? (
                <span role="alert" className="text-xs text-danger">
                  {specialErrorText(csv.error) ??
                    t('download.error', { detail: csv.error.message })}
                </span>
              ) : null}
            </span>
          ) : null}
        </span>
        {/* 휴대폰은 안내를 접는다(ListTable 보드 휴대폰 — 첫 화면에 카드 2장) */}
        <p className="w-full text-[15px] leading-relaxed text-muted mobile:hidden">
          {t('page.G2.intro')}
        </p>
      </div>
      <FilterBar
        values={filters}
        livingAreas={region?.living_areas ?? []}
        onChange={setFilter}
        onReset={resetFilters}
        mobile={readOnly}
        sort={view === 'cards' && !readOnly ? { value: sort, onChange: setSort } : undefined}
        terms={view === 'cards'}
      />
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>
          {(page) => {
            const countLine = (
              <p className="text-sm text-fg-2" aria-live="polite">
                <MetaText
                  kind="count"
                  className="font-semibold text-fg"
                  k="page.G2.count"
                  params={{ shown: page.items.length, total: page.total }}
                />
                <span className="text-muted">
                  {' · '}
                  <span data-testid="count-sort">{sortLabel(sort)}</span>
                </span>
                {query.loadingMore ? (
                  <span role="status" className="ml-2 text-accent">
                    {t('page.G2.loadingMore')}
                  </span>
                ) : null}
              </p>
            );
            if (page.items.length === 0) {
              return (
                <>
                  {countLine}
                  <Card
                    tone="subtle"
                    className="flex flex-col items-center gap-2 border-dashed py-8 text-center"
                  >
                    <p role="status" className="text-base font-semibold">
                      {t('page.G2.empty')}
                    </p>
                    <button
                      type="button"
                      onClick={resetFilters}
                      className="min-h-10 rounded-xl border border-border-strong bg-surface px-4 py-1.5 text-sm font-semibold"
                    >
                      {t('page.G2.clearFilters')}
                    </button>
                  </Card>
                </>
              );
            }
            if (view === 'cards') {
              // 휴대폰(≤768px, 읽기 전용)은 한 줄 카드, 데스크톱 카드 보기는 격자(List 보드)
              return (
                <>
                  {countLine}
                  <ComplexCards
                    rows={page.items}
                    total={page.total}
                    asof={asof ?? page.asof_date}
                    linkSearch={globalSearch}
                    variant={readOnly ? 'list' : 'grid'}
                    p10Target={p10Target}
                  />
                </>
              );
            }
            return (
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
                toolbar={countLine}
                p10Target={p10Target}
                reserveBottom={TRAY_RESERVE}
              />
            );
          }}
        </QueryState>
      )}
      {!readOnly && view === 'table' ? (
        <CompareTray
          ids={[...selected]}
          names={new Map((query.data?.items ?? []).map((r) => [r.complex_id, r.name]))}
          onRemove={toggle}
          onClear={() => setSelected(new Set())}
          search={globalSearch}
        />
      ) : null}
      <footer className="flex flex-col gap-1.5 border-t border-border pt-3 text-[13px] text-muted">
        <p>{t('page.G1.footNote')}</p>
        <ProvenanceLegend />
      </footer>
    </section>
  );
}

/** 보기 방식 '카드 · 표'(role=group, aria-pressed) */
function ViewToggle({ value, onChange }: { value: ViewMode; onChange: (v: ViewMode) => void }) {
  const item = (mode: ViewMode, icon: ReactNode) => (
    <button
      type="button"
      aria-pressed={value === mode}
      onClick={() => onChange(mode)}
      className={`inline-flex min-h-9 items-center gap-1.5 rounded-[9px] px-3 py-1 text-sm font-semibold ${
        value === mode ? 'bg-surface text-fg shadow-sm' : 'text-fg-2 hover:text-fg'
      }`}
    >
      {icon}
      {t(`page.G2.view.${mode}`)}
    </button>
  );
  const svg = {
    width: 16,
    height: 16,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  } as const;
  return (
    <div
      role="group"
      aria-label={t('page.G2.view.label')}
      className="inline-flex gap-1 rounded-xl bg-chip p-1"
    >
      {item(
        'cards',
        <svg {...svg}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>,
      )}
      {item(
        'table',
        <svg {...svg}>
          <path d="M3 5h18" />
          <path d="M3 12h18" />
          <path d="M3 19h18" />
        </svg>,
      )}
    </div>
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
      className="sticky bottom-10 z-10 flex flex-wrap items-center gap-2 rounded-2xl bg-toast px-4 py-2 text-toast-fg shadow-lg"
    >
      <span className="text-sm font-bold">{t('page.G2.tray')}</span>
      <MetaText
        kind="count"
        className="text-sm opacity-80"
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
            className="rounded-full bg-toast-fg/10 px-2.5 py-0.5 text-xs font-semibold"
            aria-label={t('page.common.remove', { name })}
          >
            {name} ×
          </button>
        );
      })}
      <span className="text-xs opacity-80">
        {ids.length >= MAX_COMPARE ? t('page.G2.trayMax') : t('page.G2.trayHint')}
      </span>
      <span className="ml-auto flex gap-2">
        {ids.length > 0 ? (
          <button
            type="button"
            onClick={onClear}
            className="min-h-9 rounded-xl border border-toast-fg/40 px-3 py-1 text-sm font-semibold"
          >
            {t('page.G2.clearSelection')}
          </button>
        ) : null}
        {ok ? (
          <Link
            to={href}
            className="inline-flex min-h-9 items-center gap-1 rounded-xl bg-accent px-4 py-1 text-sm font-semibold text-accent-fg"
          >
            {t('page.G2.compare')}
            <span aria-hidden>→</span>
          </Link>
        ) : (
          <button
            type="button"
            disabled
            className="min-h-9 rounded-xl bg-toast-fg/15 px-4 py-1 text-sm font-semibold opacity-70"
          >
            {t('page.G2.compare')}
          </button>
        )}
      </span>
    </aside>
  );
}
