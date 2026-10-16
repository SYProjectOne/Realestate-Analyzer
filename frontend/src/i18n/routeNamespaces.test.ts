/**
 * R11-I18N: 화면이 쓰는 키가 첫 렌더에 사전에 있는가 — 정적 검사.
 *
 *  1. 진입(main.tsx 에서 **정적** import 로 닿는 모듈)이 쓰는 키는 전부 core 에 있다.
 *  2. routes.tsx 가 lazy 로 여는 화면 폴더(`import('@/pages/x')`)마다: 그 index 에서 import(정적·동적 모두, barrel 포함 —
 *     넉넉하게)로 닿는 모듈이 쓰는 키는 core ∪ PAGE_NAMESPACES[x](namespaces.ts — 빌드가 그 화면 청크에 싣는 문자열)에 있다.
 *  3. 화면 폴더·차트·컴포넌트 모듈 최상위(렌더 밖)에서 이름공간 키로 t() 를 부르지 않는다 — 여러 화면이 같이 쓰는 모듈은
 *     공용 청크로 빠져 화면 문자열 등록보다 먼저 평가될 수 있다. core 만 등록한 채 그 모듈들을 불러 경고가 없는지 본다.
 *
 * 키 찾기: 주석을 지운 소스의 문자열 리터럴 'a.b.c' 과 템플릿 접두 `a.b.${…}`(그 아래 잎 전부가 있어야 한다).
 * ko.json 에 없는 점 문자열은 무시한다(키 오타는 TKey 타입이 잡는다).
 *
 * 실패하면: 메시지가 말하는 이름공간을 src/i18n/namespaces.ts 의 PAGE_NAMESPACES[화면 폴더]에 더한다(화면 코드는 그대로).
 */
import ko from './ko.json';
import {
  getPath,
  KO_NAMESPACES,
  leafPaths,
  PAGE_NAMESPACES,
  splitKo,
  type KoNamespace,
  type KoTree,
} from './namespaces';

const SOURCES = import.meta.glob<string>(
  ['/src/**/*.{ts,tsx}', '!/src/**/*.test.{ts,tsx}', '!/src/**/*.d.ts', '!/src/test/**'],
  { query: '?raw', import: 'default', eager: true },
);

const full = ko as KoTree;
const { core, namespaces } = splitKo(full);
const CORE_LEAVES = new Set(leafPaths(core));
const NS_OF_LEAF = new Map<string, KoNamespace>(
  KO_NAMESPACES.flatMap((ns) => leafPaths(namespaces[ns]).map((leaf) => [leaf, ns] as const)),
);
const TOP = new Set(Object.keys(ko));

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`\\])\/\/.*$/gm, '$1');
}

const CODE = new Map(Object.entries(SOURCES).map(([file, src]) => [file, stripComments(src)]));

function resolveSpec(from: string, spec: string): string | null {
  let base: string;
  if (spec.startsWith('@/')) base = `/src/${spec.slice(2)}`;
  else if (spec.startsWith('.')) {
    const parts = from.split('/').slice(0, -1);
    for (const seg of spec.split('/')) {
      if (seg === '..') parts.pop();
      else if (seg !== '.') parts.push(seg);
    }
    base = parts.join('/');
  } else return null;
  for (const c of [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`]) {
    if (CODE.has(c)) return c;
  }
  return null;
}

