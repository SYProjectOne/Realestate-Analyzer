import type { ReactNode } from 'react';
import { Link } from 'react-router';
import type { Dashboard } from '@/api/types';
import { C05Unsold } from '@/charts';
import { Card, FactCell, MetaText, SectionHeader, Term } from '@/components';
import { t } from '@/i18n';
import { useIsMobile } from '@/lib/useMediaQuery';
import { useGlobalSearch } from '../_shared';

/**
 * 모바일(≤768px)은 접어 둔다(펼침 1클릭, 고침 HM-15), 데스크톱은 펼친 구역.
 * `section` 은 data-section(구역 순서 테스트), `summary` 는 접힌 제목.
 */
export function Collapsible({
  title,
  summary,
  section,
  actions,
  hint,
  children,
}: {
  title: string;
  summary?: string;
  section: string;
  actions?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}) {
  const isMobile = useIsMobile();
  if (isMobile) {
    return (
      <details
        data-section={section}
        className="rounded-2xl border border-border bg-surface px-4 py-3"
      >
        <summary className="cursor-pointer text-base font-semibold">{summary ?? title}</summary>
        <div className="mt-3 flex flex-col gap-3">
          {hint ? <p className="text-sm text-muted">{hint}</p> : null}
          {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
          {children}
        </div>
      </details>
    );
  }
  return (
    <section aria-label={title} data-section={section} className="flex flex-col gap-3">
      <SectionHeader title={title} hint={hint} actions={actions} />
      {children}
    </section>
  );
}

/**
 * '{지역} 시장 한눈에'(Main 보드, 예전 지역 현황 4칸): 미분양(+ C05 전체 차트·시군구별 내역) · 입주가 가장 몰리는 해 ·
 * 점수를 매긴 단지 · 마지막으로 모은 때. 값·라벨·출처는 서버 KPI 그대로(FactCell, 고침 HM-10). 운영 숫자는 MetaText.
 */
export function RegionMarket({ data, regionName }: { data: Dashboard; regionName: string | null }) {
  const { kpis, asof_date: asof } = data;
  const search = useGlobalSearch();
  const title = t('page.G1.regionTitle', { region: regionName ?? t('empty.unknown') });
  const kpiLabel = 'text-[13px] text-muted';
  const big = 'text-[26px] font-bold leading-tight';
  return (
    <Collapsible
      title={title}
      summary={`${title}(${t('page.G1.region')})`}
      section="region"
      actions={
        <Link to={`/market${search}`} className="text-sm text-accent hover:underline">
          {t('page.G1.regionMore')}
        </Link>
      }
    >
      <ul aria-label={t('page.G1.region')} className="grid gap-4 sm:grid-cols-2">
        <Card as="li" data-kpi="unsold" className="flex min-w-0 flex-col gap-2 sm:col-span-2">
          <span className={kpiLabel}>{t('page.G1.kpi.unsold')}</span>
          <span className={big}>
            <FactCell wrap fact={kpis.unsold.total} unit="households" />
          </span>
          <span className="flex flex-wrap items-center gap-x-1 text-[13px] text-muted">
            <span>{t('page.G1.kpi.unsoldSub', { ym: kpis.unsold.ym ?? t('empty.unknown') })}</span>
            <FactCell wrap fact={kpis.unsold.post_completion} unit="households" />
          </span>
          {kpis.unsold.breakdown && kpis.unsold.breakdown.length > 0 ? (
            // 계약 .20 F4: 지역 합계 내역(시군구별 원천 Fact — 출처 1클릭, 고침 HM-11)
            <details className="text-[13px]">
              <summary className="cursor-pointer text-accent">
                {t('page.G1.kpi.unsoldBreakdown')}
              </summary>
              <span
                data-testid="unsold-breakdown"
                className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2 lg:grid-cols-3"
              >
                {kpis.unsold.breakdown.map((part) => (
                  <span key={part.scope_code ?? part.scope_name} className="flex flex-wrap gap-1">
                    <span>{part.scope_name}</span>
                    <FactCell wrap fact={part.total} unit="households" />
                  </span>
                ))}
              </span>
            </details>
          ) : null}
          {/* C05 전체 차트(범례·축·툴팁·표로 보기 — 고침 HM-12·HM-13) */}
          <C05Unsold data={{ unsold: data.unsold_series }} height={200} asof={asof} />
        </Card>
        <Card as="li" data-kpi="movePeak" className="flex min-w-0 flex-col gap-1.5">
          <span className={kpiLabel}>{t('page.G1.kpi.movePeak')}</span>
          <span className={big}>
            <FactCell wrap fact={kpis.move_in_peak.year} unit="text" />
          </span>
          <span className="flex flex-wrap items-center gap-x-1 text-[13px] text-muted">
            <span>{t('page.G1.kpi.movePeakSub')}</span>
            <FactCell wrap fact={kpis.move_in_peak.units} unit="households" />
          </span>
        </Card>
        <Card as="li" data-kpi="judged" className="flex min-w-0 flex-col gap-1.5">
          <span className={`${kpiLabel} inline-flex items-center gap-1`}>
            {t('page.G1.kpi.judged')}
            <Term k="judge_scope" />
          </span>
          <span className={big}>
            <FactCell wrap fact={kpis.judged_count} unit="count" />
          </span>
        </Card>
        <Card as="li" data-kpi="freshness" className="flex min-w-0 flex-col gap-1.5 sm:col-span-2">
          <span className={kpiLabel}>{t('page.G1.kpi.freshness')}</span>
          <span className="text-xl font-bold leading-tight">
            <FactCell wrap fact={kpis.data_freshness.last_success_at} unit="date" asof={asof} />
          </span>
          <span className="flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
            {/* 수집 대상 개수 — 운영 메타(사실 아님) */}
            <MetaText
              kind="count"
              k="page.G1.kpi.freshnessSub"
              params={{
                failing: kpis.data_freshness.failing_sources,
                stale: kpis.data_freshness.stale_sources,
              }}
            />
          </span>
        </Card>
      </ul>
    </Collapsible>
  );
}
