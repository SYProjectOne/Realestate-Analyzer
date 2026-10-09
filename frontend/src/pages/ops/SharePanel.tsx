import { useId, useState } from 'react';
import { useCanWrite } from '@/api/auth';
import { useCreateShareLink, useRevokeShareLink, useShareLinks } from '@/api/hooks';
import type { ShareLinkCreated } from '@/api/types';
import { Badge } from '@/components';
import { t } from '@/i18n';
import { formatDate } from '@/lib/format';
import { enumText, QueryState, Section, tdClass, thClass } from '../_shared';

/** 공유 링크 메모 최대 길이(계약 ShareLinkCreate.label, 서버 64자) */
export const SHARE_LABEL_MAX = 64;

/** 공유 링크 주소 — 토큰은 hash 에만(서버로 가지 않는다) */
export function shareUrl(token: string, origin: string = window.location.origin): string {
  return `${origin}/share#${token}`;
}

/**
 * G7 SharePanel (M9, 계약 2026-10-09.4) — 읽기 전용 공유 링크 발급·목록·회수.
 * 쓰기 토큰만 보인다(읽기·공유 토큰은 GET /share-links 가 403 — 아예 부르지 않는다).
 * 토큰은 발급 응답에서 한 번만 받으므로 그때만 링크를 보이고, 닫으면 다시 볼 수 없다.
 */
export function SharePanel() {
  const canWrite = useCanWrite();
  if (!canWrite) return null;
  return <SharePanelBody />;
}

function SharePanelBody() {
  const query = useShareLinks(true);
  const create = useCreateShareLink();
  const revoke = useRevokeShareLink();
  const labelId = useId();
  const [label, setLabel] = useState('');
  const [created, setCreated] = useState<ShareLinkCreated | null>(null);

  return (
    <Section title={t('page.G7.share.title')}>
      <p className="text-xs text-muted">{t('page.G7.share.intro')}</p>
      <form
        className="flex flex-wrap items-end gap-2"
        data-write
        onSubmit={(e) => {
          e.preventDefault();
          const trimmed = label.trim();
          create.mutate(
            { label: trimmed ? trimmed.slice(0, SHARE_LABEL_MAX) : null },
            {
              onSuccess: (result) => {
                setCreated(result);
                setLabel('');
              },
            },
          );
        }}
      >
        <div className="flex flex-col gap-0.5">
          <label htmlFor={labelId} className="text-xs text-muted">
            {t('page.G7.share.label')}
          </label>
          <input
            id={labelId}
            value={label}
            maxLength={SHARE_LABEL_MAX}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={t('page.G7.share.labelHint')}
            className="w-64 rounded-sm border border-border bg-surface px-2 py-1 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={create.isPending}
          className="rounded-sm bg-accent px-3 py-1.5 text-sm text-accent-fg disabled:opacity-50"
        >
          {t('page.G7.share.create')}
        </button>
        {create.error ? (
          <p role="alert" className="text-sm text-danger">
            {t('page.common.loadError', { detail: create.error.message })}
          </p>
        ) : null}
      </form>
      {created ? <CreatedLink created={created} onDone={() => setCreated(null)} /> : null}
      <QueryState
        query={query}
        empty={(rows) => (rows.length === 0 ? t('page.G7.share.none') : null)}
      >
        {(links) => (
          <div className="overflow-x-auto">
            <table aria-label={t('page.G7.share.list')} className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <th scope="col" className={thClass}>
                    {t('page.G7.share.col.label')}
                  </th>
                  <th scope="col" className={thClass}>
                    {t('page.G7.share.col.status')}
                  </th>
                  <th scope="col" className={thClass}>
                    {t('page.G7.share.col.created')}
                  </th>
                  <th scope="col" className={thClass}>
                    {t('page.G7.share.col.expires')}
                  </th>
                  <th scope="col" className={thClass}>
                    <span className="sr-only">{t('page.G7.share.revoke')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {links.map((link) => (
                  <tr key={link.id} data-status={link.status}>
                    <th scope="row" className={`${tdClass} text-left font-normal`}>
                      {link.label ?? t('page.common.none')}
                    </th>
                    <td className={tdClass}>
                      <Badge tone={link.status === 'active' ? 'neutral' : 'muted'}>
                        {enumText('page.G7.share.status', link.status)}
                      </Badge>
                    </td>
                    <td className={tdClass}>{formatDate(link.created_at)}</td>
                    <td className={tdClass}>
                      {link.status === 'revoked' && link.revoked_at
                        ? t('page.G7.share.revokedAt', { date: formatDate(link.revoked_at) })
                        : formatDate(link.expires_at)}
                    </td>
                    <td className={tdClass}>
                      {link.status === 'active' ? (
                        <button
                          type="button"
                          disabled={revoke.isPending}
                          onClick={() => revoke.mutate(link.id)}
                          className="rounded-sm border border-border px-2 py-0.5 text-xs disabled:opacity-50"
                        >
                          {t('page.G7.share.revoke')}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </QueryState>
      {revoke.error ? (
        <p role="alert" className="text-sm text-danger">
          {t('page.common.loadError', { detail: revoke.error.message })}
        </p>
      ) : null}
    </Section>
  );
}

function CreatedLink({ created, onDone }: { created: ShareLinkCreated; onDone: () => void }) {
  const url = shareUrl(created.token);
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null);
  const inputId = useId();
  return (
    <div
      data-testid="share-created"
      className="flex flex-col gap-2 rounded-sm border border-accent p-2 text-sm"
    >
      <label htmlFor={inputId} className="font-medium">
        {t('page.G7.share.createdTitle')}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <input
          id={inputId}
          readOnly
          value={url}
          onFocus={(e) => e.currentTarget.select()}
          className="min-w-0 flex-1 rounded-sm border border-border bg-bg px-2 py-1 font-mono text-xs"
        />
        <button
          type="button"
          onClick={() => {
            const done = (ok: boolean) => setCopied(ok ? 'ok' : 'fail');
            try {
              void navigator.clipboard.writeText(url).then(
                () => done(true),
                () => done(false),
              );
            } catch {
              done(false);
            }
          }}
          className="rounded-sm border border-border px-2 py-1 text-xs"
        >
          {t('page.G7.share.copy')}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-sm border border-border px-2 py-1 text-xs"
        >
          {t('page.G7.share.done')}
        </button>
      </div>
      {copied === 'ok' ? (
        <p role="status" className="text-xs text-muted">
          {t('page.G7.share.copied')}
        </p>
      ) : null}
      {copied === 'fail' ? (
        <p role="status" className="text-xs text-danger">
          {t('page.G7.share.copyFailed')}
        </p>
      ) : null}
      <p className="text-xs text-muted">{t('page.G7.share.once')}</p>
      <p className="text-xs text-muted">
        {t('page.G7.share.expires', { date: formatDate(created.link.expires_at) })}
      </p>
    </div>
  );
}
