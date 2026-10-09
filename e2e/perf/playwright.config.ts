import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import os from 'node:os';
import { BACKEND, backendCommand, backendEnv, FRONTEND, OUTPUT_DIR, WRITE_TOKEN } from '../env';

/**
 * T16 성능 측정(RA §9) — 합성 1,000단지(`devseed --synth 1000`, contracts/fixtures/tools/synth.py) 위 실제 API + 프론트.
 * 실행: `cd e2e && npm run perf` (또는 `python scripts/tasks.py regress --perf`).
 * 출력: API 첫 페이지 응답 시간(size 50 · G2 가 실제로 부르는 size 1000), G2 스크롤 rAF 프레임 간격(p50·p95·max·fps).
 * 결과 JSON = perf/perf-results.json (무시 목록: playwright-report 아래).
 */
const API_PORT = Number(process.env.E2E_PERF_API_PORT ?? 18866);
const WEB_PORT = Number(process.env.E2E_PERF_WEB_PORT ?? 15493);
const DATA = (process.env.E2E_PERF_DATA ?? path.join(os.tmpdir(), 'sa-e2e-perf')).replaceAll('\\', '/');
process.env.E2E_PERF_API = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.perf\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 30_000 },
  outputDir: path.join(OUTPUT_DIR, 'perf'),
  reporter: [['list']],
  use: { baseURL: `http://localhost:${WEB_PORT}`, locale: 'ko-KR' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: backendCommand(API_PORT, '--synth 1000'),
      cwd: BACKEND,
      env: backendEnv(DATA),
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 300_000,
    },
    {
      // 운영 빌드로 잰다(개발 서버의 React 개발 모드·HMR 비용은 사용자 화면에 없다) — vite preview 도 /api 프록시(server.proxy)를 쓴다
      command: `npx vite build --outDir ${DATA}/web-dist --emptyOutDir && npx vite preview --outDir ${DATA}/web-dist --port ${WEB_PORT} --strictPort`,
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
