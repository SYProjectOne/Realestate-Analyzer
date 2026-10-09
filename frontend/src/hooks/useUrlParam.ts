import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

/**
 * URL 쿼리 하나를 상태처럼 쓴다. 다른 쿼리는 보존한다.
 * set(null)이면 지운다. `drop`에 준 키도 함께 지운다(예: 지역을 바꾸면 snapshot 제거).
 */
export function useUrlParam(
  name: string,
): [
  string | null,
  (value: string | null, options?: { drop?: string[]; replace?: boolean }) => void,
] {
  const [params, setParams] = useSearchParams();
  const value = params.get(name);
  const set = useCallback(
    (next: string | null, options: { drop?: string[]; replace?: boolean } = {}) => {
      setParams(
        (prev) => {
          const copy = new URLSearchParams(prev);
          if (next === null || next === '') copy.delete(name);
          else copy.set(name, next);
          for (const key of options.drop ?? []) copy.delete(key);
          return copy;
        },
        { replace: options.replace ?? false },
      );
    },
    [name, setParams],
  );
  return [value, set];
}
