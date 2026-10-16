import type { ReactNode } from 'react';
import { useChecklist, useClaims, useIntakeQueue, useOpsSources } from '@/api/hooks';
import type { ChecklistItem, IntakeQueue, IntakeQueueCategory } from '@/api/types';
import { MetaText } from '@/components';
import { t, type TKey } from '@/i18n';
import { enumText } from '../_shared';
import { contradictedClaims } from './ClaimsPanel';
import { opsMenuText, opsSection, SectionLink, type OpsSectionKey } from './sections';
import { failingSources } from './SourceStatusTable';

const DAY_MS = 86_400_000;

/** 기준일 + n일(YYYY-MM-DD) */
export function addDays(date: string, days: number): string {
  const base = Date.parse(`${date.slice(0, 10)}T00:00:00Z`);
  return new Date(base + days * DAY_MS).toISOString().slice(0, 10);
}

/**
 * '2주 안 다가오는 기한' — 열린 항목 중 기한이 기준일 ~ 기준일+14일인 줄 수, 그리고 기한이 기준일보다 앞인데 아직 열린 줄 수
 * (줄 세기 — D25-3. 무엇이 급한지 판단하지 않는다)
 */
export function dueCounts(
  items: readonly ChecklistItem[],
  asof: string,
): { soon: number; overdue: number; from: string; to: string } {
  const from = asof.slice(0, 10);
  const to = addDays(from, 14);
  let soon = 0;
  let overdue = 0;
  for (const item of items) {
    if (item.status !== 'open' || !item.due_date) continue;
    const due = item.due_date.slice(0, 10);
    if (due < from) overdue += 1;
    else if (due <= to) soon += 1;
  }
  return { soon, overdue, from, to };
}

/** 대기열 분류별 줄 수(서버 순서 그대로) */
export function intakeCategoryCounts(
  queue: IntakeQueue,
): { category: IntakeQueueCategory; n: number }[] {
  const counts = new Map<IntakeQueueCategory, number>();
  for (const g of queue.groups) {
    counts.set(g.category, (counts.get(g.category) ?? 0) + g.items.length);
  }
  return [...counts.entries()].map(([category, n]) => ({ category, n }));
}

/**
 * G7 '오늘 확인할 것' 타일 4장(목업 N2·OP-10) — 값은 서버 수(대기열 `total`) 또는 줄 개수만(D25-3).
 * '급한 것' 같은 판단 이름을 붙이지 않고 대기열 분류 이름·건수를 그대로 적는다. 각 타일은 그 묶음으로 가는 링크.
 * 지역·기준일이 정해지기 전에는(첫 로딩) 조회하지 않는다.
 */
export function TodayTiles({
  regionId,
  snapshotId,
  asof,
  enabled,
}: {
  regionId: number | null;
  snapshotId: string | null;
  asof: string | null;
  enabled: boolean;
}) {
  return (
    <section aria-label={t('page.G7.today.title')} className="flex flex-col gap-2">
      <h2 className="sr-only">{t('page.G7.today.title')}</h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="today-tiles">
        {enabled ? (
          <TilesBody regionId={regionId} snapshotId={snapshotId} asof={asof} />
        ) : (
          (['intake', 'sources', 'claims', 'checklist'] as const).map((k) => (
            <Tile key={k} k={k} label={tileLabel(k)} value={t('page.G7.today.loading')} />
          ))
        )}
      </div>
      <p className="text-xs text-muted">{t('page.G7.today.rule')}</p>
    </section>
  );
}

const TILE_LABEL: Record<'intake' | 'sources' | 'claims' | 'checklist', TKey> = {
  intake: 'page.G7.today.intake',
  sources: 'page.G7.today.sources',
  claims: 'page.G7.today.claims',
  checklist: 'page.G7.today.due',
};

function tileLabel(k: keyof typeof TILE_LABEL): string {
  return t(TILE_LABEL[k]);
}

