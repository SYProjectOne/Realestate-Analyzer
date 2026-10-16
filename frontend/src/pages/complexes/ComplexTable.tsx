import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type Column,
  type ColumnDef,
  type HeaderGroup,
  type Row,
  type VisibilityState,
} from '@tanstack/react-table';
import {
  observeElementRect,
  useVirtualizer,
  type Range,
  type Virtualizer,
} from '@tanstack/react-virtual';
import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Link } from 'react-router';
import type { ComplexRow } from '@/api/types';
import {
  Badge,
  FactCell,
  MetaText,
  IntakeBadge,
  MetaValue,
  Term,
  TieBadge,
  UnstableBadge,
  type GlossaryKey,
} from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { metaText } from '@/lib/meta';
import {
  changeFieldText,
  enumText,
  JudgeScopeBadge,
  NameLabelBadge,
  RejudgeNeededBadge,
  ScopeReason,
} from '../_shared';
import { nextSort, type SortKey } from './params';

/** 열 선택 저장(브라우저별 편의 설정) */
export const COLUMN_STORAGE_KEY = 'sa.g2.columns';
const ROW_HEIGHT = 44;
/** 이 행 수 이하면 가상 스크롤 창 밖 행도 전부 그린다(overscan = 행 수) */
const SMALL_LIST = 50;
/** jsdom·숨김 상태처럼 높이를 잴 수 없을 때 쓰는 뷰포트 */
const FALLBACK_RECT = { width: 1200, height: 560 };
/** R8-JITTER: 맨 위 행이 그대로인 동안 실측 때문에 줄어든 범위를 붙잡아 두는 최대 행 수(앞뒤 각각) */
export const RANGE_HOLD = 2;

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
  | 'down_payment_won'
  | 'competition'
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
  intake: 'intake',
};

/** 열 제목 옆 용어 ⓘ(R9-UI P6 — 표는 열 제목에만) */
const TERM_OF: Partial<Record<ColumnId, GlossaryKey>> = {
  living_area: 'living_area',
  intake: 'intake_status',
  price: 'current_price',
  down_payment: 'down',
  resale_end: 'resale_end',
  gap: 'gap',
  total: 'total',
  p10: 'p10',
  inclusion: 'inclusion',
};

/**
 * 기본으로 숨기는 열(열 선택으로 켠다) — R9-UI P4(D28-4): 기본 8열(단지·접수·구매가·계약금 비율·전매 종료·입주·가격 갭·종합 점수).
 * 생활권은 단지 이름 아래 줄로 옮겼고(열은 열 선택으로 켜면 정렬 가능), +10%·단지 분류·택지·총 세대·마지막 변경은 열 선택 1클릭.
 */
export const DEFAULT_HIDDEN: VisibilityState = {
  living_area: false,
  p10: false,
  inclusion: false,
  land_type: false,
  units_total: false,
  last_change: false,
  competition: false,
  down_payment_won: false,
};

/** 저장 형식 버전 — 2 = R9-UI 기본 8열 */
const STORAGE_VERSION = 2;
/** 버전 없는 예전 저장값의 기본(그 값과 같은 항목은 사용자가 바꾼 것이 아니다) */
const LEGACY_DEFAULT: VisibilityState = {
  p10: false,
  land_type: false,
  units_total: false,
  down_payment: false,
};

/**
 * 저장된 열 선택 읽기. 예전 저장값(버전 없음)은 예전 기본과 다른 항목(= 사용자가 바꾼 열)만 남기고 새 기본을 따른다 —
 * 예전 기본이 통째로 저장돼 있어 그대로 덮으면 새 기본(계약금 비율 표시·단지 분류 숨김)이 적용되지 않는다.
 */
