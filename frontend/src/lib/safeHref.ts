/**
 * href scheme 화이트리스트 (R3 minor 16). 서버·수집 자료에서 온 URL 은 `href` 에 넣기 전에 반드시 여기를 거친다.
 *
 * 허용: `http:`·`https:` 절대 URL, 같은 출처 경로(`/` 로 시작, `//`·`/\` 제외).
 * 거부(null): `javascript:`·`data:`·`vbscript:`·`file:`·`mailto:` 등 다른 scheme, 제어 문자·공백이 섞인 값,
 * 상대 경로·`#` 조각, 빈 값. 거부된 URL 은 링크 없이 글자로만 보인다(`ExternalLink`).
 */
export function safeHref(raw: string | null | undefined): string | null {
  if (typeof raw !== 'string') return null;
  const value = raw.trim();
  if (value === '') return null;
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    // 제어 문자·공백(브라우저는 scheme 안의 탭·개행을 지우고 해석한다 — 'java\nscript:')
    if (code <= 0x20 || code === 0x7f) return null;
  }
  if (value.startsWith('/')) {
    // 프로토콜 상대(//host)·역슬래시(/\host)는 다른 출처로 간다
    if (value.startsWith('//') || value.startsWith('/\\')) return null;
    return value;
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  return url.href;
}
