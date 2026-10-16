import { useId, useState } from 'react';
import { t } from '@/i18n';
import type { FactLike } from '@/lib/contract';
import type { FactUnit, IsoDate } from '@/lib/format';
import { EmptyState } from './EmptyState';
import { FactCell } from './FactCell';
import { MetaValue } from './MetaValue';

export interface DataColumn {
  key: string;
  /** 열 머리(ko.json에서 온 문자열) */
  header: string;
  /** 숫자·Fact 셀의 단위. 생략하면 'number' */
  unit?: FactUnit;
}

/** 셀: Fact(라벨·출처 포함) > 숫자(차트 파생값, unit으로 포맷) > 문자열 > 빈 값 */
export type DataCell = FactLike | number | string | null | undefined;

export interface DataTable {
  columns: DataColumn[];
  rows: Record<string, DataCell>[];
}

export interface DataTableToggleProps {
  table: DataTable;
  /** 표 caption(차트 제목). 접근성 이름에도 쓴다 */
  caption: string;
  defaultOpen?: boolean;
  /** 날짜 D± 기준일 */
  asof?: IsoDate | null;
  /** Fact 셀 클릭 → 출처 패널. 생략하면 전역 ProvenancePanel */
  onOpenProvenance?: (prov: string) => void;
}

const isFact = (cell: DataCell): cell is FactLike =>
  typeof cell === 'object' && cell !== null && 'label' in cell && 'v' in cell;

function Cell({
  cell,
  column,
  asof,
  onOpenProvenance,
}: {
  cell: DataCell;
  column: DataColumn;
  asof?: IsoDate | null;
  onOpenProvenance?: (prov: string) => void;
}) {
  if (cell === null || cell === undefined) return <EmptyState inline />;
  if (isFact(cell)) {
    return (
      <FactCell fact={cell} unit={column.unit} asof={asof} onOpenProvenance={onOpenProvenance} />
    );
  }
  if (typeof cell === 'number')
    // 차트 파생값(라벨 없는 숫자) — 비수치 메타로 표시한다. 사실은 Fact 셀로 온다.
    return <MetaValue kind="derived" value={cell} as={column.unit ?? 'number'} />;
  return <span>{cell}</span>;
}

/** "표로 보기" 토글 — D7 "차트 데이터는 표로 열어볼 수 있음". 모든 차트가 ChartFrame을 통해 쓴다. */
export function DataTableToggle({
  table,
  caption,
  defaultOpen = false,
  asof,
  onOpenProvenance,
}: DataTableToggleProps) {
  const [open, setOpen] = useState(defaultOpen);
  const regionId = useId();
  return (
    <div className="text-sm">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex min-h-8 items-center rounded-lg border border-border-strong bg-surface px-2.5 py-1 text-xs font-medium text-fg-2 hover:border-fg-2 hover:text-fg focus:outline-hidden focus-visible:ring-2 focus-visible:ring-accent"
      >
        {open ? t('table.hide') : t('table.show')}
      </button>
      {open ? (
        <div id={regionId} className="mt-2 overflow-x-auto">
          <table className="w-full border-collapse text-left text-[13px]">
            {/* 목업 §8(SH-18): 표 이름을 표 위에 작게 — 화면 낭독기도 같은 이름을 읽는다 */}
            <caption className="caption-top pb-1 text-left text-xs text-muted">
              {t('table.caption', { title: caption })}
            </caption>
            <thead>
              <tr className="bg-subtle">
                {table.columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className="border-b border-border px-2.5 py-2 font-medium text-muted"
                  >
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {table.rows.length === 0 ? (
                // 줄이 하나도 없으면 머리는 두고 '데이터 없음' 한 줄(SH-18 #284)
                <tr>
                  <td
                    colSpan={Math.max(1, table.columns.length)}
                    className="px-2.5 py-3 text-center text-muted"
                    data-testid="table-empty"
                  >
                    {t('empty.noData')}
                  </td>
                </tr>
              ) : (
                table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-b border-border last:border-b-0">
                    {table.columns.map((column) => (
                      <td key={column.key} className="px-2.5 py-2 align-top">
                        <Cell
                          cell={row[column.key]}
                          column={column}
                          asof={asof}
                          onOpenProvenance={onOpenProvenance}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
