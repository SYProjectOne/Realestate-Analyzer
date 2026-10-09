import { http, HttpResponse } from 'msw';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import {
  clearAuth,
  getAuthSnapshot,
  getAuthToken,
  hasStoredWriteToken,
  markReadOnly,
  releaseTabPin,
  ROLE_STORAGE_KEY,
  setAuth,
  setTabAuth,
  subscribeAuth,
  TAB_ROLE_KEY,
  TAB_TOKEN_KEY,
  TOKEN_STORAGE_KEY,
} from './auth';
import { apiFetch, ApiError, probeToken } from './client';

describe('토큰 저장소', () => {
  it('setAuth → localStorage(토큰·권한) → Bearer', async () => {
    expect(setAuth('  tok-w  ', 'write')).toEqual({ persisted: true });
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-w');
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('write');
    let auth: string | null = null;
    server.use(
      http.get(mswPath('/scenarios'), ({ request }) => {
        auth = request.headers.get('authorization');
        return HttpResponse.json([]);
      }),
    );
    await apiFetch('/scenarios');
    expect(auth).toBe('Bearer tok-w');
  });

  it('localStorage 가 막혀 있으면(예외) 메모리에만 두고 persisted=false', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    expect(setAuth('tok-mem', 'read')).toEqual({ persisted: false });
    expect(getAuthToken()).toBe('tok-mem');
    expect(getAuthSnapshot()).toMatchObject({ source: 'memory', role: 'read', canWrite: false });
  });

  it('쓰기 요청이 403 forbidden → 읽기 전용으로 표시(쓰기 버튼 끔)', async () => {
    setAuth('tok-x', 'write');
    server.use(
      http.post(mswPath('/jobs'), () =>
        HttpResponse.json(
          { code: 'forbidden', detail: '읽기 전용 토큰은 GET 만 허용한다' },
          { status: 403 },
        ),
      ),
    );
    await expect(
      apiFetch('/jobs', { method: 'POST', body: { job_name: 'retry', payload: {} } }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(getAuthSnapshot()).toMatchObject({ role: 'read', canWrite: false });
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('read');
  });

  it('markReadOnly 는 토큰이 없으면 아무것도 안 한다', () => {
    markReadOnly();
    expect(getAuthSnapshot().canWrite).toBe(true);
  });

  it('401 → 토큰 다이얼로그 요청(토큰 없음 = missing, 있음 = invalid)', async () => {
    server.use(
      http.get(mswPath('/scenarios'), () =>
        HttpResponse.json(
          { code: 'unauthorized', detail: 'Bearer 토큰이 필요하다' },
          { status: 401 },
        ),
      ),
    );
    await expect(apiFetch('/scenarios')).rejects.toBeInstanceOf(ApiError);
    expect(getAuthSnapshot().prompt).toBe('missing');
    setAuth('tok-bad', 'write'); // 저장하면 요청 상태가 지워진다
    expect(getAuthSnapshot().prompt).toBeNull();
    await expect(apiFetch('/scenarios')).rejects.toBeInstanceOf(ApiError);
    expect(getAuthSnapshot().prompt).toBe('invalid');
  });
});

describe('probeToken — 401 / 읽기 전용(403) / 쓰기(422)', () => {
  const tokens = { 'tok-write': 'write', 'tok-read': 'read' } as const;
  beforeEach(() => {
    server.use(
      http.get(mswPath('/regions'), ({ request }) => {
        const tok = request.headers.get('authorization')?.replace('Bearer ', '') ?? '';
        return tok in tokens
          ? HttpResponse.json([])
          : HttpResponse.json({ code: 'unauthorized', detail: 'x' }, { status: 401 });
      }),
      http.post(mswPath('/jobs'), ({ request }) => {
        const tok = request.headers.get('authorization')?.replace('Bearer ', '') ?? '';
        return tokens[tok as keyof typeof tokens] === 'read'
          ? HttpResponse.json({ code: 'forbidden', detail: 'x' }, { status: 403 })
          : HttpResponse.json({ code: 'validation_error', detail: 'x' }, { status: 422 });
      }),
    );
  });
  it.each([
    ['tok-write', 'write'],
    ['tok-read', 'read'],
    ['tok-nope', 'invalid'],
  ])('%s → %s', async (token, expected) => {
    expect(await probeToken(token)).toBe(expected);
  });
  it('확인은 저장소를 바꾸지 않는다', async () => {
    await probeToken('tok-read');
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });
});

describe('N-M7 탭 범위 토큰(sessionStorage) · 다른 탭 저장소 변경', () => {
  /** 다른 탭이 localStorage 를 바꾼 것처럼: 값을 쓰고 storage 이벤트를 보낸다(jsdom 은 같은 창에 이벤트를 안 낸다) */
  function otherTabSets(token: string, role: 'write' | 'read' | null) {
    const oldToken = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    const oldRole = window.localStorage.getItem(ROLE_STORAGE_KEY);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    if (role) window.localStorage.setItem(ROLE_STORAGE_KEY, role);
    else window.localStorage.removeItem(ROLE_STORAGE_KEY);
    window.dispatchEvent(
      new StorageEvent('storage', { key: TOKEN_STORAGE_KEY, oldValue: oldToken, newValue: token }),
    );
    if (oldRole !== role) {
      window.dispatchEvent(
        new StorageEvent('storage', { key: ROLE_STORAGE_KEY, oldValue: oldRole, newValue: role }),
      );
    }
  }

  it('setTabAuth → 이 탭(sessionStorage)만, localStorage 쓰기 토큰은 그대로 · 탭 토큰이 우선', () => {
    setAuth('tok-w', 'write');
    expect(setTabAuth('tok-share', 'read')).toEqual({ persisted: true });
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBe('tok-share');
    expect(window.sessionStorage.getItem(TAB_ROLE_KEY)).toBe('read');
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-w');
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('write');
    expect(getAuthToken()).toBe('tok-share');
    expect(getAuthSnapshot()).toMatchObject({
      token: 'tok-share',
      role: 'read',
      source: 'tab',
      canWrite: false,
      externalChange: false,
    });
  });

  it('sessionStorage 가 막혀 있어도(예외) 탭 토큰은 이 탭 메모리에서 우선한다', () => {
    setAuth('tok-w', 'write');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    expect(setTabAuth('tok-share', 'read')).toEqual({ persisted: false });
    expect(getAuthSnapshot()).toMatchObject({ token: 'tok-share', source: 'tab', canWrite: false });
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('tok-w');
  });

  it('setAuth(토큰 다이얼로그 저장)·clearAuth 는 탭 토큰도 지운다', () => {
    setTabAuth('tok-share', 'read');
    setAuth('tok-w2', 'write');
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
    expect(getAuthSnapshot()).toMatchObject({ token: 'tok-w2', source: 'storage' });
    setTabAuth('tok-share', 'read');
    clearAuth();
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
    expect(getAuthSnapshot().token).toBeNull();
  });

  it('hasStoredWriteToken: 저장 토큰이 write·권한 모름이면 true, read·없음이면 false', () => {
    expect(hasStoredWriteToken()).toBe(false);
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-unknown');
    expect(hasStoredWriteToken()).toBe(true);
    setAuth('tok-w', 'write');
    expect(hasStoredWriteToken()).toBe(true);
    setAuth('tok-r', 'read');
    expect(hasStoredWriteToken()).toBe(false);
  });

  it('다른 탭이 저장 토큰을 읽기 전용 토큰으로 바꾸면 이 탭은 기존 쓰기 토큰을 탭에 고정 + externalChange', () => {
    const unsubscribe = subscribeAuth(() => {});
    setAuth('tok-w', 'write');
    expect(getAuthSnapshot()).toMatchObject({ token: 'tok-w', source: 'storage', canWrite: true });
    otherTabSets('tok-share', 'read');
    expect(getAuthSnapshot()).toMatchObject({
      token: 'tok-w',
      role: 'write',
      source: 'tab',
      canWrite: true,
      externalChange: true,
    });
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBe('tok-w');
    // "새 토큰 사용" → 고정을 풀고 저장소의 새 토큰(읽기 전용)으로
    releaseTabPin();
    expect(getAuthSnapshot()).toMatchObject({
      token: 'tok-share',
      role: 'read',
      source: 'storage',
      canWrite: false,
      externalChange: false,
    });
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
    unsubscribe();
  });

  it('권한 모름(null) 저장 토큰도 고정한다(role 없이)', () => {
    const unsubscribe = subscribeAuth(() => {});
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-unknown');
    expect(getAuthSnapshot()).toMatchObject({ source: 'storage', role: null });
    otherTabSets('tok-share', 'read');
    expect(getAuthSnapshot()).toMatchObject({
      token: 'tok-unknown',
      role: null,
      source: 'tab',
      canWrite: true,
      externalChange: true,
    });
    unsubscribe();
  });

  it('토큰 쓰기와 권한 쓰기가 이벤트 두 개로 따로 와도(권한이 나중) 고정한다', () => {
    const unsubscribe = subscribeAuth(() => {});
    setAuth('tok-w', 'write');
    getAuthSnapshot();
    // 1) 토큰만 바뀐 중간 상태(권한은 아직 write)
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-share');
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: TOKEN_STORAGE_KEY,
        oldValue: 'tok-w',
        newValue: 'tok-share',
      }),
    );
    getAuthSnapshot();
    // 2) 권한이 read 로
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    window.dispatchEvent(
      new StorageEvent('storage', { key: ROLE_STORAGE_KEY, oldValue: 'write', newValue: 'read' }),
    );
    expect(getAuthSnapshot()).toMatchObject({
      token: 'tok-w',
      source: 'tab',
      canWrite: true,
      externalChange: true,
    });
    unsubscribe();
  });

  it('다른 탭이 다른 쓰기 토큰으로 바꾸거나, 이 탭이 읽기 전용이었으면 고정하지 않는다', () => {
    const unsubscribe = subscribeAuth(() => {});
    setAuth('tok-w', 'write');
    getAuthSnapshot();
    otherTabSets('tok-w2', 'write');
    expect(getAuthSnapshot()).toMatchObject({
      token: 'tok-w2',
      source: 'storage',
      externalChange: false,
    });
    setAuth('tok-r', 'read');
    getAuthSnapshot();
    otherTabSets('tok-share', 'read');
    expect(getAuthSnapshot()).toMatchObject({ token: 'tok-share', source: 'storage' });
    expect(window.sessionStorage.getItem(TAB_TOKEN_KEY)).toBeNull();
    unsubscribe();
  });

  it('같은 토큰이 다른 탭에서 403 으로 읽기 전용 표시되면 고정하지 않는다(진짜 읽기 전용)', () => {
    const unsubscribe = subscribeAuth(() => {});
    setAuth('tok-w', 'write');
    getAuthSnapshot();
    window.localStorage.setItem(ROLE_STORAGE_KEY, 'read');
    window.dispatchEvent(
      new StorageEvent('storage', { key: ROLE_STORAGE_KEY, oldValue: 'write', newValue: 'read' }),
    );
    expect(getAuthSnapshot()).toMatchObject({ token: 'tok-w', source: 'storage', canWrite: false });
    unsubscribe();
  });

  it('스냅샷 동일성: externalChange 가 바뀌면 새 객체, 같으면 같은 객체', () => {
    setAuth('tok-w', 'write');
    const a = getAuthSnapshot();
    expect(getAuthSnapshot()).toBe(a);
    const unsubscribe = subscribeAuth(() => {});
    otherTabSets('tok-share', 'read');
    const b = getAuthSnapshot();
    expect(b).not.toBe(a);
    expect(b.externalChange).toBe(true);
    expect(getAuthSnapshot()).toBe(b);
    unsubscribe();
  });

  it('탭 토큰으로 쓰기 요청이 403 → 탭 권한만 read(저장소 쓰기 토큰은 그대로)', async () => {
    setAuth('tok-w', 'write');
    setTabAuth('tok-x', null);
    server.use(
      http.post(mswPath('/jobs'), () =>
        HttpResponse.json({ code: 'forbidden', detail: 'x' }, { status: 403 }),
      ),
    );
    await expect(
      apiFetch('/jobs', { method: 'POST', body: { job_name: 'retry', payload: {} } }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(getAuthSnapshot()).toMatchObject({ token: 'tok-x', role: 'read', source: 'tab' });
    expect(window.localStorage.getItem(ROLE_STORAGE_KEY)).toBe('write');
  });
});
