/**
 * 화면 문자열은 ko.json 한 곳에서만 온다 (AGENTS.md 규칙 12).
 * `t('page.G1.title')`, `t('empty.unknownWithReason', { reason: '스캔' })`.
 * 키는 ko.json에서 타입으로 추론되므로 오타는 typecheck에서 걸린다.
 *
 * R11-I18N: 진입 청크에는 core(`virtual:ko/core`)만 정적으로 싣는다. 화면별 문자열(`page.<G>`)·차트(`chart`)·용어 본문
 * (`glossary`)은 빌드 플러그인 `ko-split` 이 화면 청크 안에 싣고 화면 모듈보다 먼저 registerStrings() 한다
 * (화면 폴더 → 이름공간 표는 ./namespaces.ts PAGE_NAMESPACES). t() 는 병합된 사전 하나를 본다 — 키·API 는 그대로다.
 * 원본은 ko.json 하나다. 테스트(setup.ts)·MSW 모드(main.tsx)·차트 갤러리는 loadAllNamespaces() 로 전부 등록한다.
 */
import core from 'virtual:ko/core';
import { KO_NAMESPACES, mergeInto, type KoNamespace, type KoTree } from './namespaces';
import type ko from './ko.json';

export { KO_NAMESPACES, type KoNamespace } from './namespaces';

type Dict = typeof ko;

type Leaves<T, P extends string = ''> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Leaves<T[K], `${P}${K}.`>;
}[keyof T & string];

export type TKey = Leaves<Dict>;
export type TParams = Record<string, string | number>;

/** 병합된 사전(core + 등록된 이름공간) */
const dict: KoTree = core;

/** 이름공간 청크 — 동적 import 는 리터럴이어야 Vite 가 청크로 나눈다(KO_NAMESPACES 와 1:1, 타입이 강제) */
const NAMESPACE_LOADERS: Record<KoNamespace, () => Promise<{ default: KoTree }>> = {
  'page/G0': () => import('virtual:ko/ns/page/G0'),
  'page/G0_2': () => import('virtual:ko/ns/page/G0_2'),
  'page/G1': () => import('virtual:ko/ns/page/G1'),
  'page/G2': () => import('virtual:ko/ns/page/G2'),
  'page/G3': () => import('virtual:ko/ns/page/G3'),
  'page/G4': () => import('virtual:ko/ns/page/G4'),
  'page/G5': () => import('virtual:ko/ns/page/G5'),
  'page/G6': () => import('virtual:ko/ns/page/G6'),
  'page/G7': () => import('virtual:ko/ns/page/G7'),
  'page/G8': () => import('virtual:ko/ns/page/G8'),
  chart: () => import('virtual:ko/ns/chart'),
  glossary: () => import('virtual:ko/ns/glossary'),
};

const loading = new Map<KoNamespace, Promise<void>>();

/** 문자열 트리를 사전에 붙인다(루트부터 감싼 모양 — {page:{G3:{…}}}). 테스트는 ko.json 전체를 넘긴다. */
export function registerStrings(tree: KoTree): void {
  mergeInto(dict, tree);
}

/** 이름공간 하나를 받아 등록한다(한 번만 받는다 — 같은 Promise). */
export function loadNamespace(ns: KoNamespace): Promise<void> {
  let p = loading.get(ns);
  if (!p) {
    p = NAMESPACE_LOADERS[ns]().then(
      (mod) => registerStrings(mod.default),
      (error: unknown) => {
        loading.delete(ns); // 다음 이동 때 다시 시도(청크 실패는 화면 lazy 와 같이 오류 경계로 간다)
        throw error;
      },
    );
    loading.set(ns, p);
  }
  return p;
}

export async function loadNamespaces(list: readonly KoNamespace[]): Promise<void> {
  await Promise.all(list.map(loadNamespace));
}

/** 모든 이름공간(MSW 모드·차트 갤러리 같은 개발 화면) */
export function loadAllNamespaces(): Promise<void> {
  return loadNamespaces(KO_NAMESPACES);
}

function lookup(key: string): string | undefined {
  let node: unknown = dict;
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
