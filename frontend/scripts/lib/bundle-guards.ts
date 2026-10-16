/**
 * R5-FE2: 첫 화면 번들 규칙(vite.config.ts 의 빌드 가드가 쓰고, scripts/bundle-guards.test.ts 가 고정한다).
 *
 * 진입 청크(index.html 의 `<script type=module>`)와 그것이 **정적으로** import 하는 청크 전부(= 첫 화면이 파싱·실행 전에
 * 반드시 받는 JS)에 차트 엔진(echarts·zrender)·MSW 가 들어가면 빌드를 실패시킨다. 수동 청크(manualChunks)가 공용 도우미
 * (rollup `commonjsHelpers`, vite `preload-helper`)를 정적 의존성으로 끌어가 진입 청크가 zrender(196kB)·msw(296kB)
 * 청크를 정적으로 import 하던 회귀(R5-FE2 이전)를 막는다. 진입 닫힘 크기 예산도 본다.
 */

/** Rollup OutputChunk 에서 쓰는 필드만 */
export interface ChunkLike {
  type: 'chunk';
  fileName: string;
  name: string;
  isEntry: boolean;
  imports: string[];
  code: string;
}

/** 첫 화면에 정적으로 붙으면 안 되는 수동 청크 이름(vite.config.ts manualChunks) */
export const LAZY_ONLY_CHUNKS = ['echarts', 'zrender', 'msw'] as const;

/**
 * R11-I18N: 문자열 이름공간 청크(vite.config.ts `ko-split` → manualChunks `ko-page-G3`·`ko-chart`·`ko-glossary` …) —
 * 라우트가 동적으로만 받는다. 진입이 정적으로 import 하면 나눈 의미가 없다.
 */
export const LAZY_ONLY_PREFIX = 'ko-';

export function isLazyOnly(name: string): boolean {
  return (
    (LAZY_ONLY_CHUNKS as readonly string[]).includes(name) || name.startsWith(LAZY_ONLY_PREFIX)
  );
}

/** 진입 정적 닫힘(진입 청크 + 정적 import 청크) 크기 예산(kB, 압축 전) */
export const ENTRY_CLOSURE_BUDGET_KB = 450;

export function chunkKb(chunk: ChunkLike): number {
  return Buffer.byteLength(chunk.code) / 1000;
}

/** 진입 청크에서 정적 import 로 닿는 청크들(진입 포함, 방문 순서) */
export function staticClosure(chunks: readonly ChunkLike[], entry: ChunkLike): ChunkLike[] {
  const byFile = new Map(chunks.map((c) => [c.fileName, c]));
  const seen = new Set<string>();
  const out: ChunkLike[] = [];
  const stack = [entry.fileName];
  while (stack.length > 0) {
    const file = stack.pop() as string;
    if (seen.has(file)) continue;
    seen.add(file);
    const chunk = byFile.get(file);
    if (!chunk) continue;
    out.push(chunk);
    stack.push(...chunk.imports);
  }
  return out;
}

/** 규칙 위반 문장들(없으면 빈 목록) */
export function entryViolations(
  chunks: readonly ChunkLike[],
  budgetKb: number = ENTRY_CLOSURE_BUDGET_KB,
): string[] {
  const problems: string[] = [];
  for (const entry of chunks.filter((c) => c.isEntry)) {
    const closure = staticClosure(chunks, entry);
    const lazyOnly = closure.filter((c) => isLazyOnly(c.name));
    if (lazyOnly.length > 0) {
      problems.push(
        `진입 ${entry.fileName} 가 지연 로드 전용 청크를 정적으로 import 한다: ${lazyOnly.map((c) => c.fileName).join(', ')}`,
      );
    }
    const kb = closure.reduce((sum, c) => sum + chunkKb(c), 0);
    if (kb > budgetKb) {
      problems.push(
        `진입 ${entry.fileName} 정적 닫힘 ${kb.toFixed(1)}kB > 예산 ${budgetKb}kB (${closure.map((c) => `${c.fileName} ${chunkKb(c).toFixed(1)}kB`).join(', ')})`,
      );
    }
  }
  return problems;
}
