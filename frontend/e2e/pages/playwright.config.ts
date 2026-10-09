import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

/**
 * WP6a 화면 e2e — MSW 모드 dev 서버(계약 예시 응답)로 화면 10개 핵심 요소를 확인한다.
 * 실행: `npx playwright test -c e2e/pages` (frontend/에서). 최초 1회 `npx playwright install chromium`.
 * 저장소 루트 e2e/(WP9, 실제 API)와 별개다.
 */
const PORT = Number(process.env.E2E_PAGES_PORT ?? 5175);
const FRONTEND = fileURLToPath(new URL('../..', import.meta.url));

export default defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    locale: 'ko-KR',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run dev:msw -- --port ${PORT} --strictPort`,
    cwd: FRONTEND,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
