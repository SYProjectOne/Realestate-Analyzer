import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { server } from '@/mocks/server';

// 계약 밖 요청은 조용히 통과시키지 않는다 — 핸들러가 없으면 테스트가 실패한다.
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
  // jsdom의 AbortSignal은 Node(undici) fetch가 거부한다("Expected signal to be an instance of AbortSignal").
  // TanStack Query가 넘기는 signal을 테스트에서만 떼어 낸다(MSW가 패치한 fetch보다 바깥에 감싼다).
  // React Router 데이터 라우터도 내비게이션마다 new Request(url, { signal })를 만든다 → 같은 처리.
  if (typeof window !== 'undefined') {
    const NativeRequest = globalThis.Request;
    globalThis.Request = class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(input, init?.signal ? { ...init, signal: undefined } : init);
      }
    };
    const patchedFetch = globalThis.fetch;
    globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
      patchedFetch(input, init?.signal ? { ...init, signal: undefined } : init);
  }
});
afterEach(() => {
  server.resetHandlers();
  cleanup();
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.clear();
    } catch {
      // 무시
    }
    document.documentElement.classList.remove('dark');
  }
});
afterAll(() => server.close());

if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
