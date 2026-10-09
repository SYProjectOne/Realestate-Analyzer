import { useEffect, useId, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import {
  HUMAN_CHECK_FIELDS,
  HUMAN_CHECK_NOTE_MAX,
  HUMAN_CHECK_RULES,
  HUMAN_CHECK_VALUE_MAX,
  type HumanCheckCreate8,
  type HumanCheckField,
} from '@/api/contract8';
import { useComplexes, useCreateHumanCheck, useCreateJob } from '@/api/hooks';
import { ENTERED_BY_ROLES, type EnteredByRole, type HumanCheck } from '@/api/types';
import { useToast } from '@/app/toast';
import { IntakeBadge } from '@/components';
import { t, type TKey } from '@/i18n';
import { metaText } from '@/lib/meta';
import { enumText, Section } from '../_shared';

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

/** datetime-local → ISO(로컬 시간대 오프셋 포함) */
function toIso(local: string): string {
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
}

const asField = (v: string | null): HumanCheckField =>
  v && (HUMAN_CHECK_FIELDS as readonly string[]).includes(v)
    ? (v as HumanCheckField)
    : 'intake_status';

/**
 * 값 형·범위 검사(계약 .8 HumanCheckField — 서버도 같은 규칙으로 422). 정수 필드에 '6.02'는 거부(절삭 금지,
 * 3차 리뷰 minor 11). 문제가 없으면 null.
 */
export function validateHumanValue(field: HumanCheckField, raw: string): string | null {
  const value = raw.trim();
  if (value.length > HUMAN_CHECK_VALUE_MAX) {
    return metaText('page.G7.hc.tooLong', { max: HUMAN_CHECK_VALUE_MAX });
  }
  const rule = HUMAN_CHECK_RULES[field];
  if (!rule) return null;
  if (rule.kind === 'ym') {
    return /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? null : t('page.G7.hc.badYm');
  }
  const pattern = rule.kind === 'int' ? /^-?\d+$/ : /^-?\d+(\.\d+)?$/;
  if (!pattern.test(value.replace(/,/g, ''))) {
    return rule.kind === 'int' ? t('page.G7.hc.badInt') : t('page.G7.hc.badNumber');
  }
  const n = Number(value.replace(/,/g, ''));
  if (rule.min !== undefined && n < rule.min) {
    return metaText('page.G7.hc.min', { min: rule.min });
  }
  if (rule.max !== undefined && n > rule.max) {
    return metaText('page.G7.hc.max', { max: rule.max });
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
  const createJob = useCreateJob();
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
    setError(null);
    const body: HumanCheckCreate8 = {
      complex_id: Number(complexId),
      field,
      ...(entityId !== null ? { entity_id: entityId } : {}),
      value_text: HUMAN_CHECK_RULES[field] ? value.trim().replace(/,/g, '') : value.trim(),
      kind,
      checked_at: toIso(checkedAt),
      entered_by: enteredBy,
      note: note.trim() || null,
    };
    create.mutate(body, {
      onSuccess: (result) => {
        setSaved(result);
        const suggested = result.suggested_job;
        const savedText =
          field === 'intake_status' ? t('page.G7.hc.saved') : t('page.G7.hc.savedFact');
        toast({
          message: `${savedText} · ${t('page.G7.suggestRejudge')}`,
          duration: 0,
          action: suggested
            ? {
                label: t('page.G7.rejudge'),
                onClick: () =>
                  createJob.mutate(suggested, {
                    onSuccess: () => toast({ message: t('page.G7.rejudgeQueued') }),
                  }),
              }
            : undefined,
        });
      },
    });
  };

  const rule = HUMAN_CHECK_RULES[field];
  const serverError =
    create.error instanceof ApiError ? create.error.detail : (create.error?.message ?? null);

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
        <Field label="checkedAt">
          {(id) => (
            <input
              id={id}
              type="datetime-local"
              value={checkedAt}
              onChange={(e) => setCheckedAt(e.target.value)}
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
            </span>
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
  children,
}: {
  label: string;
  wide?: boolean;
  hint?: string;
  children: (id: string, hintId: string | undefined) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={`flex flex-col gap-0.5 ${wide ? 'sm:col-span-2' : ''}`}>
      <label htmlFor={id} className="text-xs text-muted">
        {t(`page.G7.hc.${label}` as TKey)}
      </label>
      {children(id, hint ? hintId : undefined)}
      {hint ? (
        <span id={hintId} className="text-xs text-muted">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
