/**
 * R5-FE2: `npm run lighthouse` 의 계약 예시 API. preview 서버가 `/api` 를 MSW 핸들러(`src/mocks/handlers.ts`, 계약 예시
 * 응답)로 **서버에서** 답한다 — 측정하는 번들은 운영 빌드 그대로(MSW·서비스 워커·핸들러 데이터 없음)이고, 응답만 실 API
 * 대신 계약 예시다. 브라우저 MSW 로 재면 운영에 없는 msw 런타임·계약 예시 데이터(~100kB gzip)를 받고 서비스 워커를 등록한
 * 뒤에야 첫 렌더를 해서, 첫 화면 지표(FCP·LCP)가 운영보다 나쁘게 잡혔다.
 *
 * 핸들러는 그대로 다시 쓴다(`getResponse`, handlers.extra.ts 와 같은 방식). 핸들러가 없는 요청은 `onUnhandled` 로 알리고 503.
 */
import type { IncomingMessage, ServerResponse } from 'node:http';
import { getResponse, type RequestHandler } from 'msw';

type NodeRequest = IncomingMessage & { originalUrl?: string };

/** Node 요청 → Fetch `Request`(핸들러가 매칭할 절대 URL). connect 가 접두를 뗀 url 대신 originalUrl 을 쓴다 */
export async function toFetchRequest(req: NodeRequest, origin: string): Promise<Request> {
  const method = (req.method ?? 'GET').toUpperCase();
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (value === undefined) continue;
    headers.set(key, Array.isArray(value) ? value.join(', ') : value);
  }
  let body: Uint8Array<ArrayBuffer> | undefined;
  if (method !== 'GET' && method !== 'HEAD') {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk as Buffer));
    body = Uint8Array.from(Buffer.concat(chunks));
  }
  return new Request(new URL(req.originalUrl ?? req.url ?? '/', origin), {
    method,
    headers,
    body,
  });
}

/** connect 미들웨어: 핸들러 응답을 그대로(상태·헤더·본문) 쓴다 */
export function mockApiMiddleware(
  handlers: RequestHandler[],
  onUnhandled: (url: string) => void,
): (req: NodeRequest, res: ServerResponse) => void {
  return (req, res) => {
    void (async () => {
      const request = await toFetchRequest(req, `http://${req.headers.host ?? '127.0.0.1'}`);
      const response = await getResponse(handlers, request);
      if (!response) {
        onUnhandled(req.originalUrl ?? req.url ?? '');
        res.statusCode = 503;
        res.end();
        return;
      }
      res.statusCode = response.status;
      response.headers.forEach((value, key) => res.setHeader(key, value));
      res.end(Buffer.from(await response.arrayBuffer()));
    })().catch((err: unknown) => {
      onUnhandled(`${req.originalUrl ?? req.url ?? ''} (${String(err)})`);
      res.statusCode = 500;
      res.end();
    });
  };
}
