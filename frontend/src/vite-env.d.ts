/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API 접두. 기본 `/api` (vite dev 프록시가 FastAPI로 넘김) */
  readonly VITE_API_BASE?: string;
  /** 개발용 Bearer 토큰. 운영에서는 localStorage `sa.token`에 사용자가 넣는다 */
  readonly VITE_API_TOKEN?: string;
  /** "true"면 MSW로 API를 대신한다 (`npm run dev:msw`는 mode=msw로 자동) */
  readonly VITE_MSW?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
