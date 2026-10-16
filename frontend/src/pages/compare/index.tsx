import { useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useCompare, useScenarios, useSensitivity } from '@/api/hooks';
import type {
  CompareView,
  DecisionSet,
  LadderHorizon,
  LadderRow,
  Scenario,
  ScoreRow,
  Verdict3,
} from '@/api/types';
import {
  C01Ladder,
  C02Gap,
  C06ScoreBreakdown,
  C07Decision,
  C10Sensitivity,
  useChartPalette,
} from '@/charts';
import {
  Badge,
  Banner,
  BigNumber,
  Card,
  EmptyState,
  FactCell,
  IntakeBadge,
  MetaText,
  MetaValue,
  MismatchBadge,
  glossaryItem,
  Term,
  TieBadge,
  UnstableBadge,
  type GlossaryKey,
} from '@/components';
import { scenarioKey as keyOf } from '@/hooks/useScenario';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import {
  enumText,
  NoSnapshot,
  QueryState,
  RejudgeNeededBadge,
  StateCard,
  useGlobalSearch,
  usePageContext,
} from '../_shared';
import {
  AnalyzeSection,
  cellClass,
  p10TargetLine,
  headCellClass,
  outlineButtonClass,
  P10Note,
  PlainName,
  radioClass,
  ReqJudgeText,
  ReqStatusBadge,
  rowHeadClass,
  SeriesMarker,
  SourceLine,
  wideTableClass,
} from './parts';

export const MIN_IDS = 2;
export const MAX_IDS = 6;

/** `?ids=2,7,4` → [2,7,4] (정수만, 중복 제거) */
export function parseIds(raw: string | null): number[] {
  if (!raw) return [];
  const out: number[] = [];
  for (const part of raw.split(',')) {
    const n = Number(part.trim());
    if (part.trim() !== '' && Number.isInteger(n) && n > 0 && !out.includes(n)) out.push(n);
  }
  return out;
}

/**
 * G4 비교 `/compare?ids=` (RA §7-1 · 목업 Compare.dc.html, R11) — ids 2~6 검사, 상황 토글 공유.
 * 비교 단지 카드 → 조건 비교 → 점수·판정기 → 가격 갭 → 점수 분해 → 가격 전망 → 상황별 판정(C7·가상 후보·요건) → 민감도.
 * D10-1: 순위 칸에 '재판정 필요' 배지(저장값 그대로). 가상 후보 wait_new(계약 .5)는 상황별 판정에 따로.
 */
export function ComparePage() {
  const [params] = useSearchParams();
  const ids = parseIds(params.get('ids'));
  const { snapshotId, scenarioKey, isLoading } = usePageContext();
  const valid = ids.length >= MIN_IDS && ids.length <= MAX_IDS;
  const query = useCompare(snapshotId, valid ? ids : [], scenarioKey);
  const search = useGlobalSearch();

  return (
    <div className="flex flex-col gap-2">
      <nav aria-label={t('page.G4.crumb')} className="text-[13px] text-muted">
        <Link to={`/complexes${search}`} className="text-accent hover:underline">
          {t('nav.G2')}
        </Link>
        <span aria-hidden> › </span>
        <span aria-current="page">{t('nav.G4')}</span>
      </nav>
      <PageShell
        title={t('page.G4.title')}
        legend
        actions={
          <Link to={`/complexes${search}`} className={outlineButtonClass}>
            <span aria-hidden>+</span>
            {t('page.G4.addMore')}
          </Link>
        }
      >
        {!valid ? (
          <StateCard testId="compare-invalid" title={t('page.G4.invalidIds')}>
            <MetaText
              kind="count"
              className="text-sm text-muted"
              k="page.G4.invalidIdsNow"
              params={{ n: ids.length }}
            />
            <Link to={`/complexes${search}`} className="text-sm font-medium text-accent underline">
              {t('page.G4.backToList')}
            </Link>
          </StateCard>
        ) : !snapshotId && !isLoading ? (
          <NoSnapshot />
        ) : (
          <QueryState query={query}>
            {(view) => <CompareBody view={view} scenarioKey={scenarioKey} />}
          </QueryState>
        )}
      </PageShell>
    </div>
  );
}

