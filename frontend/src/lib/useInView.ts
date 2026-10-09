import { useEffect, useRef, useState, type RefObject } from 'react';

/**
 * 요소가 뷰포트에 한 번이라도 들어오면 true (이후 유지). 차트 lazy 렌더용(RA §7).
 * IntersectionObserver가 없는 환경(jsdom·구형)에서는 바로 true.
 */
export function useInView<T extends Element>(rootMargin = '200px'): [RefObject<T>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined');

  useEffect(() => {
    if (inView) return;
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [inView, rootMargin]);

  return [ref, inView];
}
