/**
 * npm run lighthouse — R3 M15 / WP6 완료 기준 "Lighthouse 80 이상"을 자동으로 잰다.
 *
 *  1. **운영 빌드**(`vite build`, mode production → dist/lighthouse). `--no-build` 면 있는 빌드를 쓴다.
 *  2. `vite preview`(같은 프로세스, Vite JS API)로 띄우고, `/api` 는 preview 서버가 계약 예시 응답으로 답한다
 *     (R5-FE2 · `scripts/lib/mock-api.ts`: MSW 핸들러 `src/mocks/handlers.ts` 를 Vite SSR 로 읽어 서버에서 `getResponse`).
 *     측정하는 번들은 운영과 같다 — 브라우저 MSW(msw 런타임·계약 예시 데이터·서비스 워커 등록이 첫 렌더 앞에 끼어
 *     첫 화면 지표가 운영보다 나쁘게 잡혔다)를 쓰지 않는다. 예전 방식은 `--msw`(MSW 모드 빌드 → dist/msw, 서비스 워커).
 *  3. 주요 화면마다 Lighthouse(devDependency `lighthouse` CLI)를 headless Chrome 으로 **LH_RUNS 번(기본 3)** 돌린다.
 *     Chrome = CHROME_PATH, 없으면 Playwright chromium(`npx playwright install chromium`).
 *  4. 성능·접근성·권장 사항(best-practices) 점수를 횟수별 **중앙값**으로 판정해 표를 찍고, 하나라도 80 미만이면 exit 1.
 *     지표(FCP·LCP·TBT·CLS)·감점 감사는 중앙값 성능 점수를 낸 실행 것이다. 기준·횟수·중앙값은 scripts/lib/lighthouse-targets.ts.
 *
 * 폼 팩터: 데스크톱 프리셋(D7: 이 도구는 데스크톱 우선) 전 화면(G0·G0-2·G1~G8, 목록은 scripts/lib/lighthouse-targets.ts) + 모바일(Lighthouse 기본, 느린 4G·CPU 4배 감속)
 * 은 모바일을 지원하는 G1·G2·G3(읽기 전용)만.
 *
 * 측정이 계약 예시 응답으로 된 화면인지(사전 점검): Lighthouse 전에 Playwright 로 화면마다 한 번 열어 h1 이 보이고 네트워크가
 * 잠잠해질 때까지 계약 예시 핸들러가 못 답한 /api(`--msw` 면 서비스 워커를 지나쳐 서버에 온 /api)가 하나도 없는지,
 * "불러오지 못했습니다" 오류가 없는지 본다 — 어기면 실패. Lighthouse 실행 중의 누수는 참고로만 적는다(`--msw` 에서는
 * Lighthouse 가 측정 뒤 페이지를 떠나며(bf-cache 감사) 재조회 요청이 진행 중이면 MSW 워커가 클라이언트를 잃고 네트워크로
 * 넘긴다 — 측정 구간 밖이다).
 *
 * 옵션: --no-build · --msw · --port <n>(기본 4391) · --only <path,...>(앞의 / 생략 가능: ops,complexes/2) ·
 * LH_RUNS(기본 3 — 화면당 측정 횟수, 중앙값으로 판정)
 */
import { execFile } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { promisify } from 'node:util';
import { chromium } from '@playwright/test';
import type { RequestHandler } from 'msw';
import { build, createServer, preview } from 'vite';
import {
  CATEGORIES,
  median,
  medianRunIndex,
  runsFromEnv,
  TARGETS,
  THRESHOLD,
  type Category,
  type FormFactor,
  type Target,
} from './lib/lighthouse-targets';
import { mockApiMiddleware } from './lib/mock-api';
import { FRONTEND_ROOT } from './lib/openapi-source';

const run = promisify(execFile);

interface Result {
  target: Target;
  /** 사전 점검(Playwright)에서 MSW 를 지나쳐 서버에 온 /api 요청·화면 오류 */
  apiLeaks: string[];
  /** Lighthouse 실행 중(측정 뒤 이동 포함) 서버에 온 /api — 참고 */
  lhLeaks: string[];
  scores: Record<Category, number>;
  /** 횟수별 성능 점수(측정 순서) */
  perfRuns: number[];
  metrics: { fcp: string; lcp: string; tbt: string; cls: string };
  failedAudits: string[];
}

