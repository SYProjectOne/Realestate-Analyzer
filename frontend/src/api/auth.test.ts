import { http, HttpResponse } from 'msw';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import {
  getAuthSnapshot,
  getAuthToken,
  markReadOnly,
  ROLE_STORAGE_KEY,
  setAuth,
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