/** 모듈이 import 하는 소스 파일(타입 전용 import 제외) */
function importsOf(file: string, withDynamic: boolean): string[] {
  const code = CODE.get(file) ?? '';
  const out: string[] = [];
  for (const m of code.matchAll(
    /(?:^|[\s;])(import|export)\s+([^'"`;]*?)\s*from\s*['"]([^'"]+)['"]/g,
  )) {
    const clause = m[2] ?? '';
    if (/^type\s/.test(clause)) continue;
    const r = resolveSpec(file, m[3] ?? '');
    if (r) out.push(r);
  }
  for (const m of code.matchAll(/(?:^|[\s;])import\s*['"]([^'"]+)['"]/g)) {
    const r = resolveSpec(file, m[1] ?? '');
    if (r) out.push(r);
  }
  if (withDynamic) {
    for (const m of code.matchAll(/import\(\s*['"]([^'"]+)['"]\s*\)/g)) {
      const r = resolveSpec(file, m[1] ?? '');
      if (r) out.push(r);
    }
  }
  return out;
}

function closure(start: string, withDynamic: boolean): string[] {
  const seen = new Set<string>();
  const stack = [start];
  while (stack.length > 0) {
    const f = stack.pop() as string;
    if (seen.has(f)) continue;
    seen.add(f);
    stack.push(...importsOf(f, withDynamic));
  }
  return [...seen];
}

/** 파일이 쓰는 ko 키의 잎(템플릿 접두면 그 아래 잎 전부) */
function keyLeavesOf(file: string): string[] {
  const code = CODE.get(file) ?? '';
  const paths = new Set<string>();
  for (const m of code.matchAll(/(['"`])([A-Za-z_]\w*(?:\.\w+)+)\1/g)) paths.add(m[2] as string);
  for (const m of code.matchAll(/`([A-Za-z_]\w*(?:\.\w+)*)\.\$\{/g)) paths.add(m[1] as string);
  const leaves: string[] = [];
  for (const p of paths) {
    if (!TOP.has(p.split('.')[0] as string)) continue;
    const node = getPath(full, p);
    if (node === undefined) continue;
    leaves.push(...(typeof node === 'string' ? [p] : leafPaths(node, `${p}.`)));
  }
  return leaves;
}

interface Missing {
  file: string;
  leaf: string;
  ns: KoNamespace | undefined;
}

/**
 * 진입 닫힘에 (barrel 로) 들어 있지만 그 이름공간 키는 화면 안에서만 그리는 모듈. 셸 파일이 이것을 그리지 않는지는
 * 아래 '셸은 용어 본문을 그리지 않는다' 가 본다.
 */
const ROUTE_ONLY: Record<string, KoNamespace> = { '/src/components/Term.tsx': 'glossary' };

/** 라우트 밖에서(이름공간 없이) 그려지는 셸 파일 */
const SHELL =
  /^\/src\/(layout\/|app\/(?!ChartGalleryPage)|pages\/(not-found|share)\/|main\.tsx|routes\.tsx|AppProviders\.tsx)/;

function missingFor(
  files: string[],
  allowed: readonly KoNamespace[],
  exempt: Record<string, KoNamespace> = {},
): Missing[] {
  const ok = new Set(allowed);
  const out: Missing[] = [];
  for (const file of files) {
    for (const leaf of keyLeavesOf(file)) {
      if (CORE_LEAVES.has(leaf)) continue;
      const ns = NS_OF_LEAF.get(leaf);
      if (ns && ok.has(ns)) continue;
      if (ns && exempt[file] === ns) continue;
      out.push({ file, leaf, ns });
    }
  }
  return out;
}

function report(missing: Missing[]): string[] {
  const byNs = new Map<string, Missing[]>();
  for (const m of missing) byNs.set(m.ns ?? '?', [...(byNs.get(m.ns ?? '?') ?? []), m]);
  return [...byNs].map(
    ([ns, ms]) =>
      `needs '${ns}' — e.g. ${ms
        .slice(0, 3)
        .map((m) => `${m.leaf} (${m.file})`)
        .join(', ')}${ms.length > 3 ? ` +${ms.length - 3}` : ''}`,
  );
}

interface RouteNs {
  module: string;
  folder: string;
  file: string;
  ns: readonly KoNamespace[];
}

/** routes.tsx 가 lazy 로 여는 화면 폴더 + 그 이름공간 */
function routeTable(): RouteNs[] {
  const src = CODE.get('/src/routes.tsx') ?? '';
  return [...src.matchAll(/import\(\s*'(@\/pages\/([^'/]+))'\s*\)/g)].map((m) => {
    const folder = m[2] as string;
    return {
      module: m[1] as string,
      folder,
      file: resolveSpec('/src/routes.tsx', m[1] as string) ?? '',
      ns: PAGE_NAMESPACES[folder] ?? [],
    };
  });
}

describe('화면 이름공간 — 화면이 쓰는 키가 첫 렌더 전에 등록된다', () => {
  const routes = routeTable();

  it('routes.tsx 의 화면 폴더 = PAGE_NAMESPACES 의 폴더(빠진 것·남은 것 없음)', () => {
    expect(routes.length).toBeGreaterThanOrEqual(11);
    expect(routes.map((r) => r.folder).sort()).toEqual(Object.keys(PAGE_NAMESPACES).sort());
    for (const r of routes) {
      expect(r.file, r.module).toBe(`/src/pages/${r.folder}/index.tsx`);
      for (const ns of r.ns) expect(KO_NAMESPACES, `${r.folder} ${ns}`).toContain(ns);
    }
  });

  it('진입(main.tsx 정적 닫힘)이 쓰는 키는 전부 core', () => {
    const files = closure('/src/main.tsx', false);
    expect(files).toContain('/src/routes.tsx');
    expect(files).toContain('/src/layout/Header.tsx');
    expect(report(missingFor(files, [], ROUTE_ONLY))).toEqual([]);
  });

  it('셸(라우트 밖)은 용어 본문(Term·glossaryItem)을 그리지 않는다 — ROUTE_ONLY 의 전제', () => {
    const shell = [...CODE.keys()].filter((f) => SHELL.test(f));
    expect(shell).toContain('/src/layout/Header.tsx');
    const offenders = shell.filter((f) =>
      /<Term\b|glossaryItem\(|<KeepNote[^>]*\bterm=/.test(CODE.get(f) ?? ''),
    );
    expect(offenders).toEqual([]);
  });

  it('검사가 실제로 키를 찾는다(자기 점검)', () => {
    const complex = routes.find((r) => r.folder === 'complex');
    expect(complex).toBeDefined();
    const files = closure(complex?.file ?? '', true);
    const leaves = new Set(files.flatMap(keyLeavesOf));
    expect([...leaves].some((l) => l.startsWith('page.G3.'))).toBe(true);
    expect([...leaves].some((l) => l.startsWith('chart.'))).toBe(true);
    expect([...leaves].some((l) => l.startsWith('glossary.items.'))).toBe(true);
    expect(missingFor(files, []).length).toBeGreaterThan(0);
  });

  it.each(routeTable().map((r) => [r.folder, r] as const))(
    '%s — core ∪ PAGE_NAMESPACES 에 모든 키',
    (folder, r) => {
      const files = closure(r.file, true);
      expect(report(missingFor(files, r.ns)), `PAGE_NAMESPACES['${folder}']`).toEqual([]);
    },
  );
});

describe('화면 문자열 등록 — 빌드 플러그인(ko-split transform)', () => {
  it('화면 index 를 불러오면 그 화면 이름공간이 등록돼 있다(core 만 있던 새 i18n 에서)', async () => {
    vi.resetModules();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const fresh = await import('./index');
    const g7 = leafPaths(namespaces['page/G7'])[0] as Parameters<typeof fresh.t>[0];
    expect(fresh.t(g7)).toBe(g7);
    await import('@/pages/ops');
    expect(fresh.t(g7)).toBe(getPath(full, g7));
    expect(fresh.t('glossary.items.total.term')).toBe(ko.glossary.items.total.term);
    expect(warn).toHaveBeenCalledTimes(1);
  }, 60_000);
});

describe('모듈 최상위에서 이름공간 키를 쓰지 않는다', () => {
  it('core 만 등록한 채 화면 폴더(index 제외)·차트·컴포넌트 모듈을 평가해도 missing key 경고가 없다', async () => {
    vi.resetModules();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const loaders = import.meta.glob([
      '/src/pages/*/*.{ts,tsx}',
      '!/src/pages/*/index.tsx',
      '!/src/pages/**/*.test.{ts,tsx}',
    ]);
    expect(Object.keys(loaders).length).toBeGreaterThanOrEqual(20);
    // 새 레지스트리의 i18n(core 만 — setup.ts 의 전체 등록은 이전 인스턴스에 했다)
    const fresh = await import('./index');
    expect(fresh.t('page.G3.title')).toBe(ko.page.G3.title);
    await import('@/charts');
    await import('@/components');
    for (const load of Object.values(loaders)) await load();
    const missing = warn.mock.calls
      .map((c) => String(c[0]))
      .filter((m) => m.startsWith('[i18n] missing key'));
    expect(missing).toEqual([]);
  }, 60_000);
});

describe('이름공간 목록', () => {
  it('KO_NAMESPACES 는 ko.json 에 실제로 있는 경로', () => {
    for (const ns of KO_NAMESPACES) {
      expect(leafPaths(namespaces[ns]).length, ns).toBeGreaterThan(0);
    }
    expect(KO_NAMESPACES.filter((ns) => ns.startsWith('page/'))).toHaveLength(10);
  });
});
