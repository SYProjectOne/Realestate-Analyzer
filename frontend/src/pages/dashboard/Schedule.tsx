import { Link } from 'react-router';
import { ApiError } from '@/api/client';
import { useChecklist } from '@/api/hooks';
import type { ChecklistItem } from '@/api/types';
import { Card, EmptyState, SectionHeader, StatusPill } from '@/components';
import { t } from '@/i18n';
import { formatDday, kstDay } from '@/lib/format';
import { useGlobalSearch } from '../_shared';
import {
  isResaleEnd,
  scheduleBasis,
  scheduleDetail,
  scheduleKindText,
  withinDays,
} from '../_shared/schedule';

/** 다가오는 일정 최대 건수·기간(일) — 4주·최대 5건(고침 HM-3) */
export const UPCOMING_MAX = 5;
export const UPCOMING_DAYS = 28;

type DatedItem = ChecklistItem & { due_date: string };

/** 열린 항목 중 기준일부터 28일 안만, 날짜순, 최대 5건(표시 범위 고르기 — 계산값을 만들지 않는다) */
export function upcomingItems(items: readonly ChecklistItem[], asof: string): DatedItem[] {
  return items
    .filter(
      (i): i is DatedItem =>
        i.status === 'open' && !!i.due_date && withinDays(i.due_date, asof, UPCOMING_DAYS),
    )
    .sort((a, b) => a.due_date.localeCompare(b.due_date))
    .slice(0, UPCOMING_MAX);
}

/**
 * 다가오는 일정(4주, Main 보드 · 고침 HM-3·HM-4): 왼쪽 D± 상자, 단지 이름(링크) · 날짜 · 무엇(청약 접수 순위·구분, 계약 .21 D29-3),
 * 오른쪽 종류 칩(전매 가능 시작·중도금 납부 …). 전매 줄은 계산 기준. 항목 title = 서버 원래 제목. 공유 링크는 /ops 가 403.
 */
export function UpcomingCard({ asof }: { asof: string }) {
  const query = useChecklist();
  const search = useGlobalSearch();
  const title = t('page.G1.upcoming.title');
  const items = upcomingItems(query.data ?? [], asof);
  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  return (
    <Card as="section" aria-label={title} data-section="upcoming" className="flex flex-col gap-3">
      <SectionHeader
        title={title}
        actions={
          <Link to={`/ops${search}`} className="text-sm text-accent hover:underline">
            {t('page.G1.upcoming.all')}
          </Link>
        }
      />
      {forbidden ? (
        <p className="text-sm text-muted">{t('page.G1.upcoming.noAccess')}</p>
      ) : query.error ? (
        <EmptyState inline message={t('page.common.loadError', { detail: query.error.message })} />
      ) : query.isLoading ? (
        <p role="status" className="text-sm text-muted">
          {t('app.loading')}
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{t('page.G1.upcoming.none')}</p>
      ) : (
        <ul aria-label={title} className="flex flex-col divide-y divide-border">
          {items.map((item) => {
            const basis = scheduleBasis(item);
            const what = scheduleDetail(item);
            const dday = formatDday(item.due_date, asof);
            const today = withinDays(item.due_date, asof, 0);
            return (
              <li
                key={item.id}
                data-due={item.due_date}
                className="flex items-start gap-3 py-3"
                title={item.title}
              >
                <span
                  data-testid="schedule-dday"
                  className={`flex min-w-14 shrink-0 items-center justify-center rounded-xl px-2 py-2.5 text-sm font-bold tabular-nums ${
                    today || isResaleEnd(item)
                      ? 'bg-warn-soft text-warn-ink'
                      : 'bg-subtle text-fg-2'
                  }`}
                >
                  {dday}
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5 text-sm">
                  {item.complex_id ? (
                    <Link
                      to={`/complexes/${item.complex_id}${search}`}
                      className="font-semibold text-fg underline"
                    >
                      {item.complex_name ?? item.title}
                    </Link>
                  ) : (
                    <span className="font-semibold">{item.title}</span>
                  )}
                  <span className="text-fg-2">
                    <span className="tabular-nums">{kstDay(item.due_date) ?? item.due_date}</span>
                    {what ? (
                      <>
                        <span aria-hidden> · </span>
                        <span data-testid="schedule-detail">{what}</span>
                      </>
                    ) : null}
                  </span>
                  {basis ? (
                    <span className="text-xs text-muted">
                      {t('page.common.scheduleBasis', { basis })}
                    </span>
                  ) : null}
                </span>
                <span data-testid="schedule-kind" className="shrink-0">
                  <StatusPill tone={isResaleEnd(item) ? 'warn' : 'neutral'}>
                    {scheduleKindText(item)}
                  </StatusPill>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
