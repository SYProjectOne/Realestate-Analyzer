/**
 * 화면 공용 조각(WP6a 소유). 여러 화면이 같은 모양을 쓰는 것만 둔다.
 * 공통 컴포넌트(@/components)로 올릴 만한 것은 보고서 "공통화 제안"에 적는다.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import type { Fact, JudgeScope } from '@/api/types';
import { Badge, EmptyState } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { useMobileLayout } from '@/hooks/useMobileLayout';
import { useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, tDynamic } from '@/i18n';
import type { FactUnit } from '@/lib/format';

export interface PageContext {
  regionId: number | null;
  /** URL 문자열 id(훅에 그대로 넘긴다) */
  snapshotId: string | null;
  /** D± 기준일 */
  asof: string | null;
  /** URL ?scenario= (null = 서버 기본 base) */
  scenarioKey: string | null;
  readOnly: boolean;
  isLoading: boolean;
}

/** 지역·기준일·상황·모바일 읽기 전용 — 모든 화면이 같은 전역 상태를 읽는다(RA §7 공통 규칙). */
export function usePageContext(): PageContext {
  const { region, isLoading: regionLoading } = useActiveRegion();
  const { snapshotId, snapshot, isLoading } = useSnapshot();
  const { scenarioId } = useScenario();
  const { readOnly } = useMobileLayout();
  const asof =
    snapshot?.asof_date ??
    (region?.latest_snapshot && String(region.latest_snapshot.id) === snapshotId
      ? region.latest_snapshot.asof_date
      : null);
  return {
    regionId: region?.id ?? null,
    snapshotId,
    asof,
    scenarioKey: scenarioId,
    readOnly,
    isLoading: regionLoading || isLoading,
  };
}

