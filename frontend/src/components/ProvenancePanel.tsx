import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { rawDocumentUrl, useProvenance } from '@/api/hooks';
import { t } from '@/i18n';
import { formatDate } from '@/lib/format';
import { EmptyState } from './EmptyState';
import { LabelBadge } from './LabelBadge';
import { ProvenanceContext } from './provenanceContext';

export interface ProvenancePanelProps {
  /** field_provenance id. null이면 닫힘 */
  provId: string | null;
  onClose: () => void;
}

/**
 * 출처 패널(오른쪽 서랍): GET /provenance/{id} → 원문 주소·확인일·라벨·발췌·상충 출처·원문 파일 링크.
 * 보통 직접 쓰지 않고 앱 루트의 ProvenanceProvider가 FactCell 클릭으로 연다.
 */
export function ProvenancePanel({ provId, onClose }: ProvenancePanelProps) {
  const { data, error, isLoading } = useProvenance(provId);

  useEffect(() => {
    if (!provId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [provId, onClose]);

  if (!provId) return null;

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label={t('provenance.title')}
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col gap-3 overflow-y-auto border-l border-border bg-surface p-4 shadow-xl"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">{t('provenance.title')}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border px-2 py-0.5 text-sm"
        >
          {t('provenance.close')}
        </button>
      </div>
      {isLoading ? <p className="text-sm text-muted">{t('app.loading')}</p> : null}
      {error ? <EmptyState reason={error.message} /> : null}
      {data ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
          <dt className="text-muted">{t('provenance.label')}</dt>
          <dd>
            <LabelBadge label={data.label} />
          </dd>
          <dt className="text-muted">{t('provenance.checkedAt')}</dt>
          <dd>{data.checked_at ? formatDate(data.checked_at) : <EmptyState inline />}</dd>
          <dt className="text-muted">{t('provenance.url')}</dt>
          <dd className="break-all">
            {data.url ? (
              <a href={data.url} target="_blank" rel="noreferrer noopener" className="underline">
                {data.url}
              </a>
            ) : (
              <EmptyState inline />
            )}
          </dd>
          <dt className="text-muted">{t('provenance.excerpt')}</dt>
          <dd>
            {data.excerpt ? (
              <blockquote className="whitespace-pre-wrap border-l-2 border-border pl-2">
                {data.excerpt}
              </blockquote>
            ) : (
              <EmptyState inline />
            )}
          </dd>
          <dt className="text-muted">{t('provenance.conflicts')}</dt>
          <dd>
            {data.conflicts.length === 0 ? (
              t('provenance.noConflicts')
            ) : (
              <ul className="list-disc pl-4">
                {data.conflicts.map((conflict) => (
                  <li key={conflict.id}>
                    <span>{conflict.value_text}</span> <LabelBadge label={conflict.label} />
                  </li>
                ))}
              </ul>
            )}
          </dd>
          {data.raw_document_id ? (
            <>
              <dt className="sr-only">{t('provenance.rawDocument')}</dt>
              <dd className="col-span-2">
                <a
                  href={rawDocumentUrl(data.raw_document_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="underline"
                >
                  {t('provenance.rawDocument')}
                </a>
              </dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </aside>
  );
}

/** 앱 루트에 한 번. FactCell이 context로 openProvenance(prov)를 부르면 패널이 열린다. */
export function ProvenanceProvider({ children }: { children: ReactNode }) {
  const [provId, setProvId] = useState<string | null>(null);
  const close = useCallback(() => setProvId(null), []);
  return (
    <ProvenanceContext.Provider value={setProvId}>
      {children}
      <ProvenancePanel provId={provId} onClose={close} />
    </ProvenanceContext.Provider>
  );
}
