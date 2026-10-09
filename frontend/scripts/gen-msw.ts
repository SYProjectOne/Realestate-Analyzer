/**
 * npm run gen:msw — openapi의 response example(s) → src/mocks/handlers.gen.ts
 * 입력 선택은 scripts/lib/openapi-source.ts (openapi.config.json 한 줄).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parse } from 'yaml';
import { generateMswHandlers } from './lib/msw-codegen';
import { FRONTEND_ROOT, resolveOpenapiSource } from './lib/openapi-source';

const OUTPUT = resolve(FRONTEND_ROOT, 'src/mocks/handlers.gen.ts');

function main(): void {
  const source = resolveOpenapiSource();
  const doc = parse(readFileSync(source.path, 'utf8'), { maxAliasCount: -1 }) as Record<string, unknown>;
  const { code, operations, skipped } = generateMswHandlers(doc, `${source.display} (${source.mode})`);
  writeFileSync(OUTPUT, code, 'utf8');
  console.log(`gen:msw  ${source.display} → src/mocks/handlers.gen.ts  (핸들러 ${operations.length}, 건너뜀 ${skipped.length})`);
  for (const s of skipped) console.log(`  skip ${s.method.toUpperCase()} ${s.path}: ${s.reason}`);
}

try {
  main();
} catch (err: unknown) {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
}
