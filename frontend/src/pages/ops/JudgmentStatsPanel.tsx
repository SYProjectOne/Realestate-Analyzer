import { useOpsJudgments } from '@/api/hooks';
import type { JudgmentOps } from '@/api/types';
import { Badge, MetaText, MetaValue } from '@/components';
import { t, tDynamic, type TKey } from '@/i18n';
import { JudgmentTable } from '../complex/JudgmentsTab';
import { QueryState } from '../_shared';
import { OpsSection } from './sections';

const DAY_MS = 86_400_000;

/** 30일 전 날짜(YYYY-MM-DD) — 기준일이 있으면 기준일에서, 없으면 오늘에서 */
export function since30(asof: string | null): string {
  const base = asof ? Date.parse(`${asof.slice(0, 10)}T00:00:00Z`) : Date.now();
  return new Date(base - 30 * DAY_MS).toISOString().slice(0, 10);
}

/** G7 JudgmentStats — 30일 호출 수·실패·캐시·도구별 막대(+ 최근 봉투) */
export function JudgmentStatsPanel({ asof }: { asof: string | null }) {
  const since = since30(asof);
  const query = useOpsJudgments({ since, size: 20 });
  const range = query.data?.stats
    ? { from: query.data.stats.since.slice(0, 10), to: query.data.stats.until.slice(0, 10) }
    : null;
  return (
    <OpsSection
      k="stats"
      actions={
        range ? (
          <Badge tone="muted">
            <span data-testid="stats-range">{t('page.G7.statsRange', range)}</span>
          </Badge>
        ) : null
      }
    >
      <QueryState query={query}>{(ops) => <StatsBody ops={ops} asof={asof} />}</QueryState>
    </OpsSection>
  );
}

function StatsBody({ ops, asof }: { ops: JudgmentOps; asof: string | null }) {
  const { stats } = ops;
  const tiles: { key: string; value: number }[] = [
    { key: 'total', value: stats.total_calls },
    { key: 'real', value: stats.real_calls },
    { key: 'cached', value: stats.cached_hits },
    { key: 'failures', value: stats.failures },
    { key: 'review', value: stats.review },
    { key: 'escaped', value: stats.escaped },
  ];
  const max = Math.max(1, ...stats.by_tool.map((b) => b.calls));
  return (
    <div className="flex flex-col gap-3">
      {stats.degraded ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {t('app.degraded')}
        </p>
      ) : null}
      <ul
        className="grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7"
        aria-label={t('page.G7.stats')}
      >
        {tiles.map((tile) => (
          <li key={tile.key} className="flex flex-col gap-1 rounded-xl border border-border p-3">
            <span className="text-xs text-muted">{t(`page.G7.stat.${tile.key}` as TKey)}</span>
            <MetaValue kind="count" value={tile.value} className="text-xl font-bold" />
          </li>
        ))}
        <li className="flex flex-col gap-1 rounded-xl border border-border p-3">
          <span className="text-xs text-muted">{t('page.G7.stat.avg')}</span>
          <span className="text-xl font-bold tabular-nums">
            {stats.avg_duration_ms === null ? (
              t('empty.unknown')
            ) : (
              <MetaText
                kind="duration"
                k="page.G3.judgment.ms"
                params={{ ms: { n: stats.avg_duration_ms, as: 'number' } }}
              />
            )}
          </span>
        </li>
      </ul>
      {/* 계약 .15 F2(D18-2): real_calls = 판정기로 실제 보낸 MCP tools/call 수(전송 계층 계수), total = real + cached */}
      <p className="text-xs text-muted" data-testid="judgment-real-hint">
        {t('page.G7.stat.realHint')}
      </p>
      <div className="flex flex-col gap-1">
        <h3 className="text-base font-bold">{t('page.G7.stat.byTool')}</h3>
        <ul aria-label={t('page.G7.stat.byTool')} className="flex flex-col gap-2 text-xs">
          {stats.by_tool.map((b) => {
            const params = { tool: b.tool, calls: b.calls, failures: b.failures };
            return (
              <li
                key={b.tool}
                className="grid grid-cols-1 items-center gap-1 sm:grid-cols-[13rem_1fr] sm:gap-3"
              >
                <span className="text-sm">
                  <b className="font-semibold">{tDynamic(`page.G7.toolName.${b.tool}`, b.tool)}</b>{' '}
                  <span className="text-muted">{b.tool}</span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <span
                    aria-hidden
                    className="h-3 rounded-sm bg-accent"
                    style={{ width: `${(b.calls / max) * 100}%`, minWidth: b.calls > 0 ? 2 : 0 }}
                  />
                  <MetaText
                    kind="count"
                    className="whitespace-nowrap text-muted"
                    k="page.G7.stat.bar"
                    params={params}
                  />
                  <MetaText
                    kind="count"
                    className="whitespace-nowrap text-muted"
                    k="page.G7.stat.barMore"
                    params={{ cached: b.cached, review: b.review, blocked: b.blocked }}
                  />
                </span>
              </li>
            );
          })}
        </ul>
        {stats.adapter_version ? (
          <span className="self-start">
            <Badge tone="muted">
              {t('page.G7.stat.adapter', { version: stats.adapter_version })}
            </Badge>
          </span>
        ) : null}
      </div>
      <JudgmentTable judgments={ops.items} asof={asof} caption={t('page.G7.stats')} />
    </div>
  );
}
