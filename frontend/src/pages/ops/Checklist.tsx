import { useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { useChecklist, usePatchChecklistItem } from '@/api/hooks';
import type { ChecklistItem } from '@/api/types';
import { Badge, EmptyState, MetaText, PublishJobProgress } from '@/components';
import { t, tDynamic, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { enumText, QueryState, tdClass, thClass } from '../_shared';
import { isResaleEnd, scheduleBasis, scheduleKindText } from '../_shared/schedule';
import { OpsSection } from './sections';

const STATUSES = ['open', 'done', 'na'] as const;
const COLS = ['kind', 'title', 'complex', 'due', 'status', 'note'] as const;

/**
 * G7 Checklist + Calendar — 법적 확인·중도금일·만료·공고 예상·계약·사실 재확인(D10-3). 종류 문구 = ko.json page.G7.checkKind.
 * 상태는 PATCH /ops/checklist/{id}. 닫힌 항목은 누가 닫았는지(closed_by auto·human, 계약 .8 S6) 배지로 보인다.
 * 계약 .14 F5(D17-5): 체크리스트는 발행 리비전 보고서 본문에 들어가므로 바뀌면 202 + job_id(snapshot.publish) — 다른 발행
 * 쓰기와 같이 그 잡을 감시한다. 바뀐 것이 없거나 발행할 리비전이 없으면 200 + job_id null.
 */
export function ChecklistPanel({ asof }: { asof: string | null }) {
  const query = useChecklist();
  const items = query.data;
  return (
    <OpsSection
      k="checklist"
      actions={
        items && items.length > 0 ? (
          <Badge tone="muted">
            <MetaText kind="count" k="page.G7.checklistSummary" params={checklistCounts(items)} />
          </Badge>
        ) : null
      }
    >
      <QueryState
        query={query}
        empty={(rows) => (rows.length === 0 ? t('page.G7.check.none') : null)}
      >
        {(rows) => <ChecklistTable items={rows} asof={asof} />}
      </QueryState>
      <section
        aria-label={t('page.G7.calendar')}
        className="flex flex-col gap-2 rounded-xl border border-border p-4"
      >
        <h3 className="text-base font-bold">{t('page.G7.calendar')}</h3>
        <QueryState query={query}>{(rows) => <Calendar items={rows} asof={asof} />}</QueryState>
      </section>
    </OpsSection>
  );
}

/** 체크리스트 상태별 줄 수(개수 세기 — D25-3) */
export function checklistCounts(items: readonly ChecklistItem[]): {
  total: number;
  open: number;
  done: number;
  na: number;
} {
  return {
    total: items.length,
    open: items.filter((i) => i.status === 'open').length,
    done: items.filter((i) => i.status === 'done').length,
    na: items.filter((i) => i.status === 'na').length,
  };
}

function ChecklistTable({ items, asof }: { items: ChecklistItem[]; asof: string | null }) {
  const patch = usePatchChecklistItem();
  const canWrite = useCanWrite();
  /** 마지막 저장 응답(발행 잡 감시용) */
  const [saved, setSaved] = useState<ChecklistItem | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table
          aria-label={t('page.G7.checklist')}
          className="w-full min-w-[44rem] border-collapse text-sm"
        >
          <thead>
            <tr>
              {COLS.map((k) => (
                <th key={k} scope="col" className={thClass}>
                  {t(`page.G7.check.${k}` as TKey)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.id}
                data-closed={item.status !== 'open'}
                className={item.status === 'open' ? '' : 'bg-subtle text-grayed'}
              >
                <td className={tdClass}>
                  <Badge tone="neutral">{enumText('page.G7.checkKind', item.kind)}</Badge>
                </td>
                <th scope="row" className={`${tdClass} text-left font-normal`}>
                  {item.title}
                </th>
                <td className={tdClass}>{item.complex_name ?? ''}</td>
                <td className={tdClass}>
                  {item.due_date ? formatDate(item.due_date, asof) : t('page.G7.check.noDue')}
                </td>
                <td className={tdClass}>
                  <select
                    aria-label={`${t('page.G7.check.status')} · ${item.title}`}
                    value={item.status}
                    data-write
                    disabled={!canWrite || patch.isPending}
                    title={canWrite ? undefined : t('auth.readOnlyHint')}
                    onChange={(e) =>
                      patch.mutate(
                        {
                          id: item.id,
                          patch: { status: e.target.value as ChecklistItem['status'] },
                        },
                        { onSuccess: setSaved },
                      )
                    }
                    className="min-h-10 rounded-[10px] border border-border-strong bg-surface px-2 text-[13px] disabled:cursor-not-allowed"
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {enumText('page.G7.checkStatus', s)}
                      </option>
                    ))}
                  </select>
                  {item.status !== 'open' && item.closed_by ? (
                    <span
                      className="ml-1"
                      data-testid="closed-by"
                      title={enumText('page.G7.check.closedByHint', item.closed_by)}
                    >
                      <Badge tone="muted">
                        {enumText('page.G7.check.closedBy', item.closed_by)}
                      </Badge>
                      {/* 모바일(툴팁 없음)에서도 읽히게 사유를 화면 낭독용으로 함께 둔다 */}
                      <span className="sr-only">
                        {enumText('page.G7.check.closedByHint', item.closed_by)}
                      </span>
                    </span>
                  ) : null}
                </td>
                <td className={`${tdClass} text-xs text-muted`}>{item.note ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">{t('page.G7.closedNote')}</p>
      {saved ? (
        saved.job_id !== null && saved.job_id !== undefined ? (
          <div className="flex flex-col gap-1" data-testid="checklist-job">
            <p className="text-xs text-muted">{t('page.G7.check.jobHint')}</p>
            <PublishJobProgress key={saved.job_id} jobId={saved.job_id} />
          </div>
        ) : (
          <p className="text-xs text-muted" data-testid="checklist-job-none">
            {t('page.G7.check.unchanged')}
          </p>
        )
      ) : null}
    </div>
  );
}

/**
 * 캘린더 종류 범례 — 데이터에 나온 종류만, 처음 나온 순서로(계약 .21 의 새 종류 '청약 접수'·'당첨자 발표'도 코드 변경 없이).
 * 글자는 scheduleKindText(모르는 종류는 서버 값 그대로), 뜻은 ko.json `page.G7.calendarLegend.kind.<종류>`(없으면 글자만).
 */
function legendEntries(items: readonly ChecklistItem[]): { label: string; help: string }[] {
  const seen = new Map<string, string>();
  for (const item of items) {
    const label = scheduleKindText(item);
    if (seen.has(label)) continue;
    const help = isResaleEnd(item)
      ? t('page.G7.calendarLegend.resaleOpen')
      : tDynamic(`page.G7.calendarLegend.kind.${item.kind}`, '');
    seen.set(label, help);
  }
  return [...seen.entries()].map(([label, help]) => ({ label, help }));
}

/**
 * 기한 있는 항목을 월별로(중도금일·전매 가능 시작·공고 예상). R9-UI 피드백: 종류 배지는 쉬운 말 — 전매제한 종료('만료')는
 * '전매 가능 시작', 계산 근거는 둘째 줄, 서버 제목 전문은 title. 같은 날 같은 제목 행은 숨기지 않고 메모가 있으면 보인다.
 */
function Calendar({ items, asof }: { items: ChecklistItem[]; asof: string | null }) {
  const dated = items
    .filter((i): i is ChecklistItem & { due_date: string } => !!i.due_date)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  if (dated.length === 0) return <EmptyState message={t('page.G7.check.noDue')} />;
  const months = new Map<string, typeof dated>();
  for (const item of dated) {
    const ym = item.due_date.slice(0, 7);
    months.set(ym, [...(months.get(ym) ?? []), item]);
  }
  return (
    <div className="flex flex-col gap-3">
      <details data-testid="calendar-legend" className="text-xs text-muted">
        <summary className="cursor-pointer">{t('page.G7.calendarLegend.title')}</summary>
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
          {legendEntries(dated).map(({ label, help }) => (
            <div key={label} className="contents">
              <dt>
                <Badge tone="neutral">{label}</Badge>
              </dt>
              <dd>{help}</dd>
            </div>
          ))}
        </dl>
      </details>
      <ol aria-label={t('page.G7.calendar')} className="flex flex-col gap-3 text-sm">
        {[...months.entries()].map(([ym, list]) => (
          <li key={ym}>
            <h3 className="text-xs font-semibold text-muted">{ym}</h3>
            <ul className="flex flex-col gap-1">
              {list.map((item) => {
                const basis = scheduleBasis(item);
                return (
                  <li
                    key={item.id}
                    className="flex flex-wrap items-center gap-1"
                    title={item.title}
                  >
                    <span className="tabular-nums">{formatDate(item.due_date, asof)}</span>
                    <Badge tone="neutral">{scheduleKindText(item)}</Badge>
                    <span>
                      {item.complex_name ? `${item.complex_name} · ` : ''}
                      {basis ? t('page.common.scheduleKind.resaleOpen') : item.title}
                    </span>
                    {item.note ? <span className="text-xs text-muted">{item.note}</span> : null}
                    {basis ? (
                      <span className="w-full pl-4 text-xs text-muted">
                        {t('page.common.scheduleBasis', { basis })}
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
