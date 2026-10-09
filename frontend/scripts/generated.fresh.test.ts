// @vitest-environment node
/**
 * R3 minor 5 — 생성물 최신성: 계약(openapi.config.json 의 source, 지금은 contracts/openapi.bundled.yaml)에서
 * gen:api·gen:msw 와 같은 함수(scripts/lib/generate.ts)로 메모리에서 다시 만들어 저장된 파일과 같아야 한다.
 * 다르면 `npm run gen:api && npm run gen:msw` 를 돌려 커밋한다(손으로 고치지 않는다).
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { generateMswSource, generateSchemaTypes } from './lib/generate';
import { FRONTEND_ROOT, resolveOpenapiSource } from './lib/openapi-source';

const lf = (s: string) => s.replace(/\r\n/g, '\n');
const read = (rel: string) => lf(readFileSync(resolve(FRONTEND_ROOT, rel), 'utf8'));

describe('생성물 최신성(계약 → 프론트)', () => {
  const source = resolveOpenapiSource();

  it('입력은 계약 파일(contract 모드)', () => {
    expect(source.mode).toBe('contract');
    expect(source.display).toMatch(/^contracts\/openapi(\.bundled)?\.yaml$/);
  });

  it('src/api/schema.d.ts = openapi-typescript(계약) — 생성 성공 + 저장본과 같다', async () => {
    const generated = lf(await generateSchemaTypes(source));
    expect(generated.length).toBeGreaterThan(10_000);
    expect(generated).toContain('export interface components');
    const saved = read('src/api/schema.d.ts');
    // 실패 메시지를 짧게: 첫 차이 줄을 보인다
    if (generated !== saved) {
      const a = generated.split('\n');
      const b = saved.split('\n');
      const i = a.findIndex((line, n) => line !== b[n]);
      expect({ line: i + 1, generated: a[i], saved: b[i] }).toEqual({
        line: 0,
        generated: '(같아야 한다 — npm run gen:api)',
        saved: '',
      });
    }
    expect(generated).toBe(saved);
  }, 60_000);

  it('src/mocks/handlers.gen.ts = 계약 예시 MSW 핸들러 — 저장본과 같다', () => {
    const { code, operations } = generateMswSource(source);
    expect(operations.length).toBeGreaterThan(30);
    expect(lf(code)).toBe(read('src/mocks/handlers.gen.ts'));
  });
});
