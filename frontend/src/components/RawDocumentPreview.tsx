import { useEffect, useState } from 'react';
import { previewKind, useDownload, useObjectUrl, type FetchedFile } from '@/api/download';
import { rawDocumentRequest, useRawFile } from '@/api/hooks';
import { t } from '@/i18n';
import { formatCount } from '@/lib/format';
import { EmptyState } from './EmptyState';

/** 텍스트 미리보기 최대 글자 수(큰 원문이 화면을 멈추지 않게) */
const TEXT_PREVIEW_MAX = 200_000;

export interface RawDocumentPreviewProps {
  /** raw_document.id */
  rawId: number | string;
  /** 처음부터 미리보기를 연다 */
  defaultOpen?: boolean;
  className?: string;
}

/**
 * 원문 파일(GET /raw/{id}) — "원문 미리보기"(텍스트·PNG를 Bearer fetch → Blob 으로 화면 안에) · "원문 파일 저장".
 * `<a href>`는 토큰을 싣지 못해 쓰지 않는다. HTML·PDF 는 미리보기 대신 저장(수집한 HTML 은 실행하지 않는다).
 */
export function RawDocumentPreview({
  rawId,
  defaultOpen = false,
  className = '',
}: RawDocumentPreviewProps) {
  const [open, setOpen] = useState(defaultOpen);
  const file = useRawFile(rawId, open);
  const { download, pending, error } = useDownload();

  return (
    <div className={`flex flex-col gap-2 ${className}`} data-testid="raw-document">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="underline"
        >
          {open ? t('provenance.rawPreviewHide') : t('provenance.rawPreview')}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => void download(rawDocumentRequest(rawId))}
          className="underline disabled:opacity-50"
        >
          {pending ? t('download.pending') : t('provenance.rawSave')}
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {t('download.error', { detail: error.message })}
        </p>
      ) : null}
      {open ? (
        file.isLoading ? (
          <p className="text-xs text-muted">{t('provenance.rawLoading')}</p>
        ) : file.error || !file.data ? (
          <EmptyState inline message={t('provenance.rawError')} />
        ) : (
          <PreviewBody file={file.data} />
        )
      ) : null}
    </div>
  );
}

function PreviewBody({ file }: { file: FetchedFile }) {
  const kind = previewKind(file.contentType);
  if (kind === 'image') return <ImagePreview file={file} />;
  if (kind === 'text') return <TextPreview blob={file.blob} />;
  return (
    <p className="text-xs text-muted">
      {t('provenance.rawPreviewUnsupported', {
        type: file.contentType.split(';')[0] || t('page.common.none'),
      })}
    </p>
  );
}

function ImagePreview({ file }: { file: FetchedFile }) {
  const url = useObjectUrl(file.blob);
  if (!url) return null;
  return (
    <img
      src={url}
      alt={t('provenance.rawImageAlt', { name: file.filename ?? '' })}
      data-testid="raw-preview-image"
      className="max-h-[60vh] max-w-full self-start rounded-sm border border-border bg-bg object-contain"
    />
  );
}

/** Blob → 문자열(UTF-8). text() 가 없는 Blob 구현(jsdom 등)은 FileReader 로 */
function readText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') return blob.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '');
    reader.onerror = () => reject(reader.error ?? new Error('read failed'));
    reader.readAsText(blob, 'utf-8');
  });
}

function TextPreview({ blob }: { blob: Blob }) {
  const [text, setText] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    setText(null);
    setFailed(false);
    readText(blob).then(
      (value) => alive && setText(value),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [blob]);
  if (failed) return <EmptyState inline message={t('provenance.rawError')} />;
  if (text === null) return <p className="text-xs text-muted">{t('provenance.rawLoading')}</p>;
  const truncated = text.length > TEXT_PREVIEW_MAX;
  return (
    <>
      {truncated ? (
        <p className="text-xs text-muted">
          {t('provenance.rawTruncated', { n: formatCount(TEXT_PREVIEW_MAX) })}
        </p>
      ) : null}
      <pre
        data-testid="raw-preview-text"
        className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-bg p-2 text-xs"
      >
        {truncated ? text.slice(0, TEXT_PREVIEW_MAX) : text}
      </pre>
    </>
  );
}
