/**
 * API 토큰 저장소(ADR-9: 쓰기 토큰 API_TOKEN / 읽기 전용 토큰 READONLY_TOKEN, GET 만).
 *
 * - 토큰은 localStorage(`sa.token`)에, 권한은 `sa.token.role`(write|read)에 둔다. 저장소가 막혀 있으면(프라이빗 창·
 *   차단된 사이트 데이터) 메모리에만 두고 `persisted=false` — 탭을 닫으면 다시 입력해야 한다. 모든 접근은 try/catch.
 * - **탭 범위 토큰**(N-M7, R3b): sessionStorage(`sa.token.tab`·`sa.token.tab.role`)가 있으면 localStorage 보다 먼저 쓴다.
 *   두 경우에 생긴다 — ① 공유 링크를 "이 탭에서만 읽기 전용으로 보기"로 열 때(저장된 쓰기 토큰은 그대로),
 *   ② 다른 탭이 저장 토큰을 다른 **읽기 전용** 토큰으로 바꿨을 때 이 탭이 쓰던 쓰기(또는 권한 모름) 토큰을 고정(pin) —
 *   이 탭은 계속 그 토큰으로 일하고 `externalChange=true`(레이아웃 배너 "새 토큰 사용" → `releaseTabPin()`).
 *   sessionStorage 가 막혀 있으면 이 탭 메모리에 같은 우선순위로 둔다.
 * - 저장된 토큰이 없으면 빌드 환경변수 `VITE_API_TOKEN`(개발·e2e)을 쓴다. 그 권한은 모른다(= 쓰기로 가정).
 * - 401 → `requestToken()`이 토큰 다이얼로그를 연다. 쓰기 요청이 403 forbidden → `markReadOnly()`.
 * - React 는 `useAuth()`(useSyncExternalStore)로 구독한다.
 */
import { useSyncExternalStore } from 'react';

export const TOKEN_STORAGE_KEY = 'sa.token';
export const ROLE_STORAGE_KEY = 'sa.token.role';
/** 탭 범위(sessionStorage) 토큰·권한·이유(share = 공유 링크를 이 탭에만 · pinned = 다른 탭 변경에서 고정) */
export const TAB_TOKEN_KEY = 'sa.token.tab';
export const TAB_ROLE_KEY = 'sa.token.tab.role';
export const TAB_REASON_KEY = 'sa.token.tab.reason';

export type TokenRole = 'write' | 'read';
/** 다이얼로그를 연 이유: 토큰 없음(401) · 토큰 틀림(401) · 사용자가 직접 */
export type TokenPromptReason = 'missing' | 'invalid' | 'manual';
/** 탭 범위 토큰이 생긴 이유 */
export type TabTokenReason = 'share' | 'pinned';

export interface AuthSnapshot {
  token: string | null;
  /** null = 모름(쓰기로 가정) */
  role: TokenRole | null;
  /** 토큰 출처: 이 탭(sessionStorage) · 저장소 · 메모리(저장 실패) · 환경변수 · 없음 */
  source: 'tab' | 'storage' | 'memory' | 'env' | null;
  /** false면 쓰기 버튼을 끈다 */
  canWrite: boolean;
  /** 다이얼로그를 열어야 하면 그 이유 */
  prompt: TokenPromptReason | null;
  /** 다른 탭이 저장 토큰을 바꿔 이 탭이 기존 토큰을 고정해 쓰는 중(배너) */
  externalChange: boolean;
}

interface TabAuth {
  token: string;
  role: TokenRole | null;
  reason: TabTokenReason;
}

let memory: { token: string; role: TokenRole | null } | null = null;
/** 환경변수 토큰은 저장하지 않으므로 403 으로 알게 된 권한만 메모리에 둔다 */
let memoryRoleForEnv: TokenRole | null = null;
/** sessionStorage 를 못 쓸 때의 탭 범위 토큰(같은 우선순위) */
let tabFallback: TabAuth | null = null;
let prompt: TokenPromptReason | null = null;
let snapshot: AuthSnapshot | null = null;
/**
 * 다른 탭의 토큰 이벤트를 받았는데 권한 값이 아직 read 가 아니었던 경우(쓰기가 이벤트 두 개로 나뉘어 옴) —
 * 바로 뒤의 권한 이벤트가 read 면 이 토큰을 고정한다. 짧은 시간만 유효.
 */
