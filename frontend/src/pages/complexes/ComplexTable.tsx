import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type VisibilityState,
} from '@tanstack/react-table';
import { observeElementRect, useVirtualizer, type Virtualizer } from '@tanstack/react-virtual';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import type { ComplexRow } from '@/api/types';
import { Badge, FactCell, IntakeBadge, TieBadge, UnstableBadge } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate, formatRank } from '@/lib/format';
import { enumText, JudgeScopeBadge } from '../_shared';
import { nextSort, type SortKey } from './params';

/** 열 선택 저장(브라우저별 편의 설정) */
export const COLUMN_STORAGE_KEY = 'sa.g2.columns';
const ROW_HEIGHT = 44;
/** jsdom·숨김 상태처럼 높이를 잴 수 없을 때 쓰는 뷰포트 */
const FALLBACK_RECT = { width: 1200, height: 560 };

type ColumnId =
  | 'select'
  | 'name'
  | 'living_area'
  | 'intake'
  | 'price'
  | 'resale_end'
  | 'move_in'
  | 'gap'
  | 'total'
  | 'p10'
  | 'inclusion'
  | 'land_type'
  | 'units_total'
  | 'down_payment'
  | 'last_change';

const SORT_OF: Partial<Record<ColumnId, SortKey>> = {
  name: 'name',
  living_area: 'living_area',
  price: 'price_mid',
  resale_end: 'resale_end',
  move_in: 'move_in_ym',
  gap: 'gap_pct',
  total: 'total',
  p10: 'p10',
  last_change: 'last_change',
};

/** 기본으로 숨기는 열(열 선택으로 켠다) */
const DEFAULT_HIDDEN: VisibilityState = {
  p10: false,
  land_type: false,
  units_total: false,
  down_payment: false,
};

function loadVisibility(): VisibilityState {
  try {
    const raw = window.localStorage.getItem(COLUMN_STORAGE_KEY);
    if (raw) return { ...DEFAULT_HIDDEN, ...(JSON.parse(raw) as VisibilityState) };
  } catch {
    // 저장소 없음 → 기본값
  }
  return DEFAULT_HIDDEN;
}

function saveVisibility(state: VisibilityState): void {
  try {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // 무시
  }
}

const colTitle = (id: ColumnId) => t(`page.G2.col.${id}` as TKey);

export interface ComplexTableProps {
  rows: ComplexRow[];
  total: number;
  asof: string | null;
  sort: string;
  onSort: (sort: string) => void;
  selected: ReadonlySet<number>;
  onToggle: (id: number) => void;
  maxSelected: number;
  readOnly: boolean;
  linkSearch: string;
}

