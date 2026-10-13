# R5-FE3 — T16 스크롤 프레임 여유 확보 (2026-10-13)

원인: GitHub CI 에서 T16(`frontend/e2e/pages/perf.spec.ts`, D10-8 p50 ≤ 17ms · p95 ≤ 34ms)이 경계에 붙어 있었다 — run 38326346203 · 38339589390 ·
38348618656 p95 33.4, run 38358960315 실패(p50 33.3, 회차별 ≤20ms 80–93/180). 브랜치 `wp/r5-fe3`(main `2f665bb` 기준). 기준·측정 방식은 그대로
(D10-8 불변, perf.spec.ts 손대지 않음). 계약·백엔드·`package.json`·차트 코드·차트 기준 이미지는 건드리지 않았다(새 npm 패키지 없음).

## 1. 재현 — CPU 감속 진단 (`frontend/scripts/perf-scroll.ts`, 비게이트)

`npx tsx scripts/perf-scroll.ts [--rates 1,2,4] [--runs 3] [--no-build] [--port n] [--trace dir]` — T16 과 같은 빌드(MSW 모드 운영 빌드 + vite preview)·
같은 스크롤(맨 위 → 프레임마다 132px × 180, 3회)을 CDP `Emulation.setCPUThrottlingRate` 배율별로 잰다. `--trace` 는 배율별 Chrome 트레이스.
보고만 하고 exit 0(판정은 perf.spec.ts). `package.json` 은 WP0 소유라 npm 스크립트로 등록하지 않았다.

수정 전 CPU ×2 결과(≤20ms 82/180, p50 16.7~33.3)가 CI 실패 회차(80–93/180)와 같은 모양 — CI 러너 ≈ 로컬 2배 감속.

## 2. 원인 (트레이스·CPU 프로파일)

| 발견 | 영향 |
| --- | --- |
| **행 높이 추정 44px, 실제 69–135px**(값·배지가 줄바꿈). 가상 스크롤이 행을 재지 않아 맨 위 행이 빠질 때 위 여백은 44px 늘고 행은 ~90px 빠짐 → **남은 행 전부가 매 프레임 ~40px 위로 밀림**(화면에서도 스크롤보다 빠르게 튐), scrollHeight 가 매 프레임 흔들림 | 매 프레임 표 전체 다시 레이아웃·페인트. 1× 프레임당 메인 스레드 9.3ms(paint 2.7 · JS 2.3 · layout 1.8 · prepaint 1.1 · style 0.7) |
| overscan 8 은 44px 가정으로 정한 값(≈350px) — 실제 행으로는 창 밖에 ~700px 씩, DOM 행 23–29개 | 레이아웃·prepaint·페인트가 그린 행 수에 비례 |

시도했으나 효과 없어 되돌린 것: 스크롤 영역 `contain: strict`(+고정 높이) — 프레임 비용 그대로. `border-separate` — 개선 없음, 모양 위험.
`table-layout: fixed` + 고정 열 너비 — 열 선택·열 너비(모양)가 바뀌어 버림.

## 3. 고친 것 (`frontend/src/pages/complexes/ComplexTable.tsx`)

| 항목 | 내용 |
| --- | --- |
| 행 실측 | `VirtualRow` 의 `<tr ref={virtualizer.measureElement}>` + `measureRow`(ResizeObserver border-box, 0 이면 추정 44 — jsdom 동작 불변). 위 여백이 빠진 행 높이와 정확히 같아져 남은 행이 움직이지 않는다 → 새 행만 레이아웃·페인트 |
| overscan | 긴 목록 8 → **2**(실측 ~90px ≈ 180px). 스크롤 이벤트에서 flushSync 로 그리므로 프로그램·휠 스크롤 모두 같은 프레임에 행이 있다 |
| 짧은 목록 | **50행 이하면 전부 그린다**(overscan = 행 수) — 예전처럼(44px×8 여유로 짧은 목록은 사실상 전부 DOM) 창 밖 행도 DOM 에 있다. e2e:api 3건(writes11·12·13: 창 밖 행 링크를 찾음)이 이 동작에 기댄다 |
| 끝 고정 | `anchorTo: 'end'` — 맨 끝으로 내린 뒤 끝 행들이 추정보다 크게 재져 전체 높이가 늘어도 끝에 붙어 있다(`e2e/pages` W8·W9 "마지막 행까지" 테스트가 잡은 회귀) |

