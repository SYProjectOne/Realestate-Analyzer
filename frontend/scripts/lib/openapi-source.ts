/**
 * gen:api · gen:msw가 읽을 openapi 파일을 고른다.
 *   - openapi.config.json의 "source" (fixture | contract | 경로) — 계약 전환은 이 한 줄
 *   - 환경변수 OPENAPI_SOURCE가 있으면 그것이 이긴다
 *   - contract: ../contracts/openapi.bundled.yaml 이 있으면 그것, 없으면 ../contracts/openapi.yaml
 */
import { existsSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const REPO_ROOT = resolve(FRONTEND_ROOT, '..');
export const FIXTURE_OPENAPI = resolve(FRONTEND_ROOT, 'scripts/fixtures/openapi.min.yaml');
export const CONTRACT_CANDIDATES = [
  resolve(REPO_ROOT, 'contracts/openapi.bundled.yaml'),
  resolve(REPO_ROOT, 'contracts/openapi.yaml'),
];

export interface OpenapiSource {
  /** 절대 경로 */
  path: string;
  /** 생성물 헤더에 적는 저장소 기준 상대 경로 (POSIX 구분자) */
  display: string;
  mode: 'fixture' | 'contract' | 'path';
}

function readConfiguredSource(): string {
  const configPath = resolve(FRONTEND_ROOT, 'openapi.config.json');
  const raw = JSON.parse(readFileSync(configPath, 'utf8')) as { source?: unknown };
  if (typeof raw.source !== 'string' || raw.source === '') {
    throw new Error(`openapi.config.json: "source"가 비어 있다`);
  }
  return raw.source;
}

function toDisplay(path: string): string {
  return relative(REPO_ROOT, path).split('\\').join('/');
}

export function resolveOpenapiSource(source: string = process.env.OPENAPI_SOURCE ?? readConfiguredSource()): OpenapiSource {
  if (source === 'fixture') {
    return { path: FIXTURE_OPENAPI, display: toDisplay(FIXTURE_OPENAPI), mode: 'fixture' };
  }
  if (source === 'contract') {
    const found = CONTRACT_CANDIDATES.find((candidate) => existsSync(candidate));
    if (!found) {
      throw new Error(
        `계약 파일이 없다: ${CONTRACT_CANDIDATES.map(toDisplay).join(' 또는 ')}. ` +
          `WP0-A 머지 전이면 openapi.config.json의 source를 "fixture"로 둔다.`,
      );
    }
    return { path: found, display: toDisplay(found), mode: 'contract' };
  }
  const path = isAbsolute(source) ? source : resolve(FRONTEND_ROOT, source);
  if (!existsSync(path)) throw new Error(`openapi 파일이 없다: ${path}`);
  return { path, display: toDisplay(path), mode: 'path' };
}
