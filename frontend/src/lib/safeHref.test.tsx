/**
 * minor 16 — 서버가 준 URL 을 href 에 넣기 전 scheme 화이트리스트(http·https·같은 출처 '/' 경로).
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { provenanceConflict } from '@/charts/gallery/fixtures';
import { ExternalLink, FactCell } from '@/components';
import { mswPath } from '@/mocks/mswPath';
import { server } from '@/mocks/server';
import { renderWithProviders } from '@/test/render';
import { safeHref } from './safeHref';

describe('safeHref', () => {
  it.each([
    ['https://www.applyhome.co.kr/', 'https://www.applyhome.co.kr/'],
    ['http://example.com/a?b=1#c', 'http://example.com/a?b=1#c'],
    ['  HTTPS://Example.com/x  ', 'https://example.com/x'],
    ['/api/raw/1', '/api/raw/1'],
    ['/complexes/3?snapshot=12', '/complexes/3?snapshot=12'],
  ])('허용: %s', (input, expected) => {
    expect(safeHref(input)).toBe(expected);
  });

  it.each([
    'javascript:alert(1)',
    'JavaScript:alert(1)',
    ' javascript:alert(1)',
    'java\nscript:alert(1)',
    'java\tscript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'vbscript:msgbox(1)',
    'file:///etc/passwd',
    'ftp://example.com/',
    'mailto:a@example.com',
    '//evil.example.com/x',
    '/\\evil.example.com',
    'relative/path',
    '#main',
    '',
    '   ',
    null,
    undefined,
  ])('거부: %j', (input) => {
    expect(safeHref(input)).toBeNull();
  });
});

describe('ExternalLink', () => {
  it('허용 URL → <a target=_blank rel=noopener>', () => {
    renderWithProviders(<ExternalLink href="https://example.com/a" />);
    const link = screen.getByRole('link', { name: 'https://example.com/a' });
    expect(link).toHaveAttribute('href', 'https://example.com/a');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('javascript:·data: → 링크 없이 글자만', () => {
    renderWithProviders(
      <>
        <ExternalLink href="javascript:alert(1)" />
        <ExternalLink href="data:text/html,x">출처</ExternalLink>
      </>,
    );
    expect(screen.queryAllByRole('link')).toHaveLength(0);
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument();
    expect(screen.getByText('출처')).toBeInTheDocument();
    expect(document.querySelector('a')).toBeNull();
  });
});

describe('ProvenancePanel — 서버 url 이 javascript:/data: 면 링크가 아니다', () => {
  it('본 출처·상충 후보 url 모두 글자만', async () => {
    const base = provenanceConflict();
    server.use(
      http.get(mswPath('/provenance/:prov_id'), () =>
        HttpResponse.json({
          ...base,
          url: 'javascript:alert(document.cookie)',
          conflicts: base.conflicts.map((c) => ({ ...c, url: 'data:text/html,<b>x</b>' })),
        }),
      ),
    );
    renderWithProviders(
      <FactCell
        fact={{ v: 1573, label: '확인됨', prov: 'fp_13001', checked_at: '2026-10-07' }}
        unit="households"
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: /1,573세대/ }));
    const panel = await screen.findByRole('dialog', { name: '출처' });
    expect(
      (await within(panel).findAllByText('javascript:alert(document.cookie)')).length,
    ).toBeGreaterThan(0);
    expect(within(panel).queryAllByRole('link')).toHaveLength(0);
    for (const a of Array.from(panel.querySelectorAll('a'))) {
      expect(a.getAttribute('href') ?? '').not.toMatch(/^(javascript|data):/i);
    }
  });
});

describe('소스 검사 — 화면 코드는 href={…} 를 직접 쓰지 않는다(ExternalLink 만)', () => {
  it('src/**/*.tsx 의 <a href={…}> 는 ExternalLink.tsx 안의 safe 값뿐', () => {
    const files = import.meta.glob<string>(['/src/**/*.tsx', '!/src/**/*.test.tsx'], {
      query: '?raw',
      import: 'default',
      eager: true,
    });
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(files)) {
      // 원시 <a …href={식}> 만(컴포넌트 <ExternalLink href={…}> 는 검사를 거친다)
      for (const match of source.matchAll(/<a\s[^>]*?href=\{([^}]*)\}/g)) {
        if (path.endsWith('/components/ExternalLink.tsx') && match[1] === 'safe') continue;
        offenders.push(`${path}: ${match[0]}`);
      }
    }
    expect(Object.keys(files).length).toBeGreaterThan(20);
    expect(offenders).toEqual([]);
  });
});
