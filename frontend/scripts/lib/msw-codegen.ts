/**
 * openapi 문서 → MSW 핸들러 TS 소스.
 * 각 operation의 첫 2xx 응답에서 예시를 꺼낸다: media.example → media.examples의 첫 값 → schema.example.
 * 로컬 `$ref`(#/...)는 따라간다. 예시가 없는 operation은 건너뛰고 목록으로 돌려준다(→ handlers.extra.ts로 보강).
 */

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type Obj = Record<string, unknown>;

const METHODS = ['get', 'post', 'put', 'patch', 'delete'] as const;
export type HttpMethod = (typeof METHODS)[number];

export interface GeneratedOperation {
  method: HttpMethod;
  path: string;
  operationId: string | null;
  status: number;
  contentType: string | null;
}

export interface SkippedOperation {
  method: HttpMethod;
  path: string;
  reason: string;
}

export interface CodegenResult {
  code: string;
  operations: GeneratedOperation[];
  skipped: SkippedOperation[];
}

const isObj = (value: unknown): value is Obj =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

export function resolveRef(doc: Obj, node: unknown, depth = 0): unknown {
  if (depth > 32) throw new Error('$ref 깊이 초과(순환?)');
  if (!isObj(node) || typeof node.$ref !== 'string') return node;
  const ref = node.$ref;
  if (!ref.startsWith('#/'))
    throw new Error(`외부 $ref는 지원하지 않는다(번들 파일을 쓸 것): ${ref}`);
  let target: unknown = doc;
  for (const raw of ref.slice(2).split('/')) {
    const key = raw.replace(/~1/g, '/').replace(/~0/g, '~');
    if (!isObj(target) || !(key in target)) throw new Error(`$ref 대상 없음: ${ref}`);
    target = target[key];
  }
  return resolveRef(doc, target, depth + 1);
}

/** 예시 값 안의 $ref까지 풀어 순수 JSON으로 만든다. */
function deepResolve(doc: Obj, node: unknown, depth = 0): Json {
  if (depth > 64) throw new Error('예시 중첩 깊이 초과');
  const resolved = resolveRef(doc, node);
  if (Array.isArray(resolved)) return resolved.map((item) => deepResolve(doc, item, depth + 1));
  if (isObj(resolved)) {
    const out: { [key: string]: Json } = {};
    for (const [key, value] of Object.entries(resolved))
      out[key] = deepResolve(doc, value, depth + 1);
    return out;
  }
  if (resolved instanceof Date) return resolved.toISOString();
  return resolved as Json;
}

function pickExample(doc: Obj, media: Obj): { found: true; value: Json } | { found: false } {
  if ('example' in media) return { found: true, value: deepResolve(doc, media.example) };
  if (isObj(media.examples)) {
    const first = Object.values(media.examples)[0];
    const example = resolveRef(doc, first);
    if (isObj(example) && 'value' in example)
      return { found: true, value: deepResolve(doc, example.value) };
  }
  const schema = resolveRef(doc, media.schema);
  if (isObj(schema) && 'example' in schema)
    return { found: true, value: deepResolve(doc, schema.example) };
  return { found: false };
}

/** `/snapshots/{sid}/dashboard` → `/snapshots/:sid/dashboard` */
export function toMswPath(path: string): string {
  return path.replace(/\{([^}]+)\}/g, ':$1');
}

/** 같은 메서드 안에서 리터럴 세그먼트가 파라미터보다 먼저 오게 정렬(/regions/resolve가 /regions/:id보다 앞). */
export function compareRoutes(a: string, b: string): number {
  const as = a.split('/');
  const bs = b.split('/');
  for (let i = 0; i < Math.min(as.length, bs.length); i += 1) {
    const x = as[i] ?? '';
    const y = bs[i] ?? '';
    if (x === y) continue;
    const xp = x.startsWith('{');
    const yp = y.startsWith('{');
    if (xp !== yp) return xp ? 1 : -1;
    return x < y ? -1 : 1;
  }
  return as.length - bs.length;
}

