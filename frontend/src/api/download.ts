/**
 * 인증이 필요한 파일(CSV·원문·보고서)을 `<a href>` 대신 fetch(Bearer) → Blob 으로 받는다.
 * `<a href>`·새 탭 열기는 Authorization 헤더를 못 실어 토큰을 켠 서버에서 401 이 난다.
 *
 * - `fetchFile`: Blob + 파일 이름(Content-Disposition) + 형식. 오류는 `apiRequest`와 같다(ApiError, 401 → 토큰 다이얼로그).
 * - `saveBlob`: object URL + `<a download>` 클릭으로 저장하고 URL 을 회수한다.
 * - `downloadFile` = 둘을 합친 것. 화면은 `useDownload()`(진행·오류 상태)를 쓴다.
 * - 미리보기(원문 텍스트·PNG)는 `hooks.useRawFile` 이 `fetchFile` 로 받고 `useObjectUrl` 로 표시한다.
 */
import { useCallback, useEffect, useState } from 'react';
import { apiRequest, type QueryParams } from './client';

/** 경로 + 조회 파라미터(API_BASE 기준, `/snapshots/12/complexes.csv`) */
export interface FileRequest {
  path: string;
  query?: QueryParams;
  /** 응답에 파일 이름이 없을 때 쓸 이름 */
  fallbackName?: string;
}

export interface FetchedFile {
  blob: Blob;
  /** Content-Disposition 의 파일 이름(없으면 fallbackName, 그것도 없으면 null) */
  filename: string | null;
  /** 응답 Content-Type(소문자, 매개변수 포함) */
  contentType: string;
}

/**
 * `attachment; filename="a.csv"` / `filename*=UTF-8''%ED%95%9C.csv` → 파일 이름.
 * RFC 6266: filename* 가 있으면 그것을 쓴다. 경로 구분자는 지운다.
 */
export function filenameFromDisposition(header: string | null | undefined): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*([^;]+)/i.exec(header);
  let name: string | null = null;
  if (star?.[1]) {
    const value = star[1].trim().replace(/^"(.*)"$/, '$1');
    const parts = /^([^']*)'[^']*'(.*)$/.exec(value);
    try {
      name = decodeURIComponent(parts ? (parts[2] ?? '') : value);
    } catch {
      name = null;
    }
  }
  if (!name) {
    const plain = /filename\s*=\s*("((?:\\.|[^"\\])*)"|[^;]+)/i.exec(header);
    if (plain) name = (plain[2] ?? plain[1] ?? '').replace(/\\(.)/g, '$1').trim();
  }
  if (!name) return null;
  const base = name.split(/[\\/]/).pop() ?? '';
  return base.trim() || null;
}

export async function fetchFile(
  request: FileRequest,
  options: { signal?: AbortSignal; accept?: string } = {},
): Promise<FetchedFile> {
  const response = await apiRequest(request.path, {
    query: request.query,
    signal: options.signal,
    accept: options.accept ?? '*/*',
  });
  const blob = await response.blob();
  const contentType = (response.headers.get('content-type') ?? blob.type ?? '').toLowerCase();
  const filename =
    filenameFromDisposition(response.headers.get('content-disposition')) ??
    request.fallbackName ??
    null;
  return { blob, filename, contentType };
}

/** Blob 을 파일로 저장한다(브라우저 다운로드). object URL 은 클릭 뒤 회수한다. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  a.style.display = 'none';
  document.body.appendChild(a);
  try {
    a.click();
  } finally {
    a.remove();
    // 즉시 회수하면 일부 브라우저가 저장을 시작하기 전에 URL 이 사라진다
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }
}

/** fetch(Bearer) → Blob → 저장. 저장한 파일 정보를 돌려준다. */
export async function downloadFile(request: FileRequest): Promise<FetchedFile> {
  const file = await fetchFile(request);
  saveBlob(file.blob, file.filename ?? 'download');
  return file;
}

export interface DownloadState {
  /** 저장 시작. 실패는 error 로(던지지 않음) */
  download: (request: FileRequest) => Promise<void>;
  pending: boolean;
  error: Error | null;
}

/** 다운로드 버튼용: 진행 중이면 버튼을 끄고, 실패하면 오류 문구를 보인다. */
export function useDownload(): DownloadState {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const download = useCallback(async (request: FileRequest) => {
    setPending(true);
    setError(null);
    try {
      await downloadFile(request);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setPending(false);
    }
  }, []);
  return { download, pending, error };
}

/** Blob → object URL(미리보기 `<img>`). Blob 이 바뀌거나 언마운트되면 회수한다. */
export function useObjectUrl(blob: Blob | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return undefined;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);
  return url;
}

/** 미리보기 종류: 텍스트(text/*, json) · 이미지(PNG 등) · 그 밖(저장만) */
export function previewKind(contentType: string): 'text' | 'image' | 'other' {
  const ct = contentType.toLowerCase();
  if (ct.startsWith('image/')) return 'image';
  if (ct.startsWith('text/html')) return 'other'; // 수집한 HTML 은 실행하지 않는다 — 저장해서 연다
  if (ct.startsWith('text/') || ct.includes('json')) return 'text';
  return 'other';
}
