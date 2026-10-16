/**
 * R11-I18N: ko.json → core + 이름공간 나누기(namespaces.ts, 빌드 플러그인 `ko-split` 이 쓴다)와 지연 등록(index.ts).
 */
import ko from './ko.json';
import {
  CORE_PINS,
  getPath,
  KO_NAMESPACES,
  leafPaths,
  mergeInto,
  namespacePath,
  splitKo,
  type KoTree,
} from './namespaces';

const full = ko as KoTree;
const { core, namespaces } = splitKo(full);

describe('splitKo — 원본 하나를 빌드 때 나눈다', () => {
  it('core ∪ 이름공간 = ko.json 전체, 겹치는 잎 없음', () => {
    const all = leafPaths(full).sort();
    const parts = [core, ...KO_NAMESPACES.map((ns) => namespaces[ns])].map((tree) =>
      leafPaths(tree),
    );
    expect(parts.flat().sort()).toEqual(all);
    expect(new Set(parts.flat()).size).toBe(all.length);
  });

  it('다시 병합하면 원본과 같은 값(깊은 병합)', () => {
    const merged = mergeInto(JSON.parse(JSON.stringify(core)) as KoTree, {});
    for (const ns of KO_NAMESPACES) mergeInto(merged, namespaces[ns]);
    for (const leaf of leafPaths(full)) expect(getPath(merged, leaf)).toBe(getPath(full, leaf));
  });

  it('원본을 바꾸지 않는다', () => {
    expect(getPath(full, 'page.G3.title')).toBeDefined();
    expect(Object.keys(ko.page)).toContain('G7');
    expect(Object.keys(ko.chart).length).toBeGreaterThan(5);
  });

  it('이름공간은 자기 경로 아래만 갖는다', () => {
    for (const ns of KO_NAMESPACES) {
      const prefix = `${namespacePath(ns)}.`;
      const leaves = leafPaths(namespaces[ns]);
      expect(leaves.length, ns).toBeGreaterThan(0);
      for (const leaf of leaves) expect(leaf.startsWith(prefix), `${ns} ${leaf}`).toBe(true);
    }
  });

  it('core 에 남는 것: page.common·notFound·share, 화면 제목, 용어(glossary)', () => {
    for (const keep of [
      'page.common',
      'page.notFound',
      'page.share',
      'app',
      'nav',
      'job',
      'glossary',
    ]) {
      expect(leafPaths(getPath(full, keep) as KoTree).length).toBeGreaterThan(0);
      expect(getPath(core, keep), keep).toEqual(getPath(full, keep));
    }
    for (const g of Object.keys(ko.page)) {
      const title = getPath(full, `page.${g}.title`);
      if (title !== undefined) expect(getPath(core, `page.${g}.title`), g).toBe(title);
    }
    for (const pin of CORE_PINS.filter((p) => !p.includes('*'))) {
      expect(getPath(core, pin), pin).toEqual(getPath(full, pin));
    }
  });

  it('core 에서 빠지는 것: 화면 본문·차트', () => {
    expect(getPath(core, 'page.G3.tabs')).toBeUndefined();
    expect(getPath(core, 'chart')).toBeUndefined();
    expect(getPath(namespaces['page/G3'], 'page.G3.title')).toBeUndefined();
  });

  it('core 는 원본의 절반 이하(진입 청크 예산 — 화면 문구가 늘어도 core 는 그대로)', () => {
    const size = (tree: KoTree) => new TextEncoder().encode(JSON.stringify(tree)).length;
    expect(size(core)).toBeLessThan(size(full) / 2);
  });
});

describe('지연 등록 — core 만 실은 i18n 모듈', () => {
  it('이름공간을 받기 전에는 키가 없고(키를 돌려줌), loadNamespace 뒤에는 값', async () => {
    vi.resetModules();
    const fresh = await import('./index');
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(fresh.t('app.disclaimer')).toBe(ko.app.disclaimer);
    expect(fresh.t('page.G3.title')).toBe(ko.page.G3.title);
    const g3Leaf = leafPaths(namespaces['page/G3'])[0] as Parameters<typeof fresh.t>[0];
    expect(fresh.t(g3Leaf)).toBe(g3Leaf);
    expect(warn).toHaveBeenCalledWith(`[i18n] missing key: ${g3Leaf}`);
    await fresh.loadNamespace('page/G3');
    expect(fresh.t(g3Leaf)).toBe(getPath(full, g3Leaf));
    // 같은 이름공간은 한 번만(같은 Promise)
    expect(fresh.loadNamespace('page/G3')).toBe(fresh.loadNamespace('page/G3'));
    expect(fresh.t('chart.C01.title')).toBe('chart.C01.title');
    await fresh.loadAllNamespaces();
    expect(fresh.t('chart.C01.title')).toBe(ko.chart.C01.title);
  });
});
