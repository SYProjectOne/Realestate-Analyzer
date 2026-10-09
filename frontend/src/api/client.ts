/**
 * fetch 래퍼: Bearer 토큰, JSON 직렬화, 오류 → `ApiError`(계약 `Error` 스키마).
 * 화면 코드는 이걸 직접 부르지 않고 `hooks.ts`의 훅을, 파일은 `download.ts`를 쓴다.
 * 401 → 토큰 다이얼로그(`auth.requestToken`), 쓰기 요청 403 forbidden → 읽기 전용 표시(`auth.markReadOnly`).
 */
import { z } from 'zod';
import { getAuthToken, markReadOnly, requestToken, type TokenRole } from './auth';
import { API_ERROR_CODES, type ApiErrorCode } from './types';

export { getAuthToken, TOKEN_STORAGE_KEY } from './auth';

/**
 * 프론트는 항상 이 접두로 부른다. FastAPI 가 API_PREFIX(/api) 아래에 있고 dev 프록시(vite.config.ts)·nginx 가
 * 경로를 그대로 넘긴다.
 */
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api';

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
  /** 응답 본문(JSON 이면 파싱한 값) — 오류 응답이 계약 본문을 담는 경우(GET /health 503 = Health) */
  readonly body: unknown;

  constructor(
    code: ClientErrorCode,
    detail: string,
    status: number | null,
    fieldErrors: FieldError[] = [],
    body: unknown = null,
  ) {
    super(`${code}: ${detail}`);
    this.name = 'ApiError';
    this.code = code;
    this.detail = detail;
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.body = body;
  }
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

/** Authorization·Accept 헤더. token 을 주면 그 토큰으로(다이얼로그의 토큰 확인) */
export function authHeaders(
  accept = 'application/json',
  token = getAuthToken(),
): Record<string, string> {
  const headers: Record<string, string> = { Accept: accept };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

/** 실패 응답 → ApiError(본문이 계약 Error 면 그 code·detail·field_errors) */
export async function toApiError(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // 본문 없음
  }
  const parsed = ErrorSchema.safeParse(payload);
  if (parsed.success) {
    return new ApiError(
      parsed.data.code,
      parsed.data.detail,
      response.status,
      parsed.data.field_errors ?? [],
      payload,
    );
  }
  return new ApiError(
    'http',
    response.statusText || `HTTP ${response.status}`,
    response.status,
    [],
    payload,
  );
}

/**
 * 요청을 보내고 성공 응답(2xx)을 돌려준다. 실패는 ApiError 로 던진다.
 * 401 이면 토큰 다이얼로그를 열고, GET 이 아닌 요청이 403 forbidden 이면 지금 토큰을 읽기 전용으로 표시한다.
 */
export async function apiRequest(path: string, options: RequestOptions = {}): Promise<Response> {
  const method = options.method ?? 'GET';
  const token = getAuthToken();
  const headers = authHeaders(options.accept, token);
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(apiUrl(path, options.query), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiError('network', err instanceof Error ? err.message : String(err), null);
  }
  if (response.ok) return response;

  const error = await toApiError(response);
  if (response.status === 401) requestToken(token ? 'invalid' : 'missing');
  if (response.status === 403 && method !== 'GET' && error.code === 'forbidden') markReadOnly();
  throw error;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiRequest(path, options);
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) return (await response.json()) as T;
  return (await response.text()) as T;
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(apiUrl(path), init);
  } catch (err) {
    throw new ApiError('network', err instanceof Error ? err.message : String(err), null);
  }
}

/**
 * 토큰 확인(다이얼로그가 저장하기 전): GET /regions 가 401 → 'invalid'. 통과하면 권한을 알아본다 —
 * 서버는 인증을 본문 검증보다 먼저 하므로(backend `api/deps.require_auth`) 빈 본문 POST /jobs 는
 * 읽기 전용 토큰이면 403 forbidden, 쓰기 토큰이면 422(본문 검증 실패)로 끝나고 아무것도 만들지 않는다.
 * 인증 없는 서버(두 토큰 모두 비움)는 어떤 토큰이든 'write'.
 */
export async function probeToken(token: string): Promise<'invalid' | TokenRole> {
  const read = await rawFetch('/regions', { headers: authHeaders('application/json', token) });
  if (read.status === 401) return 'invalid';
  if (!read.ok) throw await toApiError(read);
  const write = await rawFetch('/jobs', {
    method: 'POST',
    headers: { ...authHeaders('application/json', token), 'Content-Type': 'application/json' },
    body: '{}',
  });
  if (write.status === 401) return 'invalid';
  return write.status === 403 ? 'read' : 'write';
}
