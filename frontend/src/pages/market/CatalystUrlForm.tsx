import { useId, useState, type ReactNode } from 'react';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useCreateCatalyst } from '@/api/hooks';
import type { CatalystCreated } from '@/api/types';
import { JobProgress } from '@/components';
import { t, type TKey } from '@/i18n';
import { Section } from '../_shared';

export const CATALYST_TITLE_MAX = 200;
export const CATALYST_EXCERPT_MAX = 2000;

/** 계약 CatalystCreate.url — http(s) 공개 페이지만 */
export function isHttpUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!/^https?:\/\//i.test(trimmed)) return false;
  try {
    const url = new URL(trimmed);
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname !== '';
  } catch {
    return false;
  }
}

/**
 * G6 호재 URL 입력 (M6, DECISIONS D1-6, 계약 2026-10-09.4 POST /catalysts).
 * 사람이 공개 기사·공고 URL + 제목(+발췌)을 넣으면 서버가 호재 후보(stage 미확정)를 만들고 분류 잡을 등록한다.
 * 분류(종류·단계)는 판정기가 한다 — 화면은 판단하지 않는다. 읽기 전용 토큰이면 꺼진다.
 */
export function CatalystUrlForm({ regionId }: { regionId: number | null }) {
  const canWrite = useCanWrite();
  const create = useCreateCatalyst();
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [excerpt, setExcerpt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CatalystCreated | null>(null);
  const disabled = !canWrite || regionId === null;

  const submit = () => {
    if (regionId === null) return;
    if (!isHttpUrl(url)) {
      setError(t('page.G6.catalyst.badUrl'));
      return;
    }
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError(t('page.G6.catalyst.titleRequired'));
      return;
    }
    setError(null);
    const trimmedExcerpt = excerpt.trim();
    create.mutate(
      {
        region_id: regionId,
        url: url.trim(),
        title: trimmedTitle.slice(0, CATALYST_TITLE_MAX),
        excerpt: trimmedExcerpt ? trimmedExcerpt.slice(0, CATALYST_EXCERPT_MAX) : null,
      },
      {
        onSuccess: (result) => {
          setCreated(result);
          setUrl('');
          setTitle('');
          setExcerpt('');
        },
      },
    );
  };

  const serverError =
    create.error instanceof ApiError
      ? create.error.detail
      : create.error
        ? create.error.message
        : null;

  return (
    <Section title={t('page.G6.catalyst.title')}>
      <p className="text-xs text-muted">{t('page.G6.catalyst.intro')}</p>
      <form
        aria-label={t('page.G6.catalyst.title')}
        noValidate
        data-write
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="grid gap-3 sm:grid-cols-2"
      >
        <Field label="page.G6.catalyst.url">
          {(id) => (
            <input
              id={id}
              type="url"
              inputMode="url"
              value={url}
              disabled={disabled}
              placeholder="https://"
              onChange={(e) => setUrl(e.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="page.G6.catalyst.titleField">
          {(id) => (
            <input
              id={id}
              value={title}
              maxLength={CATALYST_TITLE_MAX}
              disabled={disabled}
              onChange={(e) => setTitle(e.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <Field label="page.G6.catalyst.excerpt" wide>
          {(id) => (
            <textarea
              id={id}
              value={excerpt}
              rows={3}
              maxLength={CATALYST_EXCERPT_MAX}
              disabled={disabled}
              onChange={(e) => setExcerpt(e.target.value)}
              className={inputClass}
            />
          )}
        </Field>
        <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
          <button
            type="submit"
            disabled={disabled || create.isPending}
            title={canWrite ? undefined : t('auth.readOnlyHint')}
            className="rounded bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
          >
            {t('page.G6.catalyst.submit')}
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
        </div>
      </form>
      {created ? (
        <div data-testid="catalyst-created" className="flex flex-col gap-1 text-sm">
          <p role="status">{t('page.G6.catalyst.saved', { name: created.catalyst.name })}</p>
          {created.job ? (
            <JobProgress jobId={created.job.id} />
          ) : (
            <p className="text-xs text-muted">{t('page.G6.catalyst.noJob')}</p>
          )}
        </div>
      ) : null}
    </Section>
  );
}

const inputClass =
  'w-full rounded border border-border bg-surface px-2 py-1 text-sm disabled:opacity-60';

function Field({
  label,
  wide = false,
  children,
}: {
  label: TKey;
  wide?: boolean;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className={`flex flex-col gap-0.5 ${wide ? 'sm:col-span-2' : ''}`}>
      <label htmlFor={id} className="text-xs text-muted">
        {t(label)}
      </label>
      {children(id)}
    </div>
  );
}