export function readVisibility(raw: string | null): VisibilityState {
  if (!raw) return DEFAULT_HIDDEN;
  const parsed = JSON.parse(raw) as Record<string, unknown>;
  const out: VisibilityState = { ...DEFAULT_HIDDEN };
  const legacy = parsed.v !== STORAGE_VERSION;
  for (const [key, value] of Object.entries(parsed)) {
    if (key === 'v' || typeof value !== 'boolean') continue;
    const legacyDefault = LEGACY_DEFAULT[key] ?? true;
    if (legacy && value === legacyDefault) continue;
    out[key] = value;
  }
  return out;
}

function loadVisibility(): VisibilityState {
  try {
    return readVisibility(window.localStorage.getItem(COLUMN_STORAGE_KEY));
  } catch {
    // 저장소 없음·깨진 값 → 기본값
    return DEFAULT_HIDDEN;
  }
}

function saveVisibility(state: VisibilityState): void {
  try {
    window.localStorage.setItem(
      COLUMN_STORAGE_KEY,
      JSON.stringify({ v: STORAGE_VERSION, ...state }),
    );
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
  /** 개수 줄(표 위 왼쪽) — 오른쪽에는 '보여 줄 열 고르기' */
  toolbar?: ReactNode;
  /** '10% 넘게 오를 가능성' 열 머리 둘째 줄의 목표 시점(상황 p10_horizon, LT-7) */
  p10Target?: string | null;
  /**
   * 창 아래에서 비워 둘 높이(px) — 하단 고정 문구 + 비교 트레이(R9-UI P4: 트레이가 표 마지막 보이는 행을 덮던 결함).
   * 표 스크롤 영역 높이 = 창 높이 − 표 위치 − 이 값(최소 MIN_TABLE_HEIGHT).
   */
  reserveBottom?: number;
}

/** 표 스크롤 영역 최소 높이(px) */
const MIN_TABLE_HEIGHT = 320;

/**
 * 표 스크롤 영역 높이를 창 안에 맞춘다(첫 화면에서 아래 끝이 트레이·고정 문구 위). 값은 표 위치·창 높이에만 기대므로
 * 행 높이 실측과 되먹임이 없다(R8-JITTER). ResizeObserver 가 없으면(jsdom) 기존 70vh.
 */
function useFitHeight(ref: { current: HTMLElement | null }, reserve: number): number | null {
  const [height, setHeight] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const update = () => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      setHeight(Math.max(MIN_TABLE_HEIGHT, Math.round(window.innerHeight - top - reserve)));
    };
    update();
    const ro = new ResizeObserver(update);
    // 위쪽(필터 펼침·안내)이 바뀌면 표 위치가 바뀐다 — 화면 구역을 본다
    const host = el.closest('section') ?? document.body;
    ro.observe(host);
    window.addEventListener('resize', update);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [ref, reserve]);
  return height;
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
  toolbar,
  p10Target = null,
  reserveBottom = 48,
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
          <span className="inline-flex min-w-36 flex-col">
            <span className="inline-flex flex-wrap items-center gap-1">
              <Link
                to={`/complexes/${row.original.complex_id}${linkSearch}`}
                className="font-medium hover:underline"
              >
                {row.original.name}
              </Link>
              {/* 계약 .16 F1(D21-8): 이름 출처 라벨(공고 예정 후보 '비공식') → 출처 서랍. 키가 없으면 그리지 않는다 */}
              <NameLabelBadge
                source={row.original}
                testId={`name-prov-${row.original.complex_id}`}
              />
            </span>
            {/* R9-UI P4: 생활권은 이름 아래 줄(같은 행) */}
            <span data-testid="name-living-area" className="text-xs text-muted">
              {row.original.living_area_name ?? enumText('page.common', null)}
            </span>
          </span>
        ),
      },
      {
        id: 'intake',
        header: () => colTitle('intake'),
        cell: ({ row }) => (
          <IntakeBadge intake={row.original.intake} asof={asof} showPath={false} reasonBelow />
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
        id: 'down_payment',
        header: () => colTitle('down_payment'),
        cell: ({ row }) => <FactCell fact={row.original.down_payment_pct} unit="pct" digits={0} />,
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
              <Badge tone="neutral">
                <MetaValue kind="rank" value={row.original.rank} as="rank" />
              </Badge>
            ) : null}
            <TieBadge tie={row.original.tie_group !== null} />
            <UnstableBadge unstable={row.original.unstable} />
            <JudgeScopeBadge scope={row.original.judge_scope} hideTarget />
            <RejudgeNeededBadge needed={row.original.rejudge_needed} />
          </span>
        ),
      },
      {
        id: 'living_area',
        header: () => colTitle('living_area'),
        cell: ({ row }) => row.original.living_area_name ?? enumText('page.common', null),
      },
      {
        id: 'p10',
        // LT-7: 목표 시점 · 당첨 확률 아님 · 보장 아님(둘째 줄)
        header: () => (
          <span className="inline-flex flex-col items-start">
            <span>{colTitle('p10')}</span>
            <span className="text-[11px] font-normal">
              {t('page.G1.p10Target', { target: p10Target ?? t('empty.unknown') })} ·{' '}
              {t('page.G1.p10Note')}
            </span>
          </span>
        ),
        cell: ({ row }) => <FactCell fact={row.original.p10} unit="prob" />,
      },
      {
        id: 'inclusion',
        header: () => colTitle('inclusion'),
        cell: ({ row }) => (
          <span className="inline-flex flex-col">
            <span className="inline-flex flex-wrap items-center gap-1">
              <span>{enumText('page.common.inclusion', row.original.inclusion_class)}</span>
              {row.original.inclusion_decision && row.original.inclusion_decision !== 'auto' ? (
                <Badge tone="muted">{enumText('page.common.status', 'review')}</Badge>
              ) : null}
            </span>
            {/* 계약 .17 F1(D22-5): 판정 범위 사유 — 서버 문자열 그대로, 키 없으면 없음 */}
            <ScopeReason
              reason={row.original.judge_scope_reason}
              rejudgeNeeded={row.original.rejudge_needed}
              testId={`scope-reason-${row.original.complex_id}`}
              compact
              className="max-w-56 truncate text-xs text-muted"
            />
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
        id: 'down_payment_won',
        header: () => colTitle('down_payment_won'),
        // 계약 .20 F1: 계약금 원 금액(서버 산술 Fact — P_mid × 계약금 %). 라벨이 길어 기본 숨김(열 선택 1클릭)
        cell: ({ row }) => (
          <span data-testid={`down-won-${row.original.complex_id}`}>
            <FactCell fact={row.original.down_payment_won ?? null} unit="won" />
          </span>
        ),
      },
      {
        id: 'competition',
        header: () => colTitle('competition'),
        // 계약 .20 F2: 1순위 해당지역 최고 경쟁률(서버 산술)·그 주택형
        cell: ({ row }) => {
          const summary = row.original.competition_summary;
          if (!summary) return <FactCell fact={null} unit="ratio" />;
          return (
            <span className="inline-flex flex-wrap items-center gap-1">
              <FactCell fact={summary.max_ratio} unit="ratio" digits={2} />
              {summary.max_ratio_type_code ? (
                <span className="text-xs text-muted">{summary.max_ratio_type_code}</span>
              ) : null}
            </span>
          );
        },
      },
      {
        id: 'last_change',
        header: () => colTitle('last_change'),
        cell: ({ row }) => {
          const change = row.original.last_change;
          if (!change) return <span className="text-grayed">{t('page.common.none')}</span>;
          return (
            <span className="inline-flex flex-col">
              <span>{changeFieldText(change.field)}</span>
              <span className="text-xs text-muted">
                {formatDate(change.at, asof)} · {enumText('page.common.severity', change.severity)}
              </span>
            </span>
          );
        },
      },
    ],
    [asof, linkSearch, maxSelected, onToggle, selected, p10Target],
  );

  // 상태 객체를 렌더마다 새로 만들지 않는다 — 표 내부 memo(보이는 열·행 셀)가 참조로 비교한다(T16 행 memo 유지)
  const columnVisibility = useMemo(
    () => ({ ...visibility, select: !readOnly }),
    [visibility, readOnly],
  );
  const table = useReactTable({
    data: rows,
    columns,
    state: { columnVisibility },
    onColumnVisibilityChange: (updater) =>
      setVisibility((prev) => (typeof updater === 'function' ? updater(prev) : updater)),
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.complex_id),
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const fitHeight = useFitHeight(scrollRef, reserveBottom);
  const tableRows = table.getRowModel().rows;
  const rangeExtractor = useHeldRange();
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    // R5-FE3: 긴 목록은 창 앞뒤 2행(실측 행 ~90px ≈ 180px). 짧은 목록(≤ SMALL_LIST)은 전부 그린다 — 예전처럼 모든 행이 DOM 에 있다
    overscan: tableRows.length <= SMALL_LIST ? tableRows.length : 2,
    // 맨 끝까지 내린 상태에서 끝 행들이 추정(44px)보다 크게 재지면 끝에 붙어 있게(마지막 행이 창 밖으로 밀리지 않게)
    anchorTo: 'end',
    initialRect: FALLBACK_RECT,
    observeElementRect: (instance: Virtualizer<HTMLDivElement, Element>, cb) =>
      observeElementRect(instance, (rect) => cb(rect.height > 0 ? rect : FALLBACK_RECT)),
    measureElement: measureRow,
    // R8-JITTER: 실측 → 범위 → 열 너비 → 실측 되먹임 끊기(useHeldRange)
    rangeExtractor,
  });
  const items = virtualizer.getVirtualItems();
  const paddingTop = items[0]?.start ?? 0;
  const paddingBottom = items.length
    ? virtualizer.getTotalSize() - (items[items.length - 1]?.end ?? 0)
    : 0;
  const visibleColumns = table.getVisibleLeafColumns();

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {toolbar ?? <span />}
        {!readOnly ? <ColumnChooser table={table} visibility={columnVisibility} /> : null}
      </div>
      <div
        ref={scrollRef}
        data-testid="complex-table-scroll"
        className="max-h-[70vh] overflow-auto rounded-2xl border border-border bg-surface"
        style={fitHeight !== null ? { maxHeight: fitHeight } : undefined}
      >
        <table
          aria-label={t('page.G2.table')}
          aria-rowcount={total + 1}
          className="w-full border-collapse text-sm"
        >
          <TableHead groups={table.getHeaderGroups()} sort={sort} onSort={onSort} />
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
                <VirtualRow
                  key={row.id}
                  row={row}
                  index={item.index}
                  selected={selected.has(row.original.complex_id)}
                  measureRef={virtualizer.measureElement}
                  columns={columns}
                  visibleColumns={visibleColumns}
                />
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

