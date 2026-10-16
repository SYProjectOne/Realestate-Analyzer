/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs';
import { resolve as resolvePath } from 'node:path';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';
import { entryViolations, type ChunkLike } from './scripts/lib/bundle-guards';
import {
  getPath,
  KO_NAMESPACES,
  mergeInto,
  PAGE_NAMESPACES,
  splitKo,
  type KoNamespace,
  type KoTree,
} from './src/i18n/namespaces';

// API 서버(FastAPI) origin. 프론트는 항상 `/api` 접두로 부르고, dev 서버는 경로를 **그대로** 넘긴다
// (FastAPI 라우터가 API_PREFIX=/api 아래에 있고 nginx 도 /api 를 떼지 않는다 → 개발·운영 경로가 같다).
// 대상에 /api 를 붙이지 않는다: API_PROXY_TARGET=http://127.0.0.1:18765 (O), …/api (X).
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

/** 최대 JS 청크 크기(kB, 압축 전) — R3c 완료 기준 */
const MAX_CHUNK_KB = 500;

/** 빌드 산출 청크가 MAX_CHUNK_KB 를 넘으면 경고가 아니라 실패 */
function maxChunkGuard(): Plugin {
  return {
    name: 'max-chunk-guard',
    apply: 'build',
    generateBundle(_options, bundle) {
      const over = Object.values(bundle)
        .filter((item) => item.type === 'chunk')
        .map((chunk) => ({ name: chunk.fileName, kb: Buffer.byteLength(chunk.code) / 1000 }))
        .filter((chunk) => chunk.kb > MAX_CHUNK_KB);
      if (over.length > 0) {
        this.error(
          `청크가 ${MAX_CHUNK_KB}kB 를 넘는다: ${over.map((c) => `${c.name} ${c.kb.toFixed(1)}kB`).join(', ')}`,
        );
      }
    },
  };
}

/**
 * R5-FE2: 진입 청크의 정적 닫힘(첫 화면이 실행 전에 반드시 받는 JS)에 echarts·zrender·msw 가 끼거나 예산을 넘으면 실패
 * (scripts/lib/bundle-guards.ts). 모든 빌드 모드(운영·msw)에 건다.
 */
