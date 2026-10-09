import { Badge } from '@/components/Badge';
import { FactCell } from '@/components/FactCell';
import { MetaText } from '@/components/MetaValue';
import { t } from '@/i18n';
import { ChartFrame } from '../ChartFrame';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import { collectLabels } from '../util';
import {
  buildOption,
  emptyReason,
  excludedCatalysts,
  groupByStage,
  stageLabel,
  timelineItems,
  toTable,
} from './buildOption';
import { C09_GRAYED, C09_STAGES, type C09Data } from './types';

export interface C09CatalystProps {
  data: C09Data;
  height?: number;
}

/** C9 호재 단계 — 단계 보드(HTML 5열) + 확정 호재 타임라인 (G6; G3는 compact). 언론·미확정은 회색 */
export function C09Catalyst({ data, height = 180 }: C09CatalystProps) {
  const palette = useChartPalette();
  const title = t('chart.C09.title');
  const groups = groupByStage(data.catalysts);
  const excluded = excludedCatalysts(data.catalysts);
  const showTimeline = !data.compact && timelineItems(data.catalysts).length > 0;
  return (
    <ChartFrame
      title={title}
      labels={collectLabels(data.catalysts.map((c) => c.stage_prob))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
    >
      <div
        className="grid grid-cols-5 gap-2 text-xs mobile:grid-cols-2"
        data-testid="catalyst-board"
      >
        {C09_STAGES.map((stage) => {
          const grayed = C09_GRAYED.includes(stage);
          return (
            <section
              key={stage}
              className="flex min-w-0 flex-col gap-1"
              aria-label={stageLabel(stage)}
            >
              <Badge tone={grayed ? 'muted' : stage === '확정' ? 'strong' : 'neutral'}>
                {stageLabel(stage)}
              </Badge>
              <ul className={`flex flex-col gap-1.5 ${grayed ? 'text-grayed' : ''}`}>
                {groups[stage].map((c) => (
                  <li key={c.id} className="wrap-break-word">
                    <span className={grayed ? '' : 'text-fg'}>{c.name}</span>
                    <span className="block text-[10px] text-muted">
                      {c.kind}
                      {c.expected_ym.v !== null ? (
                        <>
                          {' · '}
                          <FactCell fact={c.expected_ym} unit="ym" />
                        </>
                      ) : null}
                    </span>
                    {!c.location_confirmed ? (
                      <span className="block text-[10px] text-grayed">{t('chart.C09.noLink')}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      {excluded.length > 0 ? (
        <p className="text-xs text-grayed" data-testid="catalyst-excluded">
          <MetaText kind="count" k="chart.C09.excluded" params={{ n: excluded.length }} />
        </p>
      ) : null}
      {showTimeline ? (
        <EChart
          option={buildOption(data, { palette })}
          height={height}
          ariaLabel={t('chart.C09.timeline')}
        />
      ) : null}
    </ChartFrame>
  );
}
