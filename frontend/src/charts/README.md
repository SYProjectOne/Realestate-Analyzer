# src/charts — 차트 C1~C10 계약 (WP0-C 고정, 계약 2026-10-09.1)

- **주인**: WP6b (구현). **사용자**: WP6a (화면에 배치).
- 차트마다 폴더 하나: `Cxx/types.ts`(입력 데이터 타입 + `Cxx_EMPTY`), `Cxx/buildOption.ts`(순수 함수), `Cxx/index.tsx`(렌더 컴포넌트).
- **입력 타입(`CxxData`)과 export 이름이 계약**이다. 내부 option·모양은 WP6b가 RA §7-2 / meta §2-7대로 완성한다. 입력에 필드를 *추가*하는 건 optional로만.
- 화면은 `@/charts`(index.ts)에서만 import 한다.

## WP6b 완성 메모 (R1)

- **입력 원소 타입 = 계약 응답 그대로**(`src/lib/contract.ts` → 생성 `schema.d.ts`). 임시 `@/api/types` 모양(Benchmark·SupplyRow·UnsoldRow·Catalyst·DecisionSet.rows 등)은 계약과 달라 교체했다. `CxxData` 필드 이름은 유지, 추가 필드는 전부 optional:

  | 차트 | 넘기는 값 (계약)                                                         | 추가 optional                                                         |
  | ---- | ------------------------------------------------------------------------ | --------------------------------------------------------------------- |
  | C01  | `ComplexDetail.ladder` / `CompareView.ladders[id]`                       | —                                                                     |
  | C02  | `ComplexDetail.gap` / `CompareView.gaps[id]`                             | —                                                                     |
  | C03  | `Market.benchmarks` (BenchmarkView)                                      | `flags = Market.benchmark_flags`, `livingAreas = Market.living_areas` |
  | C04  | `Market.supply` (SupplyPoint), `markers = Market.move_in_markers` 그대로 | `livingAreas`                                                         |
  | C05  | `Market.unsold` / `Dashboard.unsold_series` (UnsoldPoint)                | `scope`(scope_code; 생략 시 자료 최다 범위)                           |
  | C06  | `rows = ScoreRow[]`(components = ComponentView), `weights`               | `keys = CompareView.components.keys` (A·D의 move_in)                  |
  | C07  | `CompareView.decisions[scenario_code]` (DecisionSet.items)               | —                                                                     |
  | C08  | `ComplexDetail.events`                                                   | —                                                                     |
  | C09  | `Market.catalysts` / `ComplexDetail.catalysts` (CatalystView)            | —                                                                     |
  | C10  | `GET /sensitivity` (Sensitivity — id만 있음)                             | `names = {complex_id: 이름}` (Dashboard.top5·CompareView.rows)        |

- 갤러리: `src/charts/gallery` (`ChartGallery`, `GALLERY_CASES`) — `@/charts`에서는 내보내지 않는다(예시 JSON 번들). dev 라우트 `/__charts`에 lazy 등록. 테스트 전용 엔트리 `/src/charts/gallery/gallery.html`(dev 서버).
- 스크린샷: `npx playwright test charts-gallery` (`tests/e2e/charts-gallery.spec.ts`). win32 기준 이미지는 `--update-snapshots`로 이 기계에서, linux 기준 이미지는 CI 산출물에서 받는다(D25-9).

## 모듈 계약 (`types.ts` `ChartModule<D>`)

| export (buildOption.ts)                                    | 규칙                                                                                                                                     |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `buildOption(data: D, ctx?: { palette }) => EChartsOption` | **순수 함수**: DOM·훅·전역 상태·`Date.now()` 금지. 빈 데이터에서 throw 금지(테스트로 강제). 색은 `ctx.palette`(기본 `DEFAULT_PALETTE`)만 |
| `emptyReason(data: D) => string \| null`                   | 그릴 게 없으면 화면 문구(ko.json), 있으면 null → `ChartFrame`이 `EmptyState`로 대신 그림                                                 |
| `toTable(data: D) => DataTable`                            | "표로 보기"(D7). 셀은 가능하면 `Fact` 그대로(라벨·출처 유지)                                                                             |
| `legendItems(data: D, ctx?) => ChartLegendItem[]`          | (R11) 차트 **위** HTML 범례 항목(이름·색·모양·note). 계열이 하나거나 빈 데이터면 `[]`. ECharts 범례는 `show:false`                       |

