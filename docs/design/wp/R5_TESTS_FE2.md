# R5-FE2 — 모바일 Lighthouse 성능 여유 확보 (2026-10-13)

원인: GitHub CI `frontend-lighthouse`(run 38339589390) 실패 — 모바일 성능 `/` 78 · `/complexes` 78 · `/complexes/2` 75(기준 80), FCP 3.1–3.3 s,
LCP 3.8–4.3 s, TBT 220–260 ms. 데스크톱은 모두 ≥ 88. 앞 CI 실행과 로컬(82)은 통과 — 모바일이 기준선에 붙어 있어 러너 소음에 뒤집혔다.
브랜치 `wp/r5-fe2`(main `14a6dfa` 기준). 계약 `.18` 그대로, 기준 80 그대로(RA §7 "Lighthouse 성능 80 이상"). 백엔드·계약·CI·
`frontend/package.json`·차트 기준 이미지는 건드리지 않았다(새 npm 패키지 없음). 차트 코드·옵션은 바꾸지 않았다(차트 시각 변화 없음 — `npm run e2e`
차트 갤러리 스냅숏 통과).

## 1. 원인 분석 (번들)

`vite build` 산출물을 모듈 단위로 분해했다(rollup `generateBundle` 의 chunk.modules, scratchpad 일회용 스크립트 — 커밋하지 않음).

| 발견 | 영향 |
| --- | --- |
| **진입 청크가 `zrender`(196 kB) 청크를 정적으로 import** — `manualChunks` 가 zrender·tslib 를 'zrender' 청크로 보내면서 rollup 이 그 청크 모듈의 주인 없는 정적 의존성(`\0commonjsHelpers.js`, react-dom CJS 변환이 쓰는 도우미)까지 끌어갔다 | 차트가 없는 화면도 첫 로드에 zrender 를 받고 실행. 차트 지연 로딩(RA §7)이 실제로는 반쯤 깨져 있었다 |
| **진입 청크가 `msw` 청크를 정적으로 import** — 같은 이유로 `\0vite/preload-helper.js` 가 msw 청크로 들어감 | 운영 빌드: 1 kB 청크 하나. **MSW 모드 빌드(=Lighthouse 측정 빌드)**: msw 런타임 296 kB 를 첫 로드에 정적으로 받음 |
| Lighthouse 측정 빌드가 MSW 모드 — `main.tsx` 가 첫 렌더 전에 `mocks/browser`(계약 예시 핸들러 228 kB)를 받고 서비스 워커를 등록·활성화 | 운영에 없는 비용(~100 kB gzip + SW 등록)이 FCP·LCP 앞에 끼어, 운영보다 나쁜 첫 화면을 재고 있었다 |
| 진입 청크에 zod(압축 전 기여 135 kB) — 쓰는 곳은 `api/client.ts` 의 오류 본문 판별(`ErrorSchema`) 하나 | 첫 화면 파싱·실행 비용. 시나리오 화면(G5, 데스크톱 전용)은 zod 를 계속 쓴다 → 그 청크로 이동 |

## 2. 고친 것

