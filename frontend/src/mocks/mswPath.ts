import { API_BASE } from '@/api/client';

/** API_BASE의 경로 부분(`/api`). 절대 URL이면 pathname만. */
const prefix = (() => {
  const base = API_BASE.replace(/\/$/, '');
  if (/^https?:\/\//.test(base)) return new URL(base).pathname.replace(/\/$/, '');
  return base;
})();

/** 계약 경로(`/snapshots/:sid/dashboard`) → 어느 origin이든 맞는 MSW 패턴(`*\/api/snapshots/:sid/dashboard`) */
export function mswPath(path: string): string {
  return `*${prefix}${path}`;
}