function arg(name: string): string | null {
  const i = process.argv.indexOf(name);
  return i >= 0 ? (process.argv[i + 1] ?? null) : null;
}

/** 측정 방식: server = 운영 빌드 + preview 서버가 계약 예시 응답(기본), msw = MSW 모드 빌드 + 서비스 워커(--msw) */
type MockMode = 'server' | 'msw';

const OUT_DIRS: Record<MockMode, string> = {
  server: resolve(FRONTEND_ROOT, 'dist/lighthouse'),
  msw: resolve(FRONTEND_ROOT, 'dist/msw'),
};
const BUILD_MODES: Record<MockMode, string> = { server: 'production', msw: 'msw' };

async function buildApp(mock: MockMode): Promise<void> {
  const outDir = OUT_DIRS[mock];
  console.log(`lighthouse: ${BUILD_MODES[mock]} 모드 빌드 → ${outDir}`);
  await build({
    root: FRONTEND_ROOT,
    mode: BUILD_MODES[mock],
    logLevel: 'warn',
    build: { outDir, emptyOutDir: true },
  });
}

/** 계약 예시 핸들러(src/mocks/handlers.ts)를 Vite SSR 로 읽는다(`@/` 별칭·JSON import·import.meta.env 를 앱과 같게) */
async function loadContractHandlers(): Promise<RequestHandler[]> {
  const vite = await createServer({
    root: FRONTEND_ROOT,
    mode: 'production',
    logLevel: 'warn',
    appType: 'custom',
    server: { middlewareMode: true, hmr: false, ws: false },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  try {
    const mod = (await vite.ssrLoadModule('/src/mocks/handlers.ts')) as {
      handlers: RequestHandler[];
    };
    return mod.handlers;
  } finally {
    await vite.close();
  }
}

function chromePath(): string {
  const path = process.env.CHROME_PATH ?? chromium.executablePath();
  if (!existsSync(path)) {
    throw new Error(
      `Chrome 이 없다: ${path} — \`npx playwright install chromium\` 또는 CHROME_PATH 를 준다.`,
    );
  }
  return path;
}

interface LhReport {
  categories: Record<
    Category,
    { score: number | null; auditRefs: { id: string; weight: number }[] }
  >;
  audits: Record<string, { score: number | null; displayValue?: string; title: string }>;
  runtimeError?: { code: string; message: string };
}

async function lighthouseOnce(url: string, formFactor: FormFactor, out: string): Promise<LhReport> {
  const cli = resolve(FRONTEND_ROOT, 'node_modules/lighthouse/cli/index.js');
  const args = [
    cli,
    url,
    `--only-categories=${CATEGORIES.join(',')}`,
    '--output=json',
    `--output-path=${out}`,
    '--chrome-flags=--headless=new --no-sandbox --disable-gpu',
    '--quiet',
    ...(formFactor === 'desktop' ? ['--preset=desktop'] : []),
  ];
  await run(process.execPath, args, {
    env: { ...process.env, CHROME_PATH: chromePath() },
    maxBuffer: 64 * 1024 * 1024,
    timeout: 240_000,
  });
  const report = JSON.parse(readFileSync(out, 'utf8')) as LhReport;
  if (report.runtimeError) {
    throw new Error(`${url}: ${report.runtimeError.code} ${report.runtimeError.message}`);
  }
  return report;
}

/** 계약 예시 핸들러가 못 답한 /api(`--msw`: 서비스 워커를 지나쳐 preview 서버에 온 /api) */
const apiHits: string[] = [];

async function measure(base: string, target: Target, dir: string, runs: number): Promise<Result> {
  const reports: LhReport[] = [];
  const hitsBefore = apiHits.length;
  for (let i = 0; i < runs; i += 1) {
    const name = `${target.formFactor}${target.path.replace(/\W/g, '_')}_${i}.json`;
    reports.push(await lighthouseOnce(`${base}${target.path}`, target.formFactor, join(dir, name)));
  }
  const scores = Object.fromEntries(
    CATEGORIES.map((c) => [
      c,
      median(reports.map((r) => Math.round((r.categories[c].score ?? 0) * 100))),
    ]),
  ) as Record<Category, number>;
  const perfRuns = reports.map((r) => Math.round((r.categories.performance.score ?? 0) * 100));
  const rep = reports[medianRunIndex(perfRuns)] as LhReport;
  const a = rep.audits;
  const failedAudits = CATEGORIES.flatMap((c) =>
    rep.categories[c].auditRefs
      .filter((ref) => ref.weight > 0 && (a[ref.id]?.score ?? 1) < 0.9)
      .map((ref) => `${c}:${ref.id}`),
  );
  return {
    target,
    apiLeaks: [],
    lhLeaks: apiHits.slice(hitsBefore),
    scores,
    perfRuns,
    metrics: {
      fcp: a['first-contentful-paint']?.displayValue ?? '-',
      lcp: a['largest-contentful-paint']?.displayValue ?? '-',
      tbt: a['total-blocking-time']?.displayValue ?? '-',
      cls: a['cumulative-layout-shift']?.displayValue ?? '-',
    },
    failedAudits,
  };
}

function printTable(results: Result[]): void {
  const rows = results.map((r) => [
    r.target.path,
    r.target.formFactor,
    String(r.scores.performance),
    r.perfRuns.join('/'),
    String(r.scores.accessibility),
    String(r.scores['best-practices']),
    r.metrics.fcp,
    r.metrics.lcp,
    r.metrics.tbt,
    r.metrics.cls,
    String(r.apiLeaks.length),
    passed(r) ? 'ok' : 'FAIL',
  ]);
  const head = [
    'page',
    'form',
    'perf',
    'perf runs',
    'a11y',
    'bp',
    'FCP',
    'LCP',
    'TBT',
    'CLS',
    'api miss',
    '',
  ];
  const widths = head.map((h, i) => Math.max(h.length, ...rows.map((row) => row[i]?.length ?? 0)));
  const line = (cells: string[]) => cells.map((c, i) => c.padEnd(widths[i] ?? 0)).join(' | ');
  console.log(line(head));
  console.log(widths.map((w) => '-'.repeat(w)).join('-|-'));
  for (const row of rows) console.log(line(row));
  for (const r of results) {
    if (r.failedAudits.length > 0) {
      console.log(
        `  ${r.target.formFactor} ${r.target.path} 감점 감사: ${r.failedAudits.join(', ')}`,
      );
    }
    if (r.apiLeaks.length > 0) {
      console.log(
        `  ${r.target.formFactor} ${r.target.path} 사전 점검 실패: ${r.apiLeaks.join(', ')}`,
      );
    }
    if (r.lhLeaks.length > 0) {
      console.log(
        `  (참고) ${r.target.formFactor} ${r.target.path} Lighthouse 중 계약 예시 밖 /api ${r.lhLeaks.length}건`,
      );
    }
  }
}

function passed(r: Result): boolean {
  return r.apiLeaks.length === 0 && CATEGORIES.every((c) => r.scores[c] >= THRESHOLD);
}

const LOAD_ERROR_PREFIX = '불러오지 못했습니다';

/** 사전 점검: 화면마다 새 컨텍스트로 열어 MSW 가 모든 /api 를 가로챘는지·오류 문구가 없는지 */
async function sanityCheck(base: string, paths: string[]): Promise<Map<string, string[]>> {
  const out = new Map<string, string[]>();
  const browser = await chromium.launch({ executablePath: chromePath() });
  try {
    for (const path of paths) {
      const context = await browser.newContext();
      const page = await context.newPage();
      const before = apiHits.length;
      const problems: string[] = [];
      try {
        await page.goto(`${base}${path}`, { waitUntil: 'networkidle', timeout: 60_000 });
        await page.locator('h1').first().waitFor({ state: 'visible', timeout: 30_000 });
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);
        const text = await page.locator('body').innerText();
        if (text.includes(LOAD_ERROR_PREFIX))
          problems.push(`화면 오류 문구 '${LOAD_ERROR_PREFIX}'`);
      } catch (err) {
        problems.push(err instanceof Error ? (err.message.split('\n')[0] ?? '') : String(err));
      }
      problems.push(...apiHits.slice(before).map((u) => `/api 누수 ${u}`));
      out.set(path, problems);
      await context.close();
    }
  } finally {
    await browser.close();
  }
  return out;
}

async function main(): Promise<number> {
  const port = Number(arg('--port') ?? 4391);
  const runs = runsFromEnv(process.env.LH_RUNS);
  const mock: MockMode = process.argv.includes('--msw') ? 'msw' : 'server';
  const outDir = OUT_DIRS[mock];
  // 경로는 앞의 / 없이 줘도 된다(Git Bash 가 "/ops" 를 Windows 경로로 바꾸는 것을 피한다): --only ops,complexes
  const only =
    arg('--only')
      ?.split(',')
      .filter(Boolean)
      .map((p) => `/${p.replace(/^\/+/, '')}`) ?? null;
  if (!process.argv.includes('--no-build') || !existsSync(join(outDir, 'index.html'))) {
    await buildApp(mock);
  }
  chromePath();
  const handlers = mock === 'server' ? await loadContractHandlers() : [];
  const server = await preview({
    root: FRONTEND_ROOT,
    mode: BUILD_MODES[mock],
    logLevel: 'warn',
    build: { outDir },
    // 실 API 프록시 끔(server.proxy 를 물려받지 않게) — /api 는 계약 예시(서버 핸들러 또는 MSW)만 응답해야 한다
    preview: { port, strictPort: true, host: '127.0.0.1', proxy: {} },
    plugins: [
      {
        name: 'lighthouse-contract-api',
        configurePreviewServer(server) {
          const unhandled = (url: string) => apiHits.push(url);
          server.middlewares.use(
            '/api',
            mock === 'server'
              ? mockApiMiddleware(handlers, unhandled)
              : (req, res) => {
                  unhandled(req.originalUrl ?? req.url ?? '');
                  res.statusCode = 503;
                  res.end();
                },
          );
        },
      },
    ],
  });
  console.log(
    `lighthouse: ${mock === 'server' ? '운영 빌드 + 서버 계약 예시 응답' : 'MSW 모드 빌드 + 서비스 워커'} · 화면당 ${runs}회(중앙값)`,
  );
  const base = `http://127.0.0.1:${port}`;
  const dir = mkdtempSync(join(tmpdir(), 'lh-'));
  const results: Result[] = [];
  try {
    const targets = only ? TARGETS.filter((t) => only.includes(t.path)) : TARGETS;
    if (targets.length === 0) throw new Error(`--only 에 맞는 화면이 없다: ${only?.join(',')}`);
    const sanity = await sanityCheck(base, [...new Set(targets.map((t) => t.path))]);
    for (const [path, problems] of sanity) {
      console.log(
        `lighthouse: 사전 점검 ${path} ${problems.length === 0 ? 'ok' : problems.join(' · ')}`,
      );
    }
    for (const target of targets) {
      const result = await measure(base, target, dir, runs);
      result.apiLeaks = sanity.get(target.path) ?? [];
      console.log(
        `lighthouse: ${target.formFactor} ${target.path} → ${CATEGORIES.map((c) => `${c} ${result.scores[c]}`).join(' · ')} (성능 ${result.perfRuns.join('/')})`,
      );
      results.push(result);
    }
  } finally {
    await new Promise<void>((done) => server.httpServer.close(() => done()));
    rmSync(dir, { recursive: true, force: true });
  }
  console.log('');
  printTable(results);
  const failed = results.filter((r) => !passed(r));
  console.log(
    failed.length === 0
      ? `\nlighthouse: 전부 ${THRESHOLD} 이상 (${results.length}건)`
      : `\nlighthouse: ${THRESHOLD} 미만 ${failed.length}건 — 실패`,
  );
  return failed.length === 0 ? 0 : 1;
}

main().then(
  (code) => process.exit(code),
  (err: unknown) => {
    console.error(err instanceof Error ? err.message : err);
    process.exit(1);
  },
);