/** 머리줄 — 스크롤 프레임마다 다시 그리지 않는다(정렬·열 선택이 바뀔 때만, T16) */
const TableHead = memo(function TableHead({
  groups,
  sort,
  onSort,
}: {
  groups: HeaderGroup<ComplexRow>[];
  sort: string;
  onSort: (sort: string) => void;
}) {
  return (
    <thead className="sticky top-0 z-10 bg-surface-2">
      {groups.map((group) => (
        <tr key={group.id} aria-rowindex={1}>
          {group.headers.map((header) => {
            const sortKey = SORT_OF[header.column.id as ColumnId];
            const term = TERM_OF[header.column.id as ColumnId];
            const title = flexRender(header.column.columnDef.header, header.getContext());
            return (
              <th
                key={header.id}
                scope="col"
                data-col={header.column.id}
                className="whitespace-nowrap border-b border-border px-2.5 py-2 text-left align-bottom text-xs font-semibold text-fg-2"
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
                {term ? <Term k={term} className="ml-0.5 align-middle" /> : null}
              </th>
            );
          })}
        </tr>
      ))}
    </thead>
  );
});

/**
 * 가상 스크롤 한 행. T16(D10-8) 렌더 비용: 스크롤 프레임마다 표가 다시 그려져도 **창 안에 남은 행은 다시 렌더하지
 * 않는다**(memo — 행 데이터·선택·열 정의·보이는 열이 같으면 그대로). 프레임마다 새로 들어오는 몇 행만 그린다.
 */
