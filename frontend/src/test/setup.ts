import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { server } from '@/mocks/server';

// 계약 밖 요청은 조용히 통과시키지 않는다 — 핸들러가 없으면 테스트가 실패한다.
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
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
