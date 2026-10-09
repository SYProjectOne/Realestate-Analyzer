/**
 * 실 API e2e 공통 설정 — playwright.config.ts(서버 기동)와 spec(워커 1회 실행·토큰)이 같이 쓴다.
 * 백엔드는 devseed 픽스처를 깐 임시 SQLite 위 uvicorn, 판정기는 mock(호출 없음).
 */
import { execFileSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const FRONTEND = fileURLToPath(new URL('../..', import.meta.url));
export const BACKEND = path.resolve(FRONTEND, '..', 'backend');
export const API_PORT = Number(process.env.E2E_API_PORT ?? 18765);
export const WEB_PORT = Number(process.env.E2E_API_WEB_PORT ?? 15392);
/** 쓰기 토큰(API_TOKEN) — vite 에 VITE_API_TOKEN 으로도 넘긴다(앱 기본 토큰) */
export const WRITE_TOKEN = process.env.E2E_API_TOKEN ?? 'e2e-write-token-0123456789abcdef';
/** 읽기 전용 토큰(READONLY_TOKEN) — GET 만 */
export const READ_TOKEN = process.env.E2E_API_READ_TOKEN ?? 'e2e-read-token-0123456789abcdef';
const DATA = (process.env.E2E_API_DATA ?? path.join(os.tmpdir(), 'sa-e2e-api')).replaceAll(
  '\\',
  '/',
);

export const backendEnv: Record<string, string> = {
  ENV: 'dev',
  DATABASE_URL: `sqlite:///${DATA}/e2e.db`,
  RAW_DIR: `${DATA}/raw`,
  REPORT_DIR: `${DATA}/reports`,
  REFERENCE_DIR: `${DATA}/reference`,
  API_TOKEN: WRITE_TOKEN,
  READONLY_TOKEN: READ_TOKEN,
  JUDGE_ADAPTER: 'mock',
  LOG_JSON: 'false',
};

/**
 * 큐에 쌓인 잡을 비울 때까지 1회 실행(`python -m app.worker --once`) — 보고서 생성 같은 잡을 테스트 안에서 끝낸다.
 * 상주 worker 를 띄우지 않으므로 다른 테스트가 넣은 잡이 몰래 돌지 않는다.
 */
export function runWorkerOnce(): void {
  execFileSync('uv', ['run', 'python', '-m', 'app.worker', '--once'], {
    cwd: BACKEND,
    env: { ...process.env, ...backendEnv },
    stdio: 'pipe',
    timeout: 120_000,
  });
}
