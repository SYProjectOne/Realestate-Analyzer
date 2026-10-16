import { useId, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useCreateRegion, useResolveRegion } from '@/api/hooks';
import type { RegionCandidate, RegionCreated, RegionSelection } from '@/api/types';
import { useToast } from '@/app/toast';
import { Card, JobProgress, MetaText } from '@/components';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { enumText, useDebounced } from '../_shared';
import { checkWindow, isApplyhomeQueryLoc } from './applyhomeWindow';
import { Crumbs } from './Crumbs';
import { HelpToggle } from './HelpToggle';
import { ERROR_BOX, StepNo, type StepState } from './ui';

const DEBOUNCE_MS = 300;

const sameCandidate = (
  a: Pick<RegionSelection, 'kind' | 'code'>,
  b: Pick<RegionSelection, 'kind' | 'code'>,
) => a.kind === b.kind && a.code === b.code;

function StepItem({
  n,
  state,
  title,
  hint,
}: {
  n: string;
  state: StepState;
  title: string;
  hint: ReactNode;
}) {
  return (
    <li
      aria-current={state === 'current' ? 'step' : undefined}
      data-step-state={state}
      className={`flex items-center gap-2.5 rounded-[14px] bg-surface px-4 py-3.5 ${
        state === 'todo' ? 'border border-border' : 'border-2 border-accent'
      }`}
    >
      <StepNo n={n} state={state} />
      <span className="flex min-w-0 flex-col">
        <b className={`text-[15px] ${state === 'todo' ? 'text-fg-2' : 'text-fg'}`}>{title}</b>
        <span className="text-xs text-muted">{hint}</span>
      </span>
    </li>
  );
}

/**
 * G0 지역 입력 `/regions/new` (D2-5, 목업 RegionNew — 1 찾기 → 2 확인·이름 → 3 분석 시작 → 4 진행)
 * 검색창(자유 지명, 디바운스 자동완성 → GET /regions/resolve) · 후보 다중 선택 칩 · 이름 · "분석 시작"
 * → POST /regions → JobProgress(region.bootstrap 잡). 지역명은 사용자 입력·서버 응답만 쓴다.
 * 계약 .15 F3·F4(D20-1): '청약홈 조회 기간(고급)' 선택 입력 — 비우면 `applyhome_query` 를 보내지 않아 서버 기본 창(지난 24개월 +
 * 향후 12개월), 입력하면 그 칸만(`from_ym`·`to_ym` 'YYYY-MM'). 형식은 서버와 같은 검사, 서버 422 는 그 칸 안내.
 */
