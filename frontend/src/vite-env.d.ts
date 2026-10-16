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

/** R11-I18N: ko.json 에서 빌드 때 나눈 문자열(vite.config.ts `ko-split`, 규칙은 src/i18n/namespaces.ts) */
declare module 'virtual:ko/core' {
  import type { KoTree } from '@/i18n/namespaces';
  const tree: KoTree;
  export default tree;
}
declare module 'virtual:ko/ns/*' {
  import type { KoTree } from '@/i18n/namespaces';
  const tree: KoTree;
  export default tree;
}
/** 점 경로 아래 키 목록(예: `virtual:ko/keys/glossary.items`) — 본문 없이 키 이름만 */
declare module 'virtual:ko/keys/*' {
  const keys: string[];
  export default keys;
}
