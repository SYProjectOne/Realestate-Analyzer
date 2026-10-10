import { useEffect, useId, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { humanCheckJobId, useComplexes, useCreateHumanCheck } from '@/api/hooks';
import {
  ENTERED_BY_ROLES,
  HUMAN_CHECK_FIELDS,
  type EnteredByRole,
  type HumanCheck,
  type HumanCheckCreate,
  type HumanCheckField,
} from '@/api/types';
import { useToast } from '@/app/toast';
import { IntakeBadge, PublishJobProgress } from '@/components';
import { t, type TKey } from '@/i18n';
import { metaText } from '@/lib/meta';
import { enumText, idText, Section } from '../_shared';
import { HUMAN_CHECK_NOTE_MAX, HUMAN_CHECK_RULES, HUMAN_CHECK_VALUE_MAX } from './humanCheckRules';

const KINDS = ['phone', 'visit', 'email'] as const;
const INTAKE_VALUES = ['가능', '미정', '확인 불가', '불가'] as const;

/** 사람 확인 폼 앵커·미리 채우기 URL 파라미터(ClaimsPanel '사람 확인으로 복원'이 쓴다) */
export const HUMAN_CHECK_ANCHOR = 'human-check';
export const HC_PARAM = { complex: 'hc_complex', field: 'hc_field', entity: 'hc_entity' } as const;

/** 강등 사실을 사람 확인으로 복원하는 폼 주소(같은 /ops, 미리 채움 + 폼으로 스크롤) */
export function humanCheckSearch(
  current: URLSearchParams,
  target: { complexId: number | null; field: HumanCheckField; entityId?: number | null },
): string {
  const next = new URLSearchParams(current);
  if (target.complexId !== null) next.set(HC_PARAM.complex, String(target.complexId));
  next.set(HC_PARAM.field, target.field);
  if (target.entityId !== null && target.entityId !== undefined) {
    next.set(HC_PARAM.entity, String(target.entityId));
  } else next.delete(HC_PARAM.entity);
  return `?${next.toString()}`;
}

/** datetime-local 기본값(현재 시각, 분 단위) */
function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

/** 서버가 받는 미래 여유(계약 .11 F7 — 지금보다 10분 넘게 미래면 422) */
export const CHECKED_AT_FUTURE_SLACK_MS = 10 * 60_000;

/** 분 단위 시간대 오프셋 → '+09:00' */
export function offsetText(offsetMinutes: number): string {
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const abs = Math.abs(offsetMinutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, '0');
  const mm = String(abs % 60).padStart(2, '0');
  return `${sign}${hh}:${mm}`;
}

/**
 * datetime-local(`YYYY-MM-DDTHH:mm[:ss]`, 브라우저 시간대) → 시간대가 붙은 RFC3339(`…:ss+09:00`, 계약 .11 F7).
 * 형식이 아니거나 없는 날짜면 null — 지금 시각으로 바꿔치지 않는다(조용한 대체 금지).
 */
export function toRfc3339(local: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local);
  if (!m) return null;
  const [, y, mo, d, h, mi, sec = '00'] = m;
  const date = new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(sec));
  if (
    Number.isNaN(date.getTime()) ||
    date.getFullYear() !== Number(y) ||
    date.getMonth() !== Number(mo) - 1 ||
    date.getDate() !== Number(d)
  ) {
    return null;
  }
  return `${y}-${mo}-${d}T${h}:${mi}:${sec}${offsetText(-date.getTimezoneOffset())}`;
}

/** 확인 시각 입력 검사: 비었거나 형식 오류 → 입력 안내, 10분 넘게 미래 → 미래 안내. 문제 없으면 null */
export function checkedAtProblem(local: string, now: number = Date.now()): string | null {
  const iso = toRfc3339(local);
  if (iso === null) return t('page.G7.hc.checkedAtRequired');
  if (Date.parse(iso) - now > CHECKED_AT_FUTURE_SLACK_MS)
    return t('page.G7.hc.checkedAtFutureLocal');
  return null;
}

const asField = (v: string | null): HumanCheckField =>
  v && (HUMAN_CHECK_FIELDS as readonly string[]).includes(v)
    ? (v as HumanCheckField)
    : 'intake_status';

/** 값 칸 정규화: 사실 필드는 천 단위 쉼표·공백을 뺀다(서버도 뺀다), 그 밖은 앞뒤 공백만 */
export function normalizeHumanValue(field: HumanCheckField, raw: string): string {
  const value = raw.trim();
  return HUMAN_CHECK_RULES[field] ? value.replace(/[,\s]/g, '') : value;
}

