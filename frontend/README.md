# frontend — 웹 GUI (React 18 + TS + Vite)

| 경로                                                                                                                                                                                           | 주인                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `package.json`, `package-lock.json`, 도구 설정(vite·tsconfig·eslint·tailwind·playwright), `scripts/`, `eslint-rules/`, `src/api/`, `src/mocks/`, `src/layout/`, `src/hooks/`, `src/routes.tsx` | WP0 (WP0-C 스캐폴드)         |
| `src/pages/`                                                                                                                                                                                   | WP6a                         |
| `src/components/`, `src/charts/`                                                                                                                                                               | WP6b — 계약은 각 폴더 README |

## 명령

```bash
npm ci
npm run gen:api     # openapi → src/api/schema.d.ts (생성물, 손으로 고치지 않음)
npm run gen:msw     # openapi response example(s) → src/mocks/handlers.gen.ts (생성물)
npm run dev         # 실 API 모드: /api 프록시 → http://localhost:8000 (경로 그대로)
npm run dev:msw     # MSW 모드: API 없이 계약 예시 응답
npm test | npm run lint | npm run typecheck | npm run build
npm run e2e         # Playwright MSW 모드(스모크 tests/e2e + 화면 e2e/pages). 최초 1회 npx playwright install chromium
npm run e2e:api     # Playwright 실 API 모드(e2e/api): devseed DB + uvicorn + vite 를 스스로 띄운다
npm run lighthouse  # 운영 빌드 + preview(서버가 계약 예시로 /api 응답) → 화면 10개(G0·G0-2·G1~G8, 모바일 G1~G3) Lighthouse(성능·접근성·권장 사항) 화면당 3회 중앙값 표, 80 미만이면 exit 1 (--msw: 예전 MSW 빌드)
```

## 실 API 모드 ↔ MSW 모드

| 모드   | 명령                                                 | API 응답                                           | 언제                                 |
| ------ | ---------------------------------------------------- | -------------------------------------------------- | ------------------------------------ |
| 실 API | `npm run dev`                                        | FastAPI(`API_PROXY_TARGET`, 기본 `localhost:8000`) | 백엔드와 함께 개발·확인              |
| MSW    | `npm run dev:msw` (또는 `VITE_MSW=true npm run dev`) | `src/mocks/handlers*.ts`(계약 예시 + 상태 보강)    | 백엔드 없이 화면 작업, `npm run e2e` |

- 전환 기준은 `src/main.tsx` 한 곳: `mode === 'msw'` 또는 `VITE_MSW=true` 면 MSW 워커를 켜고, 아니면 실제 `/api` 로 보낸다.
- **프록시는 경로를 바꾸지 않는다.** FastAPI 라우터가 `API_PREFIX=/api` 아래에 있고 운영 nginx 도 `/api` 를 그대로 넘기므로
  개발·운영 경로가 같다(`/api/regions` → `http://localhost:8000/api/regions`). `API_PROXY_TARGET` 에는 **origin 만**
  적는다(`http://127.0.0.1:18765`, `/api` 붙이지 않음).
- 실 API 로 띄우기(백엔드 쪽):

  ```bash
  cd ../backend
  uv run python -m app.api.devseed                 # 임시 SQLite 에 인천·김포 픽스처
  API_TOKEN=<쓰기> READONLY_TOKEN=<읽기> uv run uvicorn app.main:app --port 8000
  cd ../frontend && npm run dev                    # (다른 포트면 API_PROXY_TARGET=http://127.0.0.1:<port>)
  ```

  두 토큰을 모두 비우면 서버가 인증 없이 연다(개발 기본값) — 그때는 토큰 입력이 필요 없다.

## API 토큰 (ADR-9)

- 요청마다 `Authorization: Bearer <토큰>`. 토큰은 ① 브라우저 저장소(`localStorage` `sa.token`, 권한 `sa.token.role`)
  ② 없으면 빌드 환경변수 `VITE_API_TOKEN`(개발·e2e) 순서로 쓴다(`src/api/auth.ts`).
- **토큰 설정 다이얼로그**: API 가 401 을 주면(토큰 없음·틀림) 자동으로 열리고, 헤더의 "API 토큰" 버튼으로도 연다.
  저장 전에 토큰을 확인한다 — `GET /regions` 401 이면 거절, 이어서 빈 본문 `POST /jobs` 가 403 이면 **읽기 전용**,
  422 면 쓰기 토큰(서버는 인증을 본문 검증보다 먼저 하므로 아무것도 만들지 않는다).
- 읽기 전용 토큰이면 저장·실행 버튼(지역 분석 시작·생활권 저장·시나리오 저장/재판정·사람 확인·체크리스트·소스 재시도·
  보고서 생성)이 꺼지고 전역 안내 배너가 뜬다(`useCanWrite()`). 쓰기 요청이 403 forbidden 을 받아도 같은 상태가 된다.
