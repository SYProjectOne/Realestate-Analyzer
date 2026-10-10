/**
 * href scheme 화이트리스트 (R3 minor 16). 서버·수집 자료에서 온 URL 은 `href` 에 넣기 전에 반드시 여기를 거친다.
 *
 * 허용: `http:`·`https:` 절대 URL, 같은 출처 경로(`/` 로 시작, `//`·`/\` 제외).
 * 거부(null): `javascript:`·`data:`·`vbscript:`·`file:`·`mailto:` 등 다른 scheme, 제어 문자·공백이 섞인 값,
 * 상대 경로·`#` 조각, 빈 값. 거부된 URL 은 링크 없이 글자로만 보인다(`ExternalLink`).
 * 5차 리뷰 minor: IDNA 가 지우는 보이지 않는 문자(U+00AD 소프트 하이픈·U+200B 폭 없는 공백·U+034F·
 * U+FE00~FE0F 이체 선택자·U+180B~180F·U+2060·U+FEFF 등 Default_Ignorable_Code_Point, 서식 문자 Cf)는
 * 그대로든 %-인코딩이든 거부한다 — 보이는 주소와 실제 호스트가 달라진다(`10.0.0.1`·`localhost` 우회).
 * %-인코딩된 제어 문자(`%00`~`%1F`·`%7F`)와 잘못된 %-인코딩도 거부한다.
 */
const INVISIBLE = /[\p{Default_Ignorable_Code_Point}\p{Cf}]/u;
const PCT_CONTROL = /%(?:[01][0-9a-f]|7f)/i;

/** 보이지 않는 문자·제어 문자가 그대로 또는 %-인코딩으로 섞였는가 */
function hasHidden(value: string): boolean {
  if (INVISIBLE.test(value) || PCT_CONTROL.test(value)) return true;
  if (!value.includes('%')) return false;
  const authority = /^[a-z][a-z0-9+.-]*:\/\/([^/?#]*)/i.exec(value)?.[1] ?? '';
  for (const part of [authority, value]) {
    try {
      if (INVISIBLE.test(decodeURIComponent(part))) return true;
    } catch {
      // 호스트 부분의 잘못된 %-인코딩은 해석이 구현마다 달라 거부(경로·쿼리의 낱 '%' 는 허용)
      if (part === authority && part.includes('%')) return true;
    }
  }
  return false;
}

export function safeHref(raw: string | null | undefined): string | null {
  if (typeof raw !== 'string') return null;
  const value = raw.trim();
  if (value === '') return null;
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    // 제어 문자·공백(브라우저는 scheme 안의 탭·개행을 지우고 해석한다 — 'java\nscript:')
    if (code <= 0x20 || code === 0x7f) return null;
  }
  if (hasHidden(value)) return null;
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
