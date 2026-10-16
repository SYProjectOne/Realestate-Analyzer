/**
 * R11-I18N: 화면 글자에 ko.json 키가 그대로 보이는가(t() 가 키를 못 찾으면 키를 돌려준다 — 이름공간이 늦거나 빠진 경우).
 * Lighthouse 사전 점검(scripts/lighthouse.ts)과 e2e(e2e/api/i18n-lazy.spec.ts)가 쓴다.
 *
 * 점으로 이은 영문 낱말(`page.G3.tabs`, 한글 잎이면 앞부분 `chart.C08.kind`)이 ko.json 의 경로(잎 또는 하위 트리)면 키 노출로 본다.
 */
import ko from '../../src/i18n/ko.json' with { type: 'json' };

type Tree = { [key: string]: string | Tree };

function hasPath(tree: Tree, path: string): boolean {
  let node: string | Tree | undefined = tree;
  for (const part of path.split('.')) {
    if (node === undefined || typeof node === 'string') return false;
    node = node[part];
  }
  return node !== undefined;
}

export function rawKeysIn(text: string): string[] {
  const found = new Set<string>();
  for (const m of text.matchAll(/[A-Za-z_]\w*(?:\.\w+)+/g)) {
    if (hasPath(ko as Tree, m[0])) found.add(m[0]);
  }
  return [...found];
}
