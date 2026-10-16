import { useId } from 'react';
import { Link } from 'react-router';
import { useChecklist, useComplexes } from '@/api/hooks';
import type { ChecklistItem, ComplexRow, Dashboard } from '@/api/types';
import { Card, FactCell, IntakeBadge, Skeleton, StatusPill, Term } from '@/components';
import { t } from '@/i18n';
import { formatDday, kstDay } from '@/lib/format';
import { useGlobalSearch } from '../_shared';
import { scheduleDetail, scheduleKindText, withinDays } from '../_shared/schedule';

/** 지금 접수 가능 링크·카드 목록이 거는 값(계약 IntakeStatus) */
export const OPEN_NOW = '가능';
/** 첫 줄 아래 접수 가능 카드 수(Main 보드 3장) — 나머지는 '접수 가능 단지 모두 보기' */
export const OPEN_CARDS = 3;
/** '곧 청약 접수' 띠가 고르는 기간(일) — 다가오는 일정(4주)과 같은 창 */
export const APPLY_SOON_DAYS = 28;
/** 띠 한 줄에 보이는 일정 칸 수 */
const APPLY_SOON_MAX = 4;
/** 띠에 넣는 체크리스트 종류(계약 .21 D29-3: 공고문 청약 일정) */
const APPLY_KINDS: ReadonlySet<ChecklistItem['kind']> = new Set(['청약 접수', '당첨자 발표']);

/** 전역 쿼리(region·snapshot·scenario)를 지키며 접수 가능 필터를 건 G2 주소 */
function useOpenNowHref(): string {
  const search = useGlobalSearch();
  const params = new URLSearchParams(search);
  params.set('intake_status', OPEN_NOW);
  return `/complexes?${params.toString()}`;
}

/**
 * G1 첫 줄(Main 보드 hero, 고침 HM-1): h1 "지금 청약을 넣을 수 있는 단지는 N곳이에요".
 * N = 서버 KPI `intake_open_count`(FactCell — 라벨 배지·출처 점선 밑줄 그대로). 화면은 세지 않는다.
 * h1 앞에 화면 이름 '홈'(스크린리더 전용)을 둔다 — 메뉴 이름과 같은 화면 이름.
 */
export function Hero({ data, regionName }: { data: Dashboard; regionName: string | null }) {
  const headingId = useId();
  const href = useOpenNowHref();
  return (
    <section
      aria-labelledby={headingId}
      data-section="openNow"
      className="flex flex-wrap items-end justify-between gap-4"
    >
      <div className="flex min-w-0 flex-[1_1_520px] flex-col gap-2.5">
        <p className="text-sm text-muted" data-testid="hero-lead">
          {t('page.G1.hero.lead', {
            region: regionName ?? t('empty.unknown'),
            date: kstDay(data.asof_date) ?? data.asof_date,
          })}
        </p>
        <h1
          id={headingId}
          className="text-[28px] font-bold leading-tight tracking-tight text-fg sm:text-[38px]"
        >
          <span className="sr-only">{t('page.G1.title')} </span>
          {t('page.G1.hero.before')}
          <span className="text-accent" data-testid="hero-count">
            <FactCell wrap fact={data.kpis.intake_open_count} unit="count" />
          </span>
          {t('page.G1.hero.after')}
        </h1>
        <p className="flex flex-wrap items-center gap-1.5 text-[13px] text-muted">
          {t('label.legend')} · {t('page.G2.filter.intake_status')}
          <Term k="intake_status" />
        </p>
        <p className="text-base leading-relaxed text-fg-2">{t('page.G1.openNow.hint')}</p>
      </div>
      <Link
        to={href}
        className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-[15px] font-semibold text-accent-fg hover:opacity-90"
      >
        {t('page.G1.openNow.link')}
        <span aria-hidden>→</span>
      </Link>
    </section>
  );
}

/**
 * 지금 접수 가능한 단지 카드(Main 보드 '지금 접수 가능한 단지', 새로 더한 것 N2): G2 목록 API 를
 * `filter[intake_status]=가능`·접수 정렬(같은 상태 안 마감 임박, 계약 .20 F10)로 받아 앞의 3곳만. 값은 목록 행 Fact 그대로.
 */
export function OpenNowCards({
  snapshotId,
  scenarioKey,
  asof,
}: {
  snapshotId: string | null;
  scenarioKey: string | null;
  asof: string;
}) {
  const query = useComplexes(snapshotId, {
    page: 1,
    size: OPEN_CARDS,
    sort: 'intake',
    ...(scenarioKey ? { scenario: scenarioKey } : {}),
    filter: { intake_status: OPEN_NOW },
  });
  const title = t('page.G1.openNow.title');
  // 카드 한 장 높이만큼 자리를 잡아 둔다 — 목록이 늦게 와도 아래 구역이 밀리지 않게(CLS, Lighthouse 모바일)
  if (query.isLoading)
    return (
      <div className="min-h-[330px]">
        <Skeleton lines={3} card />
      </div>
    );
  if (query.error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {t('page.common.loadError', { detail: query.error.message })}
      </p>
    );
  }
  const page = query.data;
  if (!page) return null;
  if (page.items.length === 0) {
    return (
      <p className="text-sm text-muted" data-testid="open-now-none">
        {t('page.G1.openNow.none')}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-section="openCards">
      <ul aria-label={title} className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {page.items.map((row) => (
          <OpenNowCard key={row.complex_id} row={row} asof={asof} />
        ))}
      </ul>
    </div>
  );
}

