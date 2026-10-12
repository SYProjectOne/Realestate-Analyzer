/**
 * 화면 공용 조각(WP6a 소유). 여러 화면이 같은 모양을 쓰는 것만 둔다.
 * 공통 컴포넌트(@/components)로 올릴 만한 것은 보고서 "공통화 제안"에 적는다.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router';
import { ApiError, isMaterializePending } from '@/api/client';
import { useScenarios } from '@/api/hooks';
import type { Fact, JudgeScope, Scenario, Snapshot } from '@/api/types';
import { Badge, EmptyState } from '@/components';
import { useActiveRegion } from '@/hooks/useActiveRegion';
import { useMobileLayout } from '@/hooks/useMobileLayout';
import { useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, tDynamic } from '@/i18n';
import { queryErrorText } from '@/lib/errorText';
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
  query: {
    data: T | undefined;
    error: Error | null;
    isLoading: boolean;
    /** 재시도 중인 마지막 실패(TanStack) — 503 materialize_pending 이면 '준비 중'(계약 .11 F12) */
    failureReason?: Error | null;
    /** 보이는 값이 같은 리비전·시나리오의 이전 값(필터 변경 중, M7) */
    isPlaceholderData?: boolean;
    refetch?: () => unknown;
  };
  children: (data: T) => ReactNode;
  /** 데이터가 비었을 때 보일 문구(판단은 호출 측: data → boolean) */
  empty?: (data: T) => string | null;
}) {
  if (query.data !== undefined) {
    // M7: 이전 값(같은 리비전·시나리오에서만 남는다)을 두는 동안 새 조건이 아직 준비 중이면 그 사실도 보인다
    const pending =
      query.isPlaceholderData && isMaterializePending(query.failureReason) ? (
        <MaterializePending />
      ) : null;
    const emptyText = empty?.(query.data) ?? null;
    if (emptyText) {
      return (
        <>
          {pending}
          <EmptyState message={emptyText} />
        </>
      );
    }
    return (
      <>
        {pending}
        {children(query.data)}
      </>
    );
  }
  if (query.error) return <QueryError error={query.error} refetch={query.refetch} />;
  if (isMaterializePending(query.failureReason)) return <MaterializePending />;
  return (
    <p role="status" className="text-sm text-muted">
      {t('app.loading')}
    </p>
  );
}

/** 503 materialize_pending 재시도 중: '준비 중 — 자동으로 다시' */
export function MaterializePending() {
  return (
    <p role="status" data-testid="materialize-pending" className="text-sm text-muted">
      {t('page.common.materializePending')}
    </p>
  );
}

export { queryErrorText } from '@/lib/errorText';

/** 내장 시나리오 code — 모든 발행 리비전에 결과가 있다 */
const BUILTIN_SCENARIOS: ReadonlySet<string> = new Set(['base', 'A', 'B', 'C', 'D']);

/**
 * 계약 .10 S2(D13-1): 발행 리비전은 발행 순간 시나리오별 저장본만 돌려준다 — 발행 **뒤에** 만든 사용자 시나리오
 * (`?scenario=<id>`)로 옛 발행 리비전을 읽으면 404. 그 결과는 시나리오 실행(G5)이 만드는 새 리비전에 있다.
 * 6차 minor 24: 404 면 다 그렇다고 보지 않는다 — 계약 오류 code 가 `not_found` 이고, 그 시나리오가 목록에 있으며
 * 생성 시각이 리비전 발행 시각 **뒤**일 때만이다. 발행 전에 만든 시나리오(저장본 있음)·목록에 없는 시나리오(삭제·
 * 없는 id)·본문 없는 404(code 'http')·시나리오 목록을 아직 모를 때는 일반 오류로 보인다.
 */