function CompareBody({ view, scenarioKey }: { view: CompareView; scenarioKey: string | null }) {
  const { snapshotId } = usePageContext();
  const sensitivity = useSensitivity(snapshotId, scenarioKey);
  const { data: scenarios = [] } = useScenarios();
  const palette = useChartPalette();
  const rows = orderRows(view);
  const names = Object.fromEntries(rows.map((r) => [String(r.complex_id), r.name]));
  const scenario =
    scenarios.find((s) => s.id === view.scenario_id) ??
    (scenarioKey ? (scenarios.find((s) => keyOf(s) === scenarioKey) ?? null) : null);
  const scenarioName = scenario?.name ?? scenarioKey ?? '';
  const colorOf = (i: number) => palette.categorical[i] ?? palette.strong;
  const asof = view.asof_date;
  /*
   * R9-UI P9(30-proposal §10): 사실 비교를 먼저 — 조건 비교(공고 값·산술) → 점수·판정기(+ 두 지표 차이) →
   * 가격 갭 → 점수 분해 → 가격 전망 → 상황별 판정 → 민감도. 블록은 순서만 바뀌고 빠지는 것이 없다(data-block).
   */
  return (
    <div className="flex flex-col gap-5">
      <MetaText
        kind="count"
        className="text-sm text-muted"
        k="page.G4.summary"
        params={{ n: rows.length, name: scenarioName }}
      />
      <ComplexCards view={view} rows={rows} colorOf={colorOf} />
      <div data-block="terms">
        <TermsTable view={view} rows={rows} colorOf={colorOf} />
      </div>
      <div data-block="grid">
        <AnalyzeSection eyebrow={t('page.G4.scores')} title={t('page.G4.scoresQ')}>
          <ol className="m-0 grid list-none gap-2 p-0 md:grid-cols-2">
            {(['rankNote', 'decideNote'] as const).map((k, i) => (
              <li
                key={k}
                className="flex items-start gap-3 rounded-xl bg-subtle px-4 py-3 text-sm leading-relaxed text-fg-2"
              >
                <span
                  aria-hidden
                  className="inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-bold text-accent-ink"
                >
                  <MetaValue kind="seq" value={i + 1} as="plain" />
                </span>
                <span>{t(`page.G4.${k}`)}</span>
              </li>
            ))}
          </ol>
          <CompareGrid
            view={view}
            rows={rows}
            scenarioKey={scenarioKey}
            scenario={scenario}
            scenarioName={scenarioName}
          />
        </AnalyzeSection>
      </div>
      {/* 차트 제목(h3) 앞의 구역 제목 — 제목 순서(h1 → h2 → h3, Lighthouse heading-order) */}
      <h2 className="sr-only">{t('page.common.charts')}</h2>
      <div data-block="C02">
        <AnalyzeSection eyebrow={t('page.G4.gaps')} title={t('page.G4.gapsQ')}>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {rows.map((row, i) => (
              <GapCell key={row.complex_id} view={view} row={row} color={colorOf(i)} />
            ))}
          </div>
        </AnalyzeSection>
      </div>
      <div data-block="C06">
        <AnalyzeSection eyebrow={t('chart.C06.title')} title={t('page.G4.breakdownQ')}>
          <C06ScoreBreakdown
            data={{
              rows,
              weights: view.components.weights,
              orientation: 'horizontal',
              keys: view.components.keys,
            }}
            height={Math.max(180, rows.length * 56)}
            asof={asof}
          />
        </AnalyzeSection>
      </div>
      <div data-block="ladder">
        <LadderOverlay view={view} rows={rows} />
      </div>
      <div data-block="decision">
        <DecisionPanel view={view} scenarioKey={scenarioKey} />
      </div>
      {sensitivity.data ? (
        <div data-block="C10">
          <AnalyzeSection eyebrow={t('chart.C10.title')} title={t('chart.C10.question')}>
            <C10Sensitivity data={{ sensitivity: sensitivity.data, names }} asof={asof} />
          </AnalyzeSection>
        </div>
      ) : null}
    </div>
  );
}

