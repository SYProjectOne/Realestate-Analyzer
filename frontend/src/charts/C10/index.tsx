import { UnstableBadge } from '@/components/UnstableBadge';
import { t } from '@/i18n';
import { formatRank } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { buildOption, emptyReason, toTable } from './buildOption';
import type { C10Data } from './types';

export interface C10SensitivityProps {
  data: C10Data;
  height?: number;
}

/** C10 민감도 — HTML 표(변형 × TOP 5, 변동 없는 행 회색) + 작은 순위 선 (G4, G5) */
export function C10Sensitivity({ data, height = 200 }: C10SensitivityProps) {
  const palette = useChartPalette();
  const title = t('chart.C10.title');
  const s = data.sensitivity;
  return (
    <ChartFrame
      title={title}
      badges={<UnstableBadge unstable={s?.unstable ?? false} />}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead>
            <tr>
              <th scope="col" className="border-b border-border px-2 py-1 text-muted">
                {t('chart.col.variant')}
              </th>
              {(s?.baseline_top5 ?? []).map((b) => (
                <th
                  key={b.complex_id}
                  scope="col"
                  className="border-b border-border px-2 py-1 text-muted"
                >
                  {formatRank(b.rank)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(s?.cells ?? []).map((cell) => (
              <tr key={cell.variant} className={cell.changed ? '' : 'text-grayed'}>
                <th scope="row" className="px-2 py-1 font-normal">
                  {cell.variant}
                </th>
                {[...cell.top5]
                  .sort((a, b) => a.rank - b.rank)
                  .map((x) => (
                    <td key={x.complex_id} className="px-2 py-1">
                      {x.name}
                    </td>
                  ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
    </ChartFrame>
  );
}