const VirtualRow = memo(function VirtualRow({
  row,
  index,
  selected,
  measureRef,
}: {
  row: Row<ComplexRow>;
  index: number;
  selected: boolean;
  /** 실제 행 높이를 가상 스크롤에 알린다(virtualizer.measureElement — 인스턴스 메서드라 렌더마다 같다) */
  measureRef: (node: HTMLTableRowElement | null) => void;
  /** 셀 렌더러(선택 상태·기준일·링크를 닫아 둔다) — 바뀌면 행을 다시 그린다 */
  columns: readonly ColumnDef<ComplexRow>[];
  /** 열 선택 — 바뀌면 행을 다시 그린다 */
  visibleColumns: readonly Column<ComplexRow>[];
}) {
  return (
    <tr
      ref={measureRef}
      data-index={index}
      aria-rowindex={index + 2}
      aria-selected={selected || undefined}
      style={{ height: ROW_HEIGHT }}
      className={selected ? 'bg-accent-soft' : 'hover:bg-subtle'}
    >
      {row.getVisibleCells().map((cell) => (
        <td key={cell.id} className="border-b border-border px-2.5 py-1 align-middle">
          {flexRender(cell.column.columnDef.cell, cell.getContext())}
        </td>
      ))}
    </tr>
  );
});