function entryChunkGuard(): Plugin {
  return {
    name: 'entry-chunk-guard',
    apply: 'build',
    generateBundle(_options, bundle) {
      const chunks = Object.values(bundle).filter(
        (item): item is typeof item & ChunkLike => item.type === 'chunk',
      );
      const problems = entryViolations(chunks);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
  };
}

const KO_JSON = fileURLToPath(new URL('./src/i18n/ko.json', import.meta.url));
const KO_VIRTUAL = 'virtual:ko/';
const KO_RESOLVED = `\0${KO_VIRTUAL}`;

/**
 * R11-I18N: ko.json(원본 한 파일, AGENTS 규칙 12)을 가상 모듈로 나눠 낸다 — 빌드·dev·vitest 모두.
 *  - `virtual:ko/core`: 진입 청크에 들어가는 core 사전(src/i18n/index.ts 가 정적 import)
 *  - `virtual:ko/page/<화면 폴더>`: 그 화면 이름공간(PAGE_NAMESPACES)을 **등록하는** 모듈. transform 이
 *    `src/pages/<폴더>/index.tsx` 맨 앞에 import 를 넣는다 → 화면 청크와 함께 받고, 화면 모듈보다 먼저 평가된다.
 *  - `virtual:ko/bundle/<화면 폴더>`: 그 화면 이름공간을 합친 트리(청크 `ko-route-<폴더>`, 위 등록 모듈이 정적 import)
 *  - `virtual:ko/ns/<이름공간>`: 이름공간 하나(청크 `ko-page-G3`·`ko-chart` …) — loadNamespace(MSW 모드·차트 갤러리)
 *  - `virtual:ko/keys/<점 경로>`: 그 아래 키 이름 목록(본문 없이 — 예: 용어 키 목록)
 * 나누는 규칙은 src/i18n/namespaces.ts. 매 load 마다 원본을 다시 읽는다(dev 에서 ko.json 을 고치면 바로 반영).
 */
function koSplit(): Plugin {
  const readKo = (): KoTree => JSON.parse(readFileSync(KO_JSON, 'utf8')) as KoTree;
  const asModule = (value: unknown) =>
    `export default JSON.parse(${JSON.stringify(JSON.stringify(value))});\n`;
  return {
    name: 'ko-split',
    resolveId(id) {
      return id.startsWith(KO_VIRTUAL) ? `\0${id}` : null;
    },
    load(id) {
      if (!id.startsWith(KO_RESOLVED)) return null;
      this.addWatchFile(KO_JSON);
      const rest = id.slice(KO_RESOLVED.length);
      const full = readKo();
      if (rest === 'core') return asModule(splitKo(full).core);
      if (rest.startsWith('ns/')) {
        const ns = rest.slice('ns/'.length) as KoNamespace;
        if (!KO_NAMESPACES.includes(ns)) this.error(`ko-split: unknown namespace ${ns}`);
        return asModule(splitKo(full).namespaces[ns]);
      }
      if (rest.startsWith('page/')) {
        // 그 화면 이름공간을 합친 청크 하나(`ko-route-<폴더>`)를 **정적** import 해 등록 — 화면 청크와 같이(병렬로) 받고
        // 화면 모듈보다 먼저 평가된다. 요청은 화면당 하나(이름공간마다 따로 받으면 모바일 G3 가 −2점 — R11-I18N A/B 실측).
        // 여러 화면이 쓰는 이름공간(chart·page/G3)은 화면 묶음마다 사본이 들어간다(이동할 때 몇 kB).
        const folder = rest.slice('page/'.length);
        const list = PAGE_NAMESPACES[folder];
        if (!list) this.error(`ko-split: no PAGE_NAMESPACES entry ${folder}`);
        if (list.length === 0) return `export {};\n`;
        return `import { registerStrings } from '@/i18n';\nimport s from '${KO_VIRTUAL}bundle/${folder}';\nregisterStrings(s);\n`;
      }
      if (rest.startsWith('bundle/')) {
        const folder = rest.slice('bundle/'.length);
        const split = splitKo(full);
        const out: KoTree = {};
        for (const ns of PAGE_NAMESPACES[folder] ?? []) mergeInto(out, split.namespaces[ns]);
        return asModule(out);
      }
      if (rest.startsWith('keys/')) {
        const node = getPath(full, rest.slice('keys/'.length));
        if (node === undefined || typeof node === 'string')
          this.error(`ko-split: no subtree ${rest}`);
        return asModule(Object.keys(node));
      }
      this.error(`ko-split: unknown module ${id}`);
    },
    transform(code, id) {
      // 화면 index 모듈 맨 앞(첫 줄, 줄 번호를 밀지 않는다 — 소스맵 그대로)에 화면 문자열 등록 import
      const path = id.replace(/\\/g, '/').split('?')[0] ?? '';
      const m = /\/src\/pages\/([^/]+)\/index\.tsx$/.exec(path);
      if (!m || !((m[1] as string) in PAGE_NAMESPACES)) return null;
      return { code: `import '${KO_VIRTUAL}page/${m[1]}';${code}`, map: null };
    },
    handleHotUpdate({ file, server }) {
      if (resolvePath(file) !== resolvePath(KO_JSON)) return undefined;
      const mods = [...server.moduleGraph.idToModuleMap.values()].filter((m) =>
        m.id?.startsWith(KO_RESOLVED),
      );
      for (const m of mods) server.moduleGraph.invalidateModule(m);
      return mods;
    },
  };
}

/** 첫 화면 공용 라이브러리(React·라우터·쿼리) — 'vendor' 청크(진입이 정적으로 import, 앱 코드와 따로 캐시) */
const VENDOR =
  /\/node_modules\/(react|react-dom|scheduler|react-router|cookie|set-cookie-parser|@tanstack\/(react-query|query-core))\//;

export default defineConfig(({ mode }) => ({
  plugins: [koSplit(), react(), maxChunkGuard(), entryChunkGuard()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    // R3c 완료 기준: 최대 청크 ≤ 500kB — maxChunkGuard 가 넘으면 빌드를 실패시킨다
    chunkSizeWarningLimit: MAX_CHUNK_KB,
    rollupOptions: {
      output: {
        // echarts(트리 셰이킹 후에도 ~650kB)를 렌더 엔진(zrender + 공용 tslib)과 echarts 로 나눈다(순환 청크 없음).
        // 둘 다 차트가 뷰포트에 들어올 때 lazy 로 받는다(EChart.tsx).
        // R5-FE2: rollup 은 수동 청크 모듈의 정적 의존성 중 주인 없는 것을 그 청크로 끌어간다 — 공용 도우미(`\0commonjsHelpers`·
        // `\0vite/preload-helper`)가 zrender·msw 청크로 들어가 진입 청크가 그 청크들을 정적으로 import 했다(첫 화면 +196kB,
        // MSW 빌드는 +296kB). 도우미('\0' 가상 모듈)와 React 계열은 'vendor' 로 못박는다. entry-chunk-guard 가 회귀를 막는다.
        manualChunks(id) {
          const path = id.replace(/\\/g, '/');
          // R11-I18N: ko 가상 모듈은 vendor('\0' 도우미 규칙)로 끌려가면 안 된다 — core 는 진입 청크(i18n 과 같이),
          // 화면 묶음은 `ko-route-<폴더>`, 이름공간 하나는 `ko-page-G3` 등(MSW 모드·갤러리의 loadAllNamespaces)
          if (id.startsWith(KO_RESOLVED)) {
            const ns = id.slice(KO_RESOLVED.length);
            if (ns.startsWith('bundle/')) return `ko-route-${ns.slice('bundle/'.length)}`;
            return ns.startsWith('ns/')
              ? `ko-${ns.slice('ns/'.length).replace(/\//g, '-')}`
              : undefined;
          }
          if (VENDOR.test(path)) return 'vendor';
          if (id.startsWith('\0') && !path.includes('/node_modules/')) return 'vendor';
          if (!path.includes('/node_modules/')) return undefined;
          if (/\/node_modules\/(zrender|tslib)\//.test(path)) return 'zrender';
          // MSW 모드 빌드(e2e/pages·dev:msw) 전용 — 운영 빌드에는 없다(main.tsx 의 죽은 동적 import 로 모듈만 해석돼
          // 빈 'msw' 청크 경고가 나므로 운영 빌드에서는 이름을 붙이지 않는다)
          if (
            mode !== 'production' &&
            /\/node_modules\/(msw|@mswjs|@bundled-es-modules)\//.test(path)
          )
            return 'msw';
          if (path.includes('/node_modules/echarts/')) return 'echarts';
          return undefined;
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', 'eslint-rules/**/*.test.{js,ts}', 'scripts/**/*.test.ts'],
    css: false,
    restoreMocks: true,
    // 모든 파일 같은 값(6차 리뷰: `_shared/testing` 을 import 하지 않는 파일은 vitest 기본 5초라 findBy 5초와 겹쳐
    // 부하에서 'Test timed out' 으로 먼저 끊겼다). 화면 하나가 쿼리·지연 로드 청크를 여럿 기다린다.
    testTimeout: 20_000,
  },
}));
