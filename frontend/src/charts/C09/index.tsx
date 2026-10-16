import { FactCell } from '@/components/FactCell';
import { MetaText } from '@/components/MetaValue';
import { t } from '@/i18n';
import type { IsoDate } from '@/lib/format';
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
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C09.source` */
  source?: string;
}

/**
 * C9 호재(개발 소식) 단계 — 단계 보드(HTML 5칸, 칸마다 개수) + 확정 소식 일정표 (G6; G3는 compact = 보드만).
 * 언론 보도만·미확정은 회색. 개수는 목록 세기(D25-3)만 한다.
 */
export function C09Catalyst({ data, height = 180, asof, source }: C09CatalystProps) {
  const palette = useChartPalette();
  const title = t('chart.C09.title');
  const groups = groupByStage(data.catalysts);
  const excluded = excludedCatalysts(data.catalysts);
  const timeline = timelineItems(data.catalysts);
  return (
    <ChartFrame
      title={title}
      subtitle={t('chart.C09.subtitle')}
      labels={collectLabels(data.catalysts.map((c) => c.stage_prob))}
      table={toTable(data)}
      emptyReason={emptyReason(data)}
      asof={asof}
      source={source ?? t('chart.C09.source')}
    >
      <div
        className="grid grid-cols-5 gap-2 text-xs mobile:grid-cols-2"
        data-testid="catalyst-board"
      >
        {C09_STAGES.map((stage) => {
          const grayed = C09_GRAYED.includes(stage);
          const list = groups[stage];
          return (
            <section
              key={stage}
              className={`flex min-w-0 flex-col gap-2 rounded-lg p-2.5 ${
                grayed ? 'bg-bg text-grayed' : 'border border-border bg-surface'
              }`}
              aria-label={stageLabel(stage)}
              data-stage={stage}
            >
              <header className="flex flex-wrap items-baseline justify-between gap-1">
                <span
                  className={`text-[13px] font-semibold ${grayed ? 'text-muted' : stage === '확정' ? 'text-accent' : 'text-fg'}`}
                >
                  {stageLabel(stage)}
                </span>
                <MetaText
                  kind="count"
                  k="chart.C09.count"
                  params={{ n: list.length }}
                  className="text-muted"
                />
              </header>
              {list.length === 0 ? (
                <p className="m-0 text-muted">{t('chart.C09.none')}</p>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {list.map((c) => (
                    <li key={c.id} className="wrap-break-word">
                      <span className={grayed ? '' : 'font-medium text-fg'}>{c.name}</span>
                      <span className="block text-[11px] text-muted">
                        {c.kind}
                        {c.expected_ym.v !== null ? (
                          <>
                            {' · '}
                            <FactCell fact={c.expected_ym} unit="ym" />
                          </>
                        ) : null}
                      </span>
                      {!c.location_confirmed ? (
                        <span className="block text-[11px] text-grayed">
                          {t('chart.C09.noLink')}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
      {excluded.length > 0 ? (
        <p className="m-0 text-xs text-grayed" data-testid="catalyst-excluded">
          <MetaText kind="count" k="chart.C09.excluded" params={{ n: excluded.length }} />
        </p>
      ) : null}
      {!data.compact ? (
        timeline.length > 0 ? (
          <div className="flex flex-col gap-1">
            <p className="m-0 text-[13px] font-semibold text-fg">{t('chart.C09.timeline')}</p>
            <EChart
              option={buildOption(data, { palette })}
              height={height}
              ariaLabel={t('chart.C09.timeline')}
            />
          </div>
        ) : (
          <p
            className="m-0 rounded-lg bg-bg px-3 py-2.5 text-xs text-muted"
            data-testid="catalyst-timeline-empty"
          >
            {t('chart.C09.timelineEmpty')}
          </p>
        )
      ) : null}
    </ChartFrame>
  );
}
