// @vitest-environment node
/**
 * R5-FE2: Lighthouse preview 서버의 계약 예시 API(`scripts/lib/mock-api.ts`) — MSW 핸들러를 서버에서 그대로 답한다.
 */
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { http, HttpResponse, type RequestHandler } from 'msw';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { mockApiMiddleware } from './lib/mock-api';

/**
 * src/mocks 는 앱 tsconfig(`@/` 별칭) 소속이라 scripts(노드 tsconfig)가 정적으로 import 하면 타입 검사가 따라 들어간다 —
 * 실행 시점에만 읽는다(vitest 가 별칭을 푼다).
 */
const SRC_MOCKS = ['..', 'src', 'mocks'].join('/');
const { handlers: contractHandlers } = (await import(`${SRC_MOCKS}/handlers`)) as {
  handlers: RequestHandler[];
};
const { server: mswServer } = (await import(`${SRC_MOCKS}/server`)) as {
  server: { close: () => void };
};

let server: Server | null = null;
/** 실제로 이 HTTP 서버에 온 요청 수(전역 MSW 가 가로채지 않았는지) */
let served = 0;

// 전역 setup(src/test/setup.ts)의 MSW 서버가 fetch 를 가로채지 않게 이 파일에서는 끈다 — 진짜 HTTP 왕복을 본다
beforeAll(() => mswServer.close());

/** connect 처럼 '/api' 에 걸고 접두를 뗀 url·originalUrl 을 넘긴다 */
async function serve(handlers: RequestHandler[], unhandled: string[]): Promise<string> {
  const middleware = mockApiMiddleware(handlers, (url) => unhandled.push(url));
  server = createServer((req, res) => {
    served += 1;
    const url = req.url ?? '/';
    if (!url.startsWith('/api/')) {
      res.statusCode = 404;
      res.end();
      return;
    }
    Object.assign(req, { originalUrl: url, url: url.slice('/api'.length) });
    middleware(req, res);
  });
  await new Promise<void>((done) => server?.listen(0, '127.0.0.1', done));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

afterEach(async () => {
  await new Promise<void>((done) => (server ? server.close(() => done()) : done()));
  server = null;
  served = 0;
});

describe('mockApiMiddleware', () => {
  it('핸들러 응답의 상태·헤더·본문을 그대로, 쿼리·본문·메서드를 핸들러에 넘긴다', async () => {
    const unhandled: string[] = [];
    const base = await serve(
      [
        http.get('*/api/things', ({ request }) =>
          HttpResponse.json(
            { q: new URL(request.url).searchParams.get('q') },
            { status: 201, headers: { 'X-Test': 'yes' } },
          ),
        ),
        http.post('*/api/echo', async ({ request }) =>
          HttpResponse.json({ got: (await request.json()) as unknown }),
        ),
      ],
      unhandled,
    );
    const got = await fetch(`${base}/api/things?q=1`);
    expect(got.status).toBe(201);
    expect(got.headers.get('x-test')).toBe('yes');
    expect(await got.json()).toEqual({ q: '1' });
    const echo = await fetch(`${base}/api/echo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ a: 1 }),
    });
    expect(await echo.json()).toEqual({ got: { a: 1 } });
    expect(unhandled).toEqual([]);
    expect(served).toBe(2);
  });

  it('핸들러가 없으면 503 이고 누수로 센다', async () => {
    const unhandled: string[] = [];
    const base = await serve([], unhandled);
    const got = await fetch(`${base}/api/nothing?x=1`);
    expect(got.status).toBe(503);
    expect(unhandled).toEqual(['/api/nothing?x=1']);
    expect(served).toBe(1);
  });

  it('계약 예시 핸들러(src/mocks/handlers)로 모바일 측정 화면이 부르는 API 를 답한다', async () => {
    const unhandled: string[] = [];
    const base = await serve(contractHandlers, unhandled);
    for (const path of ['/api/regions', '/api/health']) {
      const got = await fetch(`${base}${path}`);
      expect(got.status, path).toBe(200);
      expect(got.headers.get('content-type'), path).toContain('application/json');
    }
    expect(unhandled).toEqual([]);
    expect(served).toBe(2);
  });
});
