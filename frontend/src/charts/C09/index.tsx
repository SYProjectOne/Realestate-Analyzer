import { Badge } from '@/components/Badge';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { buildOption, emptyReason, groupByStage, stageLabel, toTable } from './buildOption';
import { C09_GRAYED, C09_STAGES, type C09Data } from './types';

export interface C09CatalystProps {
  data: C09Data;
  height?: number;
}

/** C9 호재 단계 — 단계 보드(HTML 5열) + 확정 호재 타임라인 (G6; G3는 compact) */
export function C09Catalyst({ data, height = 160 }: C09CatalystProps) {
  const palette = useChartPalette();
  const title = t('chart.C09.title');
  const groups = groupByStage(data.catalysts);
  return (
    <ChartFrame title={title} table={toTable(data)} emptyReason={emptyReason(data)}>
      <div className="grid grid-cols-5 gap-2 text-xs mobile:grid-cols-2">
        {C09_STAGES.map((stage) => {
          const grayed = C09_GRAYED.includes(stage);
          return (
            <div key={stage} className="flex flex-col gap-1">
              <Badge tone={grayed ? 'muted' : 'neutral'}>{stageLabel(stage)}</Badge>
              <ul className={`flex flex-col gap-1 ${grayed ? 'text-grayed' : ''}`}>
                {groups[stage].map((c) => (
                  <li key={c.id}>
                    <span>{c.name}</span>
                    {!c.location_confirmed ? (
                      <span className="block text-[10px] text-grayed">{t('chart.C09.noLink')}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {data.compact ? null : (
        <EChart
          option={buildOption(data, { palette })}
          height={height}
          ariaLabel={t('chart.C09.timeline')}
        />
      )}
    </ChartFrame>
  );
}