export interface HeldRange {
  /** 창 맨 위 행(overscan 제외) */
  top: number;
  /** 창 맨 아래 행(overscan 제외) */
  bottom: number;
  count: number;
  start: number;
  end: number;
}

/**
 * 그린 행 범위 고르기(rangeExtractor) — 기본(창 ± overscan)에 **히스테리시스**를 더한다.
 *
 * R8-JITTER 원인: 이 표는 열 너비를 그린 행들의 내용으로 정한다(auto table layout — 모양 유지를 위해 fixed 로 바꾸지 않는다).
 * 그린 범위에 행 하나가 들고 나면 열 너비 → 줄바꿈 → 실측 행 높이가 바뀌고, 그 높이로 다시 계산한 범위가 다시 행 하나를
 * 빼거나 넣어, 입력이 없어도 두 배치를 매 프레임 오갈 수 있다(실데이터 101단지 · 1800×980 에서 12행 ↔ 13행, 가운데에서는
 * 위쪽 행 높이 보정으로 scrollTop 까지 흔들림). 고정점이 없는 되먹임이다.
 *
 * 끊는 법: **창의 기준 행과 행 수가 그대로인 동안** 실측 때문에 줄어든 범위는 앞뒤 각각 최대 RANGE_HOLD 행까지 이전 범위를
 * 유지한다(넓어지는 건 바로 따른다). 범위가 줄지 않으니 되먹임이 한 방향으로만 움직여 몇 프레임 안에 멈춘다. 기준 행은 가상
 * 스크롤의 자체 보정이 지키는 행이다 — 보통은 창 맨 위 행(위쪽 행 높이 보정이 맨 위 행 화면 위치를 지킨다), 마지막 행이 창에
 * 있으면 마지막 행(anchorTo 'end' 가 끝에 붙여 두느라 전체 높이가 바뀌면 scrollTop·맨 위 행이 움직인다). 기준 행이 바뀌면
 * (= 사용자 스크롤) 붙잡은 범위를 버린다 — 스크롤 중 DOM 행 수는 그대로.
 */
