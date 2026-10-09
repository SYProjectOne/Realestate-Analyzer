import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useCompare, useScenarios, useSensitivity } from '@/api/hooks';
import type { CompareView, DecisionSet, LadderHorizon, ScoreRow } from '@/api/types';
import { C01Ladder, C02Gap, C06ScoreBreakdown, C07Decision, C10Sensitivity } from '@/charts';
import {
  Badge,
  EmptyState,
  FactCell,
  IntakeBadge,
  MismatchBadge,
  TieBadge,
  UnstableBadge,
} from '@/components';
import { scenarioKey as keyOf } from '@/hooks/useScenario';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatCount, formatRank } from '@/lib/format';
import {
  enumText,
  NoSnapshot,
  QueryState,
  Section,
  tdClass,
  thClass,
  useGlobalSearch,
  usePageContext,
} from '../_shared';

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
 * G4 비교 `/compare?ids=` (RA §7-1) — ids 2~6 검사, 상황 토글 공유.
 * CompareGrid(열 = 단지) · C6 가로 · C1 overlay · C2 나란히 · TermsTable · DecisionPanel(C7·배지) · C10
 */
export function ComparePage() {
  const [params] = useSearchParams();
  const ids = parseIds(params.get('ids'));
  const { snapshotId, scenarioKey, isLoading } = usePageContext();
  const valid = ids.length >= MIN_IDS && ids.length <= MAX_IDS;
  const query = useCompare(snapshotId, valid ? ids : [], scenarioKey);
  const search = useGlobalSearch();

  return (
    <PageShell title={t('page.G4.title')}>
      {!valid ? (
        <EmptyState message={t('page.G4.invalidIds', { n: formatCount(ids.length) })}>
          <Link to={`/complexes${search}`} className="underline">
            {t('page.common.backToList')}
          </Link>
        </EmptyState>
      ) : !snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>
          {(view) => <CompareBody view={view} scenarioKey={scenarioKey} />}
        </QueryState>
      )}
    </PageShell>
  );
}