/** G2 ComplexTable — TanStack Table + 가상 스크롤(react-virtual), 열 선택 저장 */
export function ComplexTable({
  rows,
  total,
  asof,
  sort,
  onSort,
  selected,
  onToggle,
  maxSelected,
  readOnly,
  linkSearch,
}: ComplexTableProps) {
  const [visibility, setVisibility] = useState<VisibilityState>(loadVisibility);
  useEffect(() => saveVisibility(visibility), [visibility]);

  const columns = useMemo<ColumnDef<ComplexRow>[]>(
    () => [
      {
        id: 'select',
        enableHiding: false,
        header: () => <span className="sr-only">{colTitle('select')}</span>,
        cell: ({ row }) => {
          const id = row.original.complex_id;
          const checked = selected.has(id);
          return (
            <input
              type="checkbox"
              data-write
              aria-label={t('page.G2.select', { name: row.original.name })}
              checked={checked}
              disabled={!checked && selected.size >= maxSelected}
              onChange={() => onToggle(id)}
            />
          );
        },
      },
      {
        id: 'name',
        enableHiding: false,
        header: () => colTitle('name'),
        cell: ({ row }) => (
          <Link
            to={`/complexes/${row.original.complex_id}${linkSearch}`}
            className="font-medium hover:underline"
          >
            {row.original.name}
          </Link>
        ),
      },
      {
        id: 'living_area',
        header: () => colTitle('living_area'),
        cell: ({ row }) => row.original.living_area_name ?? enumText('page.common', null),
      },
      {
        id: 'intake',
        header: () => colTitle('intake'),
        cell: ({ row }) => (
          <IntakeBadge intake={row.original.intake} asof={asof} showPath={false} />
        ),
      },
      {
        id: 'price',
        header: () => colTitle('price'),
        cell: ({ row }) => (
          <span className="inline-flex flex-wrap items-center gap-1">
            <FactCell fact={row.original.price_low} unit="eok" />
            <span aria-hidden>~</span>
            <FactCell fact={row.original.price_high} unit="eok" />
          </span>
        ),
      },
      {
        id: 'resale_end',
        header: () => colTitle('resale_end'),
        cell: ({ row }) => <FactCell fact={row.original.resale_end} unit="date" asof={asof} />,
      },
      {
        id: 'move_in',
        header: () => colTitle('move_in'),
        cell: ({ row }) => <FactCell fact={row.original.move_in_ym} unit="ym" />,
      },
      {
        id: 'gap',
        header: () => colTitle('gap'),
        cell: ({ row }) => <FactCell fact={row.original.gap_pct} unit="pct" />,
      },
      {
        id: 'total',
        header: () => colTitle('total'),
        cell: ({ row }) => (
          <span className="inline-flex flex-wrap items-center gap-1">
            <FactCell fact={row.original.total} unit="score" />
            {row.original.rank !== null ? (
              <Badge tone="neutral">{formatRank(row.original.rank)}</Badge>
            ) : null}
            <TieBadge tie={row.original.tie_group !== null} />
            <UnstableBadge unstable={row.original.unstable} />
            <JudgeScopeBadge scope={row.original.judge_scope} hideTarget />
          </span>
        ),
      },
      {
        id: 'p10',
        header: () => colTitle('p10'),
        cell: ({ row }) => <FactCell fact={row.original.p10} unit="prob" />,
      },
      {
        id: 'inclusion',
        header: () => colTitle('inclusion'),
        cell: ({ row }) => (
          <span className="inline-flex flex-wrap items-center gap-1">
            <span>{enumText('page.common.inclusion', row.original.inclusion_class)}</span>
            {row.original.inclusion_decision && row.original.inclusion_decision !== 'auto' ? (
              <Badge tone="muted">{enumText('page.common.status', 'review')}</Badge>
            ) : null}
          </span>
        ),
      },
      {
        id: 'land_type',
        header: () => colTitle('land_type'),
        cell: ({ row }) => <FactCell fact={row.original.land_type} unit="text" />,
      },
      {
        id: 'units_total',
        header: () => colTitle('units_total'),
        cell: ({ row }) => <FactCell fact={row.original.units_total} unit="households" />,
      },
      {
        id: 'down_payment',
        header: () => colTitle('down_payment'),
        cell: ({ row }) => <FactCell fact={row.original.down_payment_pct} unit="pct" digits={0} />,
      },
      {
        id: 'last_change',
        header: () => colTitle('last_change'),
        cell: ({ row }) => {
          const change = row.original.last_change;
          if (!change) return <span className="text-grayed">{t('page.common.none')}</span>;
          return (
            <span className="inline-flex flex-col">
              <span>{change.field}</span>
              <span className="text-xs text-muted">
                {formatDate(change.at, asof)} · {enumText('page.common.severity', change.severity)}
              </span>
            </span>
          );
        },
      },
    ],
    [asof, linkSearch, maxSelected, onToggle, selected],
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { columnVisibility: { ...visibility, select: !readOnly } },
    onColumnVisibilityChange: (updater) =>
      setVisibility((prev) => (typeof updater === 'function' ? updater(prev) : updater)),
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.complex_id),
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const tableRows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
    initialRect: FALLBACK_RECT,
    observeElementRect: (instance: Virtualizer<HTMLDivElement, Element>, cb) =>
      observeElementRect(instance, (rect) => cb(rect.height > 0 ? rect : FALLBACK_RECT)),
  });
  const items = virtualizer.getVirtualItems();
  const paddingTop = items[0]?.start ?? 0;
  const paddingBottom = items.length
    ? virtualizer.getTotalSize() - (items[items.length - 1]?.end ?? 0)
    : 0;
  const visibleColumns = table.getVisibleLeafColumns();

  return (
    <div className="flex flex-col gap-2">
      {!readOnly ? <ColumnChooser table={table} /> : null}
      <div
        ref={scrollRef}
        data-testid="complex-table-scroll"
        className="max-h-[70vh] overflow-auto rounded border border-border bg-surface"
      >
        <table
          aria-label={t('page.G2.table')}
          aria-rowcount={total + 1}
          className="w-full border-collapse text-sm"
        >
          <thead className="sticky top-0 z-10 bg-surface">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id} aria-rowindex={1}>
                {group.headers.map((header) => {
                  const sortKey = SORT_OF[header.column.id as ColumnId];
                  const title = flexRender(header.column.columnDef.header, header.getContext());
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      className="whitespace-nowrap border-b border-border px-2 py-1.5 text-left text-xs font-medium text-muted"
                      aria-sort={sortState(sort, sortKey)}
                    >
                      {sortKey ? (
                        <SortButton
                          title={title}
                          label={colTitle(header.column.id as ColumnId)}
                          state={sortState(sort, sortKey)}
                          onClick={() => onSort(nextSort(sort, sortKey))}
                        />
                      ) : (
                        title
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {paddingTop > 0 ? (
              <tr aria-hidden="true">
                <td colSpan={visibleColumns.length} style={{ height: paddingTop, padding: 0 }} />
              </tr>
            ) : null}
            {items.map((item) => {
              const row = tableRows[item.index];
              if (!row) return null;
              return (
                <tr
                  key={row.id}
                  data-index={item.index}
                  aria-rowindex={item.index + 2}
                  aria-selected={selected.has(row.original.complex_id) || undefined}
                  style={{ height: ROW_HEIGHT }}
                  className="hover:bg-bg"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="border-b border-border px-2 py-1 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
            {paddingBottom > 0 ? (
              <tr aria-hidden="true">
                <td colSpan={visibleColumns.length} style={{ height: paddingBottom, padding: 0 }} />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function sortState(sort: string, key: SortKey | undefined): 'ascending' | 'descending' | undefined {
  if (!key) return undefined;
  if (sort === key) return 'ascending';
  if (sort === `-${key}`) return 'descending';
  return undefined;
}

function SortButton({
  title,
  label,
  state,
  onClick,
}: {
  title: ReactNode;
  label: string;
  state: 'ascending' | 'descending' | undefined;
  onClick: () => void;
}) {
  const next =
    state === 'descending'
      ? t('page.G2.sortAsc', { col: label })
      : t('page.G2.sortDesc', { col: label });
  return (
    <button
      type="button"
      onClick={onClick}
      title={next}
      className="inline-flex items-center gap-1 hover:text-fg"
    >
      {title}
      <span aria-hidden>{state === 'ascending' ? '▲' : state === 'descending' ? '▼' : '↕'}</span>
    </button>
  );
}

function ColumnChooser({ table }: { table: ReturnType<typeof useReactTable<ComplexRow>> }) {
  return (
    <details className="self-end text-sm" data-write>
      <summary className="cursor-pointer rounded border border-border px-2 py-1">
        {t('page.G2.columns')}
      </summary>
      <fieldset className="mt-1 flex flex-wrap gap-3 rounded border border-border bg-surface p-2">
        <legend className="sr-only">{t('page.G2.columns')}</legend>
        {table
          .getAllLeafColumns()
          .filter((column) => column.getCanHide())
          .map((column) => (
            <label key={column.id} className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={column.getIsVisible()}
                onChange={column.getToggleVisibilityHandler()}
              />
              {colTitle(column.id as ColumnId)}
            </label>
          ))}
      </fieldset>
    </details>
  );
}
