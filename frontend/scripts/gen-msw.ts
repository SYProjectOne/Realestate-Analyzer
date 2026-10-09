/**
 * npm run gen:msw — openapi의 response example(s) → src/mocks/handlers.gen.ts
 * 입력 선택은 scripts/lib/openapi-source.ts (openapi.config.json 한 줄).
 * 생성 코드는 scripts/lib/generate.ts — 최신성 테스트(scripts/generated.fresh.test.ts)도 같은 함수를 쓴다.
 */
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { generateMswSource } from './lib/generate';
import { FRONTEND_ROOT, resolveOpenapiSource } from './lib/openapi-source';

const OUTPUT = resolve(FRONTEND_ROOT, 'src/mocks/handlers.gen.ts');

function main(): void {
  const source = resolveOpenapiSource();
  const { code, operations, skipped } = generateMswSource(source);
  writeFileSync(OUTPUT, code, 'utf8');
  console.log(
    `gen:msw  ${source.display} → src/mocks/handlers.gen.ts  (핸들러 ${operations.length}, 건너뜀 ${skipped.length})`,
  );
  for (const s of skipped) console.log(`  skip ${s.method.toUpperCase()} ${s.path}: ${s.reason}`);
}

try {
  main();
} catch (err: unknown) {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
}
