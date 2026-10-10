import { useQueryClient } from '@tanstack/react-query';
import { useId, useMemo, useState, type ReactNode } from 'react';
import { useCanWrite } from '@/api/auth';
import {
  queryKeys,
  useCompare,
  useCreateJob,
  useCreateScenario,
  useDashboard,
  useScenarioPreview,
  useScenarios,
  useSensitivity,
} from '@/api/hooks';
import type { ComponentKey, Scenario, ScenarioPreview, ScoreRow, Weights } from '@/api/types';
import { useToast } from '@/app/toast';
import { C07Decision, C10Sensitivity } from '@/charts';
import { Badge, EmptyState, FactCell, JobProgress, MetaText, MetaValue } from '@/components';
import { snapshotText } from '@/components/SnapshotPicker';
import { scenarioKey as keyOf, useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, type TKey } from '@/i18n';
import { PageShell } from '@/layout/PageShell';
import { resultSnapshotId, type JobLike } from '@/lib/contract';
import { metaNumber } from '@/lib/meta';
import { enumText, Section, tdClass, thClass, usePageContext } from '../_shared';
import {
  fromScenario,
  rebalance,
  toScenarioCreate,
  weightsSum,
  type FieldErrors,
  type ScenarioFormValues,
} from './schema';

/**
 * G5 시나리오(내 조건) `/scenario` (RA §7-1)
 * ScenarioForm(10 필드, zod) · WeightPreview(슬라이더 6, 합 1) · RequirementPreview(판정기 호출 없음)
 * · RunButton(캐시 히트 → POST /jobs) · JobProgress(2초 폴링) · DiffTable · C7 · C10
 * escaped 봉투 → 상단 배너 "판정기가 질문을 남겼습니다" + 질문 텍스트.
 */
export function ScenarioPage() {
  const { data: scenarios = [], isLoading } = useScenarios();
  const { scenarioKey } = usePageContext();
  const current =
    scenarios.find((s) => keyOf(s) === scenarioKey) ??
    scenarios.find((s) => s.code === 'base') ??
    scenarios[0] ??
    null;
  return (
    <PageShell title={t('page.G5.title')}>
      {isLoading ? (
        <p className="text-sm text-muted">{t('app.loading')}</p>
      ) : (
        <ScenarioBody key={current?.id ?? 'none'} scenarios={scenarios} current={current} />
      )}
    </PageShell>
  );
}

function ScenarioBody({ scenarios, current }: { scenarios: Scenario[]; current: Scenario | null }) {
  const { snapshotId } = usePageContext();
  const key = current ? keyOf(current) : null;
  const dashboard = useDashboard(snapshotId, key);
  const topIds = (dashboard.data?.top5 ?? []).slice(0, 6).map((r) => r.complex_id);
  const compare = useCompare(snapshotId, topIds, key);
  const sensitivity = useSensitivity(snapshotId, key);
  const decision = key ? (compare.data?.decisions[key] ?? null) : null;
  const names = Object.fromEntries(
    (dashboard.data?.top5 ?? []).map((r) => [String(r.complex_id), r.name]),
  );

  return (
    <div className="flex flex-col gap-4">
      {decision && (decision.escaped || decision.status === 'escaped') ? (
        <div role="alert" className="rounded-sm border border-danger bg-surface p-3 text-sm">
          <p className="font-semibold text-danger">{t('page.G5.escaped')}</p>
          {decision.question ? <p className="mt-1">{decision.question}</p> : null}
        </div>
      ) : null}
      <BaseScenarioPicker scenarios={scenarios} current={current} />
      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <ScenarioEditor current={current} />
        <RunPanel current={current} before={dashboard.data?.top5 ?? null} />
      </div>
      <RequirementPreview scenario={current} />
      <div className="grid gap-4 xl:grid-cols-2">
        <C07Decision data={{ decision }} />
        <C10Sensitivity data={{ sensitivity: sensitivity.data ?? null, names }} />
      </div>
    </div>
  );
}

