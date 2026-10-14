import { useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { useChecklist, usePatchChecklistItem } from '@/api/hooks';
import type { ChecklistItem } from '@/api/types';
import { Badge, EmptyState, PublishJobProgress } from '@/components';
import { t, type TKey } from '@/i18n';
import { formatDate } from '@/lib/format';
import { enumText, QueryState, Section, tdClass, thClass } from '../_shared';
import { scheduleBasis, scheduleKindText } from '../_shared/schedule';

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
  return (
    <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
      <Section title={t('page.G7.checklist')}>
        <QueryState
          query={query}
          empty={(rows) => (rows.length === 0 ? t('page.G7.check.none') : null)}
        >
          {(items) => <ChecklistTable items={items} asof={asof} />}
        </QueryState>
      </Section>
      <Section title={t('page.G7.calendar')}>
        <QueryState query={query}>{(items) => <Calendar items={items} asof={asof} />}</QueryState>
      </Section>
    </div>
  );
}

function ChecklistTable({ items, asof }: { items: ChecklistItem[]; asof: string | null }) {
  const patch = usePatchChecklistItem();
  const canWrite = useCanWrite();
  /** 마지막 저장 응답(발행 잡 감시용) */
  const [saved, setSaved] = useState<ChecklistItem | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table aria-label={t('page.G7.checklist')} className="w-full border-collapse text-sm">
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
              <tr key={item.id} className={item.status === 'open' ? '' : 'text-grayed'}>
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
                    className="rounded-sm border border-border bg-surface px-1 py-0.5 text-xs"
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

/** 캘린더 종류 범례(R9-UI 피드백) — 배지 글자의 뜻. 종류는 계약 enum 값 */
const LEGEND: readonly { kind: ChecklistItem['kind'] | null; help: TKey }[] = [
  { kind: null, help: 'page.G7.calendarLegend.resaleOpen' },
  { kind: '중도금', help: 'page.G7.calendarLegend.interim' },
  { kind: '계약', help: 'page.G7.calendarLegend.contract' },
  { kind: '만료', help: 'page.G7.calendarLegend.expire' },
  { kind: '공고 예상', help: 'page.G7.calendarLegend.notice' },
];

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
          {LEGEND.map(({ kind, help }) => (
            <div key={help} className="contents">
              <dt>
                <Badge tone="neutral">
                  {kind === null
                    ? t('page.common.scheduleKind.resaleOpen')
                    : scheduleKindText({ kind, title: '' })}
                </Badge>
              </dt>
              <dd>{t(help)}</dd>
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