/** 카드형 구역: h2 + 본문 */
export function Section({
  title,
  actions,
  children,
  className = '',
  id,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      aria-label={title}
      className={`flex flex-col gap-3 rounded-sm border border-border bg-surface p-3 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

/** 쿼리 상태(로딩·오류·데이터) 공통 표시 */
export function QueryState<T>({
  query,
  children,
  empty,
}: {
  query: { data: T | undefined; error: Error | null; isLoading: boolean };
  children: (data: T) => ReactNode;
  /** 데이터가 비었을 때 보일 문구(판단은 호출 측: data → boolean) */
  empty?: (data: T) => string | null;
}) {
  if (query.data !== undefined) {
    const emptyText = empty?.(query.data) ?? null;
    if (emptyText) return <EmptyState message={emptyText} />;
    return <>{children(query.data)}</>;
  }
  if (query.error) {
    return <EmptyState message={t('page.common.loadError', { detail: query.error.message })} />;
  }
  return (
    <p role="status" className="text-sm text-muted">
      {t('app.loading')}
    </p>
  );
}

/** 스냅샷이 없을 때(지역 분석 전) 안내 */
export function NoSnapshot() {
  return <EmptyState message={t('app.noSnapshot')} />;
}

/** 값 디바운스(G0 자동완성) */
export function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

/** 다른 화면으로 갈 때 전역 쿼리(region·snapshot·scenario)를 유지한 search 문자열 */
export function useGlobalSearch(): string {
  const [params] = useSearchParams();
  const keep = new URLSearchParams();
  for (const key of ['region', 'snapshot', 'scenario']) {
    const v = params.get(key);
    if (v) keep.set(key, v);
  }
  const s = keep.toString();
  return s ? `?${s}` : '';
}

/** 서버 enum 값 → ko.json 표시 문자열(없으면 값 그대로) */
export function enumText(prefix: string, value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return t('page.common.none');
  return tDynamic(`${prefix}.${value}`, value);
}

/**
 * 판정 범위 배지(C2, 계약 2026-10-09.4) — 표시 문구는 ko.json `page.common.judgeScope`.
 * `hideTarget`이면 '판정 대상'은 그리지 않는다(표·카드에서 예외만 드러낸다).
 */
export function JudgeScopeBadge({
  scope,
  hideTarget = false,
}: {
  scope: JudgeScope | null | undefined;
  hideTarget?: boolean;
}) {
  if (!scope || (hideTarget && scope === '판정 대상')) return null;
  return (
    <span data-testid="judge-scope" data-scope={scope}>
      <Badge tone={scope === '판정 대상' ? 'neutral' : 'muted'}>
        {enumText('page.common.judgeScope', scope)}
      </Badge>
    </span>
  );
}

/**
 * '재판정 필요' 배지(D10-1, 계약 2026-10-09.6 rejudge_needed). 행의 범위·순위·총점은 그 스냅샷의 저장값이고,
 * 현재 사실로 계산한 범위가 저장값과 다르다는 표시만 한다(현재값을 같은 행에 섞지 않는다). false·없음이면 그리지 않는다.
 */
export function RejudgeNeededBadge({ needed }: { needed: boolean | null | undefined }) {
  if (!needed) return null;
  return (
    <span data-testid="rejudge-needed" title={t('page.common.rejudgeNeededHint')}>
      <Badge tone="strong">{t('page.common.rejudgeNeeded')}</Badge>
    </span>
  );
}

/** 행 번호 표기 "#127" (판정 seq·잡 id — 수치가 아니라 식별자) */
export function idText(id: number | string | null | undefined): string {
  return id === null || id === undefined ? '' : `#${String(id)}`;
}

/**
 * 표본 건수 Fact — 집계 사실(중앙값 등)의 건수 n 을 **그 사실과 같은 출처·확인일**로 보인다
 * (R3c: 실거래 건수가 FactCell 밖이던 것).
 * 라벨은 근거가 있을 때만 '확인됨'이다(5차 리뷰 minor — 화면이 근거 없이 '확인됨'을 만들지 않는다):
 *  - 집계 사실이 '확인됨' = 서버가 센 표본 행이 전부 확인됨(서버 집계 라벨 = 표본 행 라벨 중 가장 약한 것) → '확인됨'
 *  - 집계 사실이 '확인됨'이 아니면 표본 행 중 확인되지 않은 것이 섞였다 → 건수도 '추정'
 *    (사유는 중앙값의 사유를 빌리지 않고 '표본에 추정 행 포함' — 4차 리뷰 minor)
 *  - 집계 사실이 '확인 불가'이거나 출처·건수가 없으면 '확인 불가'(사유는 집계 사실의 사유, 없으면 '표본 출처 없음')
 */
export function sampleCountFact(base: Fact, n: number | null | undefined): Fact {
  const unknown = base.label === '확인 불가' || n === null || n === undefined || base.prov === null;
  if (unknown) {
    return {
      v: null,
      label: '확인 불가',
      prov: base.prov,
      checked_at: base.checked_at,
      reason: base.reason ?? t('page.common.sampleNoSource'),
      unit: 'count',
    };
  }
  const confirmed = base.label === '확인됨';
  return {
    v: n,
    label: confirmed ? '확인됨' : '추정',
    prov: base.prov,
    checked_at: base.checked_at,
    reason: confirmed ? null : t('page.common.sampleCountEstimated'),
    unit: 'count',
  };
}

/** 봉투 상태가 점수·추천에 쓰이지 않는(회색 "미해결") 상태인가 */
export function isUnresolved(status: string | null | undefined): boolean {
  return status === 'review' || status === 'escaped' || status === 'blocked' || status === 'error';
}

export const thClass = 'border-b border-border px-2 py-1 text-left text-xs font-medium text-muted';
export const tdClass = 'border-b border-border px-2 py-1 align-top';

/** 계약 Fact.unit 힌트 → FactCell 단위. 힌트가 없으면 fallback */
export function unitOf(fact: Fact | null | undefined, fallback: FactUnit): FactUnit {
  switch (fact?.unit) {
    case 'won':
      return 'won';
    case 'm2':
      return 'm2';
    case 'pct':
      return 'pct';
    case 'ratio':
      return 'ratio';
    case 'prob':
      return 'prob';
    case 'score':
      return 'score';
    case 'units':
      return 'households';
    case 'count':
      return 'count';
    case 'date':
      return 'date';
    case 'ym':
      return 'ym';
    case 'year':
    case 'text':
      return 'text';
    case 'months':
    case 'years':
    case 'm':
      return 'number';
    default:
      return fallback;
  }
}
