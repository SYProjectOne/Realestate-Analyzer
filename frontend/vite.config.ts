/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';
import { entryViolations, type ChunkLike } from './scripts/lib/bundle-guards';

// API 서버(FastAPI) origin. 프론트는 항상 `/api` 접두로 부르고, dev 서버는 경로를 **그대로** 넘긴다
// (FastAPI 라우터가 API_PREFIX=/api 아래에 있고 nginx 도 /api 를 떼지 않는다 → 개발·운영 경로가 같다).
// 대상에 /api 를 붙이지 않는다: API_PROXY_TARGET=http://127.0.0.1:18765 (O), …/api (X).
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

/** 최대 JS 청크 크기(kB, 압축 전) — R3c 완료 기준 */
const MAX_CHUNK_KB = 500;

/** 빌드 산출 청크가 MAX_CHUNK_KB 를 넘으면 경고가 아니라 실패 */
function maxChunkGuard(): Plugin {
  return {
    name: 'max-chunk-guard',
    apply: 'build',
    generateBundle(_options, bundle) {
      const over = Object.values(bundle)
        .filter((item) => item.type === 'chunk')
        .map((chunk) => ({ name: chunk.fileName, kb: Buffer.byteLength(chunk.code) / 1000 }))
        .filter((chunk) => chunk.kb > MAX_CHUNK_KB);
      if (over.length > 0) {
        this.error(
          `청크가 ${MAX_CHUNK_KB}kB 를 넘는다: ${over.map((c) => `${c.name} ${c.kb.toFixed(1)}kB`).join(', ')}`,
        );
      }
    },
  };
}

/**
 * R5-FE2: 진입 청크의 정적 닫힘(첫 화면이 실행 전에 반드시 받는 JS)에 echarts·zrender·msw 가 끼거나 예산을 넘으면 실패
 * (scripts/lib/bundle-guards.ts). 모든 빌드 모드(운영·msw)에 건다.
 */
function entryChunkGuard(): Plugin {
  return {
    name: 'entry-chunk-guard',
    apply: 'build',
    generateBundle(_options, bundle) {
      const chunks = Object.values(bundle).filter(
        (item): item is typeof item & ChunkLike => item.type === 'chunk',
      );
      const problems = entryViolations(chunks);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
  };
}

/** 첫 화면 공용 라이브러리(React·라우터·쿼리) — 'vendor' 청크(진입이 정적으로 import, 앱 코드와 따로 캐시) */
const VENDOR =
  /\/node_modules\/(react|react-dom|scheduler|react-router|cookie|set-cookie-parser|@tanstack\/(react-query|query-core))\//;

export default defineConfig(({ mode }) => ({
  plugins: [react(), maxChunkGuard(), entryChunkGuard()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    // R3c 완료 기준: 최대 청크 ≤ 500kB — maxChunkGuard 가 넘으면 빌드를 실패시킨다
    chunkSizeWarningLimit: MAX_CHUNK_KB,
    rollupOptions: {
      output: {
        // echarts(트리 셰이킹 후에도 ~650kB)를 렌더 엔진(zrender + 공용 tslib)과 echarts 로 나눈다(순환 청크 없음).
        // 둘 다 차트가 뷰포트에 들어올 때 lazy 로 받는다(EChart.tsx).
        // R5-FE2: rollup 은 수동 청크 모듈의 정적 의존성 중 주인 없는 것을 그 청크로 끌어간다 — 공용 도우미(`\0commonjsHelpers`·
        // `\0vite/preload-helper`)가 zrender·msw 청크로 들어가 진입 청크가 그 청크들을 정적으로 import 했다(첫 화면 +196kB,
        // MSW 빌드는 +296kB). 도우미('\0' 가상 모듈)와 React 계열은 'vendor' 로 못박는다. entry-chunk-guard 가 회귀를 막는다.
        manualChunks(id) {
          const path = id.replace(/\\/g, '/');
          if (VENDOR.test(path)) return 'vendor';
          if (id.startsWith('\0') && !path.includes('/node_modules/')) return 'vendor';
          if (!path.includes('/node_modules/')) return undefined;
          if (/\/node_modules\/(zrender|tslib)\//.test(path)) return 'zrender';
          // MSW 모드 빌드(e2e/pages·dev:msw) 전용 — 운영 빌드에는 없다(main.tsx 의 죽은 동적 import 로 모듈만 해석돼
          // 빈 'msw' 청크 경고가 나므로 운영 빌드에서는 이름을 붙이지 않는다)
          if (
            mode !== 'production' &&
            /\/node_modules\/(msw|@mswjs|@bundled-es-modules)\//.test(path)
          )
            return 'msw';
          if (path.includes('/node_modules/echarts/')) return 'echarts';
          return undefined;
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'eslint-rules/**/*.test.{js,ts}', 'scripts/**/*.test.ts'],
    css: false,
    restoreMocks: true,
    // 모든 파일 같은 값(6차 리뷰: `_shared/testing` 을 import 하지 않는 파일은 vitest 기본 5초라 findBy 5초와 겹쳐
    // 부하에서 'Test timed out' 으로 먼저 끊겼다). 화면 하나가 쿼리·지연 로드 청크를 여럿 기다린다.
    testTimeout: 20_000,
  },
}));
