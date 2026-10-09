/**
 * 화면 문자열은 ko.json 한 곳에서만 온다 (AGENTS.md 규칙 12).
 * `t('page.G1.title')`, `t('empty.unknownWithReason', { reason: '스캔' })`.
 * 키는 ko.json에서 타입으로 추론되므로 오타는 typecheck에서 걸린다.
 */
import ko from './ko.json';

type Dict = typeof ko;

type Leaves<T, P extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Leaves<T[K], `${P}${K}.`>;
}[keyof T & string];

export type TKey = Leaves<Dict>;
export type TParams = Record<string, string | number>;

function lookup(key: string): string | undefined {
  let node: unknown = ko;
  for (const part of key.split('.')) {
    if (node === null || typeof node !== 'object') return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

export function t(key: TKey, params?: TParams): string {
  const template = lookup(key);
  if (template === undefined) {
    if (import.meta.env.DEV) console.warn(`[i18n] missing key: ${key}`);
    return key;
  }
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}

/** 런타임 문자열 키(예: 서버 enum 값)를 안전하게 찾는다. 없으면 fallback. */
export function tDynamic(key: string, fallback: string, params?: TParams): string {
  const template = lookup(key);
  if (template === undefined) return fallback;
  return params ? t(key as TKey, params) : template;
}
