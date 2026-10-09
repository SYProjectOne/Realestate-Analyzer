/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// API 서버(FastAPI) origin. 프론트는 항상 `/api` 접두로 부르고, dev 서버는 경로를 **그대로** 넘긴다
// (FastAPI 라우터가 API_PREFIX=/api 아래에 있고 nginx 도 /api 를 떼지 않는다 → 개발·운영 경로가 같다).
// 대상에 /api 를 붙이지 않는다: API_PROXY_TARGET=http://127.0.0.1:18765 (O), …/api (X).
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
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
    chunkSizeWarningLimit: 1200,
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
