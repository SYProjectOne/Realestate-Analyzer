/**
 * npm run gen:api — openapi → src/api/schema.d.ts (openapi-typescript).
 * 입력 선택은 scripts/lib/openapi-source.ts (openapi.config.json 한 줄).
 * 생성 코드는 scripts/lib/generate.ts — 최신성 테스트(scripts/generated.fresh.test.ts)도 같은 함수를 쓴다.
 */
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { generateSchemaTypes } from './lib/generate';
import { FRONTEND_ROOT, resolveOpenapiSource } from './lib/openapi-source';

export const SCHEMA_OUTPUT = resolve(FRONTEND_ROOT, 'src/api/schema.d.ts');

async function main(): Promise<void> {
  const source = resolveOpenapiSource();
  writeFileSync(SCHEMA_OUTPUT, await generateSchemaTypes(source), 'utf8');
  console.log(`gen:api  ${source.display} → src/api/schema.d.ts`);
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