export function isScenarioMissing(
  error: unknown,
  scenarioKey: string | null,
  snapshot: Pick<Snapshot, 'status' | 'published_at'> | null | undefined,
  scenarios: readonly Pick<Scenario, 'id' | 'code' | 'created_at'>[] | undefined,
): boolean {
  if (!(error instanceof ApiError) || error.status !== 404 || error.code !== 'not_found') {
    return false;
  }
  if (scenarioKey === null || BUILTIN_SCENARIOS.has(scenarioKey)) return false;
  if (snapshot?.status !== 'published' || !scenarios) return false;
  const scenario = scenarios.find((s) => (s.code ?? String(s.id)) === scenarioKey);
  if (!scenario) return false;
  // 시각을 모르면(옛 응답) 안내를 유지한다 — 발행 전 생성이 확실할 때만 다른 404 로 본다
  return scenarioMadeAfterPublish(scenario, snapshot) ?? true;
}

/**
 * 사용자 시나리오가 그 발행 리비전 **뒤에** 만들어졌는가(= 그 리비전 저장본에 결과가 없다, 계약 .10 S2·.11 D14-3).
 * 내장 시나리오·발행 전 리비전은 false(늘 결과가 있다·실시간). 시각을 모르면 null(판단은 서버 몫).
 */
export function scenarioMadeAfterPublish(
  scenario: Pick<Scenario, 'id' | 'code' | 'created_at'> & { is_builtin?: boolean },
  snapshot: Pick<Snapshot, 'status' | 'published_at'>,
): boolean | null {
  if (scenario.is_builtin || (scenario.code !== null && BUILTIN_SCENARIOS.has(scenario.code))) {
    return false;
  }
  if (snapshot.status !== 'published') return false;
  const created = Date.parse(scenario.created_at ?? '');
  const published = Date.parse(snapshot.published_at ?? '');
  if (!Number.isFinite(created) || !Number.isFinite(published)) return null;
  return created > published;
}

/** 쿼리 오류 표시: 발행 리비전에 없는 시나리오면 시나리오 실행 안내, 준비 중이면 다시 시도, 그 밖은 오류 문구 */
function QueryError({ error, refetch }: { error: Error; refetch?: (() => unknown) | undefined }) {
  const { scenarioId } = useScenario();
  const { snapshot } = useSnapshot();
  const scenarios = useScenarios();
  const search = useGlobalSearch();
  if (isScenarioMissing(error, scenarioId, snapshot, scenarios.data)) {
    return (
      <div role="status" data-testid="scenario-missing" className="flex flex-col gap-1 text-sm">
        <p>{t('page.common.scenarioMissing', { scenario: scenarioId ?? '' })}</p>
        <Link to={`/scenario${search}`} className="underline">
          {t('page.common.scenarioMissingRun')}
        </Link>
      </div>
    );
  }
  if (isMaterializePending(error) && refetch) {
    return (
      <div role="status" data-testid="materialize-pending" className="flex flex-col gap-1 text-sm">
        <p>{queryErrorText(error)}</p>
        <button type="button" onClick={() => void refetch()} className="self-start underline">
          {t('app.retry')}
        </button>
      </div>
    );
  }
  return <EmptyState message={queryErrorText(error)} />;
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
 * 변경 이벤트(change_event) 필드 이름 — ko.json `page.common.changeField` 에 있는 것만 바꾸고 나머지는 서버 값 그대로.
 * 계약 .15: `first_load`(지역 첫 적재 한 줄, F7)·`track`(트랙 A 공고 예정 후보, F5)·`applyhome_id`(후보와 청약홈 공고 합침, F5).
 */
export function changeFieldText(field: string): string {
  return enumText('page.common.changeField', field);
}

/** 변경 이벤트 대상(entity) — 단지 이름이 없는 행(지역·미분양 등)의 표시 이름 */
export function changeEntityText(entity: string): string {
  return enumText('page.common.changeEntity', entity);
}

/**
 * 변경 내용 한 줄: 보통은 "이전 → 이후". 계약 .15 F7 `first_load`(지역 첫 적재)는 바뀐 값이 아니라 요약 문장 한 줄이라
 * 화살표 없이 그 문장만(빈 값 → 화살표가 critical 처럼 보이지 않게).
 */
export function changeValueText(change: {
  field: string;
  old_text: string | null;
  new_text: string | null;
}): string {
  if (change.field === 'first_load' && change.old_text === null && change.new_text !== null) {
    return change.new_text;
  }
  return t('page.common.arrow', {
    old: change.old_text ?? t('page.common.none'),
    new: change.new_text ?? t('page.common.none'),
  });
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
