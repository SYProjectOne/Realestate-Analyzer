import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

/**
 * WP5 프론트 연결 스모크 — MSW 없이 실제 API(FastAPI + devseed 픽스처 DB)로 G1·G2·G3를 1개씩 확인한다.
 * 실행(frontend/에서): `npx playwright test -c e2e/api`
 *  - backend: `python -m app.api.devseed`(인천·김포 픽스처 → 임시 SQLite) 후 uvicorn 기동(쓰기 토큰 필요)
 *  - web: vite dev(MSW 끔). `/api` 프록시 → API_PROXY_TARGET(= backend/api, vite 가 /api 를 떼므로 대상에 다시 붙인다)
 * 저장소 루트 e2e/(WP9 통합)와 별개다.
 */
const FRONTEND = fileURLToPath(new URL('../..', import.meta.url));
const BACKEND = path.resolve(FRONTEND, '..', 'backend');
const API_PORT = Number(process.env.E2E_API_PORT ?? 18765);
const WEB_PORT = Number(process.env.E2E_API_WEB_PORT ?? 15392);
const TOKEN = process.env.E2E_API_TOKEN ?? 'e2e-write-token-0123456789abcdef';
const DATA = (process.env.E2E_API_DATA ?? path.join(os.tmpdir(), 'sa-e2e-api')).replaceAll(
  '\\',
  '/',
);

const backendEnv: Record<string, string> = {
  ENV: 'dev',
  DATABASE_URL: `sqlite:///${DATA}/e2e.db`,
  RAW_DIR: `${DATA}/raw`,
  REPORT_DIR: `${DATA}/reports`,
  REFERENCE_DIR: `${DATA}/reference`,
  API_TOKEN: TOKEN,
  JUDGE_ADAPTER: 'mock',
  LOG_JSON: 'false',
};

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    locale: 'ko-KR',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `uv run python -m app.api.devseed && uv run uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: BACKEND,
      env: backendEnv,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 240_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      cwd: FRONTEND,
      env: {
        API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}/api`,
        VITE_API_TOKEN: TOKEN,
        VITE_MSW: 'false',
      },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
