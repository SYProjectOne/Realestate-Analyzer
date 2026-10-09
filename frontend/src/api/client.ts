/**
 * fetch 래퍼: Bearer 토큰, JSON 직렬화, 오류 → `ApiError`(계약 `Error` 스키마).
 * 화면 코드는 이걸 직접 부르지 않고 `hooks.ts`의 훅을 쓴다.
 */
import { z } from 'zod';
import { API_ERROR_CODES, type ApiErrorCode } from './types';

/** 프론트는 항상 이 접두로 부른다. dev 서버가 `/api`를 떼고 FastAPI로 넘긴다(vite.config.ts). */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api';
export const TOKEN_STORAGE_KEY = 'sa.token';

export const ErrorSchema = z.object({
  code: z.enum(API_ERROR_CODES),
  detail: z.string(),
  field_errors: z
    .array(z.object({ loc: z.array(z.union([z.string(), z.number()])), msg: z.string() }))
    .nullish(),
  request_id: z.string().nullish(),
});

export interface FieldError {
  loc: (string | number)[];
  msg: string;
}

/** 계약 밖 오류(네트워크·5xx 본문 없음 등)는 code = 'http' | 'network'. */
export type ClientErrorCode = ApiErrorCode | 'http' | 'network';

export class ApiError extends Error {
  readonly code: ClientErrorCode;
  readonly detail: string;
  readonly status: number | null;
  /** 422 validation_error의 필드별 오류(계약 Error.field_errors) */
  readonly fieldErrors: FieldError[];

  constructor(
    code: ClientErrorCode,
    detail: string,
    status: number | null,
    fieldErrors: FieldError[] = [],
  ) {
    super(`${code}: ${detail}`);
    this.name = 'ApiError';
    this.code = code;
    this.detail = detail;
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

export function getAuthToken(): string | null {
  try {
    const stored = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    if (stored) return stored;
  } catch {
    // 저장소 접근 불가(프라이빗 창 등) → 환경변수로 폴백
  }
  return import.meta.env.VITE_API_TOKEN ?? null;
}

export type QueryValue =
  string | number | boolean | null | undefined | readonly (string | number)[];
export type QueryParams = Record<string, QueryValue | Record<string, string>>;

/** `{ page: 1, filter: { living_area: 'x' } }` → `page=1&filter[living_area]=x` (RA §4-2 목록 규칙). */
export function buildQuery(params?: QueryParams): string {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    if (Array.isArray(value)) {
      search.set(key, value.join(','));
    } else if (typeof value === 'object') {
      for (const [sub, subValue] of Object.entries(value as Record<string, string>)) {
        if (subValue !== '') search.set(`${key}[${sub}]`, subValue);
      }
    } else {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

export function apiUrl(path: string, query?: QueryParams): string {
  const base = API_BASE.replace(/\/$/, '');
  const relative = `${base}${path}${buildQuery(query)}`;
  // Node(vitest)의 fetch는 상대 URL을 못 받으므로 현재 origin 기준 절대 URL로 만든다.
  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
  return new URL(relative, origin).toString();
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  query?: QueryParams;
  body?: unknown;
  signal?: AbortSignal;
  /** Accept 헤더(기본 application/json). 원문 텍스트는 text/plain */
  accept?: string;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: options.accept ?? 'application/json' };
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(apiUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiError('network', err instanceof Error ? err.message : String(err), null);
  }

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // 본문 없음
    }
    const parsed = ErrorSchema.safeParse(payload);
    if (parsed.success) {
      throw new ApiError(
        parsed.data.code,
        parsed.data.detail,
        response.status,
        parsed.data.field_errors ?? [],
      );
    }
    throw new ApiError('http', response.statusText || `HTTP ${response.status}`, response.status);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) return (await response.json()) as T;
  return (await response.text()) as T;
}
