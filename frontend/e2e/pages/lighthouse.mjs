/**
 * Lighthouse 성능 점검(WP6 완료 기준: 성능 80 이상) — MSW 모드 프로덕션 빌드를 preview로 띄운 뒤 실행한다.
 *
 *   npx vite build --mode msw --outDir dist/msw      (dist/는 .gitignore)
 *   npx vite preview --outDir dist/msw --port 4391 --strictPort   (다른 터미널)
 *   node e2e/pages/lighthouse.mjs [baseUrl] [경로...]   예) ... http://localhost:4391 complexes market
 *   (경로는 앞의 /를 빼고 줘도 된다 — Git Bash가 "/x"를 Windows 경로로 바꾸는 것을 피하려고)
 *
 * lighthouse는 package.json에 없다 — `npx -y lighthouse@12`로 받는다(도구 추가 제안: devDependency).
 * 크롬은 CHROME_PATH가 없으면 Playwright chromium을 쓴다. 기본 = 모바일 에뮬레이션(Lighthouse 기본).
 */
/* global process, console -- Node 스크립트(eslint 설정의 node 전역은 tests/·scripts/에만 걸려 있다) */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from '@playwright/test';

const THRESHOLD = 80;
const [base = 'http://localhost:4391', ...rest] = process.argv.slice(2);
const pages = (rest.length > 0 ? rest : ['', 'complexes', 'complexes/2', 'market']).map(
  (p) => `/${p.replace(/^\/+/, '')}`,
);
const chrome = process.env.CHROME_PATH ?? chromium.executablePath();
const dir = mkdtempSync(join(tmpdir(), 'lh-'));

let failed = false;
for (const path of pages) {
  const out = join(dir, `${path.replace(/\W/g, '_') || 'root'}.json`);
  execFileSync(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    [
      '-y',
      'lighthouse@12',
      `${base}${path}`,
      '--only-categories=performance',
      '--output=json',
      `--output-path=${out}`,
      '--chrome-flags=--headless=new',
      '--quiet',
    ],
    {
      env: { ...process.env, CHROME_PATH: chrome },
      stdio: 'ignore',
      shell: process.platform === 'win32',
    },
  );
  const report = JSON.parse(readFileSync(out, 'utf8'));
  const score = Math.round(report.categories.performance.score * 100);
  const a = report.audits;
  if (score < THRESHOLD) failed = true;
  console.log(
    `${score >= THRESHOLD ? 'ok  ' : 'FAIL'} ${path} 성능 ${score}`,
    `FCP ${a['first-contentful-paint'].displayValue}`,
    `LCP ${a['largest-contentful-paint'].displayValue}`,
    `TBT ${a['total-blocking-time'].displayValue}`,
    `CLS ${a['cumulative-layout-shift'].displayValue}`,
  );
}
process.exit(failed ? 1 : 0);
