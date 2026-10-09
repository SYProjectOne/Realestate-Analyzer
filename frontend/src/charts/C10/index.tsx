import { Badge } from '@/components/Badge';
import { UnstableBadge } from '@/components/UnstableBadge';
import { t } from '@/i18n';
import { formatRank } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { buildOption, emptyReason, toTable, variantRows } from './buildOption';
import type { C10Data } from './types';

export interface C10SensitivityProps {
  data: C10Data;
  height?: number;
}

/** C10 민감도 — HTML 표(12 변형 × TOP 5, 변동 없는 행 회색) + 작은 순위 선 (G4, G5) */
export function C10Sensitivity({ data, height = 240 }: C10SensitivityProps) {
  const palette = useChartPalette();
  const title = t('chart.C10.title');
  const s = data.sensitivity;
  const rows = variantRows(data);
  const width = Math.max(5, ...rows.map((r) => r.top5.length));
  const positions = Array.from({ length: width }, (_, i) => i + 1);
  return (
    <ChartFrame
      title={title}
      badges={
        <>
          <UnstableBadge unstable={s?.unstable ?? false} />
          {s && s.stable_components.length > 0 ? (
            <Badge tone="muted" data-testid="stable-badge">
              {t('chart.C10.stable')}
            </Badge>
          ) : null}
        </>
      }
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col" className="border-b border-border px-2 py-1 text-muted">
                {t('chart.col.variant')}
              </th>
              {positions.map((p) => (
                <th key={p} scope="col" className="border-b border-border px-2 py-1 text-muted">
                  {formatRank(p)}
                </th>
              ))}
              <th scope="col" className="border-b border-border px-2 py-1 text-muted">
                {t('chart.col.changed')}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.variant}
                className={row.stable ? 'text-grayed' : ''}
                data-stable={row.stable ? 'true' : undefined}
              >
                <th scope="row" className="whitespace-nowrap px-2 py-1 font-normal">
                  {row.label}
                </th>
                {positions.map((p) => {
                  const x = row.top5[p - 1];
                  const entered = x ? row.entered.includes(x.name) : false;
                  return (
                    <td
                      key={p}
                      className={`whitespace-nowrap px-2 py-1 ${entered ? 'font-semibold' : ''}`}
                    >
                      {x ? x.name : ''}
                      {x && x.rank !== null && x.rank !== p ? (
                        <span className="text-muted">{` (${formatRank(x.rank)})`}</span>
                      ) : null}
                    </td>
                  );
                })}
                <td className="min-w-56 px-2 py-1">
                  {row.changed
                    ? [
                        row.entered.length > 0
                          ? t('chart.C10.entered', { names: row.entered.join(', ') })
                          : null,
                        row.exited.length > 0
                          ? t('chart.C10.exited', { names: row.exited.join(', ') })
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ') || t('chart.yes')
                    : t('chart.no')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
