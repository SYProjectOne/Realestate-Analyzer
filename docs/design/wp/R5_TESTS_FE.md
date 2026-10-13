# R5-FE — 화면·e2e 정리 테스트·수정 전 실패 확인 (2026-10-13)

원문: `docs/design/wp/R5_FINAL.md` `=====FE`, 결정 `docs/design/DECISIONS.md` **D25-1**(D7·D10-8·D11-9·D25-2·D25-3 참고). 브랜치 `wp/r5-fe`(main `1dec271` 기준),
계약 **2026-10-09.18 그대로**(계약 변경 없음). 백엔드·계약·CI·`frontend/package.json`·차트 리눅스 기준 이미지는 건드리지 않았다(새 npm 패키지 없음).

**방법.** 테스트를 먼저 썼다. FE 1·2·트레이 상한은 동작이 이미 있었으므로(테스트 공백) 수정 전 실패는 **동작을 일부러 깨뜨린 트리**(뮤테이션)에서 새 테스트를
돌린 실제 출력이다 — 깨뜨린 뒤 `git checkout` 으로 되돌렸다. ko.json 검사·Lighthouse 대상은 새 코드이므로 main 상태(모듈·항목 없음)에서 돌린 출력이다.

## 1. 항목별 테스트·수정 전 실패

