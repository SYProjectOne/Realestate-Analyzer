import type { ReactNode } from 'react';
import { safeHref } from '@/lib/safeHref';

export interface ExternalLinkProps {
  /** 서버·수집 자료에서 온 URL(검사 전) */
  href: string | null | undefined;
  /** 링크 글자. 없으면 URL 그대로 */
  children?: ReactNode;
  /** 허용되지 않은 URL 일 때 보일 글자. 없으면 children(없으면 URL) */
  fallback?: ReactNode;
  className?: string;
}

/**
 * 외부 링크 — `safeHref`(http·https·같은 출처 경로)를 통과한 URL 만 `<a target=_blank>` 로 그린다.
 * `javascript:`·`data:` 등은 링크 없이 글자만(R3 minor 16). 화면은 서버 URL 에 `<a href>` 를 직접 쓰지 않는다.
 */
export function ExternalLink({
  href,
  children,
  fallback,
  className = 'underline',
}: ExternalLinkProps) {
  const safe = safeHref(href);
  const text = children ?? href ?? '';
  if (!safe) {
    const plain = className.replace(/\bunderline\b/g, '').trim();
    return (
      <span className={plain || undefined} data-unsafe-href="">
        {fallback ?? text}
      </span>
    );
  }
  return (
    <a href={safe} target="_blank" rel="noreferrer noopener" className={className}>
      {text}
    </a>
  );
}
