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
 * devseed DB 의 스냅샷 degraded 플래그를 바꾼다(T18 — 판정기 다운 스냅샷). API 는 이 행을 그대로 읽는다:
 * `/health` judge = 지역 최신 스냅샷 degraded, `/regions/{id}/snapshots`·스냅샷 화면 = 그 스냅샷 degraded.
 * 테스트가 끝나면 원래 값(false)으로 되돌린다.
 */
export function setSnapshotDegraded(snapshotId: number, degraded: boolean): void {
  const db = backendEnv.DATABASE_URL!.replace(/^sqlite:\/\/\//, '');
  execFileSync(
    'uv',
    [
      'run',
      'python',
      '-c',
      'import sqlite3, sys\n' +
        'c = sqlite3.connect(sys.argv[1])\n' +
        'n = c.execute("update snapshot set degraded = ? where id = ?", (int(sys.argv[2]), int(sys.argv[3]))).rowcount\n' +
        'c.commit()\n' +
        'sys.exit(0 if n == 1 else 3)',
      db,
      degraded ? '1' : '0',
      String(snapshotId),
    ],
    { cwd: BACKEND, env: { ...process.env, ...backendEnv }, stdio: 'pipe', timeout: 60_000 },
  );
}

/**
 * devseed DB 의 한 단지에 공고 명시 할인(D11-6, 계약 .8 `payment_terms.discount_by_type`)을 넣거나 지운다.
 * devseed 픽스처에는 할인이 없어(contracts/fixtures 읽기 전용) 테스트 DB 에만 쓴다: 그 단지의 모든 납부 조건 행 ×
 * 모든 주택형에 `won` 원 + 출처 행(field_provenance 'discount_by_type.<type_code>', chosen, 라벨 `label`).
 * `label` 이 null 이면 할인·출처 행을 지워 원래대로(할인 없음) 되돌린다.
 */
export function setDiscount(complexId: number, label: string | null, won = 10_000_000): void {
  const db = backendEnv.DATABASE_URL!.replace(/^sqlite:\/\/\//, '');
  execFileSync(
    'uv',
    [
      'run',
      'python',
      '-c',
      [
        'import json, sqlite3, sys',
        'db, cid, label, won = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])',
        'c = sqlite3.connect(db)',
        'types = [r[0] for r in c.execute("select type_code from complex_type where complex_id = ?", (cid,))]',
        'pts = [r[0] for r in c.execute("select id from payment_terms where complex_id = ?", (cid,))]',
        'if not types or not pts: sys.exit(3)',
        'for pt in pts:',
        "    c.execute(\"delete from field_provenance where entity = 'payment_terms' and entity_id = ? and field like 'discount_by_type.%'\", (pt,))",
        '    disc = {t: won for t in types} if label else {}',
        '    c.execute("update payment_terms set discount_by_type = ? where id = ?", (json.dumps(disc), pt))',
        '    for t in types if label else []:',
        '        c.execute("insert into field_provenance (entity, entity_id, field, value_text, url, checked_at, label, reason, source_rank, chosen, value_norm) values (\'payment_terms\', ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)", (pt, "discount_by_type." + t, str(won), "https://www.applyhome.co.kr/e2e/discount", "2026-10-08", label, None if label == "확인됨" else "공고문 할인 문구 해석", str(won)))',
        'c.commit()',
      ].join('\n'),
      db,
      String(complexId),
      label ?? '',
      String(won),
    ],
    { cwd: BACKEND, env: { ...process.env, ...backendEnv }, stdio: 'pipe', timeout: 60_000 },
  );
}

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