/**
 * 값 형·범위 검사 — 서버 허용 범위(계약 .8, `app/api/demotion.py` parse_human_value)와 같다: 최고 공급금액
 * 1,000만~1,000억 원 정수, 입주 2000-01~2100-12, 개월 0~240 정수, 계약금 0~100 소수 둘째 자리까지.
 * 정수 필드에 '6.02'는 거부(절삭 금지, 3차 리뷰 minor 11). 문제가 없으면 null.
 */
export function validateHumanValue(field: HumanCheckField, raw: string): string | null {
  if (raw.trim().length > HUMAN_CHECK_VALUE_MAX) {
    return metaText('page.G7.hc.tooLong', { max: HUMAN_CHECK_VALUE_MAX });
  }
  const rule = HUMAN_CHECK_RULES[field];
  if (!rule) return null;
  const value = normalizeHumanValue(field, raw);
  if (rule.kind === 'ym') {
    const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(value);
    if (!m) return t('page.G7.hc.badYm');
    const year = Number(m[1]);
    const outside =
      (rule.min !== undefined && year < rule.min) || (rule.max !== undefined && year > rule.max);
    return outside ? t('page.G7.hc.badYmRange') : null;
  }
  const pattern = rule.kind === 'int' ? /^-?\d+$/ : /^-?\d+(\.\d+)?$/;
  if (!pattern.test(value)) {
    return rule.kind === 'int' ? t('page.G7.hc.badInt') : t('page.G7.hc.badNumber');
  }
  const decimals = value.split('.')[1]?.length ?? 0;
  if (rule.decimals !== undefined && decimals > rule.decimals) {
    return metaText('page.G7.hc.decimals', { n: rule.decimals });
  }
  const n = Number(value);
  const as = rule.unit;
  if (rule.min !== undefined && n < rule.min) {
    return metaText('page.G7.hc.min', { min: as ? { n: rule.min, as } : rule.min });
  }
  if (rule.max !== undefined && n > rule.max) {
    return metaText('page.G7.hc.max', { max: as ? { n: rule.max, as } : rule.max });
  }
  return null;
}

/**
 * G7 HumanCheckForm — 단지·필드·값·종류·메모 → POST /ops/human-checks.
 * 필드(계약 .8, M-5): 접수 상태 + 강등 가능한 사실 필드 5개(최고 공급금액·입주 예정·전매·거주의무 개월·계약금 %)
 * + 기타. 사실 필드의 사람 확인은 resolver 0순위 후보가 되어 같은 사실의 강등(검증 모순)을 복원한다(D11-3).
 * 접수 상태 저장 → 접수 배지 즉시 갱신(응답 created_intake + 쿼리 무효화) + "재판정 잡 등록" 제안 토스트.
 * ClaimsPanel 의 '사람 확인으로 복원'이 URL(hc_complex·hc_field·hc_entity)로 미리 채운다.
 */
