import { http, HttpResponse } from 'msw';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { captureDownloads } from '@/pages/_shared/testing';
import { TOKEN_STORAGE_KEY } from './auth';
import { ApiError } from './client';
import { downloadFile, fetchFile, filenameFromDisposition, previewKind } from './download';
import { complexesCsvRequest, rawDocumentRequest, reportRequest } from './hooks';

describe('filenameFromDisposition', () => {
  it.each([
    ['attachment; filename="complexes_2026-10-07.csv"', 'complexes_2026-10-07.csv'],
    ['attachment; filename=report.pdf', 'report.pdf'],
    ["attachment; filename*=UTF-8''%EB%B3%B4%EA%B3%A0%EC%84%9C.html", '보고서.html'],
    [
      'attachment; filename="fallback.html"; filename*=UTF-8\'\'%EB%B3%B4%EA%B3%A0%EC%84%9C.html',
      '보고서.html',
    ],
    ['attachment; filename="../../etc/passwd"', 'passwd'],
    ['inline', null],
    [null, null],
  ])('%s → %s', (header, expected) => {
    expect(filenameFromDisposition(header)).toBe(expected);
  });
});

describe('previewKind', () => {
  it('텍스트·이미지만 미리보기, HTML·PDF 는 저장', () => {
    expect(previewKind('text/plain; charset=utf-8')).toBe('text');
    expect(previewKind('application/json')).toBe('text');
    expect(previewKind('image/png')).toBe('image');
    expect(previewKind('text/html; charset=utf-8')).toBe('other');
    expect(previewKind('application/pdf')).toBe('other');
  });
});

describe('fetchFile / downloadFile — Bearer fetch → Blob', () => {
  it('저장한 토큰을 Authorization 으로 싣고, Content-Disposition 이름으로 저장한다', async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-1');
    let auth: string | null = null;
    server.use(
      http.get(mswPath('/snapshots/:sid/complexes.csv'), ({ request }) => {
        auth = request.headers.get('authorization');
        return new HttpResponse('complex_id,name\n1,a\n', {
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename="complexes_2026-10-07.csv"',
          },
        });
      }),
    );
    const saved = captureDownloads();
    const file = await downloadFile(complexesCsvRequest(12, { page: 2, size: 50, sort: '-total' }));
    expect(auth).toBe('Bearer tok-1');
    expect(file.filename).toBe('complexes_2026-10-07.csv');
    expect(file.contentType).toContain('text/csv');
    expect(saved).toEqual([
      { filename: 'complexes_2026-10-07.csv', href: expect.stringMatching(/^blob:/) },
    ]);
  });

  it('CSV 요청은 page·size 를 빼고 필터·정렬은 그대로', () => {
    const req = complexesCsvRequest(12, {
      page: 3,
      size: 50,
      sort: '-total',
      filter: { intake_status: '가능' },
    });
    expect(req.path).toBe('/snapshots/12/complexes.csv');
    expect(req.query).toEqual({ sort: '-total', filter: { intake_status: '가능' } });
  });

  it('이름이 없으면 fallbackName(보고서 목록의 filename)', async () => {
    server.use(
      http.get(
        mswPath('/reports/:id'),
        () => new HttpResponse('<!doctype html>', { headers: { 'Content-Type': 'text/html' } }),
      ),
    );
    const file = await fetchFile(reportRequest(7, 'report_2026-10-07.html'));
    expect(file.filename).toBe('report_2026-10-07.html');
  });

  it('원문 PNG 는 Blob 그대로(image/png)', async () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47]);
    server.use(
      http.get(mswPath('/raw/:id'), () =>
        HttpResponse.arrayBuffer(png.buffer, { headers: { 'Content-Type': 'image/png' } }),
      ),
    );
    const file = await fetchFile(rawDocumentRequest(9062));
    expect(file.contentType).toBe('image/png');
    expect(file.blob.size).toBe(4);
  });

  it('실패는 계약 Error 본문 → ApiError', async () => {
    server.use(
      http.get(mswPath('/reports/:id'), () =>
        HttpResponse.json({ code: 'conflict', detail: '아직 완료되지 않음' }, { status: 409 }),
      ),
    );
    const err = await fetchFile(reportRequest(7)).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).detail).toBe('아직 완료되지 않음');
  });
});
