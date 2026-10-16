import { useId, useState, type ReactNode } from 'react';
import { useCanWrite } from '@/api/auth';
import { ApiError } from '@/api/client';
import { useCreateCatalyst } from '@/api/hooks';
import type { CatalystCreated } from '@/api/types';
import { PublishJobProgress } from '@/components';
import { t, type TKey } from '@/i18n';
import { QuestionSection } from '../_shared/QuestionSection';

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
    <QuestionSection
      name={t('page.G6.catalyst.title')}
      title={t('page.G6.catalyst.titleQ')}
      kicker={<EditorTag />}
      hint={t('page.G6.catalyst.intro')}
    >
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
            className={buttonClass}
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
          {/* 계약 .12 F3·F15: job_id(분류 rejudge) → 판정 뒤 발행 잡까지 감시 */}
          {(created.job_id ?? created.job?.id ?? null) !== null ? (
            <PublishJobProgress jobId={(created.job_id ?? created.job?.id) as number} />
          ) : (
            <p className="text-xs text-muted">{t('page.G6.catalyst.noJob')}</p>
          )}
        </div>
      ) : null}
    </QuestionSection>
  );
}

/** '편집하는 사람용' 꼬리표(목업 N14) — 위치 확인 구역과 같은 모양 */
export function EditorTag() {
  return (
    <span className="inline-flex rounded-md bg-chip px-2 py-0.5 text-xs font-semibold text-fg-2">
      {t('page.G6.editor')}
    </span>
  );
}

const inputClass =
  'min-h-11 w-full rounded-[10px] border border-border-strong bg-surface px-3 py-2 text-[15px] disabled:opacity-60';

/** 목업 주 버튼(.btn): 주색 바탕 · 12px 둥글게 · 44px 높이 */
export const buttonClass =
  'min-h-11 rounded-xl bg-accent px-4 text-[15px] font-semibold text-accent-fg disabled:cursor-not-allowed disabled:opacity-50';

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
      <label htmlFor={id} className="text-[13px] font-semibold text-fg-2">
        {t(label)}
      </label>
      {children(id)}
    </div>
  );
}
