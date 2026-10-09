import { defineConfig, devices } from '@playwright/test';
import { API_PORT, BACKEND, backendEnv, FRONTEND, WEB_PORT, WRITE_TOKEN } from './env';

/**
 * 실 API e2e — MSW 없이 FastAPI + devseed 픽스처 DB(임시 SQLite)로 화면 G0~G8 과 다운로드·토큰을 확인한다.
 * 실행(frontend/에서): `npm run e2e:api` (= `npx playwright test -c e2e/api`)
 *  - backend: `python -m app.api.devseed`(인천·김포 픽스처 → 임시 SQLite) 후 uvicorn(쓰기·읽기 전용 토큰 둘 다 켬)
 *  - web: vite dev(MSW 끔). `/api` 프록시 → API_PROXY_TARGET(= backend origin, 경로는 /api 그대로)
 *  - 잡(보고서 등)은 상주 worker 없이 테스트가 `runWorkerOnce()`로 한 번 돌린다(env.ts)
 * 각 테스트는 화면이 부른 API 응답이 전부 2xx 인지 본다(4xx/5xx 0건).
 */
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
    acceptDownloads: true,
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
        API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}`,
        VITE_API_TOKEN: WRITE_TOKEN,
        VITE_MSW: 'false',
      },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