function TilesBody({
  regionId,
  snapshotId,
  asof,
}: {
  regionId: number | null;
  snapshotId: string | null;
  asof: string | null;
}) {
  const hasScope = regionId !== null || snapshotId !== null;
  const queue = useIntakeQueue(regionId, snapshotId, hasScope);
  const sources = useOpsSources(regionId);
  const claims = useClaims(snapshotId);
  const checklist = useChecklist();
  const loading = t('page.G7.today.loading');
  const unknown = t('page.G7.today.unknown');

  // ① 사람 확인이 필요한 단지 — 서버 total + 분류별 줄 수
  const q = queue.data;
  const intakeParts = q ? intakeCategoryCounts(q) : [];
  const intakeTile = (
    <Tile
      k="intake"
      label={tileLabel('intake')}
      tone={q && q.total > 0 ? 'warn' : 'default'}
      value={
        q ? (
          <MetaText kind="count" k="page.G7.iq.total" params={{ n: q.total }} />
        ) : queue.error || !hasScope ? (
          unknown
        ) : (
          loading
        )
      }
      sub={
        q ? (
          intakeParts.length === 0 ? (
            t('page.G7.today.intakeNone')
          ) : (
            <span data-testid="tile-intake-parts">
              {intakeParts.map((p, i) => (
                <span key={p.category}>
                  {i > 0 ? ' · ' : ''}
                  <MetaText
                    kind="count"
                    k="page.G7.today.part"
                    params={{ name: t(`page.G7.iq.category.${p.category}` as TKey), n: p.n }}
                  />
                </span>
              ))}
            </span>
          )
        ) : null
      }
    />
  );

  // ② 수집이 실패한 자료 — 실패가 있는 자료 줄 수
  const rows = sources.data;
  const failing = rows ? failingSources(rows) : [];
  const sourcesTile = (
    <Tile
      k="sources"
      label={tileLabel('sources')}
      tone={failing.length > 0 ? 'warn' : 'default'}
      value={
        rows ? (
          <MetaText kind="count" k="page.G7.today.countKinds" params={{ n: failing.length }} />
        ) : sources.error ? (
          unknown
        ) : (
          loading
        )
      }
      sub={
        rows
          ? failing.length === 0
            ? t('page.G7.today.sourcesNone')
            : t('page.G7.today.sourcesSub', {
                names: failing
                  .map((r) => enumText('page.G7.sourceKind', r.source_kind))
                  .join(' · '),
              })
          : null
      }
    />
  );

  // ③ 모순 주장 — 목록(상태 필터 없음)에서 모순 줄 수
  const claimRows = claims.data;
  const contradicted = claimRows ? contradictedClaims(claimRows).length : null;
  const claimsTile = (
    <Tile
      k="claims"
      label={tileLabel('claims')}
      tone={contradicted !== null && contradicted > 0 ? 'warn' : 'default'}
      value={
        contradicted !== null ? (
          <MetaText kind="count" k="page.G7.iq.total" params={{ n: contradicted }} />
        ) : claims.error || snapshotId === null ? (
          unknown
        ) : (
          loading
        )
      }
      sub={contradicted !== null ? t('page.G7.today.claimsSub') : null}
    />
  );

  // ④ 2주 안 다가오는 기한 — 열린 항목 줄 수
  const items = checklist.data;
  const due = items && asof ? dueCounts(items, asof) : null;
  const dueTile = (
    <Tile
      k="checklist"
      label={tileLabel('checklist')}
      value={
        due ? (
          <MetaText kind="count" k="page.G7.iq.total" params={{ n: due.soon }} />
        ) : checklist.error || (items && !asof) ? (
          unknown
        ) : (
          loading
        )
      }
      sub={
        due ? (
          <>
            {t('page.G7.today.dueSub', { from: due.from, to: due.to })}
            {due.overdue > 0 ? (
              <>
                {' · '}
                <MetaText kind="count" k="page.G7.today.overdue" params={{ n: due.overdue }} />
              </>
            ) : null}
          </>
        ) : null
      }
    />
  );

  return (
    <>
      {intakeTile}
      {sourcesTile}
      {claimsTile}
      {dueTile}
    </>
  );
}

function Tile({
  k,
  label,
  value,
  sub,
  tone = 'default',
}: {
  k: OpsSectionKey;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'default' | 'warn';
}) {
  const def = opsSection(k);
  return (
    <SectionLink
      id={def.id}
      data-testid={`tile-${k}`}
      className={`flex min-h-36 flex-col gap-2 rounded-2xl border p-4 text-fg no-underline hover:border-accent ${
        tone === 'warn' ? 'border-warn-border bg-warn-soft' : 'border-border bg-surface'
      }`}
    >
      <span className="flex items-center justify-between gap-2 text-sm font-semibold text-fg-2">
        {label}
        <span
          aria-hidden
          className={`size-2.5 shrink-0 rounded-full ${tone === 'warn' ? 'bg-warn' : 'bg-accent'}`}
        />
      </span>
      <span className="text-[28px] font-bold leading-tight tracking-tight tabular-nums">
        {value}
      </span>
      {sub ? <span className="text-[13px] leading-snug text-fg-2">{sub}</span> : null}
      <span className="mt-auto text-[13px] font-semibold text-accent">
        {t('page.G7.today.go', { name: opsMenuText(k) })}
      </span>
    </SectionLink>
  );
}
