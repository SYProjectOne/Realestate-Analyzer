import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router';
import { useMarket } from '@/api/hooks';
import type { CatalystUpdated, Market } from '@/api/types';
import { C03Benchmark, C04Supply, C05Unsold, C09Catalyst } from '@/charts';
import { Badge, BigNumber, Card, EmptyState, FactCell, MetaText } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { useUrlParam } from '@/hooks/useUrlParam';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import {
  NoSnapshot,
  QueryState,
  tdClass,
  thClass,
  unitOf,
  useGlobalSearch,
  usePageContext,
} from '../_shared';
import { FLAT_CHART, QuestionSection } from '../_shared/QuestionSection';
import { CatalystLocationPanel } from './CatalystLocationPanel';
import { CatalystUrlForm } from './CatalystUrlForm';
import {
  areaPriceSummary,
  moveInByYear,
  REGULATION_KINDS,
  regulationGroups,
  sharedValue,
  unsoldScopes,
} from './summary';

export const LIVING_AREA_PARAM = 'living_area';

/**
 * G6 지역 시장 `/market` (RA §7-1 · R11 목업 Market.dc.html) — 머리(질문형 제목 · 생활권 고르기) → 한눈에 보기 카드 4장
 * (서버 값·줄 개수만, D25-3·D30-5 — 미분양 지역 합계는 계약 .22 `unsold_latest`) → C3·C4·C5·규제·C9·생활권 실거래 →
 * 편집하는 사람용 호재 위치 확인·호재 URL 입력.
 * 생활권 필터는 URL `?living_area=` → GET /snapshots/{sid}/market?living_area=
 * 계약 2026-10-09.6: benchmark_absence → '벤치마크 없음(<reason>)'(N-M3), 표본 = 자기 생활권만(sample_n) ·
 * 자기 표본 0 이면 지역 전체 대체(substituted → '대체(지역 전체)' 배지, 대체 행은 C3 에 표시)(N-M4).
 * 계약 .10: 상황 토글(?scenario=)을 서버에 보내고, 생활권 실거래 건수(`n_trades`)는 서버 Fact 그대로(화면이 라벨을 만들지 않는다).
 */