function OpenNowCard({ row, asof }: { row: ComplexRow; asof: string }) {
  const search = useGlobalSearch();
  return (
    <Card
      as="li"
      padding="none"
      interactive
      className="flex flex-col overflow-hidden"
      data-complex-id={row.complex_id}
    >
      <div className="flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <IntakeBadge intake={row.intake} asof={asof} />
          <StatusPill tone="neutral">{t('page.G1.openNow.supplyNote')}</StatusPill>
        </div>
        <div className="flex flex-col gap-0.5">
          <p className="flex flex-wrap items-center gap-x-1 text-[13px] text-muted">
            <span>{row.living_area_name ?? t('empty.unknown')}</span>
            <span aria-hidden>·</span>
            <FactCell wrap fact={row.units_total} unit="households" />
          </p>
          <h2 className="text-[19px] font-bold leading-snug">
            <Link to={`/complexes/${row.complex_id}${search}`} className="text-fg hover:underline">
              {row.name}
            </Link>
          </h2>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[13px] text-muted">{t('page.G1.openNow.price')}</span>
          <span className="flex flex-wrap items-center gap-1 text-[22px] font-bold leading-tight">
            <FactCell wrap fact={row.price_low} unit="won" />
            <span aria-hidden>~</span>
            <FactCell wrap fact={row.price_high} unit="won" />
          </span>
        </div>
      </div>
      <dl className="mt-auto grid grid-cols-3 border-t border-border bg-subtle text-xs">
        <div className="flex min-w-0 flex-col gap-1 border-r border-border p-3">
          <dt className="text-muted">{t('page.G1.openNow.down')}</dt>
          <dd className="text-[15px] font-bold">
            <FactCell wrap fact={row.down_payment_won ?? null} unit="won" />
          </dd>
        </div>
        <div className="flex min-w-0 flex-col gap-1 border-r border-border p-3">
          <dt className="text-muted">{t('page.G1.openNow.resale')}</dt>
          <dd className="text-[15px] font-bold">
            <FactCell wrap fact={row.resale_end} unit="date" asof={asof} />
          </dd>
        </div>
        <div className="flex min-w-0 flex-col gap-1 p-3">
          <dt className="text-muted">{t('page.G1.openNow.moveIn')}</dt>
          <dd className="text-[15px] font-bold">
            <FactCell wrap fact={row.move_in_ym} unit="ym" />
          </dd>
        </div>
      </dl>
    </Card>
  );
}

type DatedItem = ChecklistItem & { due_date: string };

/**
 * '곧 청약 접수' 단지 고르기(새로 더한 것 N3 — 판단이 아니라 날짜 고르기): 기준일부터 4주 안의 열린 '청약 접수' 항목 중
 * 가장 이른 것의 단지. 그 단지의 열린 청약 접수·당첨자 발표 항목(기준일 이후)을 날짜순으로 최대 4칸.
 */
export function pickApplySoon(
  items: readonly ChecklistItem[],
  asof: string,
): { complexId: number; name: string; items: DatedItem[] } | null {
  const open = items.filter(
    (i): i is DatedItem => i.status === 'open' && !!i.due_date && i.complex_id !== null,
  );
  const first = open
    .filter((i) => i.kind === '청약 접수' && withinDays(i.due_date, asof, APPLY_SOON_DAYS))
    .sort((a, b) => a.due_date.localeCompare(b.due_date) || a.id - b.id)[0];
  if (!first || first.complex_id === null) return null;
  const complexId = first.complex_id;
  const mine = open
    .filter(
      (i) =>
        i.complex_id === complexId &&
        APPLY_KINDS.has(i.kind) &&
        withinDays(i.due_date, asof, Number.POSITIVE_INFINITY),
    )
    .sort((a, b) => a.due_date.localeCompare(b.due_date) || a.id - b.id)
    .slice(0, APPLY_SOON_MAX);
  return { complexId, name: first.complex_name ?? first.title, items: mine };
}

/** '곧 청약 접수가 시작돼요' 띠(Main 보드) — 공고문 일정(체크리스트)에서. 고를 단지가 없거나 권한이 없으면 그리지 않는다 */
export function ApplySoonBand({ asof }: { asof: string }) {
  const query = useChecklist();
  const search = useGlobalSearch();
  const pick = query.data ? pickApplySoon(query.data, asof) : null;
  if (!pick) return null;
  const to = `/complexes/${pick.complexId}${search}#payment`;
  return (
    <section
      aria-label={t('page.G1.applySoon.title')}
      data-section="applySoon"
      className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-toast px-6 py-5 text-toast-fg"
    >
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-[13px] opacity-80">
          {t('page.G1.applySoon.title')} · {t('page.G1.applySoon.sub')}
        </p>
        <p className="text-xl font-bold">{pick.name}</p>
      </div>
      <ul
        aria-label={`${t('page.G1.applySoon.title')}: ${pick.name}`}
        className="flex flex-wrap gap-2.5"
      >
        {pick.items.map((item, i) => (
          <li
            key={item.id}
            title={item.title}
            data-due={item.due_date}
            className={`flex min-w-28 flex-col gap-0.5 rounded-xl px-3.5 py-2.5 ${
              i === 0 ? 'bg-accent text-accent-fg' : 'bg-toast-fg/10'
            }`}
          >
            <span className="text-xs">{scheduleDetail(item) ?? scheduleKindText(item)}</span>
            <span className="text-base font-bold tabular-nums">
              {kstDay(item.due_date) ?? item.due_date} · {formatDday(item.due_date, asof)}
            </span>
          </li>
        ))}
      </ul>
      <Link
        to={to}
        className="inline-flex min-h-11 items-center rounded-xl border border-toast-fg/40 px-4 py-2 text-[15px] font-semibold text-toast-fg hover:bg-toast-fg/10"
      >
        {t('page.G1.applySoon.link')}
      </Link>
    </section>
  );
}
