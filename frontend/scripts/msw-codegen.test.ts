// @vitest-environment node
import { readFileSync } from 'node:fs';
import { parse } from 'yaml';
import { compareRoutes, generateMswHandlers, toMswPath } from './lib/msw-codegen';
import { FIXTURE_OPENAPI, resolveOpenapiSource } from './lib/openapi-source';

describe('msw-codegen', () => {
  it('경로 파라미터를 MSW 형식으로 바꾼다', () => {
    expect(toMswPath('/snapshots/{sid}/dashboard')).toBe('/snapshots/:sid/dashboard');
  });

  it('리터럴 세그먼트를 파라미터보다 앞에 둔다', () => {
    const sorted = ['/regions/{id}', '/regions/resolve', '/regions'].sort(compareRoutes);
    expect(sorted).toEqual(['/regions', '/regions/resolve', '/regions/{id}']);
  });

  it('example · examples($ref) · schema.example에서 예시를 꺼내고 없는 건 건너뛴다', () => {
    const doc = {
      paths: {
        '/a': { get: { responses: { '200': { content: { 'application/json': { example: { x: 1 } } } } } } },
        '/b/{id}': {
          get: {
            responses: {
              '200': {
                content: { 'application/json': { examples: { one: { $ref: '#/components/examples/B' } } } },
              },
            },
          },
        },
        '/c': { post: { responses: { '201': { $ref: '#/components/responses/C' } } } },
        '/d': { get: { responses: { '200': { content: { 'application/json': { schema: {} } } } } } },
        '/e': { delete: { responses: { '204': { description: 'gone' } } } },
      },
      components: {
        examples: { B: { value: { y: 'b' } } },
        responses: {
          C: { content: { 'application/json': { schema: { example: [1, 2] } } } },
        },
      },
    };
    const result = generateMswHandlers(doc, 'test.yaml');
    expect(result.operations.map((o) => `${o.method} ${o.path} ${o.status}`)).toEqual([
      'get /a 200',
      'get /b/{id} 200',
      'post /c 201',
      'delete /e 204',
    ]);
    expect(result.skipped).toEqual([{ method: 'get', path: '/d', reason: '예시 없음 (application/json)' }]);
    expect(result.code).toContain('"y": "b"');
    expect(result.code).toContain("mswPath(\"/b/:id\")");
    expect(result.code).toContain('AUTO-GENERATED');
  });

  it('임시 최소 openapi(fixture)에서 핸들러를 만든다', () => {
    const source = resolveOpenapiSource('fixture');
    expect(source.path).toBe(FIXTURE_OPENAPI);
    const doc = parse(readFileSync(source.path, 'utf8')) as Record<string, unknown>;
    const result = generateMswHandlers(doc, source.display);
    const keys = result.operations.map((o) => `${o.method} ${o.path}`);
    expect(keys).toContain('get /health');
    expect(keys).toContain('get /regions');
    expect(keys).toContain('get /snapshots/{sid}/dashboard');
    expect(result.skipped).toEqual([]);
  });
});
