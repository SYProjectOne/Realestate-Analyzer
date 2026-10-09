import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router';

/** 탭 = URL 해시(RA §7-1 G3 "탭은 URL 해시"). 모르는 해시면 첫 탭. */
export function useHashTab<T extends string>(tabs: readonly T[]): [T, (tab: T) => void] {
  const location = useLocation();
  const navigate = useNavigate();
  const hash = decodeURIComponent(location.hash.replace(/^#/, ''));
  const current = (tabs as readonly string[]).includes(hash) ? (hash as T) : (tabs[0] as T);
  const set = useCallback(
    (tab: T) =>
      navigate(
        { pathname: location.pathname, search: location.search, hash: `#${tab}` },
        { replace: true },
      ),
    [location.pathname, location.search, navigate],
  );
  return [current, set];
}
