import { Link } from 'react-router';
import { useComplexes } from '@/api/hooks';
import { t } from '@/i18n';
import { QueryState, ScopeReason, Section, useGlobalSearch } from '../_shared';

/** 목록 조회 크기(listComplexes 최대 1000) — 범위 경계는 보통 몇 건이다 */
const BOUNDARY_PAGE_SIZE = 200;

/**
 * G7 범위 경계 목록 (R3 minor 35, DECISIONS D2-6) — 지금 스냅샷에서 inclusion_class '범위 경계'인 단지.
 * 판정 범위에서 빠지므로(제외) 사람이 경계 지역을 확인할 수 있게 이름과 단지 화면 링크를 보인다.
 * 계약 .17 F1(D22-5): 단지마다 서버 판정 범위 사유(`judge_scope_reason` — '범위 경계(주소에 동 없음)' 등)를 그대로 붙인다.
 */
export function BoundaryList({ snapshotId }: { snapshotId: string | null }) {
  const search = useGlobalSearch();
  const query = useComplexes(snapshotId, {
    page: 1,
    size: BOUNDARY_PAGE_SIZE,
    sort: 'name',
    filter: { inclusion_class: '범위 경계' },
  });
  return (
    <Section title={t('page.G7.boundary.title')}>
      <p className="text-xs text-muted">{t('page.G7.boundary.intro')}</p>
      {snapshotId === null ? (
        <p className="text-sm text-muted">{t('app.noSnapshot')}</p>
      ) : (
        <QueryState
          query={query}
          empty={(page) => (page.items.length === 0 ? t('page.G7.boundary.none') : null)}
        >
          {(page) => (
            <ul aria-label={t('page.G7.boundary.title')} className="flex flex-wrap gap-2 text-sm">
              {page.items.map((row) => (
                <li key={row.complex_id}>
                  <Link
                    to={`/complexes/${row.complex_id}${search}`}
                    className="rounded-sm border border-border px-2 py-0.5 hover:underline"
                  >
                    {row.name}
                  </Link>
                  {row.living_area_name ? (
                    <span className="ml-1 text-xs text-muted">{row.living_area_name}</span>
                  ) : null}
                  <ScopeReason
                    reason={row.judge_scope_reason}
                    rejudgeNeeded={row.rejudge_needed}
                    testId="boundary-scope-reason"
                    compact
                    className="ml-1 text-xs text-muted"
                  />
                </li>
              ))}
            </ul>
          )}
        </QueryState>
      )}
    </Section>
  );
}
