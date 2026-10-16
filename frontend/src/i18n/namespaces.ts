/**
 * R11-I18N: ko.json 한 파일(AGENTS 규칙 12, 원본은 그대로)을 **빌드 때** 진입용 core 와 지연 로드 이름공간으로 나누는 규칙.
 * vite.config.ts 의 `ko-split` 플러그인(가상 모듈 `virtual:ko/*`)과 i18n/index.ts·테스트가 같이 쓴다 — 순수 함수만 둔다.
 *
 *  - core(진입 청크): 아래 이름공간을 뺀 전부 + CORE_PINS(이름공간 안이지만 셸·라우트 표가 쓰는 키)
 *  - 이름공간: page/G0 … page/G8 = `page.<G>`(title 은 core), chart = `chart.*`, glossary = `glossary.*`(셸이 쓰는 4개는 core)
 *    화면은 PAGE_NAMESPACES 대로 자기 청크 안에 싣는다(아래). 개발 화면(차트 갤러리)·MSW 모드는 이름공간 청크
 *    (`virtual:ko/ns/*`)를 loadAllNamespaces() 로 받는다.
 *  - `page.common`·`page.notFound`·`page.share`(공유 착지, 지연 로드 아님)는 core 다.
 *
 * 이름공간을 더할 때: KO_NAMESPACES 에 넣고 i18n/index.ts 의 NAMESPACE_LOADERS(동적 import 는 리터럴이어야 한다)에 한 줄.
 */

export const KO_NAMESPACES = [
  'page/G0',
  'page/G0_2',
  'page/G1',
  'page/G2',
  'page/G3',
  'page/G4',
  'page/G5',
  'page/G6',
  'page/G7',
  'page/G8',
  'chart',
  'glossary',
] as const;

export type KoNamespace = (typeof KO_NAMESPACES)[number];

/**
 * 화면 폴더(`src/pages/<폴더>/index.tsx`, routes.tsx 가 lazy 로 여는 것) → 그 화면이 쓰는 이름공간.
 *
 * 빌드 플러그인 `ko-split` 이 화면 index 모듈 맨 앞에 `import 'virtual:ko/page/<폴더>'` 를 넣는다 — 이 목록의 문자열을
 * 합친 트리를 **화면 청크 안에** 싣고 화면 모듈보다 먼저 등록한다(추가 요청 0, 첫 렌더에 문자열이 있다). 공용
 * 이름공간(chart·glossary)은 화면마다 사본이 들어간다 — 따로 받으면 모바일(HTTP/1.1 연결 6개)에서 요청 한 번이 늘어
 * LCP 가 0.1~0.3초 늦었다(R11-I18N 실측).
 *
 * 화면이 다른 화면의 `page.Gx.*`·`chart.*`·`<Term>` 을 새로 쓰면 여기에 이름공간을 더한다 —
 * src/i18n/routeNamespaces.test.ts 가 빠진 것을 이름으로 알려 준다. 화면 코드·routes.tsx 는 고치지 않는다.
 */
export const PAGE_NAMESPACES: Record<string, readonly KoNamespace[]> = {
  'region-new': ['page/G0', 'glossary'],
  'living-areas': ['page/G0_2', 'page/G0', 'glossary'],
  dashboard: ['page/G1', 'chart', 'glossary'],
  complexes: ['page/G2', 'glossary'],
  complex: ['page/G3', 'page/G2', 'chart', 'glossary'],
  compare: ['page/G4', 'page/G3', 'page/G5', 'chart', 'glossary'],
  scenario: ['page/G5', 'chart', 'glossary'],
  market: ['page/G6', 'chart', 'glossary'],
  ops: ['page/G7', 'page/G3', 'glossary'],
  reports: ['page/G8', 'glossary'],
  glossary: ['glossary'],
};

/** 화면 폴더 이름공간을 합친 트리(빌드 플러그인이 화면 청크에 싣는다) */
export function pageStrings(split: KoSplit, folder: string): KoTree {
  const list = PAGE_NAMESPACES[folder];
  if (!list) throw new Error(`no PAGE_NAMESPACES entry: ${folder}`);
  const out: KoTree = {};
  for (const ns of list) mergeInto(out, JSON.parse(JSON.stringify(split.namespaces[ns])) as KoTree);
  return out;
}

