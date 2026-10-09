import type { MouseEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router';
import { useDashboard } from '@/api/hooks';
import type { ChangeEvent, Dashboard, ScoreRow } from '@/api/types';
import { C05Unsold, C06ScoreBreakdown } from '@/charts';
import { Badge, EmptyState, FactCell, IntakeBadge, TieBadge, UnstableBadge } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { t } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { formatCount, formatDate, formatRank } from '@/lib/format';
import {
  enumText,
  NoSnapshot,
  QueryState,
  Section,
  useGlobalSearch,
  usePageContext,
} from '../_shared';

/**
 * G1 홈 대시보드 `/` (RA §7-1) — KpiTiles(5), Top5Cards, ChangeFeed, C5 작게, C6.
 * 상황 토글(헤더, URL ?scenario=) → dashboard 재조회. 카드 클릭 → G3, 피드 항목 → G3 해당 탭.
 * 지역이 하나도 없으면 /regions/new 로 보낸다(D2-5).
 */
export function DashboardPage() {
  const { isEmpty } = useActiveRegion();
  const { snapshotId, scenarioKey, isLoading } = usePageContext();
  const query = useDashboard(snapshotId, scenarioKey);

  if (isEmpty) return <Navigate to="/regions/new" replace />;

  return (
    <PageShell title={t('page.G1.title')}>
      {!snapshotId && !isLoading ? (
        <NoSnapshot />
      ) : (
        <QueryState query={query}>{(dashboard) => <DashboardBody data={dashboard} />}</QueryState>
      )}
    </PageShell>
  );
}

function DashboardBody({ data }: { data: Dashboard }) {
  const asof = data.asof_date;
  const top = data.top5.filter((row) => row.rank === null || row.rank <= 5);
  return (
    <div className="flex flex-col gap-4">
      <KpiTiles data={data} />
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Section
          title={t('page.G1.top5')}
          actions={
            <span className="text-xs text-muted">
              {t('page.G1.top5Scenario', { name: data.scenario_name })}
            </span>
          }
        >
          <ul aria-label={t('page.G1.top5')} className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {top.map((row) => (
              <Top5Card key={row.complex_id} row={row} asof={asof} />
            ))}
          </ul>
        </Section>
        <ChangeFeed changes={data.changes} asof={asof} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <C06ScoreBreakdown data={{ rows: top, weights: data.weights, orientation: 'vertical' }} />
        <C05Unsold data={{ unsold: data.unsold_series }} height={200} />
      </div>
    </div>
  );
}

function KpiTiles({ data }: { data: Dashboard }) {
  const { kpis, asof_date: asof } = data;
  const tiles = [
    {
      key: 'judged',
      title: t('page.G1.kpi.judged'),
      body: <FactCell fact={kpis.judged_count} unit="count" />,
    },
    {
      key: 'intakeOpen',
      title: t('page.G1.kpi.intakeOpen'),
      body: <FactCell fact={kpis.intake_open_count} unit="count" />,
    },
    {
      key: 'unsold',
      title: t('page.G1.kpi.unsold'),
      body: <FactCell fact={kpis.unsold.total} unit="households" />,
      sub: (
        <>
          <span>{t('page.G1.kpi.unsoldSub', { ym: kpis.unsold.ym ?? t('empty.unknown') })}</span>{' '}
          <FactCell fact={kpis.unsold.post_completion} unit="households" />
        </>
      ),
    },
    {
      key: 'movePeak',
      title: t('page.G1.kpi.movePeak'),
      body: <FactCell fact={kpis.move_in_peak.year} unit="text" />,
      sub: <FactCell fact={kpis.move_in_peak.units} unit="households" />,
    },
    {
      key: 'freshness',
      title: t('page.G1.kpi.freshness'),
      body: <FactCell fact={kpis.data_freshness.last_success_at} unit="date" asof={asof} />,
      sub: (
        <span>
          {t('page.G1.kpi.freshnessSub', {
            failing: formatCount(kpis.data_freshness.failing_sources),
            stale: formatCount(kpis.data_freshness.stale_sources),
          })}
        </span>
      ),
    },
  ];
  return (
    <ul aria-label={t('page.G1.kpis')} className="grid grid-cols-2 gap-2 md:grid-cols-5">
      {tiles.map((tile) => (
        <li
          key={tile.key}
          className="flex flex-col gap-1 rounded border border-border bg-surface p-3"
          data-kpi={tile.key}
        >
          <span className="text-xs text-muted">{tile.title}</span>
          <span className="text-lg font-semibold">{tile.body}</span>
          {tile.sub ? <span className="text-xs text-muted">{tile.sub}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function Top5Card({ row, asof }: { row: ScoreRow; asof: string }) {
  const navigate = useNavigate();
  const search = useGlobalSearch();
  const to = `/complexes/${row.complex_id}${search}`;
  // 카드 빈 곳 클릭 → G3. 안쪽 버튼(숫자 셀 = 출처 패널)·링크 클릭은 그대로 둔다.
  const onClick = (event: MouseEvent<HTMLLIElement>) => {
    if ((event.target as HTMLElement).closest('button, a')) return;
    navigate(to);
  };
  return (
    <li
      onClick={onClick}
      className="flex cursor-pointer flex-col gap-2 rounded border border-border p-3 hover:border-accent"
      data-complex-id={row.complex_id}
    >
      <div className="flex items-start justify-between gap-2">
        <Link
          to={to}
          className="font-medium hover:underline"
          aria-label={t('page.G1.open', { name: row.name })}
        >
          {row.name}
        </Link>
        {row.rank !== null ? <Badge tone="strong">{formatRank(row.rank)}</Badge> : null}
      </div>
      {row.living_area_name ? (
        <span className="text-xs text-muted">{row.living_area_name}</span>
      ) : null}
      <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm">
        <dt className="text-muted">{t('page.G1.total')}</dt>
        <dd>
          <FactCell fact={row.total} unit="score" />
        </dd>
        <dt className="text-muted">{t('page.G1.p10')}</dt>
        <dd>
          <FactCell fact={row.p10} unit="prob" />
        </dd>
      </dl>
      <div className="flex flex-wrap gap-1">
        <IntakeBadge intake={row.intake} asof={asof} />
        <TieBadge
          tie={row.tie_group !== null || row.decision?.tie === true}
          confidence={row.decision?.tie ? (row.decision.confidence ?? null) : null}
        />
        <UnstableBadge unstable={row.unstable} />
      </div>
    </li>
  );
}

function ChangeFeed({ changes, asof }: { changes: ChangeEvent[]; asof: string }) {
  const search = useGlobalSearch();
  return (
    <Section title={t('page.G1.changes')}>
      {changes.length === 0 ? (
        <EmptyState message={t('page.G1.noChanges')} />
      ) : (
        <ul aria-label={t('page.G1.changes')} className="flex flex-col divide-y divide-border">
          {changes.map((change) => {
            const body = (
              <>
                <span className="flex flex-wrap items-center gap-1">
                  <Badge tone={change.severity === 'critical' ? 'strong' : 'muted'}>
                    {enumText('page.common.severity', change.severity)}
                  </Badge>
                  {change.triggers_rejudge ? (
                    <Badge tone="muted">{t('page.G1.rejudge')}</Badge>
                  ) : null}
                  <span className="font-medium">{change.complex_name ?? change.entity}</span>
                </span>
                <span className="text-sm">
                  {change.field}{' '}
                  {t('page.common.arrow', {
                    old: change.old_text ?? t('page.common.none'),
                    new: change.new_text ?? t('page.common.none'),
                  })}
                </span>
                <span className="text-xs text-muted">{formatDate(change.detected_at, asof)}</span>
              </>
            );
            return (
              <li key={change.id} className="py-2">
                {change.complex_id ? (
                  <Link
                    to={`/complexes/${change.complex_id}${search}${change.tab ? `#${change.tab}` : ''}`}
                    className="flex flex-col gap-0.5 hover:underline"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="flex flex-col gap-0.5">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
