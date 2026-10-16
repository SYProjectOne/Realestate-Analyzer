import type { ReactNode } from 'react';
import { useLocation } from 'react-router';
import { useChecklist, useClaims, useIntakeQueue, useOpsSources } from '@/api/hooks';
import { MetaText } from '@/components';
import { t } from '@/i18n';
import { contradictedClaims } from './ClaimsPanel';
import { OPS_SECTIONS, opsMenuText, SectionLink, type OpsSectionKey } from './sections';
import { failingSources } from './SourceStatusTable';

/**
 * G7 묶음 메뉴(목업 N3) — 데스크톱은 왼쪽에 붙어 따라오는 세로 메뉴, 휴대폰·좁은 화면은 위에 한 줄로 쌓여 옆으로 민다.
 * 누르면 그 묶음 카드로 간다(주소 해시 = 묶음 id — #intake-queue·#human-check 는 기존 앵커). 건수 배지는 이미 받은
 * 목록의 줄 수·서버 total 만(D25-3). 공유 링크는 쓰기 토큰일 때만(패널도 그때만 보인다).
 */
export function OpsMenu({
  regionId,
  snapshotId,
  enabled,
  showShare,
}: {
  regionId: number | null;
  snapshotId: string | null;
  enabled: boolean;
  showShare: boolean;
}) {
  const { hash } = useLocation();
  const counts = useMenuCounts(regionId, snapshotId, enabled);
  const sections = OPS_SECTIONS.filter((s) => s.key !== 'share' || showShare);
  return (
    <nav
      aria-label={t('page.G7.menu.title')}
      className="min-w-0 rounded-2xl border border-border bg-surface p-2 lg:sticky lg:top-4 lg:self-start"
    >
      <p className="mx-2 mb-1 mt-1 text-xs font-bold text-muted">
        <span className="hidden lg:inline">{t('page.G7.menu.hint')}</span>
        <span className="lg:hidden">{t('page.G7.menu.mobileHint')}</span>
      </p>
      <ol className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
        {sections.map((s) => {
          const current = hash === `#${s.id}`;
          const count = counts[s.key];
          return (
            <li key={s.key} className="shrink-0">
              <SectionLink
                id={s.id}
                aria-current={current ? 'location' : undefined}
                data-testid={`ops-menu-${s.key}`}
                className={`flex min-h-11 items-center gap-2.5 whitespace-nowrap rounded-[10px] px-2.5 text-sm no-underline ${
                  current
                    ? 'bg-accent-soft font-semibold text-accent-ink'
                    : 'text-fg-2 hover:bg-subtle'
                }`}
              >
                <span
                  aria-hidden
                  className={`inline-flex size-[22px] shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    current ? 'bg-accent text-accent-fg' : 'bg-chip text-fg-2'
                  }`}
                >
                  {s.no}
                </span>
                <span className="flex-1">{opsMenuText(s.key)}</span>
                {s.key === 'sources' && enabled ? <SourcesFailBadge regionId={regionId} /> : null}
                {count ? (
                  <span
                    className={`rounded-full px-2 py-px text-xs font-semibold ${
                      count.warn ? 'bg-warn-soft text-warn-ink' : 'bg-subtle text-muted'
                    }`}
                  >
                    {count.node}
                  </span>
                ) : null}
              </SectionLink>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

type MenuCounts = Partial<Record<OpsSectionKey, { node: ReactNode; warn: boolean }>>;

/** 메뉴 건수 — 타일·패널과 같은 조회(캐시 공유)라 요청이 늘지 않는다 */
function useMenuCounts(
  regionId: number | null,
  snapshotId: string | null,
  enabled: boolean,
): MenuCounts {
  const hasScope = enabled && (regionId !== null || snapshotId !== null);
  const queue = useIntakeQueue(regionId, snapshotId, hasScope);
  const claims = useClaims(enabled ? snapshotId : null);
  const checklist = useChecklist();
  const out: MenuCounts = {};
  if (checklist.data) {
    out.checklist = {
      node: <MetaText kind="count" k="page.G7.menu.count" params={{ n: checklist.data.length }} />,
      warn: false,
    };
  }
  if (queue.data) {
    out.intake = {
      node: <MetaText kind="count" k="page.G7.menu.count" params={{ n: queue.data.total }} />,
      warn: queue.data.total > 0,
    };
  }
  if (claims.data) {
    const n = contradictedClaims(claims.data).length;
    out.claims = {
      node: <MetaText kind="count" k="page.G7.menu.count" params={{ n }} />,
      warn: n > 0,
    };
  }
  return out;
}

/**
 * 수집 실패 건수 배지 — 지역이 정해진 뒤에만 그려 조회한다(SourceStatusTable 과 같은 키 · 첫 로딩 중 지역 없는 조회를
 * 만들지 않는다). 실패가 없으면 그리지 않는다.
 */
function SourcesFailBadge({ regionId }: { regionId: number | null }) {
  const query = useOpsSources(regionId);
  const n = query.data ? failingSources(query.data).length : 0;
  if (n === 0) return null;
  return (
    <span className="rounded-full bg-warn-soft px-2 py-px text-xs font-semibold text-warn-ink">
      <MetaText kind="count" k="page.G7.menu.failCount" params={{ n }} />
    </span>
  );
}