export function nextHeldRange(prev: HeldRange | null, range: Range): HeldRange {
  const { startIndex, endIndex, overscan, count } = range;
  let start = Math.max(startIndex - overscan, 0);
  let end = Math.min(endIndex + overscan, count - 1);
  const sameAnchor =
    prev !== null &&
    prev.count === count &&
    (prev.top === startIndex || (prev.bottom === count - 1 && endIndex === count - 1));
  if (prev && sameAnchor) {
    start = Math.max(Math.min(start, prev.start), start - RANGE_HOLD, 0);
    end = Math.min(Math.max(end, prev.end), end + RANGE_HOLD, count - 1);
  }
  return { top: startIndex, bottom: endIndex, count, start, end };
}

/** nextHeldRange 를 가상 스크롤 rangeExtractor 로(직전 범위는 ref — 렌더마다 같은 함수라 가상 스크롤 memo 유지) */
function useHeldRange(): (range: Range) => number[] {
  const held = useRef<HeldRange | null>(null);
  return useCallback((range: Range) => {
    const next = nextHeldRange(held.current, range);
    held.current = next;
    const indexes: number[] = [];
    for (let i = next.start; i <= next.end; i += 1) indexes.push(i);
    return indexes;
  }, []);
}

/** 행 실제 높이(ResizeObserver border-box, 없으면 getBoundingClientRect). jsdom·숨김처럼 0 이면 추정값 */
function measureRow(el: Element, entry: ResizeObserverEntry | undefined): number {
  const size = entry?.borderBoxSize[0]?.blockSize ?? el.getBoundingClientRect().height;
  return size > 0 ? size : ROW_HEIGHT;
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
      className="inline-flex items-center gap-1 text-left hover:text-fg"
    >
      {title}
      {/* 정렬 안 함(둘 다 흐림) · 작은 값부터(위 삼각형) · 큰 값부터(아래 삼각형) */}
      <svg width="10" height="12" viewBox="0 0 12 14" aria-hidden className="shrink-0">
        <path
          d="M6 1 10 5.5H2z"
          className={state === 'ascending' ? 'fill-accent' : 'fill-grayed'}
          data-sort-up={state === 'ascending' || undefined}
        />
        <path
          d="M6 13 2 8.5h8z"
          className={state === 'descending' ? 'fill-accent' : 'fill-grayed'}
          data-sort-down={state === 'descending' || undefined}
        />
      </svg>
    </button>
  );
}

/** 열 선택 — 표 인스턴스는 그대로라 보이는 열(visibility)이 바뀔 때만 다시 그린다(T16) */
const ColumnChooser = memo(function ColumnChooser({
  table,
}: {
  table: ReturnType<typeof useReactTable<ComplexRow>>;
  visibility: VisibilityState;
}) {
  const hideable = table.getAllLeafColumns().filter((column) => column.getCanHide());
  const on = hideable.filter((column) => column.getIsVisible()).length;
  return (
    <details className="relative text-sm" data-write>
      <summary className="inline-flex min-h-9 cursor-pointer items-center rounded-[10px] border border-border-strong bg-surface px-3 py-1 font-semibold text-fg-2">
        <MetaText kind="count" k="page.G2.columns" params={{ n: on }} />
      </summary>
      <div className="absolute right-0 z-20 mt-1 flex w-[min(640px,90vw)] flex-col gap-2 rounded-xl border border-border bg-surface p-3 shadow-lg">
        <p className="text-xs text-muted">{t('page.G2.columnsHint')}</p>
        <fieldset className="flex flex-wrap gap-x-4 gap-y-2">
          <legend className="sr-only">{metaColumnsLegend(on)}</legend>
          {hideable.map((column) => (
            <label key={column.id} className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={column.getIsVisible()}
                onChange={column.getToggleVisibilityHandler()}
              />
              {colTitle(column.id as ColumnId)}
              {column.getIsVisible() ? null : (
                <span aria-hidden className="text-[11px] text-muted">
                  {t('page.G2.columnHidden')}
                </span>
              )}
            </label>
          ))}
        </fieldset>
      </div>
    </details>
  );
});

/** 열 고르기 묶음 이름(스크린리더) — 켜진 열 개수는 메타 */
function metaColumnsLegend(n: number): string {
  return metaText('page.G2.columns', { n });
}