| 항목 | 구현·수정 | 테스트 | 수정 전(깨뜨린 트리 / main) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **FE-1** major `?scenario=`·`?snapshot=` 화면 이동 유지 | 동작은 기존(`Header` 네비 `location.search`, `useGlobalSearch` = region·snapshot·scenario). 테스트만 추가 | `src/pages/r5fe.test.tsx` "R5-FE 1" 5개: 헤더 네비 7개 href + 클릭 G1→G2→G6→G5→G1 · G1 TOP 5 카드 이름 링크 href(전 카드)·변경 피드 링크·카드 빈 곳 클릭 → G3 · TOP 5 이름 링크 클릭 → G3 "목록으로" href · G2 표 행 링크(필터 쿼리는 G3 로 안 넘김) → G3 · G2 트레이 → G4 → G4 열 머리 → G3. 기준일은 기본값이 아닌 11, 시나리오 B. 실브라우저: `e2e/pages/pages.spec.ts` "?scenario=·?snapshot= 가 TOP 5 카드 → G3, 네비 → G2, 표 행 → G3 에서 유지" | 뮤테이션 ① `useGlobalSearch` 가 `region` 만 유지 ② 네비 `to={{ pathname }}`(search 없음): **5개 전부 `×`** — 예 `헤더 네비 링크 7개가 모두 scenario·snapshot 을 싣고 …` `AssertionError: expected null to be 'B'` | vitest 5/5 · e2e 1/1 통과 |
| **FE-2** major 차트 지연 로딩 | 동작은 기존(`EChart` + `useInView` rootMargin 200px, 화면 밖은 `chart.notRendered` 플레이스홀더). 테스트만 추가 | `src/charts/lazy.test.tsx` 2개(가짜 IntersectionObserver): 화면 밖 = 플레이스홀더·높이 유지·SVG 없음·echarts 런타임 마운트 0 → `isIntersecting=false` 그대로 → `true` 면 SVG·관찰 종료 / 차트 두 개는 각자 진입할 때만. 실브라우저: `e2e/pages/pages.spec.ts` "G6: 화면 밖 차트는 플레이스홀더(SVG 없음) → 스크롤하면 그려진다"(창 1280×600, 맨 아래 차트 top > innerHeight+200 사전 조건, 맨 위 차트 SVG 뒤에도 아래 차트 SVG 0·문구 있음 → 스크롤 → SVG) | 뮤테이션 `useInView` 초기값 `true`(즉시 렌더): vitest **2개 전부 `×`**, e2e **`×` `expect(locator).toHaveCount(expected) failed` at `await expect(last.locator('svg')).toHaveCount(0)`** | vitest 2/2 · e2e 1/1 통과 |
| **FE-3a** minor Lighthouse G0·G0-2 | `TARGETS` 를 `scripts/lib/lighthouse-targets.ts` 로 분리(스크립트는 import 하면 실행되므로) + `/regions/new`·`/regions/1/living-areas` 데스크톱 추가 | `scripts/lighthouse-targets.test.ts` 4개: `src/routes.tsx` routeDefs 화면 10개 모두 데스크톱 대상 있음(G0·G0-2 명시) · 모바일 = G1·G2·G3 · 중복 없음 · 기준 80 | main 목록: **`× routeDefs 화면 10개 모두 데스크톱 측정 대상이 있다` — missing `['/regions/new', '/regions/:id/living-areas']`** | 4/4 통과 · 실측 §2 |
| **FE-3b** minor ko.json 단일화 자동 검사 | ESLint `local/no-hangul-literal`(`eslint-rules/no-hangul-literal.js`, `eslint.config.js` src/**/*.{ts,tsx} error). JSX 텍스트 한글 = 언제나 금지, 문자열·템플릿(속성·식·TS 상수·타입 리터럴·객체 키) 한글 = 명시 예외만. 예외 목록 `eslint-rules/hangul-allowlist.js`: 계약 enum 값 40개(정확히 같은 값만) · 서버 표식 9개(값 → 그 문자열이 있는 저장소 파일) · 개발자 오류 2개(`new Error`/`TypeError`/`RangeError` 인자일 때만, ApiError 등 앱 오류 제외). 예외 파일: `*.test.*`·`src/test/`·`src/mocks/`(MSW 계약 예시)·`src/charts/gallery/`(dev·MSW 전용 `/__charts`) | `eslint-rules/no-hangul-literal.test.js` 46개: RuleTester valid 22·invalid 16(JSX 텍스트·속성·삼항·TS 상수·toast 인자·enum 포함 문장·식 있는 템플릿·목록 밖 Error·Error 밖 같은 문장·ApiError·i18n 모듈) + 근거 검사(enum ⊂ `contracts/openapi.bundled.yaml` enum, 표식은 적힌 파일에 그대로 있고 enum 과 안 겹침, 개발자 오류는 적힌 파일의 `new Error('…')` 안) + 예외 파일 정규식 + `eslint.config.js` 가 대상 파일에 규칙 error(`calculateConfigForFile`) | main: **`Error: Cannot find module './hangul-allowlist.js'`**(파일 전체 실패). 규칙만 있고 설정 전: **`× … → local/no-hangul-literal = error` 4건 `expected undefined to be 2`**. 실제 소스에 누출 주입(`dashboard/index.tsx` JSX `점수`, `lib/unitBasis.ts` `'단위 근거 보기'`): `npx eslint` **2 errors**(`JSX 안 한글 문구 '점수' 금지 …`, `한글 문자열 '단위 근거 보기' 금지 …`) | 46/46 통과 · `npm run lint` 0 — **실제 누출 0건**(아래) |
| **FE-3c** minor 트레이 6개 상한 | 동작은 기존(`MAX_COMPARE = 6`) | `src/pages/r5fe.test.tsx` "R5-FE 3"(목 10행): 6개 고르면 문구 `trayMax`·나머지 체크 전부 비활성·고른 6개는 해제 가능 · 7번째 클릭 무시 · 칩 6 · 비교 링크 ids 6(중복 없음) · 칩 하나 빼면 5개·전부 활성·`trayHint` | 뮤테이션 `MAX_COMPARE = 7`: **`×`** | 1/1 통과 |

**ko.json 검사 결과(실제 누출).** 규칙을 켜기 전 `src` 의 TS/TSX(테스트·d.ts 제외) 한글 문자열을 AST 로 전수 조사했다(scratchpad `hscan.mjs`): 27 파일 2,598건 중
`src/mocks/handlers.gen.ts` 2,455·`handlers.extra.ts` 24(MSW 계약 예시), `src/charts/gallery/**` 36(dev 갤러리), 나머지 83건은 전부 계약 enum 값 비교·타입·옵션 값,
서버 표식(`'[단위 근거] '`, 접수 사유 2개, `'출처 상충 — compare 대기'`, 사람 확인 단위 `개월·년·원`, `land_type` `공공택지·민간택지`), 개발자 오류 2개였다.
**JSX 텍스트·속성의 한글 화면 문구 누출은 0건** — 고칠 코드가 없었다. 갤러리 문구를 ko.json 으로 옮기지 않은 이유: 사용자 화면이 아니고(프로덕션 번들에 라우트 없음),
옮기면 OPS 가 커밋하는 차트 기준 이미지 영역과 겹친다.

## 2. Lighthouse 실측 1회 (2026-10-13, `npx tsx scripts/lighthouse.ts --port 4791`, LH_RUNS=1)