`registry.ts`의 `chartRegistry`가 10개를 순회한다(`buildOption.test.ts`: 빈 데이터 → option 객체·JSON 직렬화 가능·emptyReason 문자열·toTable 열 존재).
`buildOption.ts`는 ESLint `no-raw-number-render` 예외지만, 숫자 → 문자열은 `src/lib/format.ts`(formatEok·formatProb …)를 쓴다.

## 공용

- `ChartFrame` props: `title`, `subtitle?`, `labels?: Label[]`(중복 제거해 텍스트 배지), `badges?: ReactNode`, `legend?: ChartLegendItem[]`(R11 — 차트 위 HTML 범례, 줄바꿈되어 축과 겹치지 않음), `table?: DataTable`, `emptyReason?: string \| null`, `asof?`, `source?`(R11 — 바닥줄 "자료: 출처 · 기준일"), `children`.
  - R11(목업 Shell §8): 제목·배지·부제 → 범례 → 차트(또는 빈 상태) → 바닥줄(자료 줄 + [표로 보기]). 표는 `ChartFooter`(./ChartTable.tsx)가 그린다 — 보이는 캡션 "{제목} 데이터", 줄이 없으면 열 머리 아래 "데이터 없음" 한 줄. 셀 규칙은 `DataTableToggle`과 같다(Fact → FactCell).
  - 차트 컴포넌트 10개는 모두 `asof?`·`source?` props를 받는다(생략하면 출처 = ko `chart.Cxx.source`, 기준일 없음).
- `EChart` props: `option`, `height?`, `ariaLabel`. **뷰포트 진입 시 lazy**(IntersectionObserver → `React.lazy(./EChartRuntime)` — 쓰는 계열·컴포넌트만 등록한 echarts/core, 테스트는 `vi.mock('@/charts/EChartRuntime')`), SVG 렌더러. IO가 없는 환경(jsdom)은 즉시 렌더.
- `useChartPalette()`: CSS 토큰(`src/index.css`)을 읽어 라이트/다크에 맞춘 팔레트. 의미 색은 `strong`(확정·강조)과 `grayed`(비공식·미확정·미해결) 둘. 계열 구분은 `categorical` — R11부터 목업 팔레트(파랑·주황부터, 라이트 `CATEGORICAL_LIGHT`·다크 `CATEGORICAL_DARK`, dataviz 검증기 통과) + `secondary`(주황)·`strongSoft`·`rest`('나머지')·`grid`·`band`. 색은 계열(단지·생활권·기준)을 따르고 돌려 쓰지 않는다(`seriesColor`). 범례 글자·마커 모양 병기.

## 차트별 계약

