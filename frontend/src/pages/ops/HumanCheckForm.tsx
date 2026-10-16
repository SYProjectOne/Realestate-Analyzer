import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { useLocation, useSearchParams } from 'react-router';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { humanCheckJobId, useComplexDetail, useComplexes, useCreateHumanCheck } from '@/api/hooks';
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
import { enumText, idText } from '../_shared';
import {
  HC_PARAM,
  HUMAN_CHECK_ANCHOR,
  HUMAN_CHECK_NOTE_MAX,
  HUMAN_CHECK_RULES,
  HUMAN_CHECK_VALUE_MAX,
  HUMAN_NUMBER_UNITS,
  parseStrictNumber,
} from './humanCheckRules';
import { OpsSection } from './sections';

const KINDS = ['phone', 'visit', 'email'] as const;
const INTAKE_VALUES = ['가능', '미정', '확인 불가', '불가'] as const;

export { HC_PARAM, HUMAN_CHECK_ANCHOR };

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
  // new Date(y, …) 는 0~99 년을 1900 년대로 바꾼다 — 연도는 setFullYear 로(0001 년 입력이 1901 년이 되지 않게)
  const date = new Date(2000, 0, 1, 0, 0, 0);
  date.setFullYear(Number(y), Number(mo) - 1, Number(d));
  date.setHours(Number(h), Number(mi), Number(sec), 0);
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

/** 서버가 받는 가장 이른 확인 시각(계약 .12 F8 — KST 2000-01-01) */
export const CHECKED_AT_MIN_MS = Date.parse('2000-01-01T00:00:00+09:00');

/**
 * 확인 시각 입력 검사 — **형식만**(8차 m17): 비었거나 형식 오류 → 입력 안내, KST 2000-01-01 이전 → 범위 안내(F8, 고정
 * 상수). 미래 여부는 브라우저 시계로 판단하지 않는다 — 서버가 자기 시계로 보고 422 `checked_at_future` 로 알린다(F14).
 * 문제 없으면 null
 */
export function checkedAtProblem(local: string): string | null {
  const iso = toRfc3339(local);
  if (iso === null) return t('page.G7.hc.checkedAtRequired');
  if (Date.parse(iso) < CHECKED_AT_MIN_MS) return t('page.G7.hc.checkedAtTooOld');
  return null;
}

/**
 * 사람 확인 POST 422 의 checked_at 오류 종류 — 계약 .12 F14: 서버 code 로만 가른다(문구·브라우저 시계로 추측하지 않는다,
 * 7차 minor 20). `checked_at_format` = 형식·KST 2000-01-01 이전·overflow, `checked_at_future` = 서버 지금 + 10분 넘는 미래,
 * `checked_at_before_source` = 그 뒤에 관측된 공식 공고가 다른 값. 그 밖의 checked_at 422(`validation_error`)는 other,
 * checked_at 오류가 아니면 null.
 */
export function checkedAt422Kind(error: unknown): 'future' | 'early' | 'format' | 'other' | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  switch (error.code) {
    case 'checked_at_future':
      return 'future';
    case 'checked_at_before_source':
      return 'early';
    case 'checked_at_format':
      return 'format';
    default:
      return error.fieldErrors.some((f) => f.loc[f.loc.length - 1] === 'checked_at')
        ? 'other'
        : null;
  }
}

/** 폼 칸 */
type FormField = 'complex' | 'field' | 'value' | 'kind' | 'checkedAt' | 'enteredBy' | 'note';
type FieldErrors = Partial<Record<FormField, string>>;

/** 서버 422 field_errors loc 마지막 이름 → 폼 칸(그 밖은 일반 오류 줄) */
const SERVER_FIELD: Readonly<Record<string, FormField>> = {
  complex_id: 'complex',
  field: 'field',
  value_text: 'value',
  kind: 'kind',
  checked_at: 'checkedAt',
  entered_by: 'enteredBy',
  note: 'note',
};

/**
 * 사람 확인 POST 오류 → 칸별 오류 + 일반 오류 줄(8차 m17 — 여러 칸이 틀리면 **모든 칸**과 detail 을 보인다).
 * checked_at 은 서버 code 로 문구를 고른다(F14). detail 이 어느 칸 문구와 똑같으면 일반 줄에 다시 쓰지 않는다.
 */
