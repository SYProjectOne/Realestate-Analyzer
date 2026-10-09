import { useOpsJudgments } from '@/api/hooks';
import type { JudgmentOps } from '@/api/types';
import { Badge } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatCount, formatNumber } from '@/lib/format';
import { JudgmentTable } from '../complex/JudgmentsTab';
import { QueryState, Section } from '../_shared';

const DAY_MS = 86_400_000;

/** 30일 전 날짜(YYYY-MM-DD) — 기준일이 있으면 기준일에서, 없으면 오늘에서 */
export function since30(asof: string | null): string {
  const base = asof ? Date.parse(`${asof.slice(0, 10)}T00:00:00Z`) : Date.now();
  return new Date(base - 30 * DAY_MS).toISOString().slice(0, 10);
}

/** G7 JudgmentStats — 30일 호출 수·실패·캐시·도구별 막대(+ 최근 봉투) */
export function JudgmentStatsPanel({ asof }: { asof: string | null }) {
  const query = useOpsJudgments({ since: since30(asof), size: 20 });
  return (
    <Section title={t('page.G7.stats')}>
      <QueryState query={query}>{(ops) => <StatsBody ops={ops} asof={asof} />}</QueryState>
    </Section>
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
      <ul className="grid grid-cols-3 gap-2 md:grid-cols-7" aria-label={t('page.G7.stats')}>
        {tiles.map((tile) => (
          <li key={tile.key} className="flex flex-col rounded-sm border border-border p-2">
            <span className="text-xs text-muted">{t(`page.G7.stat.${tile.key}` as TKey)}</span>
            <span className="text-lg font-semibold tabular-nums">{formatCount(tile.value)}</span>
          </li>
        ))}
        <li className="flex flex-col rounded-sm border border-border p-2">
          <span className="text-xs text-muted">{t('page.G7.stat.avg')}</span>
          <span className="text-lg font-semibold tabular-nums">
            {stats.avg_duration_ms === null
              ? t('empty.unknown')
              : t('page.G3.judgment.ms', { ms: formatNumber(stats.avg_duration_ms) })}
          </span>
        </li>
      </ul>
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-medium">{t('page.G7.stat.byTool')}</h3>
        <ul aria-label={t('page.G7.stat.byTool')} className="flex flex-col gap-1 text-xs">
          {stats.by_tool.map((b) => {
            const text = t('page.G7.stat.bar', {
              tool: b.tool,
              calls: formatCount(b.calls),
              failures: formatCount(b.failures),
            });
            return (
              <li key={b.tool} className="grid grid-cols-[6rem_1fr] items-center gap-2">
                <span>{b.tool}</span>
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="h-3 rounded-sm bg-accent"
                    style={{ width: `${(b.calls / max) * 100}%`, minWidth: b.calls > 0 ? 2 : 0 }}
                  />
                  <span className="whitespace-nowrap text-muted">{text}</span>
                </span>
              </li>
            );
          })}
        </ul>
        {stats.adapter_version ? (
          <Badge tone="muted">
            {t('page.G7.stat.adapter', { version: stats.adapter_version })}
          </Badge>
        ) : null}
      </div>
      <JudgmentTable judgments={ops.items} asof={asof} caption={t('page.G7.stats')} />
    </div>
  );
}
