import { useQueryClient } from '@tanstack/react-query';
import { useId, useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
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
import {
  Badge,
  Banner,
  Card,
  EmptyState,
  FactCell,
  JobProgress,
  MetaText,
  MetaValue,
  Skeleton,
  Term,
  TieBadge,
  type GlossaryKey,
} from '@/components';
import { snapshotText } from '@/components/SnapshotPicker';
import { scenarioKey as keyOf, useScenario } from '@/hooks/useScenario';
import { useSnapshot } from '@/hooks/useSnapshot';
import { t, tDynamic, type TKey } from '@/i18n';
import { queryErrorText, specialErrorText } from '@/lib/errorText';
import { PageShell } from '@/layout/PageShell';
import { resultSnapshotId, type JobLike } from '@/lib/contract';
import { metaNumber, metaText } from '@/lib/meta';
import { enumText, useGlobalSearch, usePageContext } from '../_shared';
import {
  AnalyzeSection,
  cellClass,
  headCellClass,
  PlainName,
  primaryButtonClass,
  ReqStatusBadge,
  SourceLine,
  wideTableClass,
  targetText,
} from '../compare/parts';
import {
  fromScenario,
  rebalance,
  toScenarioCreate,
  weightsSum,
  type FieldErrors,
  type ScenarioFormValues,
} from './schema';

/**
 * G5 내 조건(시나리오) `/scenario` (RA §7-1 · 목업 Scenario.dc.html, R11)
 * 1 출발 조건(기본 제공 카드 + select) → 2 ScenarioForm(10 필드, zod) + WeightPreview(슬라이더 6, 합 1)
 * → 3 RunPanel(캐시 히트 → POST /jobs, JobProgress 2초 폴링, DiffTable) → 4 RequirementPreview(판정기 호출 없음) · C7 · C10.
 * escaped 봉투 → 맨 위 띠 "판정기가 질문을 남겼어요" + 질문 텍스트.
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
    <PageShell title={t('page.G5.title')} intro={t('page.G5.intro')}>
      <Steps />
      {isLoading ? (
        <Skeleton />
      ) : (
        <ScenarioBody key={current?.id ?? 'none'} scenarios={scenarios} current={current} />
      )}
    </PageShell>
  );
}

const STEP_KEYS = ['s1', 's2', 's3', 's4'] as const;

/** N1 4단계 진행 표시 */
function Steps() {
  return (
    <ol
      aria-label={t('page.G5.steps')}
      className="m-0 flex list-none flex-wrap gap-x-5 gap-y-2 p-0 text-sm text-fg-2"
    >
      {STEP_KEYS.map((k, i) => (
        <li key={k} className="inline-flex items-center gap-2">
          <span
            aria-hidden
            className="inline-flex size-6 items-center justify-center rounded-full bg-fg text-xs font-bold text-surface"
          >
            <MetaValue kind="seq" value={i + 1} as="plain" />
          </span>
          {t(`page.G5.step.${k}`)}
        </li>
      ))}
    </ol>
  );
}

function ScenarioBody({ scenarios, current }: { scenarios: Scenario[]; current: Scenario | null }) {
  const { snapshotId, asof } = usePageContext();
  const key = current ? keyOf(current) : null;
  const dashboard = useDashboard(snapshotId, key);
  const topIds = (dashboard.data?.top5 ?? []).slice(0, 6).map((r) => r.complex_id);
  const compare = useCompare(snapshotId, topIds, key);
  const sensitivity = useSensitivity(snapshotId, key);
  const decision = key ? (compare.data?.decisions[key] ?? null) : null;
  const names = Object.fromEntries(
    (dashboard.data?.top5 ?? []).map((r) => [String(r.complex_id), r.name]),
  );
  const name = current?.name ?? '';

  return (
    <div className="flex flex-col gap-5">
      {decision && (decision.escaped || decision.status === 'escaped') ? (
        <Banner tone="warn" role="alert" icon title={t('page.G5.escaped')}>
          {decision.question ? <span className="block">{decision.question}</span> : null}
        </Banner>
      ) : null}
      <StartPicker scenarios={scenarios} current={current} />
      <ScenarioEditor current={current} />
      <RunPanel current={current} before={dashboard.data?.top5 ?? null} />
      <RequirementPreview scenario={current} />
      <AnalyzeSection
        eyebrow={t('page.G5.judgeEyebrow', { name })}
        title={t('page.G5.judgeQ')}
        data-testid="g5-judge"
      >
        <C07Decision data={{ decision }} asof={asof} />
      </AnalyzeSection>
      <AnalyzeSection
        eyebrow={t('page.G5.sensEyebrow', { name })}
        title={t('page.G4.sensitivityQ')}
        hint={t('page.G5.sensHint')}
        data-testid="g5-sensitivity"
      >
        <C10Sensitivity data={{ sensitivity: sensitivity.data ?? null, names }} asof={asof} />
      </AnalyzeSection>
    </div>
  );
}

/** 기본 제공 조건 카드의 주요 값 한 줄 — 서버 params·policy 를 이어 붙인 입력 값(판단 문장 아님) */
export function presetFacts(s: Pick<Scenario, 'params' | 'policy'>): string {
  const p = s.params;
  const parts: string[] = [];
  if (p.homeless) parts.push(t('page.G5.fact.homeless'));
  const score = p.subscription?.score;
  if (score !== null && score !== undefined) {
    parts.push(metaText('page.G5.fact.score', { n: score }));
  }
  if (p.equity_won !== null && p.equity_won !== undefined) {
    parts.push(metaText('page.G5.fact.equity', { won: { n: p.equity_won, as: 'won' } }));
  }
  if (p.loan_limit_won !== null && p.loan_limit_won !== undefined) {
    parts.push(metaText('page.G5.fact.loan', { won: { n: p.loan_limit_won, as: 'won' } }));
  }
  if (p.purpose) parts.push(enumText('page.G5.purpose', p.purpose));
  if (p.holding_years !== null && p.holding_years !== undefined) {
    parts.push(metaText('page.G5.fact.holding', { n: p.holding_years }));
  }
  if (p.preferred_area_m2 !== null && p.preferred_area_m2 !== undefined) {
    parts.push(metaText('page.G5.fact.area', { n: p.preferred_area_m2 }));
  }
  if (p.accepts_residency_obligation === true) parts.push(t('page.G5.fact.residencyYes'));
  if (p.accepts_residency_obligation === false) parts.push(t('page.G5.fact.residencyNo'));
  const target = targetText(s.policy?.p10_horizon);
  if (target) parts.push(t('page.G5.fact.horizon', { target }));
  if (s.policy?.exclude_intake_not_open) parts.push(t('page.G5.fact.excludeNotOpen'));
  return parts.join(t('page.G5.fact.join'));
}

/** 1 출발 조건: 기본 제공 조건 카드(라디오) + 저장한 조건까지 고르는 select. 바꾸면 전역 ?scenario= */
function StartPicker({ scenarios, current }: { scenarios: Scenario[]; current: Scenario | null }) {
  const { setScenario } = useScenario();
  const id = useId();
  const builtins = scenarios.filter((s) => s.is_builtin);
  const currentKey = current ? keyOf(current) : null;
  return (
    <AnalyzeSection
      step={1}
      title={t('page.G5.startQ')}
      hint={t('page.G5.startHint')}
      actions={
        <span className="flex items-center gap-2">
          <label htmlFor={id} className="text-[13px] text-muted">
            {t('page.G5.base')}
          </label>
          <select
            id={id}
            value={currentKey ?? ''}
            onChange={(e) => setScenario(e.target.value || null)}
            className="min-h-10 rounded-[10px] border border-border-strong bg-surface px-2.5 text-sm font-semibold"
          >
            {scenarios.map((s) => (
              <option key={s.id} value={keyOf(s)}>
                {s.name}
              </option>
            ))}
          </select>
        </span>
      }
    >
      {builtins.length > 0 ? (
        <div
          role="radiogroup"
          aria-label={t('page.G5.presets')}
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
        >
          {builtins.map((s) => {
            const on = keyOf(s) === currentKey;
            const who = s.code ? tDynamic(`page.G5.who.${s.code}`, '') : '';
            return (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={on}
                data-testid="preset-card"
                onClick={() => setScenario(keyOf(s))}
                className={`flex min-h-11 flex-col items-start gap-2 rounded-[14px] p-4 text-left ${
                  on
                    ? 'border-2 border-accent bg-accent-soft'
                    : 'border border-border-strong bg-surface hover:border-fg-2'
                }`}
              >
                <span className="flex w-full flex-wrap items-center justify-between gap-1">
                  <span className="text-xs font-semibold text-muted">
                    {s.code === 'base'
                      ? t('page.G5.presetCodeBase')
                      : t('page.G5.presetCode', { code: s.code ?? '' })}
                  </span>
                  {on ? (
                    <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-bold text-accent-fg">
                      {t('page.G5.current')}
                    </span>
                  ) : null}
                </span>
                <span className="text-[15px] font-bold text-fg">{s.name}</span>
                {who ? <span className="text-xs leading-snug text-fg-2">{who}</span> : null}
                <span data-meta="input" className="text-xs leading-snug text-muted">
                  {presetFacts(s)}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
      {current?.is_builtin ? (
        <p className="m-0 rounded-xl bg-subtle px-4 py-3 text-[13px] text-fg-2">
          {t('page.G5.readOnlyBuiltin')}
        </p>
      ) : null}
    </AnalyzeSection>
  );
}

type FieldKey = Exclude<keyof ScenarioFormValues, 'name' | 'homeless' | 'has_account' | 'purpose'>;

const GROUPS: readonly {
  key: 'household' | 'money' | 'plan';
  fields: readonly (keyof ScenarioFormValues)[];
}[] = [
  { key: 'household', fields: ['residence', 'household_size', 'homeless', 'has_account', 'score'] },
  { key: 'money', fields: ['equity_won', 'loan_limit_won'] },
  { key: 'plan', fields: ['purpose', 'holding_years', 'preferred_area_m2', 'move_in_by'] },
];

const FIELD_GLOSSARY: Partial<Record<keyof ScenarioFormValues, GlossaryKey>> = {
  score: 'points',
};

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
  const nameId = useId();

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

  const field = (k: keyof ScenarioFormValues) => {
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
    if (k === 'name') return null;
    const fk: FieldKey = k;
    return (
      <TextField
        key={fk}
        name={fk}
        value={values[fk]}
        error={errors[fk]}
        glossary={FIELD_GLOSSARY[fk]}
        inputMode={fk === 'residence' || fk === 'move_in_by' ? undefined : 'decimal'}
        onChange={(v) => set(fk, v)}
      />
    );
  };
  const hasFieldError = Object.keys(errors).some((k) => k !== 'weights');

  return (
    <AnalyzeSection
      step={2}
      title={t('page.G5.formQ')}
      hint={current ? t('page.G5.formHint', { name: current.name }) : t('page.G5.formHintEmpty')}
    >
      <form
        aria-label={t('page.G5.form')}
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex flex-col gap-5"
      >
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="flex min-w-0 flex-col gap-5">
            <div className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-1">
                <label htmlFor={nameId} className="font-semibold text-fg">
                  {t('page.G5.field.name')}
                </label>
                <span aria-hidden className="font-bold text-danger">
                  *
                </span>
                <span className="sr-only">{t('page.G5.required')}</span>
              </span>
              <input
                id={nameId}
                name="name"
                value={values.name}
                placeholder={t('page.G5.placeholder.name')}
                aria-required="true"
                aria-invalid={errors.name ? true : undefined}
                aria-describedby={errors.name ? `${nameId}-error` : undefined}
                onChange={(e) => set('name', e.target.value)}
                className={inputClass(!!errors.name)}
              />
              {errors.name ? (
                <p id={`${nameId}-error`} className="m-0 text-xs font-semibold text-danger">
                  {errors.name}
                </p>
              ) : null}
              {current?.is_builtin ? (
                <p className="m-0 text-xs text-muted">
                  {t('page.G5.builtinSaveNote', { name: current.name })}
                </p>
              ) : null}
            </div>
            {GROUPS.map((g) => (
              <fieldset key={g.key} className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
                <legend className="mb-2 p-0 text-[15px] font-bold text-fg">
                  {t(`page.G5.group.${g.key}`)}
                </legend>
                <div className="grid gap-3 sm:grid-cols-2">{g.fields.map(field)}</div>
              </fieldset>
            ))}
            {hasFieldError ? (
              <p className="m-0 text-xs text-muted" data-testid="range-note">
                {t('page.G5.rangeNote')}
              </p>
            ) : null}
          </div>
          <WeightPreview
            weights={weights}
            onChange={setWeights}
            error={errors.weights}
            scenario={current}
          />
        </div>
        {create.error ? (
          <p role="alert" className="m-0 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn-ink">
            {t('page.G5.saveError', { detail: create.error.message })}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          <button
            type="submit"
            disabled={!canWrite || create.isPending}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className={primaryButtonClass}
          >
            {t('page.G5.save')}
          </button>
          <span className="text-xs text-muted">{t('page.G5.saveNote')}</span>
        </div>
      </form>
    </AnalyzeSection>
  );
}

function inputClass(error: boolean): string {
  return `min-h-11 w-full rounded-[10px] border bg-surface px-3 text-[15px] ${
    error ? 'border-danger' : 'border-border-strong'
  }`;
}

/** 칸 이름 = 쉬운 말 + (공식 이름). 공식 이름이 없으면 쉬운 말만 */
function fieldTerm(name: string): string | null {
  const v = tDynamic(`page.G5.fieldTerm.${name}`, '');
  return v || null;
}

function TextField({
  name,
  value,
  error,
  inputMode,
  glossary,
  onChange,
}: {
  name: FieldKey;
  value: string;
  error?: string | undefined;
  inputMode?: 'decimal' | undefined;
  glossary?: GlossaryKey | undefined;
  onChange: (v: string) => void;
}) {
  const id = useId();
  const unit = tDynamic(`page.G5.unit.${name}`, '');
  const placeholder = tDynamic(`page.G5.placeholder.${name}`, '');
  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm">
      <span className="flex items-center gap-1">
        <label htmlFor={id} className="font-medium text-fg-2">
          <PlainName name={t(`page.G5.field.${name}` as TKey)} official={fieldTerm(name)} />
        </label>
        {glossary ? <Term k={glossary} /> : null}
      </span>
      <span className="flex items-center gap-2">
        <input
          id={id}
          name={name}
          value={value}
          inputMode={inputMode}
          placeholder={placeholder || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(e) => onChange(e.target.value)}
          className={inputClass(!!error)}
        />
        {unit ? <span className="shrink-0 text-[13px] text-muted">{unit}</span> : null}
      </span>
      {error ? (
        <p id={`${id}-error`} className="m-0 text-xs font-semibold text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function CheckField({
  name,
  checked,
  onChange,
}: {
  name: 'homeless' | 'has_account';
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex min-h-11 items-center gap-3 self-end rounded-[10px] border border-border-strong px-3 text-sm font-semibold text-fg">
      <input
        type="checkbox"
        name={name}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="size-5 accent-[var(--color-accent,currentColor)]"
      />
      <PlainName name={t(`page.G5.field.${name}`)} official={fieldTerm(name)} />
    </label>
  );
}

function SelectField({
  name,
  value,
  options,
  onChange,
}: {
  name: 'purpose';
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm">
      <label htmlFor={id} className="font-medium text-fg-2">
        <PlainName name={t(`page.G5.field.${name}`)} official={fieldTerm(name)} />
      </label>
      <select
        id={id}
        name={name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`${inputClass(false)} font-semibold`}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o === '' ? t('page.G5.purpose.') : enumText('page.G5.purpose', o)}
          </option>
        ))}
      </select>
    </div>
  );
}

/** 비중 한 줄 설명 — '오를 가능성'은 이 조건의 목표 시점(policy.p10_horizon) + 당첨 확률 아님 · 보장 아님 */
function weightWhy(k: ComponentKey, scenario: Scenario | null): string {
  if (k === 'p10') {
    const target = targetText(scenario?.policy?.p10_horizon);
    return target ? t('page.G5.p10Why', { target }) : t('page.G5.p10WhyUnknown');
  }
  return tDynamic(`chart.C10.why.${k}`, '');
}

function WeightPreview({
  weights,
  onChange,
  error,
  scenario,
}: {
  weights: Weights;
  onChange: (w: Weights) => void;
  error?: string | undefined;
  scenario: Scenario | null;
}) {
  const keys = Object.keys(weights) as ComponentKey[];
  const sum = weightsSum(weights);
  const off = Math.abs(sum - 1) > 0.001;
  return (
    <fieldset
      aria-label={t('page.G5.weights')}
      className="m-0 flex min-w-0 flex-col gap-4 self-start rounded-2xl border border-border bg-subtle p-4"
    >
      <legend className="px-1 text-[15px] font-bold text-fg">
        {t('page.G5.weightsQ')}{' '}
        <span className="text-xs font-normal text-muted">({t('page.G5.weights')})</span>
      </legend>
      <p className="m-0 text-xs leading-relaxed text-fg-2">{t('page.G5.weightsHint')}</p>
      {keys.map((k) => {
        const v = weights[k] ?? 0;
        const label = tDynamic(`page.G5.weightName.${k}`, k);
        const pct = metaNumber({ n: v, as: 'prob', digits: 0 });
        return (
          <label key={k} className="flex flex-col gap-1.5 text-sm" data-weight={k}>
            <span className="flex items-baseline justify-between gap-2">
              <span className="font-semibold text-fg">{label}</span>
              <MetaText
                kind="input"
                k="page.G5.weightValue"
                params={{ pct, dec: { n: v, as: 'number', digits: 2 } }}
                className="shrink-0 text-sm font-bold text-accent-ink"
              />
            </span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={v}
              aria-label={label}
              aria-valuetext={pct}
              onChange={(e) => onChange(rebalance(weights, k, Number(e.target.value)))}
              className="w-full accent-[var(--color-accent,currentColor)]"
            />
            <span className="text-xs leading-snug text-muted">{weightWhy(k, scenario)}</span>
          </label>
        );
      })}
      <p
        className={`m-0 border-t border-border pt-3 text-[15px] font-bold ${off ? 'text-danger' : 'text-fg-2'}`}
        data-testid="weights-sum"
      >
        <MetaText
          kind="input"
          k="page.G5.weightsSum"
          params={{
            pct: { n: sum, as: 'prob', digits: 0 },
            sum: { n: sum, as: 'number', digits: 2 },
          }}
        />
      </p>
      {error ? (
        <p role="alert" className="m-0 text-xs font-semibold text-danger">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

/** N14 요건 요약 — 행 세기(D25-3): 세 요건 모두 충족 · 하나라도 미충족 · 그 밖(확인 불가·미입력 섞임) */
export function reqSummary(rows: ScenarioPreview['requirements_pre']): {
  all: number;
  anyNo: number;
  mixed: number;
} {
  const out = { all: 0, anyNo: 0, mixed: 0 };
  for (const row of rows) {
    const statuses = REQ_COLS.map((c) => row[c].status);
    if (statuses.every((s) => s === '충족')) out.all += 1;
    else if (statuses.some((s) => s === '미충족')) out.anyNo += 1;
    else out.mixed += 1;
  }
  return out;
}

const REQ_COLS = ['access', 'regulation', 'funds'] as const;
/** N15 처음 보이는 요건 표 줄 수 — 나머지는 [나머지 n곳 더 보기] */
export const REQ_FIRST_ROWS = 8;

function RequirementPreview({ scenario }: { scenario: Scenario | null }) {
  const { snapshotId } = usePageContext();
  const preview = useScenarioPreview(scenario?.id ?? null, snapshotId);
  const summary = preview.data ? reqSummary(preview.data.requirements_pre) : null;
  return (
    <AnalyzeSection
      step={4}
      title={t('page.G5.requirementsQ')}
      hint={t('page.G5.requirementsHint')}
      actions={
        summary ? (
          <span className="flex flex-wrap gap-1.5" data-testid="req-summary">
            <SummaryChip tone="accent" k="page.G5.reqSummary.all" n={summary.all} />
            <SummaryChip tone="neutral" k="page.G5.reqSummary.anyNo" n={summary.anyNo} />
            <SummaryChip tone="caution" k="page.G5.reqSummary.mixed" n={summary.mixed} />
          </span>
        ) : null
      }
    >
      {preview.data ? (
        <RequirementTable preview={preview.data} />
      ) : preview.error ? (
        <EmptyState message={queryErrorText(preview.error)} />
      ) : (
        <Skeleton lines={2} />
      )}
    </AnalyzeSection>
  );
}

function SummaryChip({
  tone,
  k,
  n,
}: {
  tone: 'accent' | 'neutral' | 'caution';
  k: TKey;
  n: number;
}) {
  const cls =
    tone === 'accent'
      ? 'bg-accent-soft text-accent-ink border-transparent'
      : tone === 'neutral'
        ? 'bg-chip text-fg-2 border-transparent'
        : 'border-dashed border-est-border text-est';
  return (
    <span className={`rounded-full border px-3 py-1 text-[13px] font-semibold ${cls}`}>
      <MetaText kind="count" k={k} params={{ n }} />
    </span>
  );
}

function RequirementTable({ preview }: { preview: ScenarioPreview }) {
  const [all, setAll] = useState(false);
  const search = useGlobalSearch();
  const rows = preview.requirements_pre;
  const shown = all ? rows : rows.slice(0, REQ_FIRST_ROWS);
  const rest = rows.length - shown.length;
  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table aria-label={t('page.G5.requirements')} className={wideTableClass}>
          <thead>
            <tr>
              <th scope="col" className={headCellClass}>
                {t('page.G5.req.complex')}{' '}
                <MetaText
                  kind="count"
                  k="page.G5.req.complexCount"
                  params={{ total: rows.length, shown: shown.length }}
                  className="text-xs font-normal text-muted"
                />
              </th>
              {REQ_COLS.map((c) => (
                <th key={c} scope="col" className={headCellClass}>
                  <PlainName name={t(`page.G5.req.${c}`)} official={t(`page.G5.reqTerm.${c}`)} />
                  <span className="mt-0.5 block text-xs font-normal text-muted">
                    {preview.requirements[c].text}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr
                key={row.complex_id}
                className={row.excluded ? 'text-grayed' : ''}
                data-excluded={row.excluded ? 'true' : undefined}
              >
                <th scope="row" className={`${cellClass} text-left font-semibold`}>
                  <span className="inline-flex flex-wrap items-center gap-1.5">
                    <Link to={`/complexes/${row.complex_id}${search}`} className="hover:underline">
                      {row.name}
                    </Link>
                    {row.excluded ? <Badge tone="muted">{t('page.G5.req.excluded')}</Badge> : null}
                  </span>
                </th>
                {REQ_COLS.map((c) => (
                  <td key={c} className={cellClass}>
                    <span className="flex flex-col items-start gap-1">
                      <ReqStatusBadge status={row[c].status} />
                      {/* 근거 문장 = 서버 문장 그대로(계약 .22: '중간 가격') */}
                      <span className="text-xs leading-snug text-muted">{row[c].evidence}</span>
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rest > 0 ? (
        <button
          type="button"
          onClick={() => setAll(true)}
          className="self-center rounded-[10px] border border-border-strong bg-surface px-4 py-2 text-sm font-semibold text-fg hover:border-fg-2"
        >
          <MetaText kind="count" k="page.G5.reqMore" params={{ n: rest }} />
        </button>
      ) : null}
      <SourceLine>
        <span data-testid="cache-hits">
          <MetaText
            kind="count"
            k="page.G5.cache"
            params={{ hits: preview.cache_hits, misses: preview.cache_misses }}
          />
        </span>{' '}
        · {t('page.G5.reqDisclaimer')}
      </SourceLine>
    </div>
  );
}

function CacheBox({ label, n, testId }: { label: string; n: number; testId: string }) {
  return (
    <span
      className="flex min-w-[96px] flex-col rounded-xl bg-subtle px-3 py-2"
      data-testid={testId}
    >
      <span className="text-xs text-muted">{label}</span>
      <MetaText
        kind="count"
        k="page.G5.cacheCount"
        params={{ n }}
        className="text-lg font-bold text-fg"
      />
    </span>
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
    <AnalyzeSection
      step={3}
      title={t('page.G5.runQ')}
      hint={t('page.G5.runHint', { name: current?.name ?? '' })}
      actions={
        <>
          {preview.data ? (
            <>
              <CacheBox
                label={t('page.G5.cacheHits')}
                n={preview.data.cache_hits}
                testId="run-cache-hits"
              />
              <CacheBox
                label={t('page.G5.cacheMisses')}
                n={preview.data.cache_misses}
                testId="run-cache-misses"
              />
            </>
          ) : null}
          <button
            type="button"
            onClick={run}
            disabled={!canWrite || !current || !snapshotId || createJob.isPending}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className={primaryButtonClass}
          >
            {t('page.G5.run')}
          </button>
        </>
      }
    >
      {jobId !== null || finished ? (
        <Card tone="info" padding="md" className="flex flex-col gap-3">
          {finished ? (
            <p role="status" className="m-0 text-sm font-bold text-info-ink" data-testid="g5-done">
              {t('page.G5.runDone')}
            </p>
          ) : (
            <p className="m-0 text-sm text-fg-2">{t('page.G5.running')}</p>
          )}
          {jobId !== null ? <JobProgress jobId={String(jobId)} onDone={onDone} /> : null}
          {finished ? (
            <p
              className="m-0 flex flex-wrap items-center justify-between gap-2 text-sm text-fg-2"
              data-testid="g5-after"
            >
              <span>
                {t('page.G5.afterRevision', {
                  snapshot: afterSnapshot ? snapshotText(afterSnapshot) : t('page.G5.afterPending'),
                })}
              </span>
              {showsOther ? (
                <button
                  type="button"
                  onClick={() => setSnapshot(afterId)}
                  className="rounded-[10px] border border-border-strong bg-surface px-3 py-1.5 text-sm font-semibold text-fg"
                >
                  {t('page.G5.openRevision')}
                </button>
              ) : null}
            </p>
          ) : null}
        </Card>
      ) : null}
      {afterError ? (
        <div
          role="alert"
          data-testid="g5-after-error"
          className="flex flex-wrap items-center gap-2 rounded-xl bg-warn-soft px-4 py-3 text-sm text-warn-ink"
        >
          <span>
            {specialErrorText(afterError) ??
              t('page.G5.afterError', { detail: afterError.message })}
          </span>
          <button
            type="button"
            onClick={() => void after.refetch()}
            disabled={after.isFetching}
            className="rounded-[10px] border border-border-strong bg-surface px-3 py-1 font-semibold text-fg disabled:opacity-50"
          >
            {t('app.retry')}
          </button>
        </div>
      ) : null}
      {finished && baseline && !afterFresh && !afterError ? (
        <p className="m-0 text-sm text-muted" data-testid="g5-after-loading">
          {t('page.G5.afterLoading')}
        </p>
      ) : null}
      {baseline && afterFresh && after.data ? (
        <DiffTable
          before={baseline.rows}
          after={after.data.top5}
          beforeSnapshotId={baseline.snapshotId}
          afterSnapshotId={afterId}
        />
      ) : null}
    </AnalyzeSection>
  );
}

function DiffHead({ children }: { children: ReactNode }) {
  return (
    <th scope="col" className={headCellClass}>
      {children}
    </th>
  );
}

/**
 * 이전 run 대비 순위·점수. 7차 M8(D15-8): '이전' 열은 기준 리비전, '이후' 열은 잡이 쓴 새 리비전의 값이다 — 숫자 셀의 출처
 * 서랍은 그 값이 나온 리비전으로 조회한다(헤더의 보고 있는 리비전이 아니라).
 */
export function DiffTable({
  before,
  after,
  beforeSnapshotId,
  afterSnapshotId,
}: {
  before: ScoreRow[];
  after: ScoreRow[];
  beforeSnapshotId?: string | null;
  afterSnapshotId?: string | null;
}) {
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
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <h3 className="m-0 text-base font-bold text-fg sm:text-[17px]">{t('page.G5.diffQ')}</h3>
        <p className="m-0 text-[13px] text-muted">{t('page.G5.diffHint')}</p>
      </div>
      {!changed ? (
        <p className="m-0 text-sm font-semibold text-fg-2">{t('page.G5.noDiff')}</p>
      ) : null}
      <div className="overflow-x-auto">
        <table aria-label={t('page.G5.diff')} className={wideTableClass}>
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
                <DiffHead key={k}>{t(`page.G5.diffCol.${k}`)}</DiffHead>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <th scope="row" className={`${cellClass} text-left font-semibold`}>
                  {r.name}
                </th>
                <td className={cellClass}>
                  {r.before?.rank != null ? (
                    <span className="inline-flex items-center gap-1">
                      <MetaValue kind="rank" value={r.before.rank} as="rank" />
                      <TieBadge tie={r.before.tie_group !== null} />
                    </span>
                  ) : (
                    t('page.common.none')
                  )}
                </td>
                <td className={cellClass}>
                  {r.after?.rank != null ? (
                    <span className="inline-flex items-center gap-1">
                      <MetaValue kind="rank" value={r.after.rank} as="rank" />
                      <TieBadge tie={r.after.tie_group !== null} />
                    </span>
                  ) : (
                    t('page.common.none')
                  )}
                </td>
                <td className={cellClass}>
                  <FactCell
                    fact={r.before?.total ?? null}
                    unit="score"
                    provSnapshotId={beforeSnapshotId}
                  />
                </td>
                <td className={cellClass}>
                  <FactCell
                    fact={r.after?.total ?? null}
                    unit="score"
                    provSnapshotId={afterSnapshotId}
                  />
                </td>
                <td className={cellClass} data-testid="diff-delta-rerank">
                  <FactCell
                    fact={r.after?.delta_rerank ?? null}
                    unit="score"
                    emptyReason={t('page.common.deltaRerankNone')}
                    provSnapshotId={afterSnapshotId}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