- 저장소가 막혀 있으면(프라이빗 창 등, 모든 접근 try/catch) 이 탭 메모리에만 두고 그렇게 안내한다.
- **탭 범위 토큰**(N-M7): sessionStorage `sa.token.tab`(+`.role`·`.reason`)가 있으면 localStorage 보다 먼저 쓴다.
  `/share#<토큰>` 을 열 때 이 브라우저에 쓰기(또는 권한 모름) 토큰이 저장돼 있으면 확인 다이얼로그 —
  "이 탭에서만 읽기 전용으로 보기"(기본, sessionStorage) · "저장된 토큰을 공유 토큰으로 바꾸기"(localStorage) · "취소".
  다른 탭이 저장 토큰을 다른 읽기 전용 토큰으로 바꾸면, 쓰기 토큰을 쓰던 탭은 그 토큰을 탭 범위에 고정하고
  "다른 탭에서 저장된 토큰이 바뀌었습니다" 배너("새 토큰 사용" = 고정 해제)를 보인다.

## 파일 다운로드·원문 미리보기 (`src/api/download.ts`)

CSV(`/snapshots/{sid}/complexes.csv`)·원문(`/raw/{id}`)·보고서(`/reports/{id}`)는 `<a href>` 가 아니라
fetch(Bearer) → Blob → `<a download>` 로 저장한다(`useDownload()`; 파일 이름은 `Content-Disposition`, 없으면 목록의 이름).
원문 미리보기(`RawDocumentPreview`)는 텍스트·PNG 를 같은 방식으로 받아 화면 안에 보이고, HTML·PDF 는 저장만 한다
(수집한 HTML 은 실행하지 않는다).

## 실 API e2e (`e2e/api`)

`npm run e2e:api` — 백엔드 `devseed`(임시 SQLite, `E2E_API_DATA` 또는 OS 임시 폴더) + uvicorn(쓰기·읽기 전용 토큰) +
vite(MSW 끔)를 띄우고 G0~G8, Bearer 다운로드 3종, 원문 미리보기(텍스트·PNG), 토큰 다이얼로그(읽기 전용·401)를 본다.
잡(보고서)은 상주 worker 없이 테스트가 `python -m app.worker --once` 로 한 번 돌린다. 각 테스트는 `/api` 4xx/5xx 0건
(토큰 확인처럼 의도한 응답만 명시적으로 허용). 포트·토큰: `E2E_API_PORT`·`E2E_API_WEB_PORT`·`E2E_API_TOKEN`·`E2E_API_READ_TOKEN`.

## 계약 전환 (WP0-A 머지 후)

`openapi.config.json`의 `"source": "fixture"` → `"contract"` 한 줄. 그러면 `../contracts/openapi.bundled.yaml`(있으면) 또는 `../contracts/openapi.yaml`을 읽는다. 일회성으로는 `OPENAPI_SOURCE=contract npm run gen:api`.
그 다음 `src/api/types.ts`의 임시 타입을 `components['schemas'][...]` 별칭으로 바꾼다(화면·차트는 types.ts만 import 하므로 여기서 끝난다).

## 규칙

- 화면 문자열은 `src/i18n/ko.json` + `t()` — ESLint `local/no-hangul-literal`이 JSX·TS 한글 리터럴을 거부한다(예외는 `eslint-rules/hangul-allowlist.js`: 계약 enum 값·서버 표식·개발자 오류, 근거를 테스트가 확인). 숫자는 `FactCell` 또는 `src/lib/format.ts` — ESLint `local/no-raw-number-render`가 강제.
- 문자열 지연 로드(R11-I18N): 원본은 ko.json 하나 그대로, 빌드 플러그인 `ko-split`(vite.config.ts)이 진입용 core 와 이름공간(`page/G0`…`page/G8`·`chart`·`glossary`, 규칙 `src/i18n/namespaces.ts`)으로 나눈다. 화면 문자열은 플러그인이 `src/pages/<폴더>/index.tsx` 앞에 등록 import 를 넣어 **그 화면 청크 안에** 싣는다(추가 요청 0, 표는 `PAGE_NAMESPACES`). 화면이 다른 화면의 `page.Gx.*`·`chart.*`·`<Term>`을 새로 쓰면 `PAGE_NAMESPACES[폴더]`에 이름공간을 더한다 — `src/i18n/routeNamespaces.test.ts`가 빠진 것을 이름으로 알려 준다. 화면 코드·`routes.tsx`는 고치지 않는다. 모듈 최상위(렌더 밖)에서 이름공간 키로 `t()`를 부르지 않는다(필요하면 `CORE_PINS`).
- 지역명 하드코딩 금지(목 데이터·테스트 제외). 라벨은 텍스트 배지. 하단 고정 문구는 레이아웃이 붙인다.