| 항목 | 파일 | 내용 |
| --- | --- | --- |
| 청크 분할 | `frontend/vite.config.ts` | `manualChunks`: React·react-dom·scheduler·react-router·TanStack Query 와 `\0` 가상 도우미를 **'vendor'** 청크로 고정 → zrender·msw 청크가 도우미를 끌어가지 않는다. `msw` 수동 청크는 운영 모드가 아닐 때만(운영 빌드의 빈 청크 경고 제거). config 를 `({ mode }) =>` 함수로 |
| 회귀 방지(빌드 실패) | `frontend/scripts/lib/bundle-guards.ts`, `vite.config.ts` `entry-chunk-guard` | 진입 청크의 **정적 닫힘**(진입 + 정적 import 청크)에 `echarts`·`zrender`·`msw` 가 있거나 합계가 **450 kB**(압축 전)를 넘으면 `vite build` 실패. 운영·msw 모드 모두 |
| zod 제거(진입) | `frontend/src/api/client.ts` | `ErrorSchema`(zod) → `parseErrorBody`(손 판별, 같은 판정: code ∈ 계약 code, detail 문자열, field_errors·request_id nullish, field_errors 항목 loc·msg 만) |
| 측정 방식 | `frontend/scripts/lighthouse.ts`, `scripts/lib/mock-api.ts` | **운영 빌드**(`mode production → dist/lighthouse`)를 재고, `/api` 는 preview 서버가 MSW 핸들러(`src/mocks/handlers.ts`, 계약 예시)를 Vite SSR 로 읽어 **서버에서** `getResponse` 로 답한다. 번들은 운영과 같고(MSW·SW·예시 데이터 없음) 응답만 계약 예시 — 아래 §5 |
| 중앙값 판정 | `frontend/scripts/lib/lighthouse-targets.ts`, `scripts/lighthouse.ts` | `DEFAULT_RUNS = 3`(`LH_RUNS` 로 변경), 범주별 점수 **중앙값**으로 판정(짝수 횟수면 가운데 둘 중 낮은 값). 지표·감점 감사는 중앙값 성능 점수를 낸 실행 것. 표에 `perf runs`(횟수별 성능) 열 |
| 옵션 | `scripts/lighthouse.ts`, `README.md` | `--msw`(예전 방식: MSW 모드 빌드 + 서비스 워커), `--form desktop|mobile`, `--keep <dir>`(JSON 보고서 보존). 사전 점검은 그대로(화면마다 h1·오류 문구 없음·계약 예시 핸들러가 못 답한 `/api` 0) |

하지 않은 것(효과 대비 위험): 출처 서랍(`ProvenancePanel` + `RawDocumentPreview`, 압축 전 ~20 kB)·토큰 다이얼로그 지연 로드 — 여러 화면 테스트가
클릭 직후 서랍을 동기적으로 찾는다. 경로별 청크 `modulepreload` 주입 — 첫 화면 LCP 는 데이터 사슬(`/regions` → `/snapshots` → 화면 API, 3 왕복)이
화면 청크보다 길어 효과가 작다(§4 네트워크 기록).

## 3. 테스트 (먼저 쓰고, 수정 전 실패 확인)

| 테스트 | 내용 | 수정 전 |
| --- | --- | --- |
| `src/api/errorBody.test.ts` (17) | `parseErrorBody` 가 zod 스키마와 같은 판정: 계약 code 전부 통과, 계약 밖 code·타입 틀림·field_errors 모양 틀림·request_id 숫자 → null, 추가 키 무시, `toApiError` 가 http 로 떨어짐 | `parseErrorBody` 없음(import 실패) |
| `scripts/bundle-guards.test.ts` (6) | 정적 닫힘 계산(순환 1회), R5-FE2 이전 모양(진입 → zrender·msw) 위반 2건, 차트 엔진이 동적 청크에서만 닿으면 통과, 예산 합계, `vite.config.ts` 에 가드 플러그인 | 모듈 없음. **뮤테이션**: vite.config.ts 에서 vendor 규칙 두 줄을 지우고 `vite build` → `[entry-chunk-guard] 진입 assets/index-C9Tl8kHX.js 가 지연 로드 전용 청크를 정적으로 import 한다: assets/zrender-Cgj0XQ5k.js` · `정적 닫힘 594.9kB > 예산 450kB` 로 빌드 실패(되돌림) |
| `scripts/mock-api.test.ts` (3) | 실제 HTTP 왕복(전역 MSW 끔): 핸들러 응답 상태·헤더·본문 그대로·쿼리·POST 본문 전달, 핸들러 없음 → 503 + 누수 기록, 계약 예시 핸들러로 `/api/regions`·`/api/health` 200 JSON | 모듈 없음 |
| `scripts/lighthouse-targets.test.ts` (+4) | 기본 3회·`LH_RUNS` 해석, 중앙값(홀수·짝수 낮은 값·빈 목록 오류), 한 번 튄 낮은 점수가 판정을 뒤집지 않음, 지표는 중앙값 실행 것 | `DEFAULT_RUNS`·`median` export 없음 |

