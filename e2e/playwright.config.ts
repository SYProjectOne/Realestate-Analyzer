import { defineConfig, devices } from '@playwright/test';
import { API_PORT, BACKEND, backendCommand, backendEnv, FRONTEND, WEB_PORT, WRITE_TOKEN } from './env';

/**
 * WP9 R3 사용자 흐름 e2e — 실제 API(uvicorn, devseed DB) + Mock 판정기 + 실제 프론트(vite, MSW 끔).
 * 실행: `cd e2e && npm ci && npm test` (또는 저장소 루트 `python scripts/tasks.py regress`).
 *
 * 흐름(frontend/e2e/api 의 화면 단위 스모크와 겹치지 않게 '흐름' 단위):
 *  1. G8 보고서 PDF 생성 → worker → 다운로드(T15)
 *  2. G7 사람 확인 '가능' → 재판정 잡 → worker → G1 TOP 5·접수 배지 변화(T3)
 *  3. G0 자유 지명 '송도' → 후보 선택 → POST /regions → bootstrap 잡(녹화 재생) → G1 결과
 * 순서가 상태에 의존한다(같은 DB) — 파일 이름 번호 순서, worker 1개, 직렬.
 */
export default defineConfig({
  testDir: './flows',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  outputDir: './test-results',
  reporter: [['list'], ['json', { outputFile: 'playwright-report/results.json' }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    locale: 'ko-KR',
    acceptDownloads: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: backendCommand(API_PORT),
      cwd: BACKEND,
      env: backendEnv(),
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 300_000,
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
