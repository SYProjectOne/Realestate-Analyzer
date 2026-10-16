import { Link, useParams } from 'react-router';
import { useComplexDetail } from '@/api/hooks';
import type { ComplexDetail } from '@/api/types';
import { Card, SectionHeader } from '@/components';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { useIsMobile } from '@/lib/useMediaQuery';
import { QueryState, useGlobalSearch, usePageContext } from '../_shared';
import { ComplexHeader } from './ComplexHeader';
import { JudgmentsTab } from './JudgmentsTab';
import { ProvenanceTab } from './ProvenanceTab';
import { CatalystsTab, EventsTab, GapTab, LadderTab, PaymentTab, PriceTab } from './tabs';
import { useHashTab } from './useHashTab';

/** ChangeEvent.tab과 같은 키 — G1 피드 항목이 `#payment`처럼 해당 탭을 연다 */
export const G3_TABS = [
  'price',
  'payment',
  'events',
  'ladder',
  'gap',
  'catalysts',
  'provenance',
  'judgments',
] as const;
export type G3Tab = (typeof G3_TABS)[number];

/**
 * G3 단지 상세 `/complexes/:id` (RA §7-1)
 * ComplexHeader(3단 머리) + 탭 7개(URL 해시 8키): 타입별 가격 · 내야 할 돈·일정 · 경쟁률·추가 모집(C8) · 주변 시세 비교(C2) ·
 * 가격 전망(C1) · 개발 소식(+C9 작게) · 근거 원문(지연 로드, 안에 판정 기록 접힌 구획 — #judgments 면 펼침)
 */
export function ComplexPage() {
  const { id } = useParams<{ id: string }>();
  const { snapshotId, scenarioKey } = usePageContext();
  const query = useComplexDetail(id, snapshotId, scenarioKey);
  const search = useGlobalSearch();
  const name = query.data?.header.name ?? null;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {/* 현재 위치 줄(목업 Detail): 단지 찾기 › 단지 이름 — 이름은 받은 뒤에만 */}
      <nav aria-label={t('page.G3.crumb.label')} className="text-sm text-muted">
        <Link to={`/complexes${search}`} className="text-accent hover:underline">
          {t('page.G3.crumb.list')}
        </Link>
        {name ? (
          <>
            <span aria-hidden> › </span>
            <span aria-current="page">{name}</span>
          </>
        ) : null}
      </nav>
      <PageShell
        title={t('page.G3.title')}
        legend
        actions={
          <Link
            to={`/complexes${search}`}
            className="inline-flex min-h-9 items-center rounded-xl border border-border-strong bg-surface px-3 text-sm font-medium text-fg hover:border-accent"
          >
            {t('page.G3.backToList')}
          </Link>
        }
      >
        <QueryState query={query}>{(detail) => <Detail detail={detail} />}</QueryState>
      </PageShell>
    </div>
  );
}

/**
 * 보이는 탭 7개(R9-UI P8, D28-3) — 판정 기록(`#judgments`)은 근거 원문 탭 안의 접힌 구획. 주변 시세 비교(관측값)를
 * 가격 전망(판정) 앞에 둔다. 해시 키는 G3_TABS 그대로.
 */
export const G3_VISIBLE_TABS = [
  'price',
  'payment',
  'events',
  'gap',
  'ladder',
  'catalysts',
  'provenance',
] as const satisfies readonly G3Tab[];
type VisibleTab = (typeof G3_VISIBLE_TABS)[number];