export function humanCheckServerErrors(error: unknown): { fields: FieldErrors; general: string[] } {
  if (!error) return { fields: {}, general: [] };
  if (!(error instanceof ApiError)) {
    const detail = error instanceof Error ? error.message : String(error);
    return { fields: {}, general: [t('page.G7.hc.serverError', { detail })] };
  }
  const byField: Partial<Record<FormField, string[]>> = {};
  const unmapped: string[] = [];
  for (const fe of error.fieldErrors) {
    const target = SERVER_FIELD[String(fe.loc[fe.loc.length - 1] ?? '')];
    if (target) (byField[target] ??= []).push(fe.msg);
    else unmapped.push(fe.msg);
  }
  const fields: FieldErrors = {};
  for (const [name, msgs] of Object.entries(byField) as [FormField, string[]][]) {
    fields[name] = msgs.join(' · ');
  }
  // 계약 .14 F3(R3i m2): 할인 값만 틀리면 code 로 — 형식·범위 / 기준 타입 차감 바탕 이상
  if (error.code === 'discount_format' || error.code === 'discount_not_below_price') {
    const detail = fields.value ?? error.detail;
    fields.value =
      error.code === 'discount_format'
        ? t('page.G7.hc.discountFormat', { detail })
        : t('page.G7.hc.discountNotBelowPrice', { detail });
  }
  const kind = checkedAt422Kind(error);
  if (kind !== null) {
    const detail = fields.checkedAt ?? error.detail;
    fields.checkedAt =
      kind === 'future'
        ? t('page.G7.hc.checkedAtFuture', { detail })
        : kind === 'early'
          ? t('page.G7.hc.checkedAtTooEarly', { detail })
          : kind === 'format'
            ? t('page.G7.hc.checkedAtFormat', { detail })
            : t('page.G7.hc.checkedAtServer', { detail });
  }
  const raw = new Set(error.fieldErrors.map((fe) => fe.msg));
  const general = [
    ...(error.detail && !raw.has(error.detail)
      ? [t('page.G7.hc.serverError', { detail: error.detail })]
      : []),
    ...unmapped,
  ];
  if (general.length === 0 && Object.keys(fields).length === 0) {
    general.push(t('page.G7.hc.serverError', { detail: error.detail || error.code }));
  }
  return { fields, general };
}

const asField = (v: string | null): HumanCheckField =>
  v && (HUMAN_CHECK_FIELDS as readonly string[]).includes(v)
    ? (v as HumanCheckField)
    : 'intake_status';

/**
 * 값 칸 정규화: 앞뒤 공백만 뗀다. 계약 .14 F3·F4: 서버가 엄격하게 읽으므로(쉼표 세 자리마다·숫자 사이 공백 없음) 화면이
 * 쉼표·공백을 지워 고쳐 쓰지 않는다 — 그러면 '1,0' 이 10 으로 들어간다(9차 m2).
 */
export function normalizeHumanValue(_field: HumanCheckField, raw: string): string {
  return raw.trim();
}

/**
 * 값 형·범위 검사 — 서버(`app/api/demotion.py` parse_human_value, 계약 .14 F3·F4)와 같다: 엄격한 숫자 형식(ASCII 숫자,
 * 쉼표는 세 자리마다, 숫자 사이 공백 없음, 그 필드 단위만 — 앞 공백 한 칸까지, 할인은 공백 없음), 음수 거절, 최고 공급금액
 * 1,000만~1,000억 원 정수, 할인 0~1,000억 원 정수, 입주 2000-01~2100-12, 개월 0~240 정수('N년' = N×12), 계약금 0~100 소수
 * 둘째 자리까지. 정수 필드에 '6.02'는 거부(절삭 금지, 3차 리뷰 minor 11). 문제가 없으면 null.
 */
