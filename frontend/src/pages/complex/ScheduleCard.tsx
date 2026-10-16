import type { ReactNode } from 'react';
import type { ComplexDetail, Fact } from '@/api/types';
import { EmptyState, FactCell } from '@/components';
import { t } from '@/i18n';
import { Tier } from './Tier';

interface Step {
  key: string;
  label: string;
  /** 기준일과 비교할 날(끝날이 있으면 끝날) — 서버 값 그대로 */
  day: Fact | null | undefined;
  value: ReactNode;
}

/** 날짜·연월 Fact 의 문자열 값(YYYY-MM-DD · YYYY-MM). 없으면 null */
function dayText(fact: Fact | null | undefined): string | null {
  return typeof fact?.v === 'string' ? fact.v : null;
}

/**
 * 일정은 어디쯤 왔나요? — 공고문 날짜를 순서대로 늘어놓은 진행 줄(목업 Detail · Mobile).
 * 접수 일정(apply_dates) → 당첨자 발표 → 계약(contract_dates) → 되팔기 가능(전매 종료) → 입주. 값은 FactCell(D± · 라벨 · 출처).
 * 점 모양: 기준일에 이미 지난 날은 채운 점, 다음 일정은 강조 테두리 — 날짜 문자열 비교일 뿐 새 값을 만들지 않는다.
 */
export function ScheduleCard({ detail }: { detail: ComplexDetail }) {
  const { header, asof_date: asof } = detail;
  const steps: Step[] = [
    ...header.apply_dates.map((item, i) => ({
      key: `apply-${String(i)}`,
      label: item.kind,
      day: item.end ?? item.start,
      value: <Range start={item.start} end={item.end ?? null} asof={asof} />,
    })),
    {
      key: 'winner',
      label: t('page.G3.summary.winnerDate'),
      day: header.winner_date,
      value: <FactCell wrap fact={header.winner_date} unit="date" asof={asof} />,
    },
    ...header.contract_dates.map((item, i) => ({
      key: `contract-${String(i)}`,
      label: `${t('page.G3.summary.contract')} · ${item.kind}`,
      day: item.end ?? item.start,
      value: <Range start={item.start} end={item.end ?? null} asof={asof} />,
    })),
    {
      key: 'resale',
      label: t('page.G3.schedule.resale'),
      day: header.resale_end,
      value: (
        <FactCell
          wrap
          fact={header.resale_end}
          unit="date"
          asof={asof}
          emptyReason={t('empty.unknown')}
        />
      ),
    },
    {
      key: 'move-in',
      label: t('page.G3.schedule.moveIn'),
      day: header.move_in_ym,
      value: <FactCell wrap fact={header.move_in_ym} unit="ym" />,
    },
  ];
  const past = (s: Step) => {
    const d = dayText(s.day);
    return d !== null && d < asof;
  };
  const nextIndex = steps.findIndex((s) => !past(s) && dayText(s.day) !== null);
  return (
    <Tier tier="schedule" title={t('page.G3.schedule.title')} hint={t('page.G3.schedule.hint')}>
      {header.apply_dates.length === 0 ? (
        <p className="text-sm" data-testid="apply-dates">
          <EmptyState inline reason={t('page.G3.summary.noScheduleReason')} />
        </p>
      ) : null}
      <ol
        aria-label={t('page.G3.schedule.title')}
        data-testid="schedule-steps"
        className="flex flex-col gap-0 md:flex-row md:overflow-x-auto md:pb-1"
      >
        {steps.map((s, i) => {
          const done = past(s);
          const next = i === nextIndex;
          const last = i === steps.length - 1;
          return (
            <li
              key={s.key}
              data-step-state={done ? 'past' : next ? 'next' : 'later'}
              className="relative flex min-w-0 gap-3 pb-4 md:min-w-[150px] md:flex-1 md:flex-col md:gap-2 md:pb-0 md:pr-3"
            >
              <span className="relative flex flex-col items-center md:flex-row">
                <span
                  aria-hidden
                  className={`z-10 inline-flex size-4 shrink-0 items-center justify-center rounded-full border-2 ${
                    done
                      ? 'border-muted bg-muted'
                      : next
                        ? 'border-accent bg-surface ring-4 ring-accent-soft'
                        : 'border-border-strong bg-surface'
                  }`}
                />
                {last ? null : (
                  <span
                    aria-hidden
                    className={`absolute left-[7px] top-4 h-full w-0.5 md:left-4 md:top-[7px] md:h-0.5 md:w-full ${
                      done ? 'bg-muted' : 'bg-border'
                    }`}
                  />
                )}
              </span>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span
                  className={`text-sm ${next ? 'font-semibold text-accent-ink' : done ? 'text-fg-2' : 'font-medium text-fg'}`}
                >
                  <span className="sr-only">
                    {done ? t('page.G3.schedule.past') : t('page.G3.schedule.upcoming')}
                  </span>
                  {s.label}
                </span>
                <span className="text-[13px] text-fg-2">{s.value}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </Tier>
  );
}

function Range({ start, end, asof }: { start: Fact; end: Fact | null; asof: string }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <FactCell wrap fact={start} unit="date" asof={asof} />
      {end ? (
        <>
          <span aria-hidden>~</span>
          <FactCell wrap fact={end} unit="date" asof={asof} />
        </>
      ) : null}
    </span>
  );
}