function Detail({ detail }: { detail: ComplexDetail }) {
  const [tab, setTab] = useHashTab(G3_TABS);
  const isMobile = useIsMobile();
  // #judgments → 근거 원문 탭 + 판정 기록 구획 펼침(G1 변경 피드·ChangeEvent.tab 링크 그대로 1클릭)
  const active: VisibleTab = tab === 'judgments' ? 'provenance' : tab;
  const panelId = (k: VisibleTab) => `g3-panel-${k}`;
  const tabId = (k: VisibleTab) => `g3-tab-${k}`;
  const tabName = (k: VisibleTab) => {
    const name = t(`page.G3.tab.${k}` as TKey);
    // 빈 탭은 지우지 않고 "(0)"(E3)
    return k === 'catalysts' && detail.catalysts.length === 0
      ? t('page.G3.tab.countZero', { name })
      : name;
  };
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ComplexHeader detail={detail} />
      <Card
        as="section"
        aria-labelledby="g3-more"
        padding="lg"
        className="flex min-w-0 flex-col gap-4"
      >
        <SectionHeader id="g3-more" title={t('page.G3.more')} />
        {isMobile ? (
          // R9-UI P1(30-proposal §2-2): 모바일은 잘리는 가로 탭 줄 대신 <select>(키보드·스크린리더 그대로)
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-fg-2">{t('page.G3.tabSelect')}</span>
            <select
              aria-label={t('page.G3.tabs')}
              value={active}
              onChange={(e) => setTab(e.target.value as VisibleTab)}
              className="min-h-11 rounded-xl border border-border-strong bg-surface px-3 text-[15px]"
            >
              {G3_VISIBLE_TABS.map((k) => (
                <option key={k} value={k}>
                  {tabName(k)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className={isMobile ? 'hidden' : 'flex flex-col gap-1'}>
          <div
            hidden={isMobile}
            role="tablist"
            aria-label={t('page.G3.tabs')}
            className="flex gap-1 overflow-x-auto border-b border-border"
          >
            {G3_VISIBLE_TABS.map((k) => (
              <button
                key={k}
                id={tabId(k)}
                type="button"
                role="tab"
                aria-selected={active === k}
                aria-controls={panelId(k)}
                tabIndex={active === k ? 0 : -1}
                onClick={() => setTab(k)}
                onKeyDown={(event) => {
                  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
                  const i = G3_VISIBLE_TABS.indexOf(k);
                  const step = event.key === 'ArrowRight' ? 1 : -1;
                  const next =
                    G3_VISIBLE_TABS[(i + step + G3_VISIBLE_TABS.length) % G3_VISIBLE_TABS.length];
                  if (next) {
                    setTab(next);
                    document.getElementById(tabId(next))?.focus();
                  }
                }}
                className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-[15px] ${
                  active === k
                    ? 'border-accent font-semibold text-accent-ink'
                    : 'border-transparent text-fg-2 hover:text-fg'
                }`}
              >
                {tabName(k)}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted">{t('page.G3.tabHint')}</p>
        </div>
        {/* 활성 탭만 마운트 — 원문(provenance) 탭은 열 때 처음 로드된다(지연 로드) */}
        <div
          role="tabpanel"
          id={panelId(active)}
          aria-labelledby={isMobile ? undefined : tabId(active)}
          aria-label={isMobile ? tabName(active) : undefined}
          tabIndex={0}
          className="min-w-0"
        >
          {active === 'price' ? <PriceTab detail={detail} /> : null}
          {active === 'payment' ? <PaymentTab detail={detail} /> : null}
          {active === 'events' ? <EventsTab detail={detail} /> : null}
          {active === 'gap' ? <GapTab detail={detail} /> : null}
          {active === 'ladder' ? <LadderTab detail={detail} /> : null}
          {active === 'catalysts' ? <CatalystsTab detail={detail} /> : null}
          {active === 'provenance' ? (
            <div className="flex flex-col gap-4">
              <ProvenanceTab detail={detail} />
              <details
                key={tab}
                open={tab === 'judgments'}
                data-testid="judgments-block"
                className="rounded-xl border border-border px-4 py-3"
              >
                <summary className="cursor-pointer text-[15px] font-semibold">
                  {t('page.G3.tab.judgments')}
                </summary>
                <div className="mt-3">
                  <JudgmentsTab judgments={detail.judgments} asof={detail.asof_date} />
                </div>
              </details>
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