| #   | 컴포넌트            | 입력 타입 (데이터 소스 = RA §7-2)                                                                                     | 빈·특수 상태                                                                                 | 비고(완성 시 할 일)                                                                                                                                                                                      |
| --- | ------------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C01 | `C01Ladder`         | `C01Data{ ladder: LadderRow[] (ComplexDetail.ladder), horizon: LadderHorizon, overlay?: {complex_id,name,ladder}[] }` | 해당 horizon 없음 → "사다리 판정 없음"; status review/escaped/blocked → 회색 막대 + "미해결" | 가로 막대 4(+5/+10/+20/보합·하락), xAxis 0~1, markLine 0.15/0.85, 라벨 = 확률 + verdict, 부제 = 목표 시점(연도 반기, `subtitle()`), horizon 탭은 호출 측. G4 overlay = scatter                           |
| C02 | `C02Gap`            | `C02Data{ gap: Gap \| null }` (ComplexDetail.gap / CompareView.gaps[id])                                              | comps 0 또는 null → "비교군 없음(사유)" (`gap.empty_reason`)                                 | 점(중앙)+위스커(custom), y축 억(`formatEok`), 배지 "신축/대체(준공년)"(`compBadge`), 보정 중앙값 = 점선 테두리 점. G4는 단지 수만큼 나란히                                                               |
| C03 | `C03Benchmark`      | `C03Data{ benchmarks: Benchmark[] (Market.benchmarks), asofYear: number \| null }`                                    | 0개 → "벤치마크 없음"; 표본 < 3 → 배지 "표본 n, 추정"(`sampleBadge`)                         | dumbbell: 분양가 → 실거래 범위, 고점 마커(triangle), `is_presale` = diamond, 툴팁 연율(`annualizedPct`, asofYear 기준)                                                                                   |
| C04 | `C04Supply`         | `C04Data{ supply: SupplyRow[] (Market.supply), markers: {complex_id,name,move_in_ym}[] }`                             | 0개 → "입주 물량 없음"                                                                       | 연도 x, 생활권 스택(R11: 한 해 최대값이 큰 5곳 + '나머지 n곳' 회색 + 생활권 모름 빗금 — 계열은 생활권마다, 값은 서버 그대로), markPoint = 판정 단지 입주월, 라벨 "추정 집계"                             |
| C05 | `C05Unsold`         | `C05Data{ unsold: UnsoldRow[] (Market.unsold), months?: number(=24) }`                                                | 0개 → "미분양 자료 없음"                                                                     | line 2개(합계·준공 후), `connectNulls=false`, 부제 "월말 기준", 배지 = source_label                                                                                                                      |
| C06 | `C06ScoreBreakdown` | `C06Data{ rows: ScoreRow[], weights: Weights, orientation?: 'vertical'\|'horizontal' }` (Dashboard·CompareView)       | 0행 → "점수 없음"; null component → 회색 빗금(decal) + "미판정"                              | stacked 6 시리즈, 기여 = w×s(`contributions`), 정렬 = 종합(`sortedRows`), 부제 = 가중치(`weightsSubtitle`), 툴팁 = `formula_text`. **완성 테스트: 기여 합 = total ±0.01**                                |
| C07 | `C07Decision`       | `C07Data{ decision: DecisionSet \| null }` (CompareView.decisions[scenario])                                          | null/0행 → "판정 없음"; status escaped → 막대 대신 "질문 남김: {question}"                   | 가로 막대(후보별 prob + escape), 부제 = confidence(`confidenceText`), `isTie`(conf<0.6) → TieBadge, mismatch → MismatchBadge                                                                             |
| C08 | `C08Timeline`       | `C08Data{ events: RemainingEvent[] (ComplexDetail.events) }`                                                          | 0개 → "본청약만"                                                                             | 시간축 scatter, 마커 모양 = kind 4종(`C08_SYMBOLS`), 라벨 = 잔여 세대·경쟁률                                                                                                                             |
| C09 | `C09Catalyst`       | `C09Data{ catalysts: Catalyst[] (Market/ComplexDetail.catalysts), compact?: boolean }`                                | 0개 → "호재 없음"                                                                            | 보드 = HTML 5열(`groupByStage`), 타임라인 = 확정만 time scatter(option), 언론·미확정 회색, `location_confirmed=false` → "위치 미확정 · 단지 연결 없음". G3는 compact                                     |
| C10 | `C10Sensitivity`    | `C10Data{ sensitivity: Sensitivity \| null }` (GET /sensitivity)                                                      | null/0셀 → "민감도 없음"                                                                     | R11: 결과 개수 줄(서버 changed 세기) + HTML 표(기준 6줄 × 줄이면/늘리면, 칸마다 1~5위 + 순위 변동, 변동 없는 칸 회색) + 순위 선(x = 기준 × 줄이면/늘리면 두 줄 축, 상위 5곳 밖 주황 띠), `unstable` 배지 |

## 완성 기준(WP6 카드)

차트 10개 각각 빈 데이터·라벨 배지 상태 스크린샷 테스트, 다크 테마 가독, 표 전환. option 빌더만 단위 테스트한다(렌더는 Playwright).