/** URL ids 순서대로 */
function orderRows(view: CompareView): ScoreRow[] {
  const byId = new Map(view.rows.map((r) => [r.complex_id, r]));
  const ordered = view.ids.map((id) => byId.get(id)).filter((r): r is ScoreRow => !!r);
  return ordered.length === view.rows.length ? ordered : view.rows;
}

function currentDecision(view: CompareView, scenarioKey: string | null): DecisionSet | null {
  const key = scenarioKey ?? 'base';
  return (
    view.decisions[key] ??
    Object.values(view.decisions).find((d) => d.scenario_id === view.scenario_id) ??
    null
  );
}

/** 표 머리 칸의 단지 이름(계열 기호 + 이름) */
function ComplexHead({ row, index, color }: { row: ScoreRow; index: number; color: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <SeriesMarker index={index} color={color} />
      <span>{row.name}</span>
    </span>
  );
}

/** N1 비교 단지 카드 줄 — 생활권·이름(상세 링크)·입주·종합·순위·접수(서버 값 그대로), 열 순서·색 = 아래 표·차트 */
function ComplexCards({
  view,
  rows,
  colorOf,
}: {
  view: CompareView;
  rows: ScoreRow[];
  colorOf: (i: number) => string;
}) {
  const search = useGlobalSearch();
  return (
    <div className="flex flex-col gap-2">
      <ul
        aria-label={t('nav.G4')}
        className="m-0 grid list-none gap-3 p-0 md:grid-cols-2 xl:grid-cols-3"
      >
        {rows.map((row, i) => (
          <Card
            as="li"
            key={row.complex_id}
            padding="md"
            className="flex flex-col gap-2 border-t-4"
            style={{ borderTopColor: colorOf(i) }}
            data-testid="compare-card"
          >
            <span className="flex flex-wrap items-center gap-2">
              <IntakeBadge intake={row.intake} showPath={false} asof={view.asof_date} />
              {row.living_area_name ? (
                <span className="text-xs text-muted">{row.living_area_name}</span>
              ) : null}
            </span>
            <Link
              to={`/complexes/${row.complex_id}${search}`}
              className="inline-flex items-center gap-2 text-[17px] font-bold text-fg hover:underline"
            >
              <SeriesMarker index={i} color={colorOf(i)} />
              {row.name}
            </Link>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-fg-2">
              <span className="inline-flex items-center gap-1">
                <span className="text-muted">{t('page.G4.card.moveIn')}</span>
                <FactCell fact={row.move_in_ym ?? null} unit="ym" />
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="text-muted">{t('page.G4.row.total')}</span>
                <FactCell fact={row.total} unit="score" />
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="text-muted">{t('page.G4.row.rank')}</span>
                {row.rank !== null ? (
                  <MetaValue kind="rank" value={row.rank} as="rank" />
                ) : (
                  <EmptyState inline />
                )}
                <TieBadge tie={row.tie_group !== null} />
              </span>
            </span>
          </Card>
        ))}
      </ul>
    </div>
  );
}

