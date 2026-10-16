import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { resetAuthForTests } from '@/api/auth';
import { registerStrings } from '@/i18n';
import ko from '@/i18n/ko.json';
import { server } from '@/mocks/server';

// R11-I18N: 앱은 core 만 정적으로 싣고 이름공간은 라우트가 받는다 — 테스트는 ko.json 전체를 처음부터 등록한다
// (지연 로드 경로 자체는 src/i18n/namespaces.test.ts·routeNamespaces.test.ts 가 본다)
registerStrings(ko);

// 화면은 라우트별 지연 로드 청크다 — 병렬 실행 부하에서도 첫 findBy 가 1초 기본값에 걸리지 않게(모든 테스트 파일)
configure({ asyncUtilTimeout: 5000 });

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
  resetAuthForTests();
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

// jsdom 에는 object URL 이 없다 — 다운로드(saveBlob)·원문 이미지 미리보기가 쓴다. 테스트는 spyOn 으로 본다.
if (typeof URL.createObjectURL !== 'function') {
  let n = 0;
  Object.defineProperty(URL, 'createObjectURL', {
    writable: true,
    value: (_blob: Blob) => `blob:mock/${++n}`,
  });
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: (_url: string) => {} });
}
