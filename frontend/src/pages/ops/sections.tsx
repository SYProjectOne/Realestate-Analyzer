import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { t, type TKey } from '@/i18n';
import { QuestionSection } from '../_shared/QuestionSection';
import { HUMAN_CHECK_ANCHOR } from './humanCheckRules';

/** 대기열 구역 앵커(다른 화면에서 `/ops#intake-queue` 로 들어올 때) — 바꾸지 않는다(D30-2) */
export const INTAKE_QUEUE_ANCHOR = 'intake-queue';

export type OpsSectionKey =
  'checklist' | 'intake' | 'human' | 'sources' | 'jobs' | 'stats' | 'claims' | 'boundary' | 'share';

interface OpsSectionDef {
  key: OpsSectionKey;
  /** 앵커 id — #intake-queue·#human-check 는 기존 주소 그대로 */
  id: string;
  /** 동그라미 번호(목업 ①~⑨) */
  no: string;
  /** 구역 공식 이름(aria-label · 표 이름) — 기존 ko 키 */
  nameKey: TKey;
  /** "이게 뭐예요?" 설명 */
  whatKey: TKey;
}

/** G7 묶음 9개(목업 Ops 메뉴 순서) */
export const OPS_SECTIONS: readonly OpsSectionDef[] = [
  {
    key: 'checklist',
    id: 'ops-checklist',
    no: '①',
    nameKey: 'page.G7.checklist',
    whatKey: 'page.G7.whatText.checklist',
  },
  {
    key: 'intake',
    id: INTAKE_QUEUE_ANCHOR,
    no: '②',
    nameKey: 'page.G7.iq.title',
    whatKey: 'page.G7.iq.intro',
  },
  {
    key: 'human',
    id: HUMAN_CHECK_ANCHOR,
    no: '③',
    nameKey: 'page.G7.human',
    whatKey: 'page.G7.humanIntro',
  },
  {
    key: 'sources',
    id: 'ops-sources',
    no: '④',
    nameKey: 'page.G7.sources',
    whatKey: 'page.G7.whatText.sources',
  },
  {
    key: 'jobs',
    id: 'ops-jobs',
    no: '⑤',
    nameKey: 'page.G7.queue',
    whatKey: 'page.G7.whatText.jobs',
  },
  {
    key: 'stats',
    id: 'ops-stats',
    no: '⑥',
    nameKey: 'page.G7.stats',
    whatKey: 'page.G7.whatText.stats',
  },
  {
    key: 'claims',
    id: 'ops-claims',
    no: '⑦',
    nameKey: 'page.G7.claims.title',
    whatKey: 'page.G7.claims.intro',
  },
  {
    key: 'boundary',
    id: 'ops-boundary',
    no: '⑧',
    nameKey: 'page.G7.boundary.title',
    whatKey: 'page.G7.boundary.intro',
  },
  {
    key: 'share',
    id: 'ops-share',
    no: '⑨',
    nameKey: 'page.G7.share.title',
    whatKey: 'page.G7.share.intro',
  },
];

export function opsSection(key: OpsSectionKey): OpsSectionDef {
  return OPS_SECTIONS.find((s) => s.key === key) as OpsSectionDef;
}

/** 메뉴 이름(목업 메뉴 9칸) */
export function opsMenuText(key: OpsSectionKey): string {
  return t(`page.G7.menu.${key}`);
}

/**
 * G7 묶음 카드: "① 일정·체크리스트" 머리말 + 질문형 h2 + "이게 뭐예요?" 설명(목업 N4). 구역 이름(aria-label)은 기존
 * 공식 이름이라 표·구역을 이름으로 찾는 테스트와 다른 화면의 앵커(#intake-queue·#human-check)가 그대로다.
 */
export function OpsSection({
  k,
  actions,
  className,
  children,
}: {
  k: OpsSectionKey;
  actions?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  const def = opsSection(k);
  return (
    <QuestionSection
      id={def.id}
      name={t(def.nameKey)}
      title={t(`page.G7.q.${k}`)}
      kicker={`${def.no} ${opsMenuText(k)}`}
      whatLabel={t('page.G7.what')}
      what={t(def.whatKey)}
      actions={actions}
      className={className}
      data-testid={`ops-section-${k}`}
    >
      {children}
    </QuestionSection>
  );
}

/** 묶음 id 로 스크롤(라우터는 해시로 스크롤하지 않는다) */
export function scrollToSection(id: string): void {
  requestAnimationFrame(() => {
    const el = document.getElementById(id);
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'start' });
  });
}

/**
 * 같은 화면의 묶음으로 가는 링크 — 주소는 지금 쿼리(?region= 등) + `#묶음 id`, 누르면 그 카드로 스크롤한다.
 * (원시 앵커 태그에 식 href 를 쓰지 않는다 — safeHref 규칙)
 */
export function SectionLink({
  id,
  className,
  children,
  'aria-current': ariaCurrent,
  'data-testid': testId,
}: {
  id: string;
  className?: string;
  children: ReactNode;
  'aria-current'?: 'location';
  'data-testid'?: string;
}) {
  const { search } = useLocation();
  return (
    <Link
      to={{ search, hash: id }}
      aria-current={ariaCurrent}
      data-testid={testId}
      className={className}
      onClick={() => scrollToSection(id)}
    >
      {children}
    </Link>
  );
}
