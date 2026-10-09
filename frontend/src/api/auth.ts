/**
 * API 토큰 저장소(ADR-9: 쓰기 토큰 API_TOKEN / 읽기 전용 토큰 READONLY_TOKEN, GET 만).
 *
 * - 토큰은 localStorage(`sa.token`)에, 권한은 `sa.token.role`(write|read)에 둔다. 저장소가 막혀 있으면(프라이빗 창·
 *   차단된 사이트 데이터) 메모리에만 두고 `persisted=false` — 탭을 닫으면 다시 입력해야 한다. 모든 접근은 try/catch.
 * - 저장된 토큰이 없으면 빌드 환경변수 `VITE_API_TOKEN`(개발·e2e)을 쓴다. 그 권한은 모른다(= 쓰기로 가정).
 * - 401 → `requestToken()`이 토큰 다이얼로그를 연다. 쓰기 요청이 403 forbidden → `markReadOnly()`.
 * - React 는 `useAuth()`(useSyncExternalStore)로 구독한다.
 */
import { useSyncExternalStore } from 'react';

export const TOKEN_STORAGE_KEY = 'sa.token';
export const ROLE_STORAGE_KEY = 'sa.token.role';

export type TokenRole = 'write' | 'read';
/** 다이얼로그를 연 이유: 토큰 없음(401) · 토큰 틀림(401) · 사용자가 직접 */
export type TokenPromptReason = 'missing' | 'invalid' | 'manual';

export interface AuthSnapshot {
  token: string | null;
  /** null = 모름(쓰기로 가정) */
  role: TokenRole | null;
  /** 토큰 출처: 저장소 · 메모리(저장 실패) · 환경변수 · 없음 */
  source: 'storage' | 'memory' | 'env' | null;
  /** false면 쓰기 버튼을 끈다 */
  canWrite: boolean;
  /** 다이얼로그를 열어야 하면 그 이유 */
  prompt: TokenPromptReason | null;
}

let memory: { token: string; role: TokenRole | null } | null = null;
/** 환경변수 토큰은 저장하지 않으므로 403 으로 알게 된 권한만 메모리에 둔다 */
let memoryRoleForEnv: TokenRole | null = null;
let prompt: TokenPromptReason | null = null;
let snapshot: AuthSnapshot | null = null;
const listeners = new Set<() => void>();

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): boolean {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

const asRole = (v: string | null | undefined): TokenRole | null =>
  v === 'write' || v === 'read' ? v : null;

function envToken(): string | null {
  const v = import.meta.env.VITE_API_TOKEN as string | undefined;
  return v ? v : null;
}

function compute(): AuthSnapshot {
  const stored = readStorage(TOKEN_STORAGE_KEY);
  let token: string | null = null;
  let role: TokenRole | null = null;
  let source: AuthSnapshot['source'] = null;
  if (stored) {
    token = stored;
    role = asRole(readStorage(ROLE_STORAGE_KEY));
    source = 'storage';
  } else if (memory) {
    token = memory.token;
    role = memory.role;
    source = 'memory';
  } else {
    token = envToken();
    source = token ? 'env' : null;
    // 환경변수 토큰에서 403 을 본 경우(메모리에 권한만 남김)
    role = token ? memoryRoleForEnv : null;
  }
  return { token, role, source, canWrite: role !== 'read', prompt };
}

function emit(): void {
  for (const l of listeners) l();
}

const onStorage = (e: StorageEvent) => {
  if (e.key === null || e.key === TOKEN_STORAGE_KEY || e.key === ROLE_STORAGE_KEY) emit();
};

export function subscribeAuth(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1 && typeof window !== 'undefined') {
    window.addEventListener('storage', onStorage); // 다른 탭에서 바꾼 토큰
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && typeof window !== 'undefined') {
      window.removeEventListener('storage', onStorage);
    }
  };
}

const same = (a: AuthSnapshot, b: AuthSnapshot) =>
  a.token === b.token &&
  a.role === b.role &&
  a.source === b.source &&
  a.canWrite === b.canWrite &&
  a.prompt === b.prompt;

/** 매번 저장소를 다시 읽되, 같으면 같은 객체를 돌려준다(useSyncExternalStore 요구). */
export function getAuthSnapshot(): AuthSnapshot {
  const next = compute();
  if (snapshot === null || !same(snapshot, next)) snapshot = next;
  return snapshot;
}

/** 지금 쓸 토큰(저장소 → 메모리 → VITE_API_TOKEN) */
export function getAuthToken(): string | null {
  return compute().token;
}

/**
 * 토큰과 권한을 저장한다. 저장소에 못 쓰면 메모리에만 두고 false 를 돌려준다(화면이 안내).
 * 다이얼로그 요청 상태는 지운다.
 */
export function setAuth(token: string, role: TokenRole): { persisted: boolean } {
  const trimmed = token.trim();
  const persisted =
    writeStorage(TOKEN_STORAGE_KEY, trimmed) && writeStorage(ROLE_STORAGE_KEY, role);
  if (persisted) {
    memory = null;
  } else {
    writeStorage(TOKEN_STORAGE_KEY, null);
    memory = { token: trimmed, role };
  }
  prompt = null;
  emit();
  return { persisted };
}

/** 저장한 토큰을 지운다(환경변수 토큰이 있으면 그걸로 돌아간다). */
export function clearAuth(): void {
  writeStorage(TOKEN_STORAGE_KEY, null);
  writeStorage(ROLE_STORAGE_KEY, null);
  memory = null;
  memoryRoleForEnv = null;
  emit();
}

/** 쓰기 요청이 403 forbidden 이면 지금 토큰은 읽기 전용이다 → 쓰기 버튼을 끈다. */
export function markReadOnly(): void {
  const cur = compute();
  if (cur.role === 'read' || !cur.token) return;
  if (cur.source === 'storage') writeStorage(ROLE_STORAGE_KEY, 'read');
  else if (cur.source === 'memory' && memory) memory = { ...memory, role: 'read' };
  else memoryRoleForEnv = 'read';
  emit();
}

/** 토큰 다이얼로그를 연다(401 이면 apiFetch 가 부른다). 이미 열려 있으면 이유만 더 구체적인 쪽으로. */
export function requestToken(reason: TokenPromptReason): void {
  if (prompt === reason) return;
  if (prompt === 'manual' && reason !== 'manual') return;
  prompt = reason;
  emit();
}

export function dismissTokenPrompt(): void {
  if (prompt === null) return;
  prompt = null;
  emit();
}

/** 테스트용: 메모리 상태를 비운다(localStorage 는 setup 이 비운다). */
export function resetAuthForTests(): void {
  memory = null;
  memoryRoleForEnv = null;
  prompt = null;
  emit();
}

export function useAuth(): AuthSnapshot {
  return useSyncExternalStore(subscribeAuth, getAuthSnapshot, getAuthSnapshot);
}

/** 쓰기(POST·PUT·PATCH) 버튼을 켜도 되는가 — 읽기 전용 토큰이면 false */
export function useCanWrite(): boolean {
  return useAuth().canWrite;
}
