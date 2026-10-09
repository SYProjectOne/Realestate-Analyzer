/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

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

export default defineConfig({
  plugins: [react(), maxChunkGuard()],
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
        // echarts(트리 셰이킹 후에도 ~650kB)를 렌더 엔진(zrender)·계열·나머지로 나눈다. 셋 다 차트가
        // 뷰포트에 들어올 때 lazy 로 받는다(EChart.tsx).
        manualChunks(id) {
          const path = id.replace(/\\/g, '/');
          if (!path.includes('/node_modules/')) return undefined;
          if (path.includes('/node_modules/zrender/')) return 'zrender';
          if (path.includes('/node_modules/echarts/lib/chart/')) return 'echarts-charts';
          if (path.includes('/node_modules/echarts/lib/component/')) return 'echarts-components';
          if (path.includes('/node_modules/echarts/')) return 'echarts-core';
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
  },
});
