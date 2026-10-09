/** 화면 테스트 도우미 — MSW 요청 기록(본문 포함). 테스트 파일에서만 import 한다. */
import { configure } from '@testing-library/react';
import { server } from '@/mocks/server';

// 화면은 라우트별 지연 로드 청크다 — 파일의 첫 테스트는 모듈 변환까지 기다린다(기본 1초는 짧다)
configure({ asyncUtilTimeout: 5000 });
// 화면 하나가 쿼리 여러 개를 띄운다(G7 등) — 부하가 있는 CI에서도 넘치지 않게
vi.setConfig({ testTimeout: 20_000 });

export interface RecordedRequest {
  method: string;
  url: URL;
  /** 요청 헤더(Authorization 확인용) */
  headers: Headers;
  body: Promise<unknown>;
}

/** 이후 나가는 요청을 모두 기록한다. stop()으로 끈다. */
export function recordRequests(): { requests: RecordedRequest[]; stop: () => void } {
  const requests: RecordedRequest[] = [];
  const listener = ({ request }: { request: Request }) => {
    const clone = request.clone();
    requests.push({
      method: request.method,
      url: new URL(request.url),
      headers: new Headers(request.headers),
      body: clone
        .text()
        .then((text) => (text ? (JSON.parse(text) as unknown) : null))
        .catch(() => null),
    });
  };
  server.events.on('request:start', listener);
  return { requests, stop: () => server.events.removeListener('request:start', listener) };
}

/** 경로가 suffix로 끝나는(메서드 일치) 요청만 */
export function matching(
  requests: RecordedRequest[],
  method: string,
  suffix: string | RegExp,
): RecordedRequest[] {
  return requests.filter(
    (r) =>
      r.method === method &&
      (typeof suffix === 'string' ? r.url.pathname.endsWith(suffix) : suffix.test(r.url.pathname)),
  );
}

export interface CapturedDownload {
  filename: string;
  href: string;
}

/**
 * `saveBlob`의 `<a download>` 클릭을 가로채 기록한다(jsdom 은 다운로드·이동을 하지 않는다).
 * vitest `restoreMocks` 가 테스트 끝에 되돌린다.
 */
export function captureDownloads(): CapturedDownload[] {
  const saved: CapturedDownload[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    if (this.hasAttribute('download')) saved.push({ filename: this.download, href: this.href });
  });
  return saved;
}