/** 이름공간 → ko.json 점 경로('page/G3' → 'page.G3') */
export function namespacePath(ns: KoNamespace): string {
  return ns.replace(/\//g, '.');
}

/**
 * 이름공간 안이지만 core 에 남기는 점 경로. `*` 는 한 단계 아무 키.
 *  - `page.*.title`: routes.tsx `titleKey`(라우트 표·셸) — 화면 청크 전에 필요할 수 있다
 *  - `glossary.nav|more|open|close`: 머리글 메뉴·용어 '?' 버튼 틀(Term 본문 `glossary.items` 는 이름공간)
 *  - `page.G5.error`: scenario/schema.ts 가 모듈 최상위(zod 스키마 메시지)에서 t() 를 부른다 — 화면 청크가 이름공간보다
 *    먼저 평가될 수 있다(routeNamespaces.test.ts '최상위' 검사). 화면 모듈 최상위 t() 키는 여기에 둔다.
 */
export const CORE_PINS: readonly string[] = [
  'page.*.title',
  'page.G5.error',
  'glossary.nav',
  'glossary.more',
  'glossary.open',
  'glossary.close',
];

export type KoTree = { [key: string]: string | KoTree };

function isTree(v: unknown): v is KoTree {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

/** 점 경로의 값(없으면 undefined) */
export function getPath(tree: KoTree, path: string): string | KoTree | undefined {
  let node: string | KoTree | undefined = tree;
  for (const part of path.split('.')) {
    if (!isTree(node)) return undefined;
    node = node[part];
  }
  return node;
}

/** 루트부터 점 경로까지 감싼 트리({page:{G3:{…}}}) — 등록할 때 깊은 병합으로 제자리에 붙는다 */
function wrap(path: string, value: string | KoTree): KoTree {
  return path
    .split('.')
    .reverse()
    .reduce<string | KoTree>((acc, part) => ({ [part]: acc }), value) as KoTree;
}

/** target 에 src 를 깊게 병합한다(제자리 변경). 같은 잎은 src 가 이긴다. */
export function mergeInto(target: KoTree, src: KoTree): KoTree {
  for (const [k, v] of Object.entries(src)) {
    const cur = target[k];
    if (isTree(v) && isTree(cur)) mergeInto(cur, v);
    else target[k] = isTree(v) ? mergeInto({}, v) : v;
  }
  return target;
}

function pinMatches(pin: string, path: string): boolean {
  const a = pin.split('.');
  const b = path.split('.');
  return a.length === b.length && a.every((seg, i) => seg === '*' || seg === b[i]);
}

/** 이름공간 루트(nsRoot) 아래에서 핀이 아닌 부분만 떼어 낸다. 반환: [core 에 남는 부분, 이름공간 부분] */
function splitSubtree(
  node: string | KoTree,
  path: string,
  pins: readonly string[],
): [string | KoTree | undefined, string | KoTree | undefined] {
  if (pins.some((p) => pinMatches(p, path))) return [node, undefined];
  if (!isTree(node)) return [undefined, node];
  const keep: KoTree = {};
  const move: KoTree = {};
  for (const [k, v] of Object.entries(node)) {
    const [kk, mm] = splitSubtree(v, `${path}.${k}`, pins);
    if (kk !== undefined) keep[k] = kk;
    if (mm !== undefined) move[k] = mm;
  }
  return [
    Object.keys(keep).length > 0 ? keep : undefined,
    Object.keys(move).length > 0 ? move : undefined,
  ];
}

export interface KoSplit {
  core: KoTree;
  /** 이름공간마다 루트부터 감싼 트리({page:{G3:{…}}}) */
  namespaces: Record<KoNamespace, KoTree>;
}

/** ko.json 전체 → core + 이름공간. 원본은 바꾸지 않는다. */
export function splitKo(full: KoTree, pins: readonly string[] = CORE_PINS): KoSplit {
  const core = JSON.parse(JSON.stringify(full)) as KoTree;
  const namespaces = {} as Record<KoNamespace, KoTree>;
  for (const ns of KO_NAMESPACES) {
    const path = namespacePath(ns);
    const parts = path.split('.');
    const last = parts.pop() as string;
    const parent = parts.length > 0 ? getPath(core, parts.join('.')) : core;
    const node = isTree(parent) ? parent[last] : undefined;
    if (!isTree(parent) || node === undefined) {
      throw new Error(`ko.json namespace path missing: ${path}`);
    }
    const [keep, move] = splitSubtree(node, path, pins);
    if (keep === undefined) delete parent[last];
    else parent[last] = keep;
    namespaces[ns] = move === undefined ? {} : wrap(path, move);
  }
  return { core, namespaces };
}

/** 트리의 잎 경로 전부 */
export function leafPaths(tree: KoTree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([k, v]) =>
    isTree(v) ? leafPaths(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}