export function RegionNewPage() {
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query, DEBOUNCE_MS);
  const resolve = useResolveRegion(debounced);
  const [selected, setSelected] = useState<RegionSelection[]>([]);
  const [name, setName] = useState('');
  const create = useCreateRegion();
  const canWrite = useCanWrite();
  const [created, setCreated] = useState<RegionCreated | null>(null);
  const [done, setDone] = useState(false);
  const toast = useToast();
  const searchId = useId();
  const nameId = useId();
  const fromId = useId();
  const toId = useId();
  const [fromYm, setFromYm] = useState('');
  const [toYm, setToYm] = useState('');
  const win = checkWindow(fromYm, toYm);
  const [windowOpen, setWindowOpen] = useState(false);
  const windowBlocked = win.invalid.length > 0 || win.reversed;
  const windowServerErrors =
    create.error instanceof ApiError
      ? create.error.fieldErrors.filter((e) => isApplyhomeQueryLoc(e.loc))
      : [];

  const toggle = (c: RegionCandidate) =>
    setSelected((prev) =>
      prev.some((s) => sameCandidate(s, c))
        ? prev.filter((s) => !sameCandidate(s, c))
        : [...prev, { kind: c.kind, code: c.code, full_name: c.full_name }],
    );

  const trimmed = name.trim();
  const canStart =
    canWrite &&
    selected.length > 0 &&
    trimmed.length > 0 &&
    !windowBlocked &&
    !create.isPending &&
    !created;

  const start = () => {
    if (!canStart) return;
    create.mutate(
      {
        name: trimmed,
        query_text: query.trim(),
        selections: selected,
        ...(win.query ? { applyhome_query: win.query } : {}),
      },
      {
        onSuccess: (result) => {
          setCreated(result);
          toast({ message: t('page.G0.started') });
        },
      },
    );
  };

  const searched = debounced.trim().length >= 2;
  const candidates = searched ? (resolve.data ?? []) : [];
  const picked = selected.length > 0;

  const steps: { n: string; state: StepState; title: TKey; hint: ReactNode }[] = [
    {
      n: '1',
      state: picked || created ? 'done' : 'current',
      title: 'page.G0.steps.find',
      hint: t('page.G0.steps.findHint'),
    },
    {
      n: '2',
      state: created || (picked && trimmed) ? 'done' : picked ? 'current' : 'todo',
      title: 'page.G0.steps.confirm',
      hint: picked ? (
        <MetaText kind="count" k="page.G0.steps.confirmHint" params={{ n: selected.length }} />
      ) : (
        t('page.G0.steps.confirmNone')
      ),
    },
    {
      n: '3',
      state: created ? 'done' : canStart ? 'current' : 'todo',
      title: 'page.G0.steps.start',
      hint: t('page.G0.steps.startHint'),
    },
    {
      n: '4',
      state: done ? 'done' : created ? 'current' : 'todo',
      title: 'page.G0.steps.progress',
      hint: t('page.G0.steps.progressHint'),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <Crumbs items={[t('page.G0.crumb')]} />
      <PageShell title={t('page.G0.title')} intro={t('page.G0.intro')}>
        <ol
          aria-label={t('page.G0.stepsLabel')}
          className="grid grid-cols-2 gap-2.5 lg:grid-cols-4"
        >
          {steps.map((s) => (
            <StepItem key={s.n} n={s.n} state={s.state} title={t(s.title)} hint={s.hint} />
          ))}
        </ol>

        <div className="flex flex-wrap items-start gap-5">
          {/* 1 지역 찾기 */}
          <Card
            as="section"
            aria-labelledby={`${searchId}-h`}
            padding="lg"
            className="flex min-w-0 flex-[1_1_560px] flex-col gap-4"
          >
            <h2
              id={`${searchId}-h`}
              className="flex items-center gap-2.5 text-lg font-bold sm:text-[21px]"
            >
              <StepNo n="1" />
              {t('page.G0.steps.find')}
            </h2>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={searchId} className="text-sm font-semibold text-fg-2">
                {t('page.G0.search')}
              </label>
              <div className="flex min-h-[52px] items-center gap-2.5 rounded-xl border-2 border-accent bg-surface px-3.5">
                <svg
                  aria-hidden
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  className="shrink-0 text-muted"
                >
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                </svg>
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  autoComplete="off"
                  placeholder={t('page.G0.searchPlaceholder')}
                  onChange={(e) => setQuery(e.target.value)}
                  className="min-w-0 flex-1 bg-transparent py-2 text-[17px] outline-hidden"
                />
              </div>
              <span className="text-[13px] text-muted">
                {t('page.G0.searchHint')}
                {candidates.length > 0 ? (
                  <>
                    {' · '}
                    <MetaText
                      kind="count"
                      k="page.G0.candidateCount"
                      params={{ n: candidates.length }}
                    />
                  </>
                ) : null}
              </span>
              {resolve.isFetching ? (
                <p role="status" className="flex items-center gap-2 text-sm text-fg-2">
                  <svg
                    aria-hidden
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                    className="animate-spin text-accent motion-reduce:animate-none"
                  >
                    <path d="M21 12a9 9 0 1 1-6.2-8.6" />
                  </svg>
                  {t('page.G0.searching')}
                </p>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              {candidates.length > 0 ? (
                <p className="text-[15px] font-semibold">
                  {t('page.G0.pickTitle')}{' '}
                  <span className="text-[13px] font-normal text-muted">
                    {t('page.G0.pickHint')}
                  </span>
                </p>
              ) : (
                <span />
              )}
              <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
                {t('page.G0.dongHelp.q')}
                <HelpToggle label={t('page.G0.dongHelp.button')} align="right">
                  {t('page.G0.dongHelp.body')}
                </HelpToggle>
              </span>
            </div>

            {searched && resolve.data && candidates.length === 0 ? (
              <p className="rounded-[10px] bg-subtle p-3 text-sm text-fg-2">
                {t('page.G0.noCandidates')}
              </p>
            ) : null}
            {resolve.error ? (
              <p role="alert" className={ERROR_BOX}>
                {t('page.common.loadError', { detail: resolve.error.message })}
              </p>
            ) : null}
            {candidates.length > 0 ? (
              <>
                <ul aria-label={t('page.G0.candidates')} className="flex flex-col gap-1">
                  {candidates.map((c) => {
                    const checked = selected.some((s) => sameCandidate(s, c));
                    return (
                      <li key={`${c.kind}-${c.code}`}>
                        <label
                          data-checked={checked || undefined}
                          className={`flex min-h-11 cursor-pointer flex-wrap items-center gap-x-2.5 gap-y-2 rounded-xl px-3.5 py-3 ${
                            checked
                              ? 'border-2 border-accent bg-accent-soft/50'
                              : 'border border-border bg-surface hover:border-border-strong'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggle(c)}
                            className="size-5 accent-accent"
                          />
                          <span
                            className={`min-w-0 flex-[1_1_220px] text-[15px] ${checked ? 'font-bold' : 'font-semibold'}`}
                          >
                            {c.full_name}
                          </span>
                          <span className="whitespace-nowrap rounded-md bg-chip px-2 py-0.5 text-xs font-semibold text-fg-2">
                            {enumText('page.common.candidateKind', c.kind)}
                          </span>
                          <span
                            data-match={c.match}
                            className={`whitespace-nowrap rounded-md px-2 py-0.5 text-xs ${
                              c.match === 'exact'
                                ? 'bg-accent-soft font-semibold text-accent-ink'
                                : 'border border-grayed bg-surface font-medium text-muted'
                            }`}
                          >
                            {enumText('page.G0.match', c.match)}
                          </span>
                          <MetaText
                            kind="count"
                            className="text-xs tabular-nums text-muted"
                            k="page.G0.dongCount"
                            params={{ n: c.legal_dong_codes.length }}
                          />
                        </label>
                      </li>
                    );
                  })}
                </ul>
                <p className="rounded-[10px] bg-subtle px-3 py-2.5 text-[13px] leading-relaxed text-muted">
                  {t('page.G0.legend')}
                </p>
              </>
            ) : null}
          </Card>

          {/* 2 고른 지역 확인 · 이름 (+ 3 분석 시작) */}
          <Card
            as="section"
            aria-labelledby={`${nameId}-h`}
            padding="lg"
            className="flex min-w-0 flex-[1_1_440px] flex-col gap-[18px]"
          >
            <h2
              id={`${nameId}-h`}
              className="flex items-center gap-2.5 text-lg font-bold sm:text-[21px]"
            >
              <StepNo n="2" state={picked ? 'current' : 'todo'} />
              {t('page.G0.steps.confirm')}
            </h2>
            <div className="flex flex-col gap-2">
              <p className="text-sm font-semibold text-fg-2">
                {t('page.G0.selected')}{' '}
                {picked ? (
                  <MetaText
                    kind="count"
                    className="font-normal tabular-nums text-muted"
                    k="page.G0.selectedCount"
                    params={{ n: selected.length }}
                  />
                ) : null}
              </p>
              {picked ? (
                <>
                  <ul aria-label={t('page.G0.selected')} className="flex flex-wrap gap-2">
                    {selected.map((s) => (
                      <li key={`${s.kind}-${s.code}`}>
                        <button
                          type="button"
                          onClick={() =>
                            setSelected((prev) => prev.filter((x) => !sameCandidate(x, s)))
                          }
                          aria-label={t('page.common.remove', { name: s.full_name })}
                          className="inline-flex min-h-11 items-center gap-2 rounded-full border border-accent bg-accent-soft py-2 pl-3.5 pr-2 text-[15px] font-semibold text-accent-ink"
                        >
                          {s.full_name}
                          <span
                            aria-hidden
                            className="inline-flex size-[26px] items-center justify-center rounded-full bg-surface"
                          >
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2.6"
                              strokeLinecap="round"
                            >
                              <path d="M6 6l12 12" />
                              <path d="M18 6 6 18" />
                            </svg>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <span className="text-xs text-muted">{t('page.G0.chipHint')}</span>
                </>
              ) : (
                <p className="rounded-[10px] border border-dashed border-grayed p-3 text-sm text-muted">
                  {t('page.G0.noneSelected')}
                </p>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={nameId} className="text-sm font-semibold text-fg-2">
                {t('page.G0.name')}
              </label>
              <input
                id={nameId}
                value={name}
                placeholder={t('page.G0.namePlaceholder')}
                onChange={(e) => setName(e.target.value)}
                className="min-h-12 w-full rounded-xl border border-border-strong bg-surface px-3.5 py-2.5 text-base"
              />
              <span className="text-xs text-muted">{t('page.G0.nameHint')}</span>
            </div>
            <details
              role="group"
              aria-label={t('page.G0.window.title')}
              className="rounded-xl border border-border px-3.5"
              open={windowOpen || windowBlocked || windowServerErrors.length > 0}
              onToggle={(e) => setWindowOpen(e.currentTarget.open)}
            >
              <summary className="min-h-11 cursor-pointer py-3 text-[15px] font-semibold">
                {t('page.G0.window.title')}
              </summary>
              <div className="flex flex-col gap-3 pb-3.5">
                <p className="text-[13px] leading-relaxed text-muted">{t('page.G0.window.hint')}</p>
                <div className="flex flex-wrap gap-3.5">
                  {(
                    [
                      ['from_ym', fromId, fromYm, setFromYm, 'page.G0.window.from'],
                      ['to_ym', toId, toYm, setToYm, 'page.G0.window.to'],
                    ] as const
                  ).map(([field, id, value, set, label]) => {
                    const invalid = win.invalid.includes(field);
                    return (
                      <div key={field} className="flex w-[150px] flex-col gap-1.5">
                        <label htmlFor={id} className="text-[13px] font-semibold text-fg-2">
                          {t(label)}
                        </label>
                        <input
                          id={id}
                          value={value}
                          inputMode="numeric"
                          autoComplete="off"
                          maxLength={7}
                          placeholder={t('page.G0.window.placeholder')}
                          aria-invalid={invalid || undefined}
                          onChange={(e) => set(e.target.value)}
                          className={`min-h-11 w-full rounded-xl border bg-surface px-3 py-2 tabular-nums ${
                            invalid ? 'border-danger' : 'border-border-strong'
                          }`}
                        />
                      </div>
                    );
                  })}
                </div>
                {win.invalid.length > 0 ? (
                  <p role="alert" className={ERROR_BOX}>
                    {t('page.G0.window.invalid')}
                  </p>
                ) : null}
                {win.reversed ? (
                  <p role="alert" className={ERROR_BOX}>
                    {t('page.G0.window.order')}
                  </p>
                ) : null}
                {windowServerErrors.map((e, i) => (
                  <p key={i} role="alert" className={ERROR_BOX}>
                    {t('page.G0.window.server', { detail: e.msg })}
                  </p>
                ))}
              </div>
            </details>

            <div className="flex flex-col gap-2.5 border-t border-subtle pt-[18px]">
              <h3 className="flex items-center gap-2.5 text-[17px] font-bold">
                <StepNo n="3" state={canStart || created ? 'current' : 'todo'} />
                {t('page.G0.steps.start')}
              </h3>
              <button
                type="button"
                onClick={start}
                disabled={!canStart}
                title={canWrite ? undefined : t('auth.readOnlyHint')}
                className="min-h-12 w-full rounded-xl bg-accent px-5 py-3 text-[17px] font-semibold text-accent-fg hover:bg-accent-ink disabled:cursor-not-allowed disabled:bg-grayed/40 disabled:text-surface"
              >
                {trimmed ? t('page.G0.startNamed', { name: trimmed }) : t('page.G0.start')}
              </button>
              {!canStart && !created ? (
                <span className="text-[13px] text-muted" data-testid="g0-start-disabled">
                  {canWrite ? t('page.G0.startDisabled') : t('auth.readOnlyHint')}
                </span>
              ) : null}
              <p className="text-[13px] text-muted">{t('page.G0.startNote')}</p>
              {create.error ? (
                <p role="alert" className={ERROR_BOX}>
                  {t('page.common.loadError', { detail: create.error.message })}
                </p>
              ) : null}
            </div>
          </Card>
        </div>

        {created ? (
          <ProgressSection
            created={created}
            done={done}
            onDone={() => {
              setDone(true);
              toast({ message: t('page.G0.done') });
            }}
          />
        ) : null}
      </PageShell>
    </div>
  );
}

/** 4 분석 진행 상황 — 시작한 뒤에만(region.bootstrap 잡, 2초 폴링은 JobProgress) */
function ProgressSection({
  created,
  done,
  onDone,
}: {
  created: RegionCreated;
  done: boolean;
  onDone: () => void;
}) {
  const headingId = useId();
  return (
    <Card
      as="section"
      aria-labelledby={headingId}
      padding="lg"
      className="flex flex-col gap-4"
      data-testid="g0-progress"
    >
      <h2 id={headingId} className="flex items-center gap-2.5 text-lg font-bold sm:text-[21px]">
        <StepNo n="4" state={done ? 'done' : 'current'} />
        {t('page.G0.progressTitle')}
      </h2>
      <div className="flex flex-col gap-2.5 rounded-[14px] bg-subtle p-4">
        <b className="text-base" data-testid="g0-progress-head">
          {done ? t('page.G0.done') : t('page.G0.progressRunning', { name: created.region.name })}
        </b>
        <JobProgress jobId={String(created.job_id)} onDone={onDone} />
        {!done ? <p className="text-[13px] text-muted">{t('page.G0.progressNote')}</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        {done ? (
          <Link
            to={`/?region=${created.region.id}`}
            className="inline-flex min-h-11 items-center rounded-xl bg-accent px-4 text-[15px] font-semibold text-accent-fg hover:bg-accent-ink"
          >
            {t('page.G0.goDashboard')}
          </Link>
        ) : null}
        <Link
          to={`/regions/${created.region.id}/living-areas`}
          className="inline-flex min-h-11 items-center rounded-xl border border-border-strong bg-surface px-4 text-[15px] font-semibold text-fg hover:border-fg-2"
        >
          {t('page.G0.goLivingAreas')}
        </Link>
        {!done ? <span className="text-[13px] text-muted">{t('page.G0.homeLater')}</span> : null}
      </div>
    </Card>
  );
}