export function validateHumanValue(field: HumanCheckField, raw: string): string | null {
  if (raw.trim().length > HUMAN_CHECK_VALUE_MAX) {
    return metaText('page.G7.hc.tooLong', { max: HUMAN_CHECK_VALUE_MAX });
  }
  const rule = HUMAN_CHECK_RULES[field];
  if (!rule) return null;
  const value = normalizeHumanValue(field, raw);
  if (rule.kind === 'ym') {
    // 서버도 연월은 공백을 지우고 읽는다
    const m = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(value.replace(/ /g, ''));
    if (!m) return t('page.G7.hc.badYm');
    const year = Number(m[1]);
    const outside =
      (rule.min !== undefined && year < rule.min) || (rule.max !== undefined && year > rule.max);
    return outside ? t('page.G7.hc.badYmRange') : null;
  }
  const parsed = parseStrictNumber(field, value);
  const as = rule.unit;
  if (!parsed.ok && parsed.reason === 'format') {
    return field === 'discount'
      ? t('page.G7.hc.badDiscountFormat')
      : t('page.G7.hc.badFormat', {
          units: (HUMAN_NUMBER_UNITS[field] ?? []).join(' · ') || t('page.G7.hc.noUnit'),
        });
  }
  if (!parsed.ok) {
    // 음수('-0' 포함) — 받는 필드가 없다(서버도 범위 오류)
    return metaText('page.G7.hc.min', { min: as ? { n: rule.min ?? 0, as } : (rule.min ?? 0) });
  }
  if (rule.kind === 'int' && parsed.decimals > 0) return t('page.G7.hc.badInt');
  const n = parsed.value;
  if (rule.min !== undefined && n < rule.min) {
    return metaText('page.G7.hc.min', { min: as ? { n: rule.min, as } : rule.min });
  }
  if (rule.max !== undefined && n > rule.max) {
    return metaText('page.G7.hc.max', { max: as ? { n: rule.max, as } : rule.max });
  }
  if (rule.decimals !== undefined && parsed.decimals > rule.decimals) {
    return metaText('page.G7.hc.decimals', { n: rule.decimals });
  }
  return null;
}

