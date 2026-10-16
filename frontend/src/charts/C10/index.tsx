import { Badge } from '@/components/Badge';
import { MetaText, MetaValue } from '@/components/MetaValue';
import { Term } from '@/components/Term';
import { UnstableBadge } from '@/components/UnstableBadge';
import { t } from '@/i18n';
import type { IsoDate } from '@/lib/format';
import { ChartFrame } from '../ChartFrame';
import { ChartLegend } from '../ChartLegend';
import { EChart } from '../EChart';
import { useChartPalette } from '../palette';
import {
  buildOption,
  changeCounts,
  changedText,
  criterionRows,
  emptyReason,
  legendItems,
  toTable,
  type C10VariantRow,
} from './buildOption';
import type { C10Data } from './types';

export interface C10SensitivityProps {
  data: C10Data;
  height?: number;
  asof?: IsoDate | null;
  /** 바닥줄 출처 설명. 생략하면 ko `chart.C10.source` */
  source?: string;
}

const thClass =
  'whitespace-nowrap border-b border-border px-3 py-2 text-left font-semibold text-fg';

/** 표 칸 하나: 그 변형의 1~5위(서버 순위) + "순위 변동: 없음/있음 — 진입·이탈". 변동 없으면 회색 */
function VariantCell({ row }: { row: C10VariantRow | null }) {
  if (!row) return <td className="px-3 py-2 align-top text-grayed">{t('empty.unknown')}</td>;
  return (
    <td
      className={`px-3 py-2 align-top ${row.stable ? 'text-grayed' : ''}`}
      data-stable={row.stable ? 'true' : undefined}
    >
      <ol className="m-0 flex list-none flex-col gap-0.5 p-0 tabular-nums">
        {row.top5.map((x) => (
          <li
            key={x.complex_id}
            className={row.entered.includes(x.name) ? 'font-semibold text-fg' : ''}
          >
            {x.rank !== null ? (
              <>
                <MetaValue kind="rank" value={x.rank} as="rank" />{' '}
              </>
            ) : null}
            {x.name}
          </li>
        ))}
      </ol>
      <p className="m-0 mt-1.5 text-xs text-muted" data-testid="c10-changed">
        {changedText(row)}
      </p>
    </td>
  );
}

/**
 * C10 민감도 — "어떤 기준의 비중을 10%p 늘리거나 줄이면 순위가 바뀌나요?" (G4, G5).
 * 결과 개수 줄(서버 changed 세기) → 표(기준 6줄 × 줄이면/늘리면, 1~5위) → 순위 선(기준 × 줄이면/늘리면).
 */
export function C10Sensitivity({ data, height = 300, asof, source }: C10SensitivityProps) {
  const palette = useChartPalette();
  const title = t('chart.C10.title');
  const s = data.sensitivity;
  const rows = criterionRows(data);
  const counts = changeCounts(data);
  return (
    <ChartFrame
      title={title}
      subtitle={t('chart.C10.question')}
      badges={
        <>
          {/* R9-UI 피드백: 비중·민감도 용어 풀이 */}
          <Term k="weight" />
          <Term k="sensitivity" />
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
      asof={asof}
      source={source ?? t('chart.C10.source')}
    >
      <p className="m-0 text-xs leading-relaxed text-muted">{t('chart.C10.explain')}</p>
      <p className="m-0 text-sm font-semibold text-fg" data-testid="c10-summary">
        <MetaText
          kind="count"
          k="chart.C10.summary"
          params={{ yes: counts.changed, no: counts.unchanged }}
        />
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-[13px]">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col" className={thClass}>
                {t('chart.C10.criterionCol')}
              </th>
              <th scope="col" className={thClass}>
                {t('chart.C10.downCol')}
              </th>
              <th scope="col" className={thClass}>
                {t('chart.C10.upCol')}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.component} className="border-b border-border/50">
                <th scope="row" className="min-w-56 px-3 py-2 align-top font-normal">
                  <span className="block font-bold text-fg">
                    {row.name}{' '}
                    <MetaText
                      kind="input"
                      k="chart.C10.now"
                      params={{ pct: row.weightPct }}
                      className="text-xs font-medium text-muted"
                    />
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-muted">{row.why}</span>
                  <span className="mt-1 block text-[11px] text-grayed">
                    {t('chart.C10.termLine', { term: row.term })}
                  </span>
                </th>
                <VariantCell row={row.down} />
                <VariantCell row={row.up} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <p className="m-0 text-sm font-semibold text-fg">{t('chart.C10.lineTitle')}</p>
        <p className="m-0 text-xs text-muted">{t('chart.C10.lineNote')}</p>
        <ChartLegend items={legendItems(data, { palette })} />
        <EChart option={buildOption(data, { palette })} height={height} ariaLabel={title} />
      </div>
    </ChartFrame>
  );
}