function CompareBody({ view, scenarioKey }: { view: CompareView; scenarioKey: string | null }) {
  const { snapshotId } = usePageContext();
  const sensitivity = useSensitivity(snapshotId, scenarioKey);
  const rows = orderRows(view);
  const names = Object.fromEntries(rows.map((r) => [String(r.complex_id), r.name]));
  return (
    <div className="flex flex-col gap-4">
      <CompareGrid view={view} rows={rows} scenarioKey={scenarioKey} />
      <C06ScoreBreakdown
        data={{ rows, weights: view.components.weights, orientation: 'horizontal' }}
        height={Math.max(180, rows.length * 48)}
      />
      <LadderOverlay view={view} rows={rows} />
      <Section title={t('page.G4.gaps')}>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((row) => (
            <C02Gap
              key={row.complex_id}
              title={row.name}
              data={{ gap: view.gaps[String(row.complex_id)] ?? null }}
              height={240}
            />
          ))}
        </div>
      </Section>
      <TermsTable view={view} rows={rows} />
      <DecisionPanel view={view} scenarioKey={scenarioKey} />
      {sensitivity.data ? <C10Sensitivity data={{ sensitivity: sensitivity.data, names }} /> : null}
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

function CompareGrid({
  view,
  rows,
  scenarioKey,
}: {
  view: CompareView;
  rows: ScoreRow[];
  scenarioKey: string | null;
}) {
  const decision = currentDecision(view, scenarioKey);
  const decisionOf = (id: number) => decision?.items.find((i) => i.complex_id === id) ?? null;
  const search = useGlobalSearch();
  return (
    <div className="overflow-x-auto rounded border border-border bg-surface">
      <table aria-label={t('page.G4.grid')} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th scope="col" className={thClass}>
              <span className="sr-only">{t('page.G4.grid')}</span>
            </th>
            {rows.map((row) => (
              <th key={row.complex_id} scope="col" className={`${thClass} text-sm text-fg`}>
                <Link to={`/complexes/${row.complex_id}${search}`} className="hover:underline">
                  {row.name}
                </Link>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className={thClass}>
              {t('page.G4.row.total')}
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={tdClass}>
                <FactCell fact={row.total} unit="score" />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={thClass}>
              {t('page.G4.row.rank')}
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={tdClass}>
                <span className="inline-flex flex-wrap gap-1">
                  {row.rank !== null ? formatRank(row.rank) : t('empty.unknown')}
                  <TieBadge tie={row.tie_group !== null} />
                  <UnstableBadge unstable={row.unstable} />
                </span>
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={thClass}>
              {t('page.G4.row.p10')}
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={tdClass}>
                <FactCell fact={row.p10} unit="prob" />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={thClass}>
              {t('page.G4.row.intake')}
            </th>
            {rows.map((row) => (
              <td key={row.complex_id} className={tdClass}>
                <IntakeBadge intake={row.intake} asof={view.asof_date} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={thClass}>
              {t('page.G4.row.decision')}
            </th>
            {rows.map((row) => {
              const item = decisionOf(row.complex_id);
              const badge = row.decision;
              return (
                <td key={row.complex_id} className={tdClass}>
                  <span className="inline-flex flex-wrap items-center gap-1">
                    <FactCell fact={item?.prob ?? badge?.prob ?? null} unit="prob" />
                    {(item?.chosen ?? badge?.chosen) ? (
                      <Badge tone="strong">{t('chart.chosen')}</Badge>
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

const HORIZONS: readonly LadderHorizon[] = ['move_in_plus_1y', 'asof_plus_3y', 'asof_plus_5y'];

function LadderOverlay({ view, rows }: { view: CompareView; rows: ScoreRow[] }) {
  const [horizon, setHorizon] = useState<LadderHorizon>('move_in_plus_1y');
  const overlay = rows.map((row) => ({
    complex_id: row.complex_id,
    name: row.name,
    ladder: view.ladders[String(row.complex_id)] ?? [],
  }));
  return (
    <Section
      title={t('page.G4.ladder')}
      actions={
        <div role="radiogroup" aria-label={t('page.G3.ladder.horizons')} className="flex gap-1">
          {HORIZONS.map((h) => (
            <button
              key={h}
              type="button"
              role="radio"
              aria-checked={h === horizon}
              onClick={() => setHorizon(h)}
              className={`rounded border border-border px-2 py-0.5 text-xs ${
                h === horizon ? 'bg-accent text-accent-fg' : ''
              }`}
            >
              {enumText('chart.C01.horizon', h)}
            </button>
          ))}
        </div>
      }
    >
      <C01Ladder data={{ ladder: overlay[0]?.ladder ?? [], horizon, overlay }} height={260} />
    </Section>
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

function TermsTable({ view, rows }: { view: CompareView; rows: ScoreRow[] }) {
  const termOf = (id: number) => view.terms.find((x) => x.complex_id === id) ?? null;
  return (
    <Section title={t('page.G4.terms')}>
      <div className="overflow-x-auto">
        <table aria-label={t('page.G4.terms')} className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th scope="col" className={thClass}>
                <span className="sr-only">{t('page.G4.terms')}</span>
              </th>
              {rows.map((row) => (
                <th key={row.complex_id} scope="col" className={`${thClass} text-fg`}>
                  {row.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TERM_KEYS.map((key) => (
              <tr key={key}>
                <th scope="row" className={thClass}>
                  {t(`page.G4.term.${key}` as TKey)}
                </th>
                {rows.map((row) => {
                  const term = termOf(row.complex_id);
                  return (
                    <td key={row.complex_id} className={tdClass}>
                      {!term ? (
                        <EmptyState inline />
                      ) : key === 'interim_terms_text' ? (
                        (term.interim_terms_text ?? t('page.common.none'))
                      ) : key === 'resale_end' ? (
                        <FactCell fact={term.resale_end} unit="date" asof={view.asof_date} />
                      ) : key === 'residency_months' ? (
                        <FactCell fact={term.residency_months} unit="number" />
                      ) : key === 'down_payment_pct' ? (
                        <FactCell fact={term.down_payment_pct} unit="pct" digits={0} />
                      ) : (
                        <FactCell fact={term[key]} unit="won" />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
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
    <Section
      title={t('page.G4.decision')}
      actions={
        keys.length > 1 ? (
          <div role="radiogroup" aria-label={t('page.G4.decision')} className="flex gap-1">
            {keys.map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={k === key}
                onClick={() => setPicked(k)}
                className={`rounded border border-border px-2 py-0.5 text-xs ${
                  k === key ? 'bg-accent text-accent-fg' : ''
                }`}
              >
                {t('page.G4.decisionScenario', { name: nameOf(k) })}
              </button>
            ))}
          </div>
        ) : null
      }
    >
      {!decision ? (
        <EmptyState message={t('page.G4.noDecision')} />
      ) : (
        <div className="flex flex-col gap-3">
          <C07Decision data={{ decision }} />
          {decision.warnings.length > 0 ? (
            <div className="text-sm">
              <h3 className="font-medium">{t('page.G4.warnings')}</h3>
              <ul className="list-disc pl-5">
                {decision.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <RequirementsTable decision={decision} />
        </div>
      )}
    </Section>
  );
}

function RequirementsTable({ decision }: { decision: DecisionSet }) {
  const items = decision.items.filter((i) => i.requirements);
  if (items.length === 0) return null;
  const cols = ['access', 'regulation', 'funds'] as const;
  return (
    <div className="overflow-x-auto">
      <table aria-label={t('page.G4.requirements')} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th scope="col" className={thClass}>
              {t('page.G5.req.complex')}
            </th>
            {cols.map((c) => (
              <th key={c} scope="col" className={thClass}>
                {t(`page.G5.req.${c}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.option_key}-${item.complex_id ?? item.label}`}>
              <th scope="row" className={`${tdClass} text-left font-normal`}>
                {item.label}
              </th>
              {cols.map((c) => {
                const check = item.requirements?.[c];
                return (
                  <td key={c} className={tdClass}>
                    {check?.pre ? (
                      <span className="inline-flex flex-wrap items-center gap-1">
                        <Badge tone={check.pre.status === '충족' ? 'neutral' : 'muted'}>
                          {enumText('page.G5.reqStatus', check.pre.status)}
                        </Badge>
                        {check.judge ? <Badge tone="muted">{check.judge}</Badge> : null}
                        <MismatchBadge mismatch={check.mismatch} />
                        <span className="w-full text-xs text-muted">{check.pre.evidence}</span>
                      </span>
                    ) : (
                      <EmptyState inline />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