function BaseScenarioPicker({
  scenarios,
  current,
}: {
  scenarios: Scenario[];
  current: Scenario | null;
}) {
  const { setScenario } = useScenario();
  const id = useId();
  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor={id} className="text-muted">
        {t('page.G5.base')}
      </label>
      <select
        id={id}
        value={current ? keyOf(current) : ''}
        onChange={(e) => setScenario(e.target.value || null)}
        className="rounded-sm border border-border bg-surface px-2 py-1"
      >
        {scenarios.map((s) => (
          <option key={s.id} value={keyOf(s)}>
            {s.name}
          </option>
        ))}
      </select>
      {current?.is_builtin ? (
        <span className="text-xs text-muted">{t('page.G5.readOnlyBuiltin')}</span>
      ) : null}
    </div>
  );
}

const FIELD_ORDER = [
  'residence',
  'homeless',
  'household_size',
  'has_account',
  'score',
  'equity_won',
  'loan_limit_won',
  'purpose',
  'holding_years',
  'preferred_area_m2',
  'move_in_by',
] as const satisfies readonly (keyof ScenarioFormValues)[];

function ScenarioEditor({ current }: { current: Scenario | null }) {
  const toast = useToast();
  const { setScenario } = useScenario();
  const create = useCreateScenario();
  const canWrite = useCanWrite();
  const [values, setValues] = useState<ScenarioFormValues>(() =>
    fromScenario(current, current?.is_builtin ? '' : (current?.name ?? '')),
  );
  const [weights, setWeights] = useState<Weights>(
    () =>
      current?.weights ?? {
        p10: 0.35,
        rerank: 0.2,
        gap: 0.15,
        benchmark: 0.1,
        supply: 0.1,
        liquidity: 0.1,
      },
  );
  const [errors, setErrors] = useState<FieldErrors>({});

  const set = <K extends keyof ScenarioFormValues>(k: K, v: ScenarioFormValues[K]) =>
    setValues((prev) => ({ ...prev, [k]: v }));

  const submit = () => {
    const result = toScenarioCreate(values, weights, current);
    if (!result.ok) {
      setErrors(result.errors);
      return;
    }
    setErrors({});
    create.mutate(result.body, {
      onSuccess: (created) => {
        toast({ message: t('page.G5.saved') });
        setScenario(keyOf(created));
      },
    });
  };

  return (
    <form
      aria-label={t('page.G5.form')}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex flex-col gap-3 rounded-sm border border-border bg-surface p-3"
    >
      <h2 className="text-base font-semibold">{t('page.G5.form')}</h2>
      <TextField
        name="name"
        value={values.name}
        error={errors.name}
        onChange={(v) => set('name', v)}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELD_ORDER.map((k) => {
          if (k === 'homeless' || k === 'has_account') {
            return <CheckField key={k} name={k} checked={values[k]} onChange={(v) => set(k, v)} />;
          }
          if (k === 'purpose') {
            return (
              <SelectField
                key={k}
                name={k}
                value={values.purpose}
                options={['', '실거주', '시세차익', '병행']}
                onChange={(v) => set('purpose', v as ScenarioFormValues['purpose'])}
              />
            );
          }
          return (
            <TextField
              key={k}
              name={k}
              value={values[k]}
              error={errors[k]}
              inputMode={k === 'residence' || k === 'move_in_by' ? undefined : 'decimal'}
              onChange={(v) => set(k, v)}
            />
          );
        })}
      </div>
      <WeightPreview weights={weights} onChange={setWeights} error={errors.weights} />
      {create.error ? (
        <p role="alert" className="text-sm text-danger">
          {t('page.common.loadError', { detail: create.error.message })}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={!canWrite || create.isPending}
        title={canWrite ? undefined : t('auth.readOnlyHint')}
        className="self-start rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
      >
        {t('page.G5.save')}
      </button>
    </form>
  );
}

function FieldShell({
  id,
  name,
  error,
  children,
}: {
  id: string;
  name: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 text-sm">
      <label htmlFor={id} className="text-xs text-muted">
        {t(`page.G5.field.${name}` as TKey)}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function TextField({
  name,
  value,
  error,
  inputMode,
  onChange,
}: {
  name: string;
  value: string;
  error?: string;
  inputMode?: 'decimal';
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <FieldShell id={id} name={name} error={error}>
      <input
        id={id}
        name={name}
        value={value}
        inputMode={inputMode}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-border bg-surface px-2 py-1"
      />
    </FieldShell>
  );
}

function CheckField({
  name,
  checked,
  onChange,
}: {
  name: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="inline-flex items-center gap-2 self-end text-sm">
      <input
        type="checkbox"
        name={name}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {t(`page.G5.field.${name}` as TKey)}
    </label>
  );
}

function SelectField({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <FieldShell id={id} name={name}>
      <select
        id={id}
        name={name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-border bg-surface px-2 py-1"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o === '' ? t('page.G5.purpose.') : enumText('page.G5.purpose', o)}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

function WeightPreview({
  weights,
  onChange,
  error,
}: {
  weights: Weights;
  onChange: (w: Weights) => void;
  error?: string;
}) {
  const keys = Object.keys(weights) as ComponentKey[];
  const sum = weightsSum(weights);
  return (
    <fieldset
      aria-label={t('page.G5.weights')}
      className="flex flex-col gap-2 rounded-sm border border-border p-2"
    >
      <legend className="px-1 text-sm font-medium">{t('page.G5.weights')}</legend>
      <p className="text-xs text-muted">{t('page.G5.weightsHint')}</p>
      {keys.map((k) => {
        const v = weights[k] ?? 0;
        const label = enumText('chart.C06.component', k);
        return (
          <label key={k} className="grid grid-cols-[8rem_1fr_3.5rem] items-center gap-2 text-sm">
            <span>{label}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={v}
              aria-label={label}
              aria-valuetext={metaNumber({ n: v, as: 'number', digits: 2 })}
              onChange={(e) => onChange(rebalance(weights, k, Number(e.target.value)))}
            />
            <MetaValue kind="input" value={v} as="number" digits={2} className="text-right" />
          </label>
        );
      })}
      <p
        className={`text-sm ${Math.abs(sum - 1) > 0.001 ? 'text-danger' : 'text-muted'}`}
        data-testid="weights-sum"
      >
        <MetaText
          kind="input"
          k="page.G5.weightsSum"
          params={{ sum: { n: sum, as: 'number', digits: 2 } }}
        />
      </p>
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

function RequirementPreview({ scenario }: { scenario: Scenario | null }) {
  const { snapshotId } = usePageContext();
  const preview = useScenarioPreview(scenario?.id ?? null, snapshotId);
  return (
    <Section title={t('page.G5.requirements')}>
      {preview.data ? (
        <RequirementTable preview={preview.data} />
      ) : preview.error ? (
        <EmptyState message={t('page.common.loadError', { detail: preview.error.message })} />
      ) : (
        <p className="text-sm text-muted">{t('app.loading')}</p>
      )}
    </Section>
  );
}

function RequirementTable({ preview }: { preview: ScenarioPreview }) {
  const cols = ['access', 'regulation', 'funds'] as const;
  return (
    <div className="overflow-x-auto">
      <table aria-label={t('page.G5.requirements')} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th scope="col" className={thClass}>
              {t('page.G5.req.complex')}
            </th>
            {cols.map((c) => (
              <th key={c} scope="col" className={thClass}>
                {t(`page.G5.req.${c}` as TKey)}
                <span className="block font-normal">{preview.requirements[c].text}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.requirements_pre.map((row) => (
            <tr key={row.complex_id} className={row.excluded ? 'text-grayed' : ''}>
              <th scope="row" className={`${tdClass} text-left font-medium`}>
                {row.name}{' '}
                {row.excluded ? <Badge tone="muted">{t('page.G5.req.excluded')}</Badge> : null}
              </th>
              {cols.map((c) => (
                <td key={c} className={tdClass}>
                  <Badge tone={row[c].status === '충족' ? 'neutral' : 'muted'}>
                    {enumText('page.G5.reqStatus', row[c].status)}
                  </Badge>
                  <span className="block text-xs text-muted">{row[c].evidence}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted" data-testid="cache-hits">
        <MetaText
          kind="count"
          k="page.G5.cache"
          params={{ hits: preview.cache_hits, misses: preview.cache_misses }}
        />
      </p>
    </div>
  );
}

function RunPanel({ current, before }: { current: Scenario | null; before: ScoreRow[] | null }) {
  const { snapshotId } = usePageContext();
  const { snapshots, setSnapshot } = useSnapshot();
  const createJob = useCreateJob();
  const canWrite = useCanWrite();
  const preview = useScenarioPreview(current?.id ?? null, snapshotId);
  const [jobId, setJobId] = useState<number | null>(null);
  const [baseline, setBaseline] = useState<{ rows: ScoreRow[]; snapshotId: string } | null>(null);
  // C-5: 재판정은 발행 스냅샷을 고치지 않고 같은 기준일 새 리비전에 쓴다(D11-1) — '이후'는 잡이 쓴 리비전에서 읽는다
  const [afterId, setAfterId] = useState<string | null>(null);
  // 잡이 끝난 시각 — '이후' 대시보드는 이 시각 뒤에 받은 응답만 쓴다(5차 minor: 캐시에 남은 옛 값으로 잠깐
  // '변화 없음'이 보이던 것 — 잡이 리비전을 알려 주지 않아 기준 리비전을 다시 읽는 경우 같은 쿼리 키다)
  const [doneAt, setDoneAt] = useState<number | null>(null);
  const qc = useQueryClient();
  const key = current ? keyOf(current) : null;
  const after = useDashboard(afterId, key);
  const finished = afterId !== null;
  const afterFresh =
    finished &&
    doneAt !== null &&
    !!after.data &&
    !after.isPlaceholderData &&
    after.dataUpdatedAt >= doneAt;
  // 6차 minor 25: '이후' 조회가 잡 뒤에 실패하면 '받는 중'에 멈추지 않고 오류 + 다시 시도
  const afterError =
    finished && doneAt !== null && !afterFresh && after.error && after.errorUpdatedAt >= doneAt
      ? after.error
      : null;

  const run = () => {
    if (!current || !snapshotId) return;
    setBaseline(before ? { rows: before, snapshotId } : null);
    setAfterId(null);
    setDoneAt(null);
    createJob.mutate(
      {
        job_name: 'rejudge',
        payload: {
          snapshot_id: Number(snapshotId),
          scenario_id: current.id,
          complex_ids: null,
          reason: t('page.G5.runReason'),
        },
      },
      { onSuccess: (job) => setJobId(job.id) },
    );
  };

  // 잡 완료 무효화(지역·리비전 목록·사실 화면)는 api/jobWatch 가 한다
  const onDone = (job: JobLike) => {
    const id = resultSnapshotId(job) ?? baseline?.snapshotId ?? snapshotId;
    setDoneAt(Date.now());
    setAfterId(id);
    // 캐시가 아직 신선(staleTime)해도 잡 뒤 값을 다시 받는다
    if (id) void qc.invalidateQueries({ queryKey: queryKeys.dashboard(id, key) });
  };

  const afterSnapshot = snapshots.find((s) => String(s.id) === afterId) ?? null;
  const showsOther = afterId !== null && afterId !== snapshotId;

  return (
    <Section title={t('page.G5.run')}>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={run}
          disabled={!canWrite || !current || !snapshotId || createJob.isPending}
          title={canWrite ? undefined : t('auth.readOnlyHint')}
          className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
        >
          {t('page.G5.run')}
        </button>
        {preview.data ? (
          <MetaText
            kind="count"
            className="text-xs text-muted"
            k="page.G5.cache"
            params={{ hits: preview.data.cache_hits, misses: preview.data.cache_misses }}
          />
        ) : null}
      </div>
      {jobId !== null ? (
        <>
          {!finished ? <p className="text-xs text-muted">{t('page.G5.running')}</p> : null}
          <JobProgress jobId={String(jobId)} onDone={onDone} />
        </>
      ) : null}
      {finished ? (
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted" data-testid="g5-after">
          <span>
            {t('page.G5.afterRevision', {
              snapshot: afterSnapshot ? snapshotText(afterSnapshot) : t('page.G5.afterPending'),
            })}
          </span>
          {showsOther ? (
            <button type="button" onClick={() => setSnapshot(afterId)} className="underline">
              {t('page.G5.openRevision')}
            </button>
          ) : null}
        </p>
      ) : null}
      {afterError ? (
        <div
          role="alert"
          data-testid="g5-after-error"
          className="flex flex-wrap items-center gap-2 text-xs text-danger"
        >
          <span>{t('page.G5.afterError', { detail: afterError.message })}</span>
          <button
            type="button"
            onClick={() => void after.refetch()}
            disabled={after.isFetching}
            className="underline disabled:opacity-50"
          >
            {t('app.retry')}
          </button>
        </div>
      ) : null}
      {finished && baseline && !afterFresh && !afterError ? (
        <p className="text-xs text-muted" data-testid="g5-after-loading">
          {t('page.G5.afterLoading')}
        </p>
      ) : null}
      {baseline && afterFresh && after.data ? (
        <DiffTable before={baseline.rows} after={after.data.top5} />
      ) : null}
    </Section>
  );
}

/** 이전 run 대비 순위·점수 */
export function DiffTable({ before, after }: { before: ScoreRow[]; after: ScoreRow[] }) {
  const rows = useMemo(() => {
    const prev = new Map(before.map((r) => [r.complex_id, r]));
    const ids = [
      ...new Set([...after.map((r) => r.complex_id), ...before.map((r) => r.complex_id)]),
    ];
    return ids.map((id) => ({
      id,
      name: after.find((r) => r.complex_id === id)?.name ?? prev.get(id)?.name ?? `#${id}`,
      before: prev.get(id) ?? null,
      after: after.find((r) => r.complex_id === id) ?? null,
    }));
  }, [before, after]);
  const changed = rows.some(
    (r) => r.before?.rank !== r.after?.rank || r.before?.total.v !== r.after?.total.v,
  );
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-sm font-semibold">{t('page.G5.diff')}</h3>
      {!changed ? <p className="text-xs text-muted">{t('page.G5.noDiff')}</p> : null}
      <table aria-label={t('page.G5.diff')} className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {(
              [
                'name',
                'rankBefore',
                'rankAfter',
                'totalBefore',
                'totalAfter',
                'deltaRerank',
              ] as const
            ).map((k) => (
              <th key={k} scope="col" className={thClass}>
                {t(`page.G5.diffCol.${k}` as TKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <th scope="row" className={`${tdClass} text-left font-normal`}>
                {r.name}
              </th>
              <td className={tdClass}>
                {r.before?.rank != null ? (
                  <MetaValue kind="rank" value={r.before.rank} as="rank" />
                ) : (
                  t('page.common.none')
                )}
              </td>
              <td className={tdClass}>
                {r.after?.rank != null ? (
                  <MetaValue kind="rank" value={r.after.rank} as="rank" />
                ) : (
                  t('page.common.none')
                )}
              </td>
              <td className={tdClass}>
                <FactCell fact={r.before?.total ?? null} unit="score" />
              </td>
              <td className={tdClass}>
                <FactCell fact={r.after?.total ?? null} unit="score" />
              </td>
              <td className={tdClass} data-testid="diff-delta-rerank">
                <FactCell
                  fact={r.after?.delta_rerank ?? null}
                  unit="score"
                  emptyReason={t('page.common.deltaRerankNone')}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
