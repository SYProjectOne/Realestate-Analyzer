/**
 * e2e 공통 설정(WP9 R3) — playwright.config.ts(서버 기동)와 spec(worker 실행·API 확인)이 같이 쓴다.
 *
 * 백엔드: `python -m app.api.devseed`(인천·김포 픽스처 → 임시 SQLite) → `support/reference_offline.py`
 * (reference.refresh 잡을 공식 사본으로, 네트워크 없음) → uvicorn. 판정기 = Mock(JUDGE_ADAPTER=mock).
 * 잡은 상주 worker 없이 테스트가 직접 돌린다:
 *  - `runWorkerOnce()` = 실제 CLI `python -m app.worker --once` (재판정·보고서 — 수집 없음)
 *  - `runReplayWorker()` = 같은 진입점(runner.main --once)에 녹화 재생 수집기를 넣은 대역(지역 bootstrap —
 *    worker CLI 에 녹화 재생 모드가 없어서; support/replay_worker.py 머리말 참고)
 */
import { execFileSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const E2E = fileURLToPath(new URL('.', import.meta.url));
export const ROOT = path.resolve(E2E, '..');
export const BACKEND = path.join(ROOT, 'backend');
export const FRONTEND = path.join(ROOT, 'frontend');
export const API_PORT = Number(process.env.E2E_FLOW_API_PORT ?? 18865);
export const WEB_PORT = Number(process.env.E2E_FLOW_WEB_PORT ?? 15492);
export const WRITE_TOKEN = process.env.E2E_FLOW_TOKEN ?? 'e2e-flow-write-token-0123456789ab';
export const READ_TOKEN = process.env.E2E_FLOW_READ_TOKEN ?? 'e2e-flow-read-token-0123456789abc';
export const DATA = (process.env.E2E_FLOW_DATA ?? path.join(os.tmpdir(), 'sa-e2e-flows')).replaceAll('\\', '/');
export const API = `http://127.0.0.1:${API_PORT}`;

export function backendEnv(data: string = DATA): Record<string, string> {
  return {
    ENV: 'dev',
    DATABASE_URL: `sqlite:///${data}/e2e.db`,
    RAW_DIR: `${data}/raw`,
    REPORT_DIR: `${data}/reports`,
    REFERENCE_DIR: `${data}/reference`,
    API_TOKEN: WRITE_TOKEN,
    READONLY_TOKEN: READ_TOKEN,
    JUDGE_ADAPTER: 'mock',
    LOG_JSON: 'false',
    LOG_LEVEL: 'WARNING',
    // 저장소 .env(실제 키)를 읽지 않게
    ENV_FILE: `${data}/none.env`,
  };
}

/** 백엔드 서버 명령: devseed → 참조 표(오프라인) → uvicorn */
export function backendCommand(port: number, extraSeed = ''): string {
  return [
    `uv run python -m app.api.devseed ${extraSeed}`.trim(),
    'uv run python ../e2e/support/reference_offline.py',
    `uv run uvicorn app.main:app --host 127.0.0.1 --port ${port}`,
  ].join(' && ');
}

function uv(args: string[]): string {
  return execFileSync('uv', ['run', ...args], {
    cwd: BACKEND,
    env: { ...process.env, ...backendEnv() },
    encoding: 'utf-8',
    stdio: 'pipe',
    timeout: 300_000,
  });
}

/** 실제 worker CLI 1회(`python -m app.worker --once`) — 큐를 비운다 */
export function runWorkerOnce(): string {
  return uv(['python', '-m', 'app.worker', '--once']);
}

/** 녹화 재생 수집기 worker 1회(지역 bootstrap) */
export function runReplayWorker(): string {
  return uv(['python', '../e2e/support/replay_worker.py']);
}

export const AUTH = { Authorization: `Bearer ${WRITE_TOKEN}` };
