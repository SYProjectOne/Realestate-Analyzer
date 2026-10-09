import { useId, useState, type ReactNode } from 'react';
import { useCanWrite } from '@/api/auth';
import { useComplexes, useCreateHumanCheck, useCreateJob } from '@/api/hooks';
import {
  ENTERED_BY_ROLES,
  type EnteredByRole,
  type HumanCheck,
  type HumanCheckCreate,
} from '@/api/types';
import { useToast } from '@/app/toast';
import { IntakeBadge } from '@/components';
import { t, type TKey } from '@/i18n';
import { enumText, Section } from '../_shared';

const FIELDS = ['intake_status', 'price', 'units', 'other'] as const;
const KINDS = ['phone', 'visit', 'email'] as const;
const INTAKE_VALUES = ['가능', '미정', '확인 불가', '불가'] as const;

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

/**
 * G7 HumanCheckForm — 단지·필드·값·종류·메모 → POST /ops/human-checks.
 * 저장 → 접수 배지 즉시 갱신(응답 created_intake + 쿼리 무효화) + "재판정 잡 등록" 제안 토스트(suggested_job).
 */
export function HumanCheckForm({ snapshotId }: { snapshotId: string | null }) {
  const complexes = useComplexes(snapshotId, { page: 1, size: 1000, sort: 'name' });
  const create = useCreateHumanCheck();
  const createJob = useCreateJob();
  const canWrite = useCanWrite();
  const toast = useToast();
  const [complexId, setComplexId] = useState('');
  const [field, setField] = useState<(typeof FIELDS)[number]>('intake_status');
  const [value, setValue] = useState('');
  const [kind, setKind] = useState<(typeof KINDS)[number]>('phone');
  const [checkedAt, setCheckedAt] = useState(nowLocal);
  const [enteredBy, setEnteredBy] = useState<EnteredByRole | ''>('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<HumanCheck | null>(null);

  const submit = () => {
    if (!complexId || !value.trim() || !enteredBy) {
      setError(t('page.G7.hc.required'));
      return;
    }
    setError(null);
    const body: HumanCheckCreate = {
      complex_id: Number(complexId),
      field,
      value_text: value.trim(),
      kind,
      checked_at: toIso(checkedAt),
      entered_by: enteredBy,
      note: note.trim() || null,
    };
    create.mutate(body, {
      onSuccess: (result) => {
        setSaved(result);
        const suggested = result.suggested_job;
        toast({
          message: `${t('page.G7.hc.saved')} · ${t('page.G7.suggestRejudge')}`,
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

  return (
    <Section title={t('page.G7.human')}>
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
              onChange={(e) => setComplexId(e.target.value)}
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
                setField(e.target.value as (typeof FIELDS)[number]);
                setValue('');
              }}
              className={inputClass}
            >
              {FIELDS.map((f) => (
                <option key={f} value={f}>
                  {enumText('page.G7.hcField', f)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="value">
          {(id) =>
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
                value={value}
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
        <Field label="note" wide>
          {(id) => (
            <textarea
              id={id}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className={inputClass}
            />
          )}
        </Field>
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
          {create.error ? (
            <p role="alert" className="text-sm text-danger">
              {t('page.common.loadError', { detail: create.error.message })}
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
  children,
}: {
  label: string;
  wide?: boolean;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className={`flex flex-col gap-0.5 ${wide ? 'sm:col-span-2' : ''}`}>
      <label htmlFor={id} className="text-xs text-muted">
        {t(`page.G7.hc.${label}` as TKey)}
      </label>
      {children(id)}
    </div>
  );
}
