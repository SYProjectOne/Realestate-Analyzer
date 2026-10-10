import { useId } from 'react';
import { useMarket } from '@/api/hooks';
import type { Market } from '@/api/types';
import { C03Benchmark, C04Supply, C05Unsold, C09Catalyst } from '@/charts';
import { Badge, EmptyState, FactCell, MetaText } from '@/components';
import { useUrlParam } from '@/hooks/useUrlParam';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import {
  NoSnapshot,
  QueryState,
  sampleCountFact,
  Section,
  tdClass,
  thClass,
  unitOf,
  usePageContext,
} from '../_shared';
import { CatalystLocationPanel } from './CatalystLocationPanel';
import { CatalystUrlForm } from './CatalystUrlForm';

export const LIVING_AREA_PARAM = 'living_area';

/**
 * G6 지역 시장 `/market` (RA §7-1) — C3·C4·C5·C9(보드+타임라인) · RegulationCard · LivingAreaCompare.
 * 생활권 필터는 URL `?living_area=` → GET /snapshots/{sid}/market?living_area=
 * 호재 URL 입력(M6, POST /catalysts) — 사람이 넣은 공개 URL → 호재 후보 + 분류 잡.
 * 계약 2026-10-09.6: benchmark_absence → '벤치마크 없음(<reason>)'(N-M3), 표본 = 자기 생활권만(sample_n) ·
 * 자기 표본 0 이면 지역 전체 대체(substituted → '대체(지역 전체)' 배지, 대체 행은 C3 에 표시)(N-M4).
 */
export function MarketPage() {
  const { regionId, snapshotId, scenarioKey, isLoading } = usePageContext();
  const [livingArea, setLivingArea] = useUrlParam(LIVING_AREA_PARAM);
  const query = useMarket(snapshotId, livingArea, scenarioKey);
  const selectId = useId();
  return (
    <PageShell
      title={t('page.G6.title')}
      actions={
        <span className="flex items-center gap-2 text-sm">
          <label htmlFor={selectId} className="text-muted">
            {t('page.G6.livingArea')}
          </label>
          <select
            id={selectId}
            value={livingArea ?? ''}
            onChange={(e) => setLivingArea(e.target.value || null, { replace: true })}
            className="rounded-sm border border-border bg-surface px-2 py-1"
          >
            <option value="">{t('page.G6.allAreas')}</option>
            {(query.data?.living_areas ?? []).map((la) => (
              <option key={la.id} value={la.id}>
                {la.name}
              </option>
            ))}
          </select>
        </span>
      }
    >
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>
          {(market) => (
            <>
              <MarketBody market={market} />
              <CatalystLocationPanel market={market} snapshotId={snapshotId} />
            </>
          )}
        </QueryState>
      )}
      {isLoading ? null : <CatalystUrlForm regionId={regionId} />}
    </PageShell>
  );
}

function MarketBody({ market }: { market: Market }) {
  const asofYear = Number(market.asof_date.slice(0, 4)) || null;
  const markers = market.move_in_markers
    .filter((m) => typeof m.move_in_ym.v === 'string')
    .map((m) => ({ complex_id: m.complex_id, name: m.name, move_in_ym: String(m.move_in_ym.v) }));
  const areaName = (id: string) => market.living_areas.find((la) => la.id === id)?.name ?? id;
  return (
    <div className="flex flex-col gap-4">
      {/* 차트 제목(h3) 앞의 구역 제목 — 제목 순서(h1 → h2 → h3, Lighthouse heading-order) */}
      <h2 className="sr-only">{t('page.common.charts')}</h2>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="flex flex-col gap-2">
          {market.benchmark_absence ? (
            <p
              role="note"
              data-testid="benchmark-absence"
              data-code={market.benchmark_absence.code}
              className="text-sm"
            >
              <Badge tone="muted">
                {t('page.common.benchmarkAbsent', { reason: market.benchmark_absence.reason })}
              </Badge>
            </p>
          ) : null}
          <C03Benchmark
            data={{
              benchmarks: market.benchmarks,
              asofYear,
              flags: market.benchmark_flags,
              livingAreas: market.living_areas,
            }}
          />
          {market.benchmark_flags.length > 0 ? (
            <ul aria-label={t('page.G6.flags')} className="flex flex-wrap gap-1 text-xs">
              {market.benchmark_flags.map((flag) => (
                <li key={flag.living_area} className="inline-flex flex-wrap items-center gap-1">
                  <Badge tone={flag.sample_n < 3 ? 'muted' : 'neutral'}>
                    <MetaText
                      kind="count"
                      k="page.G6.flag"
                      params={{ name: areaName(flag.living_area), n: flag.sample_n }}
                    />
                    {flag.no_recent_sale_case ? ` · ${t('page.G6.noRecentSale')}` : ''}
                  </Badge>
                  {flag.substituted ? (
                    <Badge tone="muted" data-testid="flag-substituted">
                      {t('badge.substituteRegion')}
                    </Badge>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <C04Supply data={{ supply: market.supply, markers }} />
        <C05Unsold data={{ unsold: market.unsold }} />
        <RegulationCard market={market} />
      </div>
      <C09Catalyst data={{ catalysts: market.catalysts }} />
      <LivingAreaCompare market={market} />
    </div>
  );
}

function RegulationCard({ market }: { market: Market }) {
  const items = market.regulation.items;
  return (
    <Section title={t('page.G6.regulation')}>
      {items.length === 0 ? (
        <EmptyState reason={t('page.common.none')} />
      ) : (
        <dl className="flex flex-col gap-2 text-sm">
          {items.map((item) => (
            <div key={`${item.key}-${item.title}`} className="flex flex-col gap-0.5">
              <dt className="font-medium">{item.title}</dt>
              <dd className="flex flex-wrap items-center gap-1">
                <FactCell
                  fact={item.value}
                  unit={unitOf(item.value, 'text')}
                  asof={market.asof_date}
                />
                {item.scope ? (
                  <span className="text-xs text-muted">
                    {t('page.G6.regulationScope', { scope: item.scope })}
                  </span>
                ) : null}
              </dd>
              {item.note ? <dd className="text-xs text-muted">{item.note}</dd> : null}
            </div>
          ))}
        </dl>
      )}
    </Section>
  );
}

const PRICE_COLS = ['name', 'low', 'median', 'high', 'n', 'window', 'basis'] as const;

function LivingAreaCompare({ market }: { market: Market }) {
  return (
    <Section title={t('page.G6.prices')}>
      {market.living_area_prices.length === 0 ? (
        <EmptyState reason={t('page.common.none')} />
      ) : (
        <div className="overflow-x-auto">
          <table aria-label={t('page.G6.prices')} className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {PRICE_COLS.map((k) => (
                  <th key={k} scope="col" className={thClass}>
                    {t(`page.G6.priceCol.${k}` as TKey)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {market.living_area_prices.map((row) => (
                <tr key={row.living_area}>
                  <th scope="row" className={`${tdClass} text-left font-medium`}>
                    {row.name}
                  </th>
                  <td className={tdClass}>
                    <FactCell fact={row.low_won} unit="eok" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={row.median_won} unit="eok" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={row.high_won} unit="eok" />
                  </td>
                  <td className={tdClass}>
                    <FactCell fact={sampleCountFact(row.median_won, row.n_trades)} unit="count" />
                  </td>
                  <td className={tdClass}>{row.trade_window ?? t('empty.unknown')}</td>
                  <td className={`${tdClass} text-xs text-muted`}>{row.basis ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