export function HumanCheckForm({ snapshotId }: { snapshotId: string | null }) {
  const complexes = useComplexes(snapshotId, { page: 1, size: 1000, sort: 'name' });
  const create = useCreateHumanCheck();
  const canWrite = useCanWrite();
  const toast = useToast();
  const [params] = useSearchParams();
  const [complexId, setComplexId] = useState(() => params.get(HC_PARAM.complex) ?? '');
  const [field, setField] = useState<HumanCheckField>(() => asField(params.get(HC_PARAM.field)));
  const [entityId, setEntityId] = useState<number | null>(() => {
    const v = params.get(HC_PARAM.entity);
    return v && /^\d+$/.test(v) ? Number(v) : null;
  });
  const [value, setValue] = useState('');
  const [kind, setKind] = useState<(typeof KINDS)[number]>('phone');
  const [checkedAt, setCheckedAt] = useState(nowLocal);
  const [enteredBy, setEnteredBy] = useState<EnteredByRole | ''>('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checkedAtLocalError, setCheckedAtLocalError] = useState<string | null>(null);
  /** 마지막으로 보낸 checked_at(서버 422 가 미래 때문인지 이른 확인일 때문인지 가른다) */
  const [sentAt, setSentAt] = useState<string | null>(null);
  const [saved, setSaved] = useState<HumanCheck | null>(null);

  // 같은 화면에서 '사람 확인으로 복원' 링크를 누르면 URL 만 바뀐다 → 폼을 그 값으로 다시 채운다
  const preComplex = params.get(HC_PARAM.complex);
  const preField = params.get(HC_PARAM.field);
  const preEntity = params.get(HC_PARAM.entity);
  useEffect(() => {
    if (preField === null && preComplex === null) return;
    if (preComplex !== null) setComplexId(preComplex);
    setField(asField(preField));
    setEntityId(preEntity && /^\d+$/.test(preEntity) ? Number(preEntity) : null);
    setValue('');
    setError(null);
  }, [preComplex, preField, preEntity]);

  const submit = () => {
    if (!complexId || !value.trim() || !enteredBy) {
      setError(t('page.G7.hc.required'));
      return;
    }
    const invalid = validateHumanValue(field, value);
    if (invalid) {
      setError(invalid);
      return;
    }
    if (note.length > HUMAN_CHECK_NOTE_MAX) {
      setError(metaText('page.G7.hc.noteTooLong', { max: HUMAN_CHECK_NOTE_MAX }));
      return;
    }
    const timeProblem = checkedAtProblem(checkedAt);
    setCheckedAtLocalError(timeProblem);
    if (timeProblem) {
      setError(null);
      return;
    }
    const checkedAtIso = toRfc3339(checkedAt) as string;
    setError(null);
    setSentAt(checkedAtIso);
    const body: HumanCheckCreate = {
      complex_id: Number(complexId),
      field,
      ...(entityId !== null ? { entity_id: entityId } : {}),
      value_text: normalizeHumanValue(field, value),
      kind,
      checked_at: checkedAtIso,
      entered_by: enteredBy,
      note: note.trim() || null,
    };
    create.mutate(body, {
      onSuccess: (result) => {
        setSaved(result);
        // 계약 .9(D12-5): 서버가 재판정 잡을 자동 등록한다(rejudge_job_id) — suggested_job 을 다시 POST 하지 않고
        // 그 잡의 진행만 보인다. 끝나면 api/jobWatch 가 지역·리비전·사실 화면을 무효화한다.
        const savedText =
          field === 'intake_status' ? t('page.G7.hc.saved') : t('page.G7.hc.savedFact');
        const jobId = humanCheckJobId(result);
        toast({
          message:
            jobId !== null
              ? `${savedText} · ${t('page.G7.hc.rejudgeAuto', { id: idText(jobId) })}`
              : savedText,
        });
      },
    });
  };

  const rule = HUMAN_CHECK_RULES[field];
  // 계약 .10 S6·.11 F7·F8: checked_at 422 — loc ["body","checked_at"]. 이른 확인일(이미 수집된 공고가 **다른 값**)
  // 또는 10분 넘는 미래. 확인 시각 칸의 오류로 보인다(조용히 지는 사람 확인 금지). 보낸 시각이 지금보다 뒤면 미래 안내
  const serverCheckedAt =
    create.error instanceof ApiError && create.error.status === 422
      ? (create.error.fieldErrors.find((f) => f.loc[f.loc.length - 1] === 'checked_at')?.msg ??
        null)
      : null;
  const serverSaysFuture = sentAt !== null && Date.parse(sentAt) > Date.now();
  const checkedAtError =
    checkedAtLocalError ??
    (serverCheckedAt
      ? serverSaysFuture
        ? t('page.G7.hc.checkedAtFuture', { detail: serverCheckedAt })
        : t('page.G7.hc.checkedAtTooEarly', { detail: serverCheckedAt })
      : null);
  const serverError = serverCheckedAt
    ? null
    : create.error instanceof ApiError
      ? create.error.detail
      : (create.error?.message ?? null);

  return (
    <Section title={t('page.G7.human')} id={HUMAN_CHECK_ANCHOR}>
      <p className="text-xs text-muted">{t('page.G7.humanIntro')}</p>
      <form
        aria-label={t('page.G7.human')}
        noValidate
        data-write
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <Field label="complex">
          {(id) => (
            <select
              id={id}
              value={complexId}
              onChange={(e) => {
                setComplexId(e.target.value);
                setEntityId(null);
              }}
              className={inputClass}
            >
              <option value="">{t('page.common.none')}</option>
              {(complexes.data?.items ?? []).map((c) => (
                <option key={c.complex_id} value={c.complex_id}>
                  {c.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="field">
          {(id) => (
            <select
              id={id}
              value={field}
              onChange={(e) => {
                setField(asField(e.target.value));
                setEntityId(null);
                setValue('');
                setError(null);
              }}
              className={inputClass}
            >
              {HUMAN_CHECK_FIELDS.map((f) => (
                <option key={f} value={f}>
                  {enumText('page.G7.hcField', f)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="value" hint={rule ? t(`page.G7.hcHint.${field}` as TKey) : undefined}>
          {(id, hintId) =>
            field === 'intake_status' ? (
              <select
                id={id}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className={inputClass}
              >
                <option value="">{t('page.common.none')}</option>
                {INTAKE_VALUES.map((v) => (
                  <option key={v} value={v}>
                    {enumText('intake.status', v)}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={id}
                type={rule?.kind === 'ym' ? 'month' : 'text'}
                inputMode={rule && rule.kind !== 'ym' ? 'decimal' : undefined}
                value={value}
                maxLength={HUMAN_CHECK_VALUE_MAX}
                aria-describedby={hintId}
                onChange={(e) => setValue(e.target.value)}
                className={inputClass}
              />
            )
          }
        </Field>
        <Field label="kind">
          {(id) => (
            <select
              id={id}
              value={kind}
              onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}
              className={inputClass}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {enumText('page.G7.hcKind', k)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label="checkedAt"
          error={checkedAtError ?? undefined}
          hint={t('page.G7.hc.checkedAtTz', { tz: offsetText(-new Date().getTimezoneOffset()) })}
        >
          {(id, hintId) => (
            <input
              id={id}
              type="datetime-local"
              value={checkedAt}
              onChange={(e) => {
                setCheckedAt(e.target.value);
                setCheckedAtLocalError(null);
              }}
              aria-invalid={checkedAtError ? true : undefined}
              aria-describedby={hintId}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="enteredBy">
          {(id) => (
            <select
              id={id}
              value={enteredBy}
              onChange={(e) => setEnteredBy(e.target.value as EnteredByRole | '')}
              className={inputClass}
            >
              <option value="">{t('page.common.none')}</option>
              {ENTERED_BY_ROLES.map((role) => (
                <option key={role} value={role}>
                  {enumText('page.G7.hcRole', role)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="note" wide hint={t('page.G7.hc.noteHint')}>
          {(id, hintId) => (
            <textarea
              id={id}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={HUMAN_CHECK_NOTE_MAX}
              aria-describedby={hintId}
              rows={2}
              className={inputClass}
            />
          )}
        </Field>
        {entityId !== null ? (
          <p className="text-xs text-muted sm:col-span-2" data-testid="hc-entity">
            {t('page.G7.hc.entityPinned')}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
          <button
            type="submit"
            disabled={!canWrite || create.isPending}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
          >
            {t('page.G7.hc.submit')}
          </button>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}
          {serverError ? (
            <p role="alert" className="text-sm text-danger">
              {t('page.common.loadError', { detail: serverError })}
            </p>
          ) : null}
          {saved?.created_intake ? (
            <span
              className="inline-flex items-center gap-1 text-sm"
              data-testid="human-check-result"
            >
              <span className="text-muted">{t('page.G7.hc.latest')}</span>
              <IntakeBadge intake={saved.created_intake} />
            </span>
          ) : saved ? (
            <span className="text-sm" data-testid="human-check-result">
              {t('page.G7.hc.factSaved', {
                field: enumText('page.G7.hcField', saved.field),
                value: saved.value_text,
              })}
              {saved.entity ? (
                // 서버가 정한 사실 행(계약 .8 HumanCheck.entity·entity_id) — 번호는 행 id(비수치 메타)
                <span className="ml-1 text-xs text-muted" data-testid="human-check-target">
                  {t('page.G7.hc.target', {
                    entity: enumText('page.G7.hcEntity', saved.entity),
                    id: idText(saved.entity_id),
                  })}
                </span>
              ) : null}
            </span>
          ) : null}
          {saved ? (
            <div className="w-full" data-testid="human-check-job">
              {humanCheckJobId(saved) !== null ? (
                // 계약 .11 F6: 201 + job_id(rejudge) — 새 리비전 발행까지 지금 발행 리비전이 기본
                <PublishJobProgress jobId={humanCheckJobId(saved) as number} />
              ) : (
                <p className="text-xs text-muted">{t('page.G7.hc.noRejudge')}</p>
              )}
            </div>
          ) : null}
        </div>
      </form>
    </Section>
  );
}

const inputClass = 'w-full rounded-sm border border-border bg-surface px-2 py-1 text-sm';

function Field({
  label,
  wide = false,
  hint,
  error,
  children,
}: {
  label: string;
  wide?: boolean;
  hint?: string;
  /** 서버 검증 오류(그 칸) — 힌트 자리에 경고로 */
  error?: string;
  children: (id: string, hintId: string | undefined) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const text = error ?? hint;
  return (
    <div className={`flex flex-col gap-0.5 ${wide ? 'sm:col-span-2' : ''}`}>
      <label htmlFor={id} className="text-xs text-muted">
        {t(`page.G7.hc.${label}` as TKey)}
      </label>
      {children(id, text ? hintId : undefined)}
      {text ? (
        <span
          id={hintId}
          role={error ? 'alert' : undefined}
          className={`text-xs ${error ? 'text-danger' : 'text-muted'}`}
        >
          {text}
        </span>
      ) : null}
    </div>
  );
}