정적 모양(셀·열·머리줄·배지)은 그대로. 바뀐 동작은 스크롤 위치 ↔ 행 대응이 정확해진 것(전에는 행이 스크롤보다 빠르게 튐)과 스크롤바 길이(실측 합계).
테스트는 하나도 고치지 않았다.

## 4. 측정 (로컬 Ryzen 5 5600, Playwright chromium headless, 다른 에이전트 부하 CPU ~40%) — `perf-scroll.ts`, 3회

| CPU 감속 | 수정 전 (main) | 실측만 | 실측 + overscan 4 | **최종** (실측 + overscan 2 + anchorTo end + 짧은 목록) |
| --- | --- | --- | --- | --- |
| ×1 | p50 16.7 · p95 16.8 · ≤20ms 180/180 | 16.7 · 16.7 · 180 | 16.7 · 16.8 · 180 | **16.7 · 16.8 · 180/180** |
| ×2 | p50 33.3 · p95 50.0 · ≤20ms 82/180 | 16.7 · 16.7 · 180 | — | **16.7 · 16.7 · 180/180**(최대 16.8) |
| ×4 | p50 50.1 · p95 99.9 · ≤20ms 7/180 | 33.3 · 33.4 · 84 | 16.7 · 33.4 · 115 | **16.7 · 16.8 · 180/180**(회차 180·180·168) |
| ×6 | p50 100 · p95 166.6 · 6/180 | | | |

목표: ×4 ≥ 90% 프레임 ≤ 20ms(162/180) 와 p95 ≤ 20ms → 충족(중앙값 180/180, p95 16.8). ×2 p95 ≤ 34ms → 충족(16.7). 같은 기준 앞 측정(overscan 2 · anchorTo 전)
×4 177/180, anchorTo 뒤 175/180 — 회차 편차는 다른 프로세스 부하.
트레이스(×1, 프레임당 메인 스레드 평균): 수정 전 9.3ms → 실측 3.6ms → overscan 4 2.9ms.

## 5. 완료 기준 실행 (frontend/)

포트: E2E_PORT 5970 · E2E_PAGES_PORT 5971 · E2E_PERF_PORT 5972 · E2E_API_PORT 18595 · E2E_API_WEB_PORT 5991 · Lighthouse 4995, `E2E_API_DATA` 새 폴더.

| 명령 | 결과 |
| --- | --- |
| `npm ci` | exit 0 |
| `npm run typecheck` · `npm run lint` | exit 0 · exit 0 |
| `npx vitest run` | 64 파일 · 890 통과 |
| `npm run build` | exit 0 (entry-chunk-guard·max-chunk-guard 통과) |
| `npm audit` | found 0 vulnerabilities |
| `npm run e2e` | 46 통과 · 22 통과 (T16 3회 중앙값 p50 16.7 · p95 16.8, 회차마다 ≤20ms 180/180) |
| `npm run e2e:api` | 45 통과 (3.7분) |
| `npm run lighthouse` | 13건 전부 80 이상, 모바일 94 / 93 / 93, 데스크톱 98–100 |

첫 `e2e:api`(overscan 2 만) 3건 실패 → 짧은 목록 전부 그리기로 해결, 첫 `e2e/pages` W8·W9 실패 → anchorTo end 로 해결. 스모크 1회 부하 중 1건 실패,
재실행 46/46 통과.
