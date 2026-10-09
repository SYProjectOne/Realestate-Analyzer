import { defineConfig, devices } from '@playwright/test';

/**
 * 프론트 스모크 e2e — MSW 모드 dev 서버(API 없이 계약 예시 응답)로 화면 골격을 확인한다.
 * 실제 API + Mock 판정기 통합 e2e는 저장소 루트 e2e/(WP9) 소관.
 */
const PORT = Number(process.env.E2E_PORT ?? 5174);

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    locale: 'ko-KR',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run dev:msw -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