## 4. 측정 (로컬, Ryzen 5 5600 6C/12T, Playwright chromium headless)

**부하 조건.** 다른 에이전트의 백엔드 테스트(node·python 다수)가 같은 PC 에서 동시에 돌았다. 수정 전 측정 시작 시 CPU 71 %, 수정 후 최종 측정 시작 시 43 %.
수정 전 측정 중 일부 구간에 내 `tsc` 가 같이 돌았다(데스크톱 `/` 71 은 그 영향으로 본다 — 3회 중 2회가 낮았다).

### 4-1. 모바일 (G1·G2·G3, 화면당 3회 중앙값)

| 화면 | 수정 전 (main, MSW 빌드) | 번들 수정만 (`--msw`) | **수정 후 (기본: 운영 빌드 + 서버 계약 예시)** |
| --- | --- | --- | --- |
| `/` G1 | **83** · FCP 3.0 s · LCP 3.7 s · TBT 70 ms | 86 (87/86/86) · 2.4 s · 3.7 s · 120 ms | **93** (93/93/93) · FCP 2.1 s · LCP 2.9 s · TBT 70 ms |
| `/complexes` G2 | **85** · 3.1 s · 3.6 s · 310 ms | 87 (90/87/87) · 2.3 s · 3.3 s · 210 ms | **89** (89/89/90) · 2.0 s · 3.0 s · 200 ms |
| `/complexes/2` G3 | **81** · 3.1 s · 4.0 s · 110 ms | 85 (85/85/85) · 2.4 s · 3.9 s · 80 ms | **94** (93/94/94) · 2.0 s · 2.9 s · 50 ms |
| (참고) CI run 38339589390 | 78 / 78 / 75 (1회) | | |

같은 날 앞선 수정 후 측정(부하 비슷): `/` 93 (94/93/93) · `/complexes` 92 (92/90/92) · `/complexes/2` 93 (93/93/93). G2 는 표(TanStack Table + 가상 스크롤)
렌더의 TBT(120–200 ms)로 셋 중 가장 낮다.

### 4-2. 데스크톱 (10화면, 화면당 3회 중앙값) — 변하지 않았거나 좋아졌다

| 화면 | 수정 전 | 수정 후 (perf runs) |
| --- | --- | --- |
| `/regions/new` | 99 | 100 (100/100/100) |
| `/regions/1/living-areas` | 99 | 100 (100/100/100) |
| `/` | 71¹ | 99 (99/99/99) |
| `/complexes` | 99 | 100 (100/100/100) |
| `/complexes/2` | 97 | 99 (99/99/99) |
| `/compare?ids=2,7,4` | 97 | 99 (99/99/100) |
| `/scenario` | 97 | 99 (99/98/100) |
| `/market` | 99 | 100 (**83**/100/100) — 한 번 튄 값을 중앙값이 흡수 |
| `/ops` | 97 | 99 (99/99/100) |
| `/reports` | 99 | 100 (100/100/100) |

¹ 수정 전 측정 중 같은 PC 에서 `tsc` 를 돌린 구간. 접근성·권장 사항은 전·후 모두 13건 전부 100. 수정 후 결과 `lighthouse: 전부 80 이상 (13건)`, exit 0,
사전 점검 13건 ok·계약 예시 밖 `/api` 0건. 소요 10분 43초(39회 측정 + 빌드, 이 PC·부하 기준) — CI 잡 제한 20분(이전 1회 측정은 CI 에서 3분 32초).

### 4-3. 번들 크기 (`npm run build`, 운영)