export function generateMswHandlers(doc: Obj, sourceDisplay: string): CodegenResult {
  const paths = isObj(doc.paths) ? doc.paths : {};
  const operations: GeneratedOperation[] = [];
  const skipped: SkippedOperation[] = [];
  const handlerLines: string[] = [];

  const entries = Object.entries(paths).sort(([a], [b]) => compareRoutes(a, b));
  for (const [path, rawItem] of entries) {
    const item = resolveRef(doc, rawItem);
    if (!isObj(item)) continue;
    for (const method of METHODS) {
      const op = item[method];
      if (!isObj(op)) continue;
      const responses = isObj(op.responses) ? op.responses : {};
      const successCode = Object.keys(responses)
        .filter((code) => /^2\d\d$/.test(code))
        .sort()[0];
      if (!successCode) {
        skipped.push({ method, path, reason: '2xx 응답 없음' });
        continue;
      }
      const status = Number(successCode);
      const response = resolveRef(doc, responses[successCode]);
      const content = isObj(response) && isObj(response.content) ? response.content : null;
      const operationId = typeof op.operationId === 'string' ? op.operationId : null;
      const mswPath = toMswPath(path);

      if (!content || Object.keys(content).length === 0) {
        handlerLines.push(
          `  http.${method}(mswPath(${JSON.stringify(mswPath)}), () => new HttpResponse(null, { status: ${status} })),`,
        );
        operations.push({ method, path, operationId, status, contentType: null });
        continue;
      }

      const jsonType = Object.keys(content).find((type) => type.includes('json'));
      const contentType = jsonType ?? Object.keys(content)[0] ?? null;
      const media = contentType ? resolveRef(doc, content[contentType]) : null;
      const example = isObj(media) ? pickExample(doc, media) : { found: false as const };
      if (!example.found) {
        skipped.push({ method, path, reason: `예시 없음 (${contentType ?? '?'})` });
        continue;
      }
      const body = JSON.stringify(example.value, null, 2).replace(/\n/g, '\n    ');
      if (jsonType) {
        handlerLines.push(
          `  http.${method}(mswPath(${JSON.stringify(mswPath)}), () =>\n    HttpResponse.json(${body}, { status: ${status} }),\n  ),`,
        );
      } else {
        const text =
          typeof example.value === 'string' ? example.value : JSON.stringify(example.value);
        handlerLines.push(
          `  http.${method}(mswPath(${JSON.stringify(mswPath)}), () =>\n    new HttpResponse(${JSON.stringify(text)}, { status: ${status}, headers: { 'Content-Type': ${JSON.stringify(contentType)} } }),\n  ),`,
        );
      }
      operations.push({ method, path, operationId, status, contentType });
    }
  }

  const skippedComment = skipped.length
    ? [
        '// 건너뜀(예시 없음 → handlers.extra.ts에서 보강):',
        ...skipped.map((s) => `//   ${s.method.toUpperCase()} ${s.path} — ${s.reason}`),
      ]
    : ['// 건너뜀: 없음'];

  const code = [
    '/* eslint-disable */',
    `// AUTO-GENERATED by \`npm run gen:msw\` from ${sourceDisplay}.`,
    '// 손으로 고치지 않는다. 수동 보강은 handlers.extra.ts.',
    ...skippedComment,
    "import { http, HttpResponse } from 'msw';",
    "import { mswPath } from './mswPath';",
    '',
    'export const generatedHandlers = [',
    ...handlerLines,
    '];',
    '',
    `export const generatedOperations = ${JSON.stringify(
      operations.map(({ method, path, operationId, status }) => ({
        method,
        path,
        operationId,
        status,
      })),
      null,
      2,
    )} as const;`,
    '',
  ].join('\n');

  return { code, operations, skipped };
}