function CompareGrid({
  view,
  rows,
  scenarioKey,
  scenario,
  scenarioName,
}: {
  view: CompareView;
  rows: ScoreRow[];
  scenarioKey: string | null;
  scenario: Scenario | null;
  scenarioName: string;
}) {
  const decision = currentDecision(view, scenarioKey);
  const decisionOf = (id: number) => decision?.items.find((i) => i.complex_id === id) ?? null;
  const search = useGlobalSearch();
  const palette = useChartPalette();
  const colorOf = (i: number) => palette.categorical[i] ?? palette.strong;
  return (
    <div className="overflow-x-auto">
      <table aria-label={t('page.G4.grid')} className={wideTableClass}>
        <thead>
          <tr>
            <th scope="col" className={headCellClass}>
              <span className="sr-only">{t('page.G4.grid')}</span>
            </th>
            {rows.map((row, i) => (
              <th key={row.complex_id} scope="col" className={headCellClass}>
                <Link to={`/complexes/${row.complex_id}${search}`} className="hover:underline">
                  <ComplexHead row={row} index={i} color={colorOf(i)} />
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className={rowHeadClass}>
              <PlainName name={t('page.G4.row.total')} official={t('page.G4.row.totalNote')} />
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={cellClass}>
                <FactCell fact={row.total} unit="score" className="text-lg font-bold" />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={rowHeadClass}>
              <PlainName name={t('page.G4.row.rank')} official={t('page.G4.row.rankNote')} />
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={cellClass}>
                <span className="inline-flex flex-wrap items-center gap-1">
                  {row.rank !== null ? (
                    <MetaValue kind="rank" value={row.rank} as="rank" className="font-semibold" />
                  ) : (
                    <EmptyState inline />
                  )}
                  <TieBadge tie={row.tie_group !== null} />
                  <UnstableBadge unstable={row.unstable} />
                  <RejudgeNeededBadge needed={row.rejudge_needed} />
                </span>
              </td>
            ))}
          </tr>
          <tr data-testid="compare-p10">
            <th scope="row" className={rowHeadClass}>
              <span>{t('page.G4.row.p10')}</span> <Term k="p10" />
              <P10Note target={p10TargetLine(scenario)} />
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={cellClass}>
                <FactCell fact={row.p10} unit="prob" />
              </td>
            ))}
          </tr>
          <tr data-testid="compare-delta-rerank">
            <th scope="row" className={rowHeadClass}>
              <span className="block">{t('page.G4.row.deltaRerank')}</span>
              <span className="block text-xs font-normal text-muted">
                {t('page.common.deltaRerank')}
              </span>
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={cellClass}>
                <FactCell
                  fact={row.delta_rerank}
                  unit="score"
                  emptyReason={t('page.common.deltaRerankNone')}
                />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={rowHeadClass}>
              {t('page.G4.row.intake')}
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={cellClass}>
                <IntakeBadge intake={row.intake} asof={view.asof_date} />
              </td>
            ))}
          </tr>
          <tr data-testid="compare-decision">
            <th scope="row" className={rowHeadClass}>
              {t('page.G4.row.decision', { name: scenarioName })}
            </th>
            {rows.map((row) => {
              const item = decisionOf(row.complex_id);
              const badge = row.decision;
              return (
                <td key={row.complex_id} className={cellClass}>
                  <span className="inline-flex flex-wrap items-center gap-1">
                    <FactCell fact={item?.prob ?? badge?.prob ?? null} unit="prob" />
                    {(item?.chosen ?? badge?.chosen) ? (
                      <Badge tone="accent">{t('chart.chosen')}</Badge>
                    ) : null}
                    {/* 동률 = 서버 값만, 확정(ok) 봉투일 때만(R3 minor 28) */}
                    <TieBadge
                      tie={item ? decision?.status === 'ok' && item.tie : (badge?.tie ?? false)}
                    />
                    <MismatchBadge mismatch={item?.mismatch ?? badge?.mismatch ?? false} />
                  </span>
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** C02 한 단지 칸: 머리 = 서버 가격 갭 %(+ 부호 뜻) · 이 단지 중간값 · 비교 단지 수(목록 세기), 아래 = C02 차트 */
function GapCell({ view, row, color }: { view: CompareView; row: ScoreRow; color: string }) {
  const gap = view.gaps[String(row.complex_id)] ?? null;
  return (
    <div className="flex min-w-0 flex-col gap-2" data-testid="gap-cell">
      <Card
        padding="sm"
        className="flex flex-col gap-1 border-t-4"
        style={{ borderTopColor: color }}
      >
        <BigNumber
          label={t('page.G4.gapHead')}
          size="md"
          caption={t('page.G4.gapSign')}
          data-testid="gap-head"
        >
          <FactCell fact={gap?.gap_pct ?? row.gap_pct ?? null} unit="pct" />
        </BigNumber>
        {gap ? (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
            <span className="inline-flex items-center gap-1">
              {t('page.G4.gapMid')}
              <FactCell fact={gap.price_mid} unit="won" />
            </span>
            <MetaText kind="count" k="page.G4.gapComps" params={{ n: gap.comps.length }} />
          </span>
        ) : null}
      </Card>
      <C02Gap title={row.name} data={{ gap }} height={240} asof={view.asof_date} />
    </div>
  );
}

const HORIZONS: readonly LadderHorizon[] = ['move_in_plus_1y', 'asof_plus_3y', 'asof_plus_5y'];
const VERDICTS: readonly Verdict3[] = ['uncertain', 'likely', 'unlikely'];

/** CP-7: 지금 목표 시점의 막대별 판정기 판정(서버 verdict)을 센다 — 판단 문장은 만들지 않는다 */
export function verdictCounts(rows: readonly LadderRow[]): Record<Verdict3 | 'total', number> {
  const out = { uncertain: 0, likely: 0, unlikely: 0, total: 0 };
  for (const row of rows) {
    for (const v of Object.values(row.verdicts)) {
      out.total += 1;
      if (v && VERDICTS.includes(v)) out[v] += 1;
    }
  }
  return out;
}

function LadderOverlay({ view, rows }: { view: CompareView; rows: ScoreRow[] }) {
  const [horizon, setHorizon] = useState<LadderHorizon>('move_in_plus_1y');
  const overlay = rows.map((row) => ({
    complex_id: row.complex_id,
    name: row.name,
    ladder: view.ladders[String(row.complex_id)] ?? [],
  }));
  const counts = verdictCounts(
    overlay.flatMap((o) => o.ladder.filter((r) => r.horizon === horizon)),
  );
  return (
    <AnalyzeSection
      eyebrow={t('page.G4.ladder')}
      title={t('page.G4.ladderQ')}
      hint={`${t('page.G4.ladderHint')} · ${t('page.G4.row.p10Note')}`}
      actions={
        <div className="flex flex-col items-start gap-1.5">
          <span className="text-[13px] text-muted" aria-hidden>
            {t('page.G4.ladderHorizons')}
          </span>
          <div role="radiogroup" aria-label={t('page.G4.ladderHorizons')} className="flex gap-1.5">
            {HORIZONS.map((h) => (
              <button
                key={h}
                type="button"
                role="radio"
                aria-checked={h === horizon}
                onClick={() => setHorizon(h)}
                className={radioClass(h === horizon)}
              >
                {enumText('chart.C01.horizon', h)}
              </button>
            ))}
          </div>
        </div>
      }
    >
      <C01Ladder
        data={{ ladder: overlay[0]?.ladder ?? [], horizon, overlay }}
        height={280}
        asof={view.asof_date}
      />
      {counts.total > 0 ? (
        <p className="m-0 text-sm text-fg-2" data-testid="ladder-verdict-count">
          <MetaText
            kind="count"
            k="page.G4.ladderCount"
            params={{
              uncertain: counts.uncertain,
              likely: counts.likely,
              unlikely: counts.unlikely,
              total: counts.total,
            }}
          />
        </p>
      ) : null}
    </AnalyzeSection>
  );
}

function DecisionPanel({ view, scenarioKey }: { view: CompareView; scenarioKey: string | null }) {
  const { data: scenarios = [] } = useScenarios();
  const keys = Object.keys(view.decisions);
  const initial = scenarioKey && keys.includes(scenarioKey) ? scenarioKey : (keys[0] ?? null);
  const [picked, setPicked] = useState<string | null>(initial);
  const key = picked && keys.includes(picked) ? picked : initial;
  const decision = key ? (view.decisions[key] ?? null) : null;
  const nameOf = (k: string) => scenarios.find((s) => keyOf(s) === k)?.name ?? k;
  return (
    <AnalyzeSection eyebrow={t('page.G4.decision')} title={t('page.G4.decisionQ')}>
      {keys.length > 1 ? (
        <div
          role="radiogroup"
          aria-label={t('page.G4.decisionPick')}
          className="flex flex-wrap gap-1.5"
        >
          {keys.map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={k === key}
              onClick={() => setPicked(k)}
              className={radioClass(k === key)}
            >
              {nameOf(k)}
            </button>
          ))}
        </div>
      ) : null}
      {!decision ? (
        <EmptyState message={t('page.G4.noDecision')} />
      ) : (
        <div className="flex flex-col gap-4">
          <C07Decision data={{ decision }} asof={view.asof_date} />
          <VirtualCandidates decision={decision} />
          {decision.warnings.length > 0 ? (
            <Banner tone="warn" role="note" title={t('page.G4.warnings')} data-testid="g4-warnings">
              <ul className="m-0 mt-1 list-disc pl-5">
                {decision.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Banner>
          ) : null}
          <RequirementsTable decision={decision} asof={view.asof_date} />
        </div>
      )}
    </AnalyzeSection>
  );
}

/** 가상 후보(option_key 'wait_new', complex_id null — 계약 .5 '모집공고 대기')인가 */
const isVirtual = (item: DecisionSet['items'][number]) => item.option_key === 'wait_new';

/**
 * 가상 후보 '모집공고 대기'(계약 2026-10-09.5) — 단지가 아니라 비교 표 열이 없으므로 따로 보인다.
 * 표시 = 서버 label + 판정기 decide 고를 확률(Fact) + 선택·동률·근거와 달라요 배지(서버 값).
 */
function VirtualCandidates({ decision }: { decision: DecisionSet }) {
  const items = decision.items.filter(isVirtual);
  if (items.length === 0) return null;
  return (
    <ul aria-label={t('page.G4.virtual')} className="m-0 flex list-none flex-col gap-2 p-0">
      {items.map((item) => (
        <li
          key={item.option_key}
          data-option={item.option_key}
          className="flex flex-col gap-1 rounded-xl border border-dashed border-border-strong px-4 py-3 text-sm"
        >
          <span className="font-semibold text-fg">
            {t('page.G4.virtualCandidate', { label: item.label })}
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">{t('page.G4.row.prob')}</span>
            <FactCell fact={item.prob} unit="prob" />
            {item.chosen ? <Badge tone="accent">{t('chart.chosen')}</Badge> : null}
            <TieBadge tie={decision.status === 'ok' && item.tie} />
            <MismatchBadge mismatch={item.mismatch} />
          </span>
        </li>
      ))}
    </ul>
  );
}

const REQ_COLS = ['access', 'regulation', 'funds'] as const;

function RequirementsTable({ decision, asof }: { decision: DecisionSet; asof: string }) {
  const items = decision.items.filter((i) => i.requirements);
  if (items.length === 0) return null;
  const title = t('page.G4.requirements');
  return (
    <div className="flex flex-col gap-2">
      <h3 className="m-0 text-base font-bold text-fg sm:text-[17px]">{title}</h3>
      <div className="overflow-x-auto">
        <table aria-label={title} className={wideTableClass}>
          <thead>
            <tr>
              <th scope="col" className={headCellClass}>
                {t('page.G5.req.complex')}
              </th>
              {REQ_COLS.map((c) => (
                <th key={c} scope="col" className={headCellClass}>
                  <PlainName
                    name={t(`page.G5.req.${c}` as TKey)}
                    official={t(`page.G5.reqTerm.${c}` as TKey)}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.option_key}-${item.complex_id ?? item.label}`}>
                <th scope="row" className={`${cellClass} text-left font-semibold`}>
                  <span className="inline-flex flex-wrap items-center gap-1.5">
                    {item.label}
                    {isVirtual(item) ? <Badge tone="muted">{t('chart.C07.virtual')}</Badge> : null}
                  </span>
                </th>
                {REQ_COLS.map((c) => {
                  const check = item.requirements?.[c];
                  return (
                    <td key={c} className={cellClass}>
                      {check?.pre ? (
                        <span className="flex flex-col gap-1">
                          <span className="inline-flex flex-wrap items-center gap-1.5">
                            <ReqStatusBadge status={check.pre.status} />
                            <ReqJudgeText judge={check.judge} />
                            <MismatchBadge mismatch={check.mismatch} />
                          </span>
                          {/* 근거 문장 = 서버 문장 그대로(계약 .22: '중간 가격') */}
                          <span className="text-xs leading-snug text-muted">
                            {check.pre.evidence}
                          </span>
                        </span>
                      ) : (
                        <Badge tone="muted">{t('page.G4.reqNone')}</Badge>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <SourceLine>
        {t('page.G4.reqSource')} · {t('page.G5.reqDisclaimer')} · {t('chart.asofOnly', { asof })}
      </SourceLine>
    </div>
  );
}

const TERM_KEYS = [
  'resale_end',
  'residency_months',
  'down_payment_pct',
  'down_payment_won',
  'required_equity_won',
  'interim_terms_text',
] as const;

const TERM_GLOSSARY: Partial<Record<(typeof TERM_KEYS)[number], GlossaryKey>> = {
  resale_end: 'resale_end',
  required_equity_won: 'equity',
};

/** 행 머리의 (공식 이름) — 용어 사전의 용어 이름을 그대로 쓴다(ko `glossary.items.*.term`) */
const TERM_OFFICIAL: Partial<Record<(typeof TERM_KEYS)[number] | 'intake' | 'price', GlossaryKey>> =
  {
    intake: 'intake_status',
    price: 'current_price',
    resale_end: 'resale_limit',
    down_payment_won: 'down',
    required_equity_won: 'equity',
  };

/** 표 행 머리: 쉬운 이름 + (공식 이름) + 용어 '?' */
function TermHead({
  k,
  glossary,
}: {
  k: (typeof TERM_KEYS)[number] | 'intake' | 'price';
  glossary?: GlossaryKey | undefined;
}) {
  const officialKey = TERM_OFFICIAL[k];
  const official = officialKey ? glossaryItem(officialKey).term : null;
  return (
    <>
      <PlainName name={t(`page.G4.term.${k}` as TKey)} official={official} />
      {glossary ? (
        <>
          {' '}
          <Term k={glossary} />
        </>
      ) : null}
    </>
  );
}

/** N6 중도금 조건 긴 글 — 두 줄까지 보이고 [전체 보기]로 펼친다(서버 글 그대로) */
const INTERIM_CLAMP = 60;
function InterimText({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (text.length <= INTERIM_CLAMP) return <span className="text-fg-2">{text}</span>;
  return (
    <span className="flex flex-col items-start gap-1">
      <span className={`text-fg-2 ${open ? '' : 'line-clamp-2'}`} data-testid="interim-text">
        {text}
      </span>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="rounded-md border border-border-strong px-2 py-0.5 text-xs font-semibold text-fg-2"
      >
        {open ? t('page.G4.interimLess') : t('page.G4.interimMore')}
      </button>
    </span>
  );
}

function TermsTable({
  view,
  rows,
  colorOf,
}: {
  view: CompareView;
  rows: ScoreRow[];
  colorOf: (i: number) => string;
}) {
  const termOf = (id: number) => view.terms.find((x) => x.complex_id === id) ?? null;
  const search = useGlobalSearch();
  const title = t('page.G4.termsFirst');
  const equityMissing = rows.some((row) => {
    const v = termOf(row.complex_id)?.required_equity_won?.v;
    return v === null || v === undefined;
  });
  const row = (key: string, head: ReactNode, cell: (r: ScoreRow) => ReactNode) => (
    <tr key={key}>
      <th scope="row" className={rowHeadClass}>
        {head}
      </th>
      {rows.map((r) => (
        <td key={r.complex_id} className={cellClass}>
          {cell(r)}
        </td>
      ))}
    </tr>
  );
  return (
    <AnalyzeSection eyebrow={title} title={t('page.G4.termsQ')}>
      <div className="overflow-x-auto">
        <table aria-label={title} className={wideTableClass}>
          <thead>
            <tr>
              <th scope="col" className={headCellClass}>
                {t('page.G4.termsCorner')}
              </th>
              {rows.map((r, i) => (
                <th key={r.complex_id} scope="col" className={headCellClass}>
                  <ComplexHead row={r} index={i} color={colorOf(i)} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* 접수 상태(점수 행의 Intake 그대로) */}
            {row('intake', <TermHead k="intake" />, (r) => (
              <IntakeBadge intake={r.intake} asof={view.asof_date} />
            ))}
            {/* 현재 구매가 — 점수 행 Fact(계약 .20 F8), 없으면 가격 갭 응답의 같은 Fact(프론트 계산 없음) */}
            {row('price', <TermHead k="price" />, (r) => {
              const gap = view.gaps[String(r.complex_id)] ?? null;
              const low = r.price_low ?? gap?.price_low ?? null;
              const high = r.price_high ?? gap?.price_high ?? null;
              return low || high ? (
                <span className="inline-flex flex-wrap items-center gap-1 font-semibold">
                  <FactCell fact={low} unit="won" />
                  <span aria-hidden>~</span>
                  <FactCell fact={high} unit="won" />
                </span>
              ) : (
                <EmptyState inline />
              );
            })}
            {TERM_KEYS.map((key) =>
              row(key, <TermHead k={key} glossary={TERM_GLOSSARY[key]} />, (r) => {
                const term = termOf(r.complex_id);
                if (!term) return <EmptyState inline />;
                switch (key) {
                  case 'interim_terms_text':
                    return term.interim_terms_text ? (
                      <InterimText text={term.interim_terms_text} />
                    ) : (
                      <span className="text-muted">{t('page.G4.interimNone')}</span>
                    );
                  case 'resale_end':
                    return <FactCell fact={term.resale_end} unit="date" asof={view.asof_date} />;
                  case 'residency_months':
                    return <FactCell fact={term.residency_months} unit="number" />;
                  case 'down_payment_pct':
                    return <FactCell fact={term.down_payment_pct} unit="pct" digits={0} />;
                  default:
                    return <FactCell fact={term[key]} unit="won" />;
                }
              }),
            )}
          </tbody>
        </table>
      </div>
      {equityMissing ? (
        <Banner
          tone="info"
          data-testid="equity-note"
          actions={
            <Link
              to={`/scenario${search}`}
              className="text-sm font-semibold text-accent hover:underline"
            >
              {t('nav.G5')}
            </Link>
          }
        >
          {t('page.G4.equityNote')}
        </Banner>
      ) : null}
      <SourceLine>
        {t('page.G4.termsSourceNoAsof')}
        {view.asof_date ? ` · ${t('chart.asofOnly', { asof: view.asof_date })}` : null}
      </SourceLine>
    </AnalyzeSection>
  );
}