MSW 모드 프로덕션 빌드 + preview, Playwright chromium headless. 사전 점검(화면마다 h1·`/api` 누수 0·오류 문구 없음) 13건 ok. 다른 에이전트 스위트가 같은 PC 에서 동시에 돌던 중의 값이다.

| 화면 | 경로 | 폼 | 성능 | 접근성 | 권장 | FCP | LCP | TBT | CLS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **G0** | `/regions/new` | desktop | **99** | **100** | **100** | 0.7 s | 0.9 s | 0 ms | 0.037 |
| **G0-2** | `/regions/1/living-areas` | desktop | **99** | **100** | **100** | 0.7 s | 0.8 s | 0 ms | 0.021 |
| G1 | `/` | desktop | 93 | 100 | 100 | 0.9 s | 1.4 s | 110 ms | 0.015 |
| G2 | `/complexes` | desktop | 99 | 100 | 100 | 0.7 s | 0.9 s | 0 ms | 0.034 |
| G3 | `/complexes/2` | desktop | 95 | 100 | 100 | 0.9 s | 1.4 s | 0 ms | 0.018 |
| G4 | `/compare?ids=2,7,4` | desktop | 97 | 100 | 100 | 0.8 s | 1.1 s | 40 ms | 0.018 |
| G5 | `/scenario` | desktop | 96 | 100 | 100 | 0.8 s | 1.1 s | 0 ms | 0.069 |
| G6 | `/market` | desktop | 89 | 100 | 100 | 0.7 s | 1.0 s | 240 ms | 0.018 |
| G7 | `/ops` | desktop | 96 | 100 | 100 | 0.8 s | 1.2 s | 0 ms | 0.069 |
| G8 | `/reports` | desktop | 99 | 100 | 100 | 0.7 s | 0.9 s | 0 ms | 0.051 |
| G1 | `/` | mobile | 82 | 100 | 100 | 3.1 s | 3.8 s | 110 ms | 0 |
| G2 | `/complexes` | mobile | 82 | 100 | 100 | 3.0 s | 3.6 s | 190 ms | 0 |
| G3 | `/complexes/2` | mobile | 82 | 100 | 100 | 3.1 s | 3.9 s | 90 ms | 0 |

결과 `lighthouse: 전부 80 이상 (13건)`, exit 0. 감점 감사: 데스크톱 G1·G3 LCP, G6 TBT, 모바일 3개 FCP·LCP(느린 4G·CPU 4배 프리셋 — 82 로 기준 근처).
"(참고) Lighthouse 중 /api n건"은 측정 뒤 페이지 이동(bf-cache 감사) 중 재조회로 측정 구간 밖이다(스크립트 설명 그대로).

## 3. 완료 기준 실행(frontend/)

전체 로그는 scratchpad `logs/*.log`. 포트는 다른 에이전트와 겹치지 않게 E2E_PORT 5571 · E2E_PAGES_PORT 5591 · E2E_PERF_PORT 5592 · E2E_API_PORT 18995 ·
E2E_API_WEB_PORT 15995, `E2E_API_DATA` 새 폴더.

| 명령 | 결과 |
| --- | --- |
| `npm ci` | exit 0 |
| `npm run typecheck` | exit 0 |
| `npm run lint` (`--max-warnings 0`, 새 규칙 포함) | exit 0 |
| `npx vitest run` | **61 파일 · 861 통과** |
| `npm run build` | exit 0 (`built in 16.27s`) |
| `npm audit` | `found 0 vulnerabilities` |
| `npm run e2e` (스모크·차트 갤러리 → `e2e/pages`(+perf)) | **46 통과 · 22 통과** |
| `npm run e2e:api` (FastAPI + devseed 임시 SQLite, mock 판정기) | **45 통과** (6.3분) |

## 4. 하지 않은 것

- FE-1·FE-2·트레이 상한은 동작이 이미 맞아 코드 수정 없이 테스트만 더했다. 헤더 네비가 `location.search` 전체(화면별 필터·`ids` 포함)를 다음 화면으로
  넘기는 것은 그대로 두었다(전역 3개는 유지되고, 다른 화면에서 쓰지 않는 키는 무시된다).
- `scripts/lighthouse.ts` 사전 점검의 `'불러오지 못했습니다'` 문구는 스크립트(린트 대상 밖)에 그대로 있다.
