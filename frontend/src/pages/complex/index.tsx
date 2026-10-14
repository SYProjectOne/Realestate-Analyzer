import { Link, useParams } from 'react-router';
import { useComplexDetail } from '@/api/hooks';
import type { ComplexDetail } from '@/api/types';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
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
 * ComplexHeader + 탭 8개(URL 해시): 가격표 · 납부 조건 · C8 · C1 · C2 · 호재(+C9 작게) · 출처 원문(지연 로드) · 판정기 로그
 */
export function ComplexPage() {
  const { id } = useParams<{ id: string }>();
  const { snapshotId, scenarioKey } = usePageContext();
  const query = useComplexDetail(id, snapshotId, scenarioKey);
  const search = useGlobalSearch();
  return (
    <PageShell
      title={t('page.G3.title')}
      legend
      actions={
        <Link to={`/complexes${search}`} className="text-sm underline">
          {t('page.common.backToList')}
        </Link>
      }
    >
      <QueryState query={query}>{(detail) => <Detail detail={detail} />}</QueryState>
    </PageShell>
  );
}

function Detail({ detail }: { detail: ComplexDetail }) {
  const [tab, setTab] = useHashTab(G3_TABS);
  const panelId = (k: G3Tab) => `g3-panel-${k}`;
  const tabId = (k: G3Tab) => `g3-tab-${k}`;
  return (
    <div className="flex flex-col gap-3">
      <ComplexHeader detail={detail} />
      <div
        role="tablist"
        aria-label={t('page.G3.tabs')}
        className="flex gap-1 overflow-x-auto border-b border-border"
      >
        {G3_TABS.map((k) => (
          <button
            key={k}
            id={tabId(k)}
            type="button"
            role="tab"
            aria-selected={tab === k}
            aria-controls={panelId(k)}
            tabIndex={tab === k ? 0 : -1}
            onClick={() => setTab(k)}
            onKeyDown={(event) => {
              if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
              const i = G3_TABS.indexOf(k);
              const step = event.key === 'ArrowRight' ? 1 : -1;
              const next = G3_TABS[(i + step + G3_TABS.length) % G3_TABS.length];
              if (next) {
                setTab(next);
                document.getElementById(tabId(next))?.focus();
              }
            }}
            className={`whitespace-nowrap border-b-2 px-3 py-1.5 text-sm ${
              tab === k
                ? 'border-accent font-medium'
                : 'border-transparent text-muted hover:text-fg'
            }`}
          >
            {t(`page.G3.tab.${k}` as TKey)}
          </button>
        ))}
      </div>
      {/* 활성 탭만 마운트 — 원문(provenance) 탭은 열 때 처음 로드된다(지연 로드) */}
      <div role="tabpanel" id={panelId(tab)} aria-labelledby={tabId(tab)} tabIndex={0}>
        {tab === 'price' ? <PriceTab detail={detail} /> : null}
        {tab === 'payment' ? <PaymentTab detail={detail} /> : null}
        {tab === 'events' ? <EventsTab detail={detail} /> : null}
        {tab === 'ladder' ? <LadderTab detail={detail} /> : null}
        {tab === 'gap' ? <GapTab detail={detail} /> : null}
        {tab === 'catalysts' ? <CatalystsTab detail={detail} /> : null}
        {tab === 'provenance' ? <ProvenanceTab detail={detail} /> : null}
        {tab === 'judgments' ? (
          <JudgmentsTab judgments={detail.judgments} asof={detail.asof_date} />
        ) : null}
      </div>
    </div>
  );
}