/**
 * G7 HumanCheckForm — 단지·필드·값·종류·메모 → POST /ops/human-checks.
 * 필드(계약 .8, M-5): 접수 상태 + 강등 가능한 사실 필드 5개(최고 공급금액·입주 예정·전매·거주의무 개월·계약금 %)
 * + 할인(계약 .13 F1·D16-1, 기준 타입 원 — 값 검사는 서버 422 value_text 를 값 칸에)
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
  /** 제출 전 검사의 칸별 오류(여러 칸을 한 번에 — 8차 m17) */
  const [localErrors, setLocalErrors] = useState<FieldErrors>({});
  const clearLocal = (name: FormField) =>
    setLocalErrors((prev) => {
      if (!(name in prev)) return prev;
      const next = { ...prev };
      delete next[name];
      return next;
    });
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
    setLocalErrors({});
  }, [preComplex, preField, preEntity]);

  // 다른 화면(G3 '추정' 할인 링크 — 계약 .13 F2)에서 `#human-check` 로 들어오면 폼으로 한 번 옮긴다(라우터는 해시로 스크롤하지 않는다)
  const { hash } = useLocation();
  const scrolled = useRef(false);
  useEffect(() => {
    if (scrolled.current || hash !== `#${HUMAN_CHECK_ANCHOR}`) return;
    scrolled.current = true;
    const form = document.getElementById(HUMAN_CHECK_ANCHOR);
    if (form && typeof form.scrollIntoView === 'function') form.scrollIntoView({ block: 'start' });
  }, [hash]);

  const submit = () => {
    // 8차 m17: 첫 오류에서 멈추지 않고 모든 칸을 검사해 한 번에 보인다
    const missing = !complexId || !value.trim() || !enteredBy;
    const problems: FieldErrors = {};
    if (value.trim()) {
      const invalid = validateHumanValue(field, value);
      if (invalid) problems.value = invalid;
    }
    if (note.length > HUMAN_CHECK_NOTE_MAX) {
      problems.note = metaText('page.G7.hc.noteTooLong', { max: HUMAN_CHECK_NOTE_MAX });
    }
    const timeProblem = checkedAtProblem(checkedAt);
    if (timeProblem) problems.checkedAt = timeProblem;
    setError(missing ? t('page.G7.hc.required') : null);
    setLocalErrors(problems);
    if (missing || Object.keys(problems).length > 0) {
      // 이전 저장 시도의 서버 오류는 지금 입력과 맞지 않는다
      create.reset();
      return;
    }
    const checkedAtIso = toRfc3339(checkedAt) as string;
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
  // 계약 .14 F2(D17-4): 사람 확인 할인은 기준 타입에 들어간다 — 입력 전부터 단지 상세의 기준 타입을 보인다
  const detail = useComplexDetail(field === 'discount' && complexId ? complexId : null, snapshotId);
  const basisType = detail.data?.price.basis_type_code ?? null;
  const valueHint =
    field === 'discount'
      ? basisType
        ? t('page.G7.hcHint.discountBasis', { type: basisType })
        : t('page.G7.hcHint.discount')
      : rule
        ? t(`page.G7.hcHint.${field}` as TKey)
        : undefined;
  // 계약 .10 S6·.11 F7·F8: checked_at 422 — loc ["body","checked_at"]. 이른 확인일(이미 수집된 공고가 **다른 값**)
  // 또는 10분 넘는 미래 또는 형식. 확인 시각 칸의 오류로 보인다(조용히 지는 사람 확인 금지). 종류는 서버 code 로(.12 F14)
  // 8차 m17: 다른 칸 오류·detail 도 함께(칸별 + 일반 줄)
  const server = humanCheckServerErrors(create.error);
  const errorOf = (name: FormField): string | undefined => localErrors[name] ?? server.fields[name];
  const invalidOf = (name: FormField): true | undefined => (errorOf(name) ? true : undefined);

  return (
    <OpsSection k="human">
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
        <Field label="complex" error={errorOf('complex')}>
          {(id, hintId) => (
            <select
              id={id}
              value={complexId}
              aria-invalid={invalidOf('complex')}
              aria-describedby={hintId}
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
        <Field label="field" error={errorOf('field')}>
          {(id, hintId) => (
            <select
              id={id}
              value={field}
              aria-invalid={invalidOf('field')}
              aria-describedby={hintId}
              onChange={(e) => {
                setField(asField(e.target.value));
                setEntityId(null);
                setValue('');
                setError(null);
                clearLocal('value');
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
        <Field label="value" hint={valueHint} error={errorOf('value')}>
          {(id, hintId) =>
            field === 'intake_status' ? (
              <select
                id={id}
                value={value}
                aria-invalid={invalidOf('value')}
                aria-describedby={hintId}
                onChange={(e) => {
                  setValue(e.target.value);
                  clearLocal('value');
                }}
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
                inputMode={
                  field === 'discount'
                    ? 'numeric'
                    : rule && rule.kind !== 'ym'
                      ? 'decimal'
                      : undefined
                }
                value={value}
                maxLength={HUMAN_CHECK_VALUE_MAX}
                aria-invalid={invalidOf('value')}
                aria-describedby={hintId}
                onChange={(e) => {
                  setValue(e.target.value);
                  clearLocal('value');
                }}
                className={inputClass}
              />
            )
          }
        </Field>
        <Field label="kind" error={errorOf('kind')}>
          {(id, hintId) => (
            <select
              id={id}
              value={kind}
              aria-invalid={invalidOf('kind')}
              aria-describedby={hintId}
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
          error={errorOf('checkedAt')}
          hint={t('page.G7.hc.checkedAtTz', { tz: offsetText(-new Date().getTimezoneOffset()) })}
        >
          {(id, hintId) => (
            <input
              id={id}
              type="datetime-local"
              value={checkedAt}
              onChange={(e) => {
                setCheckedAt(e.target.value);
                clearLocal('checkedAt');
              }}
              aria-invalid={invalidOf('checkedAt')}
              aria-describedby={hintId}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="enteredBy" error={errorOf('enteredBy')}>
          {(id, hintId) => (
            <select
              id={id}
              value={enteredBy}
              aria-invalid={invalidOf('enteredBy')}
              aria-describedby={hintId}
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
        <Field label="note" wide hint={t('page.G7.hc.noteHint')} error={errorOf('note')}>
          {(id, hintId) => (
            <textarea
              id={id}
              value={note}
              onChange={(e) => {
                setNote(e.target.value);
                clearLocal('note');
              }}
              maxLength={HUMAN_CHECK_NOTE_MAX}
              aria-invalid={invalidOf('note')}
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
          {server.general.length > 0 ? (
            <div role="alert" className="text-sm text-danger" data-testid="hc-server-error">
              {server.general.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
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
              {saved.field === 'discount' && saved.basis_type_code ? (
                // 계약 .14 F2: 응답 basis_type_code — 이 할인이 들어간 기준 타입
                <span className="ml-1 text-xs" data-testid="human-check-basis">
                  {t('page.G7.hc.discountBasisSaved', { type: saved.basis_type_code })}
                </span>
              ) : null}
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
    </OpsSection>
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
  /** 검증 오류(그 칸 — 제출 전 검사 또는 서버 422) — 힌트 자리에 경고로 */
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
