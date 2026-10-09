import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { TOKEN_STORAGE_KEY } from '@/api/auth';
import { t } from '@/i18n';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { captureDownloads } from '@/pages/_shared/testing';
import { renderWithProviders } from '@/test/render';
import { RawDocumentPreview } from './RawDocumentPreview';

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function serveRaw(seen: { auth: (string | null)[] }) {
  server.use(
    http.get(mswPath('/raw/:id'), ({ request, params }) => {
      seen.auth.push(request.headers.get('authorization'));
      if (params.id === '9062') {
        return HttpResponse.arrayBuffer(PNG.buffer, {
          headers: {
            'Content-Type': 'image/png',
            'Content-Disposition': 'attachment; filename="elif_popup_2026-10-07.png"',
          },
        });
      }
      if (params.id === '9100') {
        return new HttpResponse('<html></html>', { headers: { 'Content-Type': 'text/html' } });
      }
      return new HttpResponse('공급금액 표\n84A 7억', {
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
          'Content-Disposition': 'attachment; filename="notice_9001.txt"',
        },
      });
    }),
  );
}

describe('RawDocumentPreview — 원문 미리보기·저장(Bearer)', () => {
  beforeEach(() => window.localStorage.setItem(TOKEN_STORAGE_KEY, 'tok-r'));

  it('열기 전에는 받지 않고, 텍스트는 화면 안에 보인다', async () => {
    const seen = { auth: [] as (string | null)[] };
    serveRaw(seen);
    renderWithProviders(<RawDocumentPreview rawId={9001} />);
    expect(seen.auth).toHaveLength(0);
    await userEvent.click(screen.getByRole('button', { name: t('provenance.rawPreview') }));
    expect(await screen.findByTestId('raw-preview-text')).toHaveTextContent('84A 7억');
    expect(seen.auth).toEqual(['Bearer tok-r']);
    expect(screen.getByRole('button', { name: t('provenance.rawPreviewHide') })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('PNG 는 object URL 이미지로', async () => {
    const seen = { auth: [] as (string | null)[] };
    serveRaw(seen);
    const create = vi.spyOn(URL, 'createObjectURL');
    renderWithProviders(<RawDocumentPreview rawId={9062} defaultOpen />);
    const img = await screen.findByTestId('raw-preview-image');
    expect(img.getAttribute('src')).toMatch(/^blob:/);
    expect(img).toHaveAttribute(
      'alt',
      t('provenance.rawImageAlt', { name: 'elif_popup_2026-10-07.png' }),
    );
    const blob = create.mock.calls[0]?.[0] as Blob;
    expect(blob.size).toBe(PNG.length);
    expect(seen.auth).toEqual(['Bearer tok-r']);
  });

  it('HTML 은 미리보기 대신 저장 안내', async () => {
    serveRaw({ auth: [] });
    renderWithProviders(<RawDocumentPreview rawId={9100} defaultOpen />);
    expect(
      await screen.findByText(t('provenance.rawPreviewUnsupported', { type: 'text/html' })),
    ).toBeInTheDocument();
  });

  it('저장 → fetch(Bearer) → 응답 파일 이름으로 저장', async () => {
    const seen = { auth: [] as (string | null)[] };
    serveRaw(seen);
    const saved = captureDownloads();
    renderWithProviders(<RawDocumentPreview rawId={9001} />);
    await userEvent.click(screen.getByRole('button', { name: t('provenance.rawSave') }));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]?.filename).toBe('notice_9001.txt');
    expect(seen.auth).toEqual(['Bearer tok-r']);
  });

  it('실패하면 오류 문구', async () => {
    server.use(
      http.get(mswPath('/raw/:id'), () =>
        HttpResponse.json({ code: 'not_found', detail: 'raw_document 1' }, { status: 404 }),
      ),
    );
    renderWithProviders(<RawDocumentPreview rawId={1} />);
    await userEvent.click(screen.getByRole('button', { name: t('provenance.rawSave') }));
    expect(
      await screen.findByText(t('download.error', { detail: 'not_found: raw_document 1' })),
    ).toBeInTheDocument();
  });
});