| | 수정 전 | 수정 후 |
| --- | --- | --- |
| 진입 청크 | `index` 454.01 kB (gzip 141.67) | `index` 113.44 kB (gzip 37.74) |
| 진입이 정적으로 import | `zrender` 195.74 kB (66.60) · `msw` 1.14 kB (0.66) | `vendor` 287.15 kB (92.14) |
| **첫 화면 JS 정적 닫힘** | **650.9 kB (gzip 208.9)** | **400.6 kB (gzip 129.9)** — −38 % |
| zrender / echarts | 196 / 444 kB (zrender 는 첫 로드) | 195 / 444 kB (차트가 뷰포트에 들어올 때만) |
| zod | 진입 청크 | G5 시나리오 청크(70.25 kB, gzip 17.55)로 이동 |
| MSW 모드 빌드의 첫 로드 | 진입 + zrender + msw 296 kB + 핸들러 228 kB | 진입 + vendor + (렌더 전) msw·핸들러 — msw 는 `mocks/browser` 동적 import 를 따라서만 |

모바일 `/` 네트워크(수정 후, 비감속 관측): 진입 38 kB + vendor 93 kB + CSS 5.6 kB(전송) → 화면 청크들 → `/api/regions`·`/api/scenarios`·`/api/health` →
`/api/regions/1/snapshots` → `/api/snapshots/12/dashboard`. 총 전송 195 KiB. LCP 요소는 대시보드 일정 날짜(데이터 뒤 렌더).

## 5. 측정 방식 변경의 근거(대표성)

- 운영(nginx, `infra/nginx.conf`)은 정적 번들 + `/api` 프록시다. 브라우저 MSW 는 운영 번들에 없다(`main.tsx` 의 `mocks/browser` 동적 import 는 운영 빌드에서
  죽은 코드로 빠진다). 예전 측정은 운영에 없는 msw 런타임·계약 예시 데이터·서비스 워커 등록을 첫 렌더 앞에 두고 쟀다.
- 새 방식은 **운영 빌드 그대로**를 재고, API 응답만 계약 예시(같은 MSW 핸들러, 같은 응답 본문·상태)다. preview 서버가 gzip 압축을 한다(nginx `gzip on` 과 같은 조건).
  API 응답이 같은 PC 에서 즉시 오므로 실 서버보다 빠른 쪽이다 — Lighthouse 모바일 프리셋은 시뮬레이션 감속(RTT 150 ms·1.6 Mbps·CPU 4배)을 요청마다
  덧붙이므로 3 왕복 데이터 사슬 비용은 반영된다. 실 서버 처리 시간은 `e2e:api`(FastAPI + devseed) 영역이다.
- 예전 방식도 `--msw` 로 그대로 잴 수 있다(§4-1 가운데 열: 번들 수정만으로 81–85 → 85–87).

## 6. 완료 기준 실행 (frontend/)

로그 scratchpad `logs/*.log`. 포트: E2E_PORT 5770 · E2E_PAGES_PORT 5771 · E2E_PERF_PORT 5772 · E2E_API_PORT 18795 · E2E_API_WEB_PORT 5791 · Lighthouse 4795,
`E2E_API_DATA` 새 폴더.

| 명령 | 결과 |
| --- | --- |
| `npm ci` | exit 0 |
| `npm run typecheck` | exit 0 |
| `npm run lint` | exit 0 |
| `npx vitest run` | **64 파일 · 890 통과** |
| `npm run build` | exit 0 (entry-chunk-guard·max-chunk-guard 통과) |
| `npm audit` | `found 0 vulnerabilities` |
| `npm run e2e` (스모크·차트 갤러리 스냅숏 → `e2e/pages` + T16 perf) | **46 통과 · 22 통과** (T16 3회 중앙값 p50 16.7 ms · p95 16.8 ms) |
| `npm run e2e:api` | **45 통과** (5.2분) |
| `npm run lighthouse` (기본: 운영 빌드, 3회 중앙값) | **13건 전부 80 이상**, 모바일 93 / 89 / 94 |
