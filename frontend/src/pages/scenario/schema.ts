/** G5 ScenarioForm — zod 검증(10 필드 + 이름 + 가중치 합 1) */
import { z } from 'zod';
import type { ComponentKey, Scenario, ScenarioCreate, ScenarioParams, Weights } from '@/api/types';
import { t } from '@/i18n';
import { metaText } from '@/lib/meta';

const EOK = 100_000_000;
export const WEIGHT_TOLERANCE = 0.001;

/** 폼 입력 값(전부 문자열/불리언 — input 그대로) */
export interface ScenarioFormValues {
  name: string;
  residence: string;
  homeless: boolean;
  household_size: string;
  has_account: boolean;
  score: string;
  equity_won: string;
  loan_limit_won: string;
  purpose: '' | '실거주' | '시세차익' | '병행';
  holding_years: string;
  preferred_area_m2: string;
  move_in_by: string;
}

const blankToUndefined = (v: unknown) => (typeof v === 'string' && v.trim() === '' ? undefined : v);

function optionalNumber(min: number, max: number, int = false) {
  let n = z.coerce.number({
    invalid_type_error: int ? t('page.G5.error.number') : t('page.G5.error.numberAny'),
  });
  if (int) n = n.int(t('page.G5.error.number'));
  return z.preprocess(
    blankToUndefined,
    n
      .min(min, metaText('page.G5.error.min', { min: { n: min, as: 'number' } }))
      .max(max, metaText('page.G5.error.max', { max: { n: max, as: 'number' } }))
      .optional(),
  );
}

export const formSchema = z.object({
  name: z.string().trim().min(1, t('page.G5.error.required')),
  residence: z.string().trim(),
  homeless: z.boolean(),
  household_size: optionalNumber(1, 20, true),
  has_account: z.boolean(),
  score: optionalNumber(0, 84, true),
  equity_won: optionalNumber(0, 1000),
  loan_limit_won: optionalNumber(0, 1000),
  purpose: z.enum(['', '실거주', '시세차익', '병행']),
  holding_years: optionalNumber(0, 50, true),
  preferred_area_m2: optionalNumber(10, 300),
  move_in_by: z
    .string()
    .trim()
    .refine((v) => v === '' || /^\d{4}-(0[1-9]|1[0-2])$/.test(v), t('page.G5.error.ym')),
});

export type ParsedForm = z.infer<typeof formSchema>;

export function weightsSum(weights: Weights): number {
  return Object.values(weights).reduce<number>((s, v) => s + (v ?? 0), 0);
}

export const weightsSchema = z
  .record(z.number().min(0).max(1))
  .refine((w) => Math.abs(Object.values(w).reduce((s, v) => s + v, 0) - 1) <= WEIGHT_TOLERANCE, {
    message: 'sum',
  });

export type FieldErrors = Partial<Record<keyof ScenarioFormValues | 'weights', string>>;

/** 검증 → 계약 ScenarioCreate. 실패하면 필드별 메시지 */
export function toScenarioCreate(
  values: ScenarioFormValues,
  weights: Weights,
  base: Scenario | null,
): { ok: true; body: ScenarioCreate } | { ok: false; errors: FieldErrors } {
  const errors: FieldErrors = {};
  const parsed = formSchema.safeParse(values);
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      const key = issue.path[0] as keyof ScenarioFormValues;
      errors[key] ??= issue.message;
    }
  }
  if (!weightsSchema.safeParse(weights).success) {
    errors.weights = metaText('page.G5.error.weightsSum', {
      sum: { n: weightsSum(weights), as: 'prob', digits: 0 },
    });
  }
  if (!parsed.success || errors.weights) return { ok: false, errors };
  const v = parsed.data;
  const params: ScenarioParams = {
    residence: v.residence || null,
    homeless: v.homeless,
    household_size: v.household_size ?? null,
    subscription: { has_account: v.has_account, score: v.score ?? null },
    equity_won: v.equity_won === undefined ? null : Math.round(v.equity_won * EOK),
    loan_limit_won: v.loan_limit_won === undefined ? null : Math.round(v.loan_limit_won * EOK),
    purpose: v.purpose === '' ? null : v.purpose,
    holding_years: v.holding_years ?? null,
    preferred_area_m2: v.preferred_area_m2 ?? null,
    move_in_by: v.move_in_by || null,
    rewin_restricted: base?.params.rewin_restricted ?? null,
    accepts_residency_obligation: base?.params.accepts_residency_obligation ?? null,
  };
  return {
    ok: true,
    body: {
      name: v.name,
      params,
      weights,
      requirements: base?.requirements ?? null,
      policy: base?.policy ?? null,
    },
  };
}

const str = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n));
const eok = (won: number | null | undefined) =>
  won === null || won === undefined ? '' : String(Math.round((won / EOK) * 100) / 100);

/** 시나리오 → 폼 초기값 */
export function fromScenario(s: Scenario | null, name: string): ScenarioFormValues {
  const p = s?.params ?? {};
  return {
    name,
    residence: p.residence ?? '',
    homeless: p.homeless ?? false,
    household_size: str(p.household_size),
    has_account: p.subscription?.has_account ?? false,
    score: str(p.subscription?.score),
    equity_won: eok(p.equity_won),
    loan_limit_won: eok(p.loan_limit_won),
    purpose: p.purpose ?? '',
    holding_years: str(p.holding_years),
    preferred_area_m2: str(p.preferred_area_m2),
    move_in_by: p.move_in_by ?? '',
  };
}

/**
 * 가중치 합 1 제약: 한 성분을 v로 바꾸면 나머지를 기존 비율대로 (1 − v)에 맞춘다.
 * 나머지가 모두 0이면 균등 분배. 소수 4자리로 맞추고 반올림 오차는 가장 큰 성분이 흡수한다.
 */
export function rebalance(weights: Weights, key: ComponentKey, value: number): Weights {
  const keys = Object.keys(weights) as ComponentKey[];
  const v = Math.min(1, Math.max(0, value));
  const others = keys.filter((k) => k !== key);
  const otherSum = others.reduce((s, k) => s + (weights[k] ?? 0), 0);
  const rest = 1 - v;
  const next: Partial<Record<ComponentKey, number>> = { [key]: round4(v) };
  for (const k of others) {
    const share = otherSum > 0 ? (weights[k] ?? 0) / otherSum : 1 / others.length;
    next[k] = round4(rest * share);
  }
  const drift = round4(1 - Object.values(next).reduce((s, x) => s + (x ?? 0), 0));
  if (drift !== 0 && others.length > 0) {
    const largest = others.reduce((a, b) => ((next[a] ?? 0) >= (next[b] ?? 0) ? a : b));
    next[largest] = round4((next[largest] ?? 0) + drift);
  }
  return next as Weights;
}

function round4(n: number): number {
  return Math.round(n * 10_000) / 10_000;
}