export function MarketPage() {
  const { regionId, snapshotId, scenarioKey, isLoading, asof } = usePageContext();
  const { region } = useActiveRegion();
  const [livingArea, setLivingArea] = useUrlParam(LIVING_AREA_PARAM);
  const query = useMarket(snapshotId, livingArea, scenarioKey);
  const search = useGlobalSearch();
  const selectId = useId();
  /**
   * 호재 위치 저장 결과 — 시장 본문이 리비전 전환으로 다시 그려져도 남는다(CatalystLocationPanel 참고). 저장한 지역을
   * 함께 기억해 **다른 지역으로 바꾸면 보이지 않는다**(결과 표·발행 잡 진행 — 8차 m18).
   */
  const [loc, setLoc] = useState<{ regionId: number | null; result: CatalystUpdated } | null>(null);
  const locResult = loc !== null && loc.regionId === regionId ? loc.result : null;
  // 다른 지역으로 바뀌면 지운다(돌아와도 옛 결과·잡 진행을 다시 보이지 않는다)
  useEffect(() => {
    setLoc((prev) => (prev !== null && prev.regionId !== regionId ? null : prev));
  }, [regionId]);
  return (
    <PageShell
      title={region ? t('page.G6.heading', { region: region.name }) : t('page.G6.headingNoRegion')}
      intro={t('page.G6.intro')}
      legend
      actions={
        <div className="flex flex-col gap-1 text-sm">
          <label htmlFor={selectId} className="text-[13px] font-semibold text-fg-2">
            {t('page.G6.livingArea')}
          </label>
          <select
            id={selectId}
            value={livingArea ?? ''}
            onChange={(e) => setLivingArea(e.target.value || null, { replace: true })}
            className="min-h-11 min-w-56 rounded-[10px] border border-border-strong bg-surface px-3 py-2 text-[15px]"
          >
            <option value="">{t('page.G6.allAreas')}</option>
            {(query.data?.living_areas ?? []).map((la) => (
              <option key={la.id} value={la.id}>
                {la.name}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted">
            {t('page.G6.livingAreaHint')}{' '}
            {regionId !== null ? (
              <Link
                to={`/regions/${regionId}/living-areas${search}`}
                className="font-medium text-accent underline-offset-2 hover:underline"
              >
                {t('page.G6.livingAreaEdit')}
              </Link>
            ) : null}
          </span>
        </div>
      }
    >
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>
          {(market) => (
            <>
              <MarketBody
                market={market}
                asof={asof ?? market.asof_date}
                areaSelected={!!livingArea}
              />
              <CatalystLocationPanel
                // 지역이 바뀌면 열린 폼·입력도 지운다(8차 m18)
                key={regionId ?? 'none'}
                market={market}
                snapshotId={snapshotId}
                result={locResult}
                onResult={(result) => setLoc({ regionId, result })}
              />
            </>
          )}
        </QueryState>
      )}
      {/* 지역이 바뀌면 등록 결과·잡 진행을 지운다(8차 m18) */}
      {isLoading ? null : <CatalystUrlForm key={regionId ?? 'none'} regionId={regionId} />}
    </PageShell>
  );
}

function MarketBody({
  market,
  asof,
  areaSelected,
}: {
  market: Market;
  asof: string;
  areaSelected: boolean;
}) {
  const asofYear = Number(market.asof_date.slice(0, 4)) || null;
  const markers = market.move_in_markers
    .filter((m) => typeof m.move_in_ym.v === 'string')
    .map((m) => ({ complex_id: m.complex_id, name: m.name, move_in_ym: String(m.move_in_ym.v) }));
  const areaName = (id: string) => market.living_areas.find((la) => la.id === id)?.name ?? id;
  return (
    <div className="flex flex-col gap-6">
      <SummaryCards market={market} asof={asof} areaSelected={areaSelected} markers={markers} />
      {/* 차트 제목(h3) 앞의 구역 제목 — 제목 순서(h1 → h2 → h3, Lighthouse heading-order) */}
      <h2 className="sr-only">{t('page.common.charts')}</h2>
      <QuestionSection
        name={t('chart.C03.title')}
        title={t('page.G6.benchmark.title')}
        data-testid="market-benchmark"
      >
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
        <div className={FLAT_CHART}>
          <C03Benchmark
            data={{
              benchmarks: market.benchmarks,
              asofYear,
              flags: market.benchmark_flags,
              livingAreas: market.living_areas,
            }}
            asof={asof}
          />
        </div>
        {market.benchmark_flags.length > 0 ? (
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-bold text-fg">{t('page.G6.flags')}</h3>
            <ul aria-label={t('page.G6.flags')} className="flex flex-wrap gap-1.5 text-xs">
              {market.benchmark_flags.map((flag) => (
                <li key={flag.living_area} className="inline-flex flex-wrap items-center gap-1">
                  <Badge tone={flag.sample_n < 3 ? 'muted' : 'neutral'}>
                    <MetaText
                      kind="count"
                      k="page.G6.flag"
                      params={{
                        name: flag.living_area_name ?? areaName(flag.living_area),
                        n: flag.sample_n,
                      }}
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
            <p className="text-xs text-muted">{t('page.G6.flagsNote')}</p>
          </div>
        ) : null}
      </QuestionSection>
      <QuestionSection
        name={t('chart.C04.title')}
        title={t('page.G6.supply.title')}
        data-testid="market-supply"
      >
        <div className={FLAT_CHART}>
          <C04Supply
            data={{ supply: market.supply, markers, livingAreas: market.living_areas }}
            asof={asof}
          />
        </div>
      </QuestionSection>
      <div className="grid gap-6 xl:grid-cols-2">
        <UnsoldSection market={market} asof={asof} />
        <RegulationCard market={market} />
      </div>
      <QuestionSection
        name={t('chart.C09.title')}
        title={t('page.G6.catalystBoard.title')}
        data-testid="market-catalysts"
      >
        <div className={FLAT_CHART}>
          <C09Catalyst data={{ catalysts: market.catalysts }} asof={asof} />
        </div>
      </QuestionSection>
      <LivingAreaCompare market={market} />
    </div>
  );
}

/**
 * 한눈에 보기 카드 4장(목업 MK-1) — 서버 값을 그대로 쓰거나 줄 개수만 센다(D25-3). 가장 큰 곳·가장 몰리는 해 고르기,
 * 생활권 값 더하기는 하지 않는다(규칙 3·5). 미분양 합계는 계약 .22 `unsold_latest`(대시보드 kpis.unsold 와 같은 함수).
 */
function SummaryCards({
  market,
  asof,
  areaSelected,
  markers,
}: {
  market: Market;
  asof: string;
  areaSelected: boolean;
  markers: { complex_id: number; name: string; move_in_ym: string }[];
}) {
  const unsold = market.unsold_latest ?? null;
  const years = moveInByYear(markers);
  const prices = areaPriceSummary(market.living_area_prices);
  const regulated = regulationGroups(market.regulation.items, 'regulated_area');
  const priceCap = regulationGroups(market.regulation.items, 'price_cap');
  return (
    <section
      aria-label={t('page.G6.summary.title')}
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      data-testid="market-summary"
    >
      <Card className="flex flex-col gap-2" data-testid="summary-unsold">
        <BigNumber
          label={areaSelected ? t('page.G6.summary.unsoldArea') : t('page.G6.summary.unsold')}
          caption={unsold?.ym ? t('page.G6.summary.unsoldYm', { ym: unsold.ym }) : undefined}
        >
          <FactCell
            fact={unsold?.total ?? null}
            unit="households"
            asof={asof}
            emptyReason={t('page.G6.summary.unsoldMissing')}
          />
        </BigNumber>
        <p className="flex flex-wrap items-center gap-1 text-[13px] text-fg-2">
          <span>{t('page.G6.summary.unsoldPost')}</span>
          <FactCell
            fact={unsold?.post_completion ?? null}
            unit="households"
            asof={asof}
            emptyReason={t('page.G6.summary.unsoldMissing')}
          />
        </p>
      </Card>
      <Card className="flex flex-col gap-2" data-testid="summary-movein">
        <BigNumber label={t('page.G6.summary.moveIn')} caption={t('page.G6.summary.moveInHint')}>
          <MetaText kind="count" k="page.G6.summary.moveInCount" params={{ n: markers.length }} />
        </BigNumber>
        {years.length > 0 ? (
          <p className="text-[13px] text-fg-2">
            {years.map((y, i) => (
              <span key={y.year}>
                {i > 0 ? ' · ' : ''}
                <MetaText
                  kind="count"
                  k="page.G6.summary.moveInYear"
                  params={{ year: { n: Number(y.year), as: 'plain' }, n: y.count }}
                />
              </span>
            ))}
          </p>
        ) : null}
      </Card>
      <Card className="flex flex-col gap-2" data-testid="summary-prices">
        <BigNumber label={t('page.G6.summary.prices')}>
          <MetaText kind="count" k="page.G6.summary.pricesCount" params={{ n: prices.withValue }} />{' '}
          <MetaText
            kind="count"
            k="page.G6.summary.pricesOf"
            params={{ n: market.living_areas.length }}
            className="text-base font-semibold text-muted"
          />
        </BigNumber>
        {prices.window ? (
          <p className="text-[13px] text-fg-2">
            {t('page.G6.summary.pricesWindow', { window: prices.window })}
          </p>
        ) : null}
      </Card>
      <Card className="flex flex-col gap-2" data-testid="summary-regulation">
        <span className="text-[13px] text-muted">{t('page.G6.summary.regulation')}</span>
        {regulated.length === 0 ? (
          <EmptyState inline reason={t('page.G6.summary.regNone')} />
        ) : (
          <ul className="flex flex-col gap-0.5">
            {regulated.map((g) => (
              <li key={g.value} className="text-2xl font-bold tracking-tight text-fg">
                <MetaText
                  kind="count"
                  k="page.G6.summary.regValue"
                  params={{ value: g.value, n: g.count }}
                />
              </li>
            ))}
          </ul>
        )}
        {priceCap.length > 0 ? (
          <p className="text-[13px] text-fg-2">
            {t('page.G6.summary.priceCap')}{' '}
            {priceCap.map((g, i) => (
              <span key={g.value}>
                {i > 0 ? ' · ' : ''}
                <MetaText
                  kind="count"
                  k="page.G6.summary.regValue"
                  params={{ value: g.value, n: g.count }}
                />
              </span>
            ))}
          </p>
        ) : null}
      </Card>
    </section>
  );
}

/** 미분양 추이(C5) + 어느 구를 볼지 고르기(목업 N7 — 기본은 차트가 고르는 '자료가 가장 긴 곳') */
function UnsoldSection({ market, asof }: { market: Market; asof: string }) {
  const scopes = unsoldScopes(market.unsold);
  const [scope, setScope] = useState<string>('');
  const selectId = useId();
  const chosen = scopes.some((s) => s.code === scope) ? scope : '';
  return (
    <QuestionSection
      name={t('chart.C05.title')}
      title={t('page.G6.unsold.title')}
      data-testid="market-unsold"
    >
      {scopes.length > 1 ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label htmlFor={selectId} className="text-[13px] font-semibold text-fg-2">
            {t('page.G6.unsold.scope')}
          </label>
          <select
            id={selectId}
            value={chosen}
            onChange={(e) => setScope(e.target.value)}
            className="min-h-11 rounded-[10px] border border-border-strong bg-surface px-3 py-2"
          >
            <option value="">{t('page.G6.unsold.scopeAuto')}</option>
            {scopes.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <p className="text-xs leading-relaxed text-muted">{t('page.G6.unsold.note')}</p>
      <div className={FLAT_CHART}>
        <C05Unsold data={{ unsold: market.unsold, scope: chosen || null }} asof={asof} />
      </div>
    </QuestionSection>
  );
}

/**
 * 규제 요약 — 계약 RegulationItem key 8종(regulated_area·price_cap·resale·residency·loan·tax·land_permit·other)을 모두
 * 같은 순서로 보인다(목업 MK-8). 종류마다 서버 항목 줄(이름·값·범위·메모)을 그대로, 없는 종류는 '자료 없어요' 한 줄.
 */
function RegulationCard({ market }: { market: Market }) {
  const items = market.regulation.items;
  return (
    <QuestionSection
      name={t('page.G6.regulation')}
      title={t('page.G6.regulationQ')}
      hint={t('page.G6.regulationHint')}
      data-testid="market-regulation"
    >
      {items.length === 0 ? <EmptyState reason={t('page.common.none')} /> : null}
      <div className="flex flex-col divide-y divide-border">
        {REGULATION_KINDS.map((kind) => {
          const rows = items.filter((item) => item.key === kind);
          return (
            <div
              key={kind}
              className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0"
              data-testid={`regulation-${kind}`}
            >
              <h3 className="text-sm font-bold text-fg">{t(`page.G6.regKind.${kind}` as TKey)}</h3>
              {rows.length === 0 ? (
                <p className="text-xs text-muted">{t('page.G6.regKindNone')}</p>
              ) : (
                <dl className="flex flex-col gap-1.5 text-sm">
                  {rows.map((item, i) => (
                    <div key={`${item.key}-${item.title}-${i}`} className="flex flex-col gap-0.5">
                      <dt className="font-medium text-fg-2">{item.title}</dt>
                      <dd className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
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
            </div>
          );
        })}
      </div>
    </QuestionSection>
  );
}

const PRICE_VALUE_COLS = ['low', 'median', 'high', 'n'] as const;

/**
 * 생활권별 실거래 — 거래 기간이 모든 생활권에서 같으면 표 위 한 줄, 다르면 '기간' 열(목업 MK-9). 기준(basis)은 생활권마다
 * 다른 서버 설명이라 늘 열로 둔다. 값·라벨은 서버 Fact 그대로(FactCell).
 */
function LivingAreaCompare({ market }: { market: Market }) {
  const rows = market.living_area_prices;
  const window = sharedValue(rows.map((r) => r.trade_window));
  return (
    <QuestionSection
      name={t('page.G6.prices')}
      title={t('page.G6.pricesQ')}
      hint={t('page.G6.pricesHint')}
      data-testid="market-prices"
    >
      {rows.length === 0 ? (
        <EmptyState reason={t('page.common.none')} />
      ) : (
        <div className="flex flex-col gap-2">
          {window ? (
            <p className="text-xs text-muted" data-testid="prices-window">
              {t('page.G6.pricesWindowAll', { window })}
            </p>
          ) : null}
          <div className="overflow-x-auto">
            <table
              aria-label={t('page.G6.prices')}
              className="w-full min-w-[44rem] border-collapse text-sm"
            >
              <thead>
                <tr>
                  <th scope="col" className={`${thClass} whitespace-nowrap`}>
                    {t('page.G6.priceCol.name')}
                  </th>
                  {PRICE_VALUE_COLS.map((k) => (
                    <th key={k} scope="col" className={`${thClass} whitespace-nowrap text-right`}>
                      {t(`page.G6.priceCol.${k}`)}
                    </th>
                  ))}
                  {window ? null : (
                    <th scope="col" className={thClass}>
                      {t('page.G6.priceCol.window')}
                    </th>
                  )}
                  <th scope="col" className={thClass}>
                    {t('page.G6.priceCol.basis')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.living_area}>
                    <th
                      scope="row"
                      className={`${tdClass} whitespace-nowrap text-left font-semibold`}
                    >
                      {row.name}
                    </th>
                    <td className={`${tdClass} text-right`}>
                      <FactCell fact={row.low_won} unit="eok" />
                    </td>
                    <td className={`${tdClass} text-right font-semibold`}>
                      <FactCell fact={row.median_won} unit="eok" />
                    </td>
                    <td className={`${tdClass} text-right`}>
                      <FactCell fact={row.high_won} unit="eok" />
                    </td>
                    <td className={`${tdClass} text-right`}>
                      <FactCell fact={row.n_trades} unit="count" />
                    </td>
                    {window ? null : (
                      <td className={`${tdClass} whitespace-nowrap`}>
                        {row.trade_window ?? t('empty.unknown')}
                      </td>
                    )}
                    <td className={`${tdClass} text-xs text-muted`}>{row.basis ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </QuestionSection>
  );
}