let pendingPin: { token: string; role: TokenRole | null; at: number } | null = null;
const PENDING_PIN_MS = 2000;
const listeners = new Set<() => void>();

function storageOf(kind: 'local' | 'session'): Storage | null {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function readStorage(key: string, kind: 'local' | 'session' = 'local'): string | null {
  try {
    return storageOf(kind)?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function writeStorage(
  key: string,
  value: string | null,
  kind: 'local' | 'session' = 'local',
): boolean {
  try {
    const store = storageOf(kind);
    if (!store) return false;
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
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

function readTab(): TabAuth | null {
  const token = readStorage(TAB_TOKEN_KEY, 'session');
  if (token) {
    return {
      token,
      role: asRole(readStorage(TAB_ROLE_KEY, 'session')),
      reason: readStorage(TAB_REASON_KEY, 'session') === 'pinned' ? 'pinned' : 'share',
    };
  }
  return tabFallback;
}

function writeTab(tab: TabAuth | null): boolean {
  const ok =
    writeStorage(TAB_TOKEN_KEY, tab?.token ?? null, 'session') &&
    writeStorage(TAB_ROLE_KEY, tab?.role ?? null, 'session') &&
    writeStorage(TAB_REASON_KEY, tab?.reason ?? null, 'session');
  if (tab === null) {
    tabFallback = null;
    return ok;
  }
  if (ok) {
    tabFallback = null;
  } else {
    writeStorage(TAB_TOKEN_KEY, null, 'session');
    tabFallback = tab;
  }
  return ok;
}

function compute(): AuthSnapshot {
  const tab = readTab();
  const stored = readStorage(TOKEN_STORAGE_KEY);
  let token: string | null = null;
  let role: TokenRole | null = null;
  let source: AuthSnapshot['source'] = null;
  if (tab) {
    token = tab.token;
    role = tab.role;
    source = 'tab';
  } else if (stored) {
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
  return {
    token,
    role,
    source,
    canWrite: role !== 'read',
    prompt,
    externalChange: tab?.reason === 'pinned',
  };
}

function emit(): void {
  for (const l of listeners) l();
}

/** 이 탭이 쓰던 저장소 토큰을 탭 범위에 고정한다(다른 탭이 읽기 전용 토큰으로 바꿨을 때) */
function pin(token: string, role: TokenRole | null): void {
  pendingPin = null;
  writeTab({ token, role, reason: 'pinned' });
}

/**
 * 다른 탭에서 저장 토큰이 바뀌었다. 이 탭이 저장소의 쓰기(또는 권한 모름) 토큰을 쓰던 중이고 새 값이 **다른 토큰 +
 * 읽기 전용**이면 이전 토큰을 탭에 고정한다(이 탭이 갑자기 읽기 전용이 되지 않게). 같은 토큰의 권한만 read 로
 * 바뀐 경우(그 토큰이 실제로 403 을 받음)는 따른다.
 */
function onExternalChange(e: StorageEvent): void {
  const prev = snapshot;
  const tabActive = readTab() !== null;
  if (tabActive) return; // 이 탭은 이미 탭 범위 토큰을 쓴다 — 저장소 변경과 무관
  const nextToken = readStorage(TOKEN_STORAGE_KEY);
  const nextRole = asRole(readStorage(ROLE_STORAGE_KEY));
  if (e.key === TOKEN_STORAGE_KEY) {
    pendingPin = null;
    const oldToken = e.oldValue;
    if (!oldToken || oldToken === nextToken) return;
    // 이 탭이 그 토큰을 저장소에서 쓰고 있었나(마지막 스냅샷)
    const wasUsing = prev !== null && prev.source === 'storage' && prev.token === oldToken;
    if (!wasUsing || prev.role === 'read') return;
    if (nextToken && nextRole === 'read') pin(oldToken, prev.role);
    else if (nextToken) pendingPin = { token: oldToken, role: prev.role, at: Date.now() };
  } else if (e.key === ROLE_STORAGE_KEY) {
    const pending = pendingPin;
    pendingPin = null;
    if (!pending || Date.now() - pending.at > PENDING_PIN_MS) return;
    if (nextToken && nextToken !== pending.token && nextRole === 'read') {
      pin(pending.token, pending.role);
    }
  }
}

const onStorage = (e: StorageEvent) => {
  if (e.key === null || e.key === TOKEN_STORAGE_KEY || e.key === ROLE_STORAGE_KEY) {
    if (e.key !== null) onExternalChange(e);
    emit();
  }
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
  a.prompt === b.prompt &&
  a.externalChange === b.externalChange;

/** 매번 저장소를 다시 읽되, 같으면 같은 객체를 돌려준다(useSyncExternalStore 요구). */
export function getAuthSnapshot(): AuthSnapshot {
  const next = compute();
  if (snapshot === null || !same(snapshot, next)) snapshot = next;
  return snapshot;
}

/** 지금 쓸 토큰(탭 → 저장소 → 메모리 → VITE_API_TOKEN) */
export function getAuthToken(): string | null {
  return compute().token;
}

/**
 * 이 브라우저에 저장된 토큰(localStorage 또는 저장 실패 메모리)이 쓰기·권한 모름인가 —
 * 공유 링크가 덮어쓰기 전에 확인을 받아야 하는 경우. 환경변수 토큰·탭 범위 토큰은 세지 않는다.
 */
export function hasStoredWriteToken(): boolean {
  const stored = readStorage(TOKEN_STORAGE_KEY);
  if (stored) return asRole(readStorage(ROLE_STORAGE_KEY)) !== 'read';
  return memory !== null && memory.role !== 'read';
}

/**
 * 토큰과 권한을 저장한다. 저장소에 못 쓰면 메모리에만 두고 false 를 돌려준다(화면이 안내).
 * 이 탭의 탭 범위 토큰과 다이얼로그 요청 상태는 지운다(사용자가 이 탭에서 고른 토큰이 바로 쓰이게).
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
  writeTab(null);
  pendingPin = null;
  prompt = null;
  emit();
  return { persisted };
}

/**
 * 이 탭에서만 쓸 토큰(sessionStorage) — 공유 링크 "이 탭에서만 읽기 전용으로 보기". localStorage 는 건드리지 않는다.
 * sessionStorage 를 못 쓰면 이 탭 메모리에 두고 persisted=false(새로 고침하면 사라진다).
 */
export function setTabAuth(token: string, role: TokenRole | null): { persisted: boolean } {
  const persisted = writeTab({ token: token.trim(), role, reason: 'share' });
  prompt = null;
  emit();
  return { persisted };
}

/** 탭 범위 토큰(고정·공유)을 풀고 저장소 토큰으로 돌아간다 — 배너 "새 토큰 사용" */
export function releaseTabPin(): void {
  writeTab(null);
  pendingPin = null;
  emit();
}

/** 저장한 토큰을 지운다(환경변수 토큰이 있으면 그걸로 돌아간다). */
export function clearAuth(): void {
  writeStorage(TOKEN_STORAGE_KEY, null);
  writeStorage(ROLE_STORAGE_KEY, null);
  writeTab(null);
  memory = null;
  memoryRoleForEnv = null;
  pendingPin = null;
  emit();
}

/** 쓰기 요청이 403 forbidden 이면 지금 토큰은 읽기 전용이다 → 쓰기 버튼을 끈다. */
export function markReadOnly(): void {
  const cur = compute();
  if (cur.role === 'read' || !cur.token) return;
  if (cur.source === 'tab') {
    const tab = readTab();
    if (tab) writeTab({ ...tab, role: 'read' });
  } else if (cur.source === 'storage') writeStorage(ROLE_STORAGE_KEY, 'read');
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

/** 테스트용: 메모리·탭 범위 상태를 비운다(localStorage 는 setup 이 비운다). */
export function resetAuthForTests(): void {
  memory = null;
  memoryRoleForEnv = null;
  tabFallback = null;
  pendingPin = null;
  writeStorage(TAB_TOKEN_KEY, null, 'session');
  writeStorage(TAB_ROLE_KEY, null, 'session');
  writeStorage(TAB_REASON_KEY, null, 'session');
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
