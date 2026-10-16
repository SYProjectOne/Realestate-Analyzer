import { useId, useState, type ReactNode } from 'react';
import type { DataCell, DataColumn, DataTable } from '@/components/DataTableToggle';
import { EmptyState } from '@/components/EmptyState';
import { FactCell } from '@/components/FactCell';
import { MetaValue } from '@/components/MetaValue';
import { t } from '@/i18n';
import type { FactLike } from '@/lib/contract';
import type { IsoDate } from '@/lib/format';

const isFact = (cell: DataCell): cell is FactLike =>
  typeof cell === 'object' && cell !== null && 'label' in cell && 'v' in cell;

/** 셀: Fact(라벨·출처 — 누르면 출처 창) > 숫자(차트 파생값) > 글자 > 빈 값 '확인 불가' (DataTableToggle과 같은 규칙) */
function Cell({
  cell,
  column,
  asof,
}: {
  cell: DataCell;
  column: DataColumn;
  asof?: IsoDate | null;
}) {
  if (cell === null || cell === undefined) return <EmptyState inline />;
  if (isFact(cell)) return <FactCell fact={cell} unit={column.unit} asof={asof} />;
  if (typeof cell === 'number')
    return <MetaValue kind="derived" value={cell} as={column.unit ?? 'number'} />;
  return <span>{cell}</span>;
}

export interface ChartFooterProps {
  /** "표로 보기" 표. 생략하면 버튼 없음 */
  table?: DataTable;
  /** 표 이름(차트 제목) — caption "{제목} 데이터" */
  caption: string;
  /** 바닥줄 왼쪽 "자료: 출처 · 기준일" */
  source?: ReactNode;
  asof?: IsoDate | null;
}

/**
 * 차트 바닥줄(Shell §8): 왼쪽 "자료: 출처 · 기준일", 오른쪽 [표로 보기]. 누르면 바로 아래 표가 펼쳐지고 버튼은 '표 닫기'.
 * 표 이름(caption)은 "{차트 제목} 데이터", 줄이 없으면 열 머리 아래 "데이터 없음" 한 줄.
 */
export function ChartFooter({ table, caption, source, asof }: ChartFooterProps) {
  const [open, setOpen] = useState(false);
  const regionId = useId();
  if (!table && !source) return null;
  return (
    <div className="flex flex-col gap-2 text-sm" data-testid="chart-footer">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        {source ? <span data-testid="chart-source">{source}</span> : <span />}
        {table ? (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={regionId}
            onClick={() => setOpen((prev) => !prev)}
            className="min-h-8 rounded-lg border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-fg hover:border-accent"
          >
            {open ? t('table.hide') : t('table.show')}
          </button>
        ) : null}
      </div>
      {table && open ? (
        <div id={regionId} className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[13px] tabular-nums">
            <caption className="caption-top pb-1 text-left text-xs text-muted">
              {t('table.caption', { title: caption })}
            </caption>
            <thead>
              <tr>
                {table.columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className="border-b border-border bg-bg px-2.5 py-2 font-semibold text-fg"
                  >
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={Math.max(1, table.columns.length)}
                    className="px-2.5 py-2.5 text-center text-muted"
                    data-testid="chart-table-empty"
                  >
                    {t('empty.noData')}
                  </td>
                </tr>
              ) : (
                table.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="border-b border-border/50">
                    {table.columns.map((column) => (
                      <td key={column.key} className="px-2.5 py-2">
                        <Cell cell={row[column.key]} column={column} asof={asof} />
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
