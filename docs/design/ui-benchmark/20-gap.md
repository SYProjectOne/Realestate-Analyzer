# 20. 패턴 종합과 갭 분석 (Phase 3)

작성일 2026-10-14 · 입력: `00-baseline.md`(우리 앱 진단), `05-persona.md`(초보 실수요자 페르소나), `10-*.md`(사이트 노트), `11-reports.md`(보고서 레퍼런스)
대상 사용자: 05-persona의 P1~P4(청약을 처음 하는 실수요자). 사용자 요구는 "UI가 너무 어렵다 → 부동산 초보도 알 수 있게"이다.
코드는 고치지 않았다. 이 문서는 근거 정리와 갭 표만 담는다.

## 0. 근거 사용 규칙 (CEO 결정 반영)

| 구분 | 사이트 | 처리 |
|---|---|---|
| 관찰 불가(robots) | 네이버 부동산, 직방, SH, 호갱노노, 아실 | 노트·스크린샷 모두 근거로 쓰지 않는다. 사이트 수에도 넣지 않는다 |
| 전면 제외(이용 조건) | 국토부 실거래가 공개시스템(`molit-*`) | 자동 캡처를 금지하는 이용 조건이 있어 모든 evidence를 제외한다. 이 문서에서 인용하지 않는다 |
| 전면 제외(robots) | 부동산플래닛(`bdsplanet-*`) | AI UA에 `Disallow: /`가 걸려 있다. 홈 캡처는 robots 확인 전에 찍었지만 쓰지 않는다 |
| 일부 제외 | 다방 | `dabang-saletab-rea-desktop`(/sale-in-lots), `dabang-salemap-mobile`(/mobile)은 제외한다. `dabang-home-rea-desktop`, `dabang-salemap-rea-desktop`만 쓴다 |
| 일부 제외 | 리치고 | `/checklist` 리포트(`richgo-danji-desktop`)는 제외한다. `richgo-danji-rea-desktop`, `richgo-region-rea-desktop`, `richgom-*`는 쓴다 |
| 일부 제외 | Zillow | 상세(`zillow-detail-desktop`)는 robots 금지 경로로 들어가 제외한다. 검색·목록만 쓴다 |
| 허용 | KB부동산 | Claude 전용 robots 그룹이 허용한다. 근거로 쓴다 |
| 관찰 불가(봇 확인) | Redfin | 근거 없음 |

**사이트 수 세는 법**: 도메인 하나를 한 곳으로 센다(리치고 데스크톱과 리치고 모바일은 1곳). 근거로 쓸 수 있는 사이트는 국내 12곳(청약홈·LH·GH·KB·부동산지인·리치고·R-ONE·R114·땅집고·다방·디스코·밸류맵)과 해외 6곳(Zillow·Realtor.com·Rightmove·Zoopla·Domain·SUUMO)이다. 보고서 레퍼런스(`report-*`)는 위 사이트 수에 포함해 센다(부동산원 = R-ONE, KB, R114).

**등급**(메타 프롬프트 §4 Phase 3-1)
- **강한**: 4곳 이상이고 국내·해외에 모두 나온다.
- **검증된**: 2곳 이상.
- **참고**: 1곳.

구현에 쓰는 패턴은 "검증된" 이상이어야 한다(§5 완료 조건). 참고 패턴은 문구 근거로만 쓴다.

---

## 1. 패턴 카탈로그

### 1-1 요약 우선 배치

| ID | 패턴(우리 말) | 등급 | 사이트 수(국내/해외) | evidence_id |
|---|---|---|---|---|
| A1 | 상세 맨 위 한 덩어리에 **지금 상태 + 핵심 날짜 + 원문(공고문) 입구**를 둔다. 표·이미지는 그 아래에 둔다 | **강한** | 7 (4/3) | lh-detail-rea-desktop, gh-detail-rea-desktop, applyhome-detail-rea-desktop, richgom-parceldetail-mobile, suumo-detail-desktop, rightmove-detail-desktop, zoopla-detail-desktop |
| A2 | 홈 첫 줄은 **사용자 행동 단위의 개수**로 시작한다("지금 접수 중 N곳", "오늘 발표 N곳") | 검증된 | 4 (4/0) | applyhome-home-rea-desktop, lh-home-rea-desktop, r114-apply-rea-desktop, richgom-parcel-mobile |
| A3 | 계약 전에 꼭 알아야 할 **조건만 모은 상자**를 표 앞에 둔다(용어-값 목록, 항목마다 설명 버튼) | **강한** | 5 (2/3) | rightmove-detail-desktop, zoopla-detail-desktop, suumo-property-desktop, lh-detail-rea-desktop(공고내용 요약 글머리: 재당첨 제한·대금 구조), kbland-danji-rea-desktop(요약 줄의 규제지역) |
| A4 | 추정·점수·예측 옆에 **정의와 "이 값이 무엇이 아닌지"**를 한 문장으로 붙인다(보장 아님·참고용, 계산 기준·기준일) | **강한** | 4 (1/3) | richgo-danji-rea-desktop, richgom-home-rea-mobile, rightmove-detail-desktop(상환액 추정 고지), zoopla-detail-desktop(계산기 "참고용"), realtor-community-desktop(금리 기준 각주) |
| A5 | 1단에는 관측값을 두고, 판정·예측은 2단 이하에서 연다 | 참고 | 1 | richgo-danji-rea-desktop |
| A6 | 리드 문장 순서를 "맥락 → 이 단지 → 일정 한 줄"로 둔다 | 참고 | 1 | ddangzipgo-article-rea-desktop |

### 1-2 상태 배지

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| B1 | 카드·행 첫 줄에 **상태를 글자로**(접수중·마감·예정) 쓰고 **다음 일정 + D-n**을 한 줄 붙인다 | **강한** | 8 (5/3) | dabang-salemap-rea-desktop, richgom-parcel-mobile, kbland-bunyang-desktop, lh-list-rea-desktop, r114-apply-rea-desktop, domain-apartments-desktop, zillow-list-desktop, realtor-community-desktop |
| B2 | 일정 단계(특공·1순위·2순위·발표·계약)를 **짧은 텍스트 표식**과 단계 필터로 보인다 | 검증된 | 3 (3/0) | applyhome-calendar-rea-desktop, r114-apply-rea-desktop, kbland-bunyang-desktop |
| B3 | "지금 넣을 수 있는 것"을 따로 묶거나 기본 필터로 둔다(청약중/예정 섹션, 유효 공고 기본값 + 뜻 한 줄) | 검증된 | 3 (3/0) | lh-list-rea-desktop, richgom-parcel-mobile, kbland-bunyang-desktop (반례: gh-list-rea-desktop 기본값 "전체" → 첫 페이지가 마감 공고) |

### 1-3 핵심 수치 카드

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| C1 | 카드 하나에 **큰 숫자는 하나**만 둔다. 보조 수치는 회색 한 줄로 낮춘다 | **강한** | 6 (2/4) | dabang-salemap-rea-desktop, richgom-parcel-mobile, zillow-list-desktop, realtor-list-desktop, suumo-list-desktop, zoopla-detail-desktop |
| C2 | 가격 옆에 **무슨 기준의 값인지**(최고가 기준, 어느 공급분, 공급/전용 면적 기준, 가격 성격)를 붙인다 | **강한** | 5 (3/2) | applyhome-detail-rea-desktop, aptgin-region-desktop, disco-detail-rea-desktop, suumo-detail-desktop, rightmove-detail-desktop |
| C3 | 지표 카드 = 지표명(기간) + 큰 숫자·단위 + 비교 기준 한 줄 + 카드별 기준일 | 검증된 | 3 (3/0) | rone-home-rea-desktop, richgo-region-rea-desktop, aptgin-supply-rea-desktop |
| C4 | **"얼마가 필요한가" 분해**: 총액 → 계약금·중도금·잔금(비율, 언제) / 월 비용과 일시 비용 구분 | 검증된 | 3 (1/2) | lh-detail-rea-desktop(대금 구조 문장), realtor-community-desktop(계약 시 필요 금액 분해), suumo-property-desktop(월/일시 꼬리표) — 반례: applyhome-detail-rea-desktop(계약금·중도금을 PDF로만 넘김) |
| C5 | 대표값 크게 + 상·하위 범위를 행으로 나눈다 | 참고 | 1 | kbland-danji-rea-desktop |

### 1-4 표 밀도와 열 선택

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| D1 | 행이 많은 세부값(경쟁률 등)은 목록에 펼치지 않고 **셀 버튼으로 미룬다** | 검증된 | 2 (2/0) | applyhome-list-rea-desktop, gh-list-rea-desktop |
| D2 | **핵심 필터 3~4개만 노출**하고 나머지는 "필터"로 접는다. 적용 개수를 버튼에 표시한다 | **강한** | 5 (2/3) | lh-list-rea-desktop(모바일 1칸 + 상세 펼침), richgom-home-mobile(칩 한 줄 + 시트), zillow-search-desktop, rightmove-list-desktop, zoopla-list-desktop |
| D3 | 이력 표는 **5행 + 더보기**로 시작하고, 요약 표는 6~7행에 "더 보기"를 둔다 | 검증된 | 3 (2/1) | disco-detail-rea-desktop, richgo-danji-rea-desktop, suumo-detail-desktop |
| D4 | 표 단위·출처·각주는 **표 머리나 꼬리에 한 번만** 적는다(셀마다 반복하지 않음) | 검증된 | 3 (3/0) | applyhome-detail-rea-desktop("단위: 만원" 1회·표 아래 각주), kbland-danji-rea-desktop, aptgin-supply-rea-desktop |

### 1-5 상세 페이지 탭 구조

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| E1 | 상세는 탭(앵커형 포함)으로 나눈다. 순서는 **가격 → 거래 → 평형 → 자금 → 기본정보 → 주변**. 탭이 13개 넘으면 과하다(반례) | **강한** | 5 (4/1) | kbland-danji-rea-desktop, richgo-danji-rea-desktop, valueupmap-trade-rea-desktop(13개 — 반례), disco-detail-rea-desktop, suumo-detail-desktop |
| E2 | **일정은 단계별 행 하나의 표·글머리**로 모은다(특공·1순위·2순위 × 해당/기타 → 발표 → 서류 → 계약) | **강한** | 5 (4/1) | applyhome-detail-rea-desktop, lh-detail-rea-desktop, gh-detail-rea-desktop, ddangzipgo-article-rea-desktop, suumo-property-desktop |
| E3 | **빈 탭·빈 섹션도 지우지 않는다**. "(0)" 또는 문장으로 남긴다 | 검증된 | 3 (2/1) | suumo-detail-desktop, richgom-parceldetail-mobile, disco-detail-rea-desktop |
| E4 | 공통 정보와 공급 차수별 정보를 나누고 차수 표의 행 순서를 맞춘다 | 참고 | 1 | suumo-property-desktop |
| E5 | 탭을 데이터 출처 종류별로 나눈다 | 참고 | 1 | disco-detail-rea-desktop |

### 1-6 용어 설명

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| F1 | 용어·열 제목 바로 옆에 **설명 버튼(ⓘ/?)**을 두어 그 자리에서 정의를 연다 | **강한** | 5 (2/3) | rightmove-detail-desktop, zoopla-detail-desktop, realtor-community-desktop, aptgin-region-desktop, report-kb-weathermap-desktop |
| F2 | **별도 용어집·가이드**를 질문형 제목("~란?")과 결론 한 줄로 만들고, 어느 화면에서나 한 번에 닿게 한다 | **강한** | 6 (4/2) | applyhome-glossary-desktop, lh-guide-rea-desktop, r114-trends-rea-desktop, aptgin-supply-rea-desktop(전역 "용어설명" 메뉴), suumo-home-desktop("사용법" 링크), zillow-search-desktop("더 알아보기") |
| F3 | 공식 단위 뒤에 괄호로 생활 단위를, 은어 뒤에 괄호로 공식 용어를 붙인다("84㎡(약 34평)") | **강한** | 4 (3/1) | ddangzipgo-article-rea-desktop, disco-detail-rea-desktop, richgo-danji-rea-desktop(자체 시세 첫 등장 괄호 정의), rightmove-detail-desktop(면적 두 단위) |
| F4 | 쉬운 동사형·대화체 문장으로 감싸고, 목록 머리에 "이 목록이 무엇이고 누르면 무엇이 나오는지" 한 문장을 둔다 | 검증된 | 3 (3/0) | applyhome-home-rea-desktop, richgo-danji-rea-desktop, r114-apply-rea-desktop |

### 1-7 출처 표기

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| G1 | 출처·단위·기준일을 **블록(패널·표·카드) 단위로 한 줄** 붙인다 | **강한** | 7 (6/1) | kbland-danji-rea-desktop, aptgin-supply-rea-desktop, aptgin-unsold-desktop, rone-home-rea-desktop, valueupmap-trade-rea-desktop, applyhome-detail-rea-desktop, suumo-detail-desktop(개요 표 끝 정보 갱신일) |
| G2 | 원문 문서를 **눈에 띄는 상자 하나**에 모은다(형식·크기 표시) | **강한** | 5 (4/1) | lh-detail-rea-desktop, gh-detail-rea-desktop, applyhome-detail-rea-desktop, valueupmap-trade-rea-desktop(문서함), zoopla-detail-desktop(자료 버튼 줄) |
| G3 | "참고용 · 원문(공고문)이 우선" 고지를 목록·계산 블록에 고정한다 | 검증된 | 3 (1/2) | applyhome-list-rea-desktop, zillow-search-desktop, zoopla-detail-desktop |
| G4 | 값의 성격이 다를 때 **값 앞·옆의 짧은 종류 라벨**로 구분한다(실·호가, 분양가/임대가, "(추정)") | 검증된 | 4 (3/1) | richgom-home-mobile, dabang-salemap-rea-desktop, richgo-danji-rea-desktop, rightmove-detail-desktop |
| G5 | 페이지 끝 "데이터 출처" 표(구분·일시·출처) + 정정 요청 | 참고 | 1 | richgo-danji-rea-desktop, richgom-parceldetail-mobile(같은 사이트) |

### 1-8 비교 화면

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| H1 | 비교 표의 행은 **사용자가 비교하려는 사실**(가격·거리·연식·세대·입주·거래)부터 두고, 사용자가 스스로 비교하게 한다(차이를 평가어로 만들지 않음) | 검증된 | 3 (3/0) | aptgin-region-desktop, richgom-parceldetail-mobile, kbland-danji-rea-desktop |
| H2 | **비교 기준을 행 이름에 문장으로** 쓴다("전월 대비", "최근 10년 평균 대비") | 검증된 | 2 (2/0) | rone-theme-rea-desktop, richgo-region-rea-desktop |
| H3 | 비교 차트에 평균선 + 값 라벨, 대상 단지는 표 끝 별도 행 | 검증된 | 2 (2/0) | richgom-parceldetail-mobile, aptgin-unsold-desktop |
| H4 | 두 순위·지표가 서로 달라 보이면 **그 이유를 한 문장으로 미리** 적는다 | 참고 | 1 | richgo-danji-rea-desktop (구현 근거는 A4 "정의 문장"으로 쓴다) |

### 1-9 빈 상태

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| I1 | 빈 값·빈 섹션 = **사실 + 이유 + 어디서 확인하나/다음에 할 일**. 이유는 사용자의 말로 쓴다("미정", "발표 후 공개", "공고문 확인", "준비 중") | **강한** | 13 (9/4) | applyhome-competition-rea-desktop, lh-detail-rea-desktop, gh-detail-rea-desktop, kbland-danji-rea-desktop, richgom-parceldetail-mobile, disco-detail-rea-desktop, dabang-salemap-rea-desktop, r114-apply-rea-desktop, aptgin-supply-rea-desktop, zillow-search-desktop, rightmove-detail-desktop, domain-apartments-desktop, suumo-list-desktop |
| I2 | 0건도 "0건"으로 보인다 | 검증된 | 2 (2/0) | lh-home-rea-desktop, kbland-danji-rea-desktop |

### 1-10 모바일 축약

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| J1 | 모바일 목록은 표 대신 **카드**: 지역(회색) → 이름 → 상태 + D-n → 핵심 수치 한 줄 | 검증된 | 2 (2/0) | richgom-parcel-mobile, lh-list-rea-desktop(모바일 카드 — lh-list-mobile) · 반례: gh-list-rea-desktop(모바일 표 잘림), applyhome-list-rea-desktop(모바일 가로 스크롤) |
| J2 | 모바일 필터 = 핵심 1칸·칩 한 줄 + 나머지 펼침·시트 | 검증된 | 2 (2/0) | lh-list-rea-desktop(lh-list-mobile), richgom-home-mobile |
| J3 | 모바일 메뉴는 짧게 줄여 하단 고정 바로 옮긴다 | 검증된 | 3 (3/0) | lh-home-rea-desktop(lh-home-mobile), aptgin-region-mobile, richgom-parcel-mobile |

해외 사이트의 모바일 레이아웃은 관찰하지 못했다(Tier 3 노트 모두 "모바일 관찰 못 함", SUUMO 모바일 창은 PC판). 그래서 J 범주에는 "강한" 패턴이 없다.

### 1-11 보고서 첫 장 구성

| ID | 패턴 | 등급 | 사이트 수 | evidence_id |
|---|---|---|---|---|
| K1 | 첫 장 = **결론 요약 블록 + 메타 머리 상자**(기준일·발행일·본문/부록 쪽수·문의). 기준일로 시작하는 요약 문단 | 검증된 | 3 (3/0) | report-rone-weekly-p1-desktop, report-kb-weathermap-desktop(KB 리뷰 요약 2문단은 WebFetch 관찰 — `11-reports.md` §2-2), richgo-region-rea-desktop("한눈에 보기" 기준일 시작) · 반례: report-r114-report-desktop(표지 이미지만) |
| K2 | **본문과 부록(긴 표)을 나눈다**. 본문 표는 3~4열 | 검증된 | 3 (2/1) | report-rone-weekly-p1-desktop(본문 8매·붙임 7매), report-kb-weathermap-desktop(3열 표), suumo-detail-desktop(요약 표 + 개요 더 보기) |
| K3 | 차트마다 **위에 제목(지표·기간), 아래에 "자료: 출처 · 기준일"**, 같은 숫자의 표를 바로 옆·아래에 둔다 | 검증된 | 4 (4/0) | report-kb-weathermap-desktop, rone-theme-rea-desktop, richgom-parceldetail-mobile, aptgin-supply-rea-desktop |
| K4 | 정보를 **이미지에만** 넣지 않는다(텍스트·표로도 존재) | 검증된(반례 근거) | 2 | report-r114-report-desktop(카드뉴스 반례), lh-home-rea-desktop(조건이 광고 이미지 안 — 반례) |
| K5 | 증감은 색과 ▲▼(+/−) 기호를 함께 쓴다. 범례에 단위를 적는다. 날씨 같은 좋고 나쁨 비유는 쓰지 않는다 | 검증된 | 2 (2/0) | report-kb-weathermap-desktop, rone-home-rea-desktop |

### 1-12 국내 습관과 해외 패턴이 충돌하는 지점 (결정 사항으로 넘김)

메타 프롬프트 규칙: 충돌하면 국내 습관을 우선하고 충돌 사실을 결정 사항으로 남긴다. 네이버·호갱노노·아실은 관찰하지 못했으므로 "국내 습관"은 KB·리치고·청약홈·LH·다방 근거로만 판단했다.

| # | 충돌 | 국내 | 해외 | 이 문서의 기본 판단 | 결정 번호(30-proposal §12) |
|---|---|---|---|---|---|
| X1 | 상세 구조 | 가로 탭(앵커형) 5~13개 — kbland-danji-rea-desktop, richgo-danji-rea-desktop, valueupmap-trade-rea-desktop | 한 페이지 스크롤 + 용어-값 목록 + 접기 — rightmove-detail-desktop, zoopla-detail-desktop | 국내 우선: 탭은 유지하되 3~6개로 줄이고, 탭 위 1단 요약을 고정한다 | 결정 1 |
| X2 | 단지 가격 표기 | 범위 "최저~최고"(억 단위) — richgom-parcel-mobile, dabang-salemap-rea-desktop | "부터 최저가"(+) — realtor-list-desktop, zillow-list-desktop | 국내 우선: 범위 유지(SUUMO도 범위) | 결정 없음(확정) |
| X3 | 목록 기본 정렬 | 상태(청약중→예정)·일정순 — richgom-parcel-mobile, kbland-bunyang-desktop | 추천순(개인화) — zillow-list-desktop, zoopla-list-desktop | 우리는 추천순을 만들지 않는다. 지금 기본인 종합 점수순을 유지할지, 접수 상태 우선으로 바꿀지 결정 필요 | 결정 4 |
| X4 | 돈 블록 | 대금 구조 문장(중도금 유무·대출 알선) — lh-detail-rea-desktop | 월 상환액·대출 계산기 — rightmove/zoopla/realtor | 국내 우선 + 우리 규칙(대출·세금 계산 금지): 공고 값과 §6 산술 값만 | 결정 없음(규칙으로 확정) |
| X5 | 용어 처리 | 별도 용어집·가이드 페이지 — applyhome-glossary-desktop, lh-guide-rea-desktop, r114-trends-rea-desktop | 값 옆 ⓘ 버튼 — rightmove/zoopla/realtor | 둘 다 쓴다: 값 옆 ⓘ에서 한 줄 정의를 열고, 거기서 용어 모음 페이지로 이어 준다 | 결정 9 |

---

## 2. 갭 표

정렬: 효과 상 → 품 S → M → L, 그다음 효과 중·하. "지금 문제"의 근거는 모두 `00-baseline.md`의 관찰과 그 evidence_id다. 규칙 열의 번호는 메타 프롬프트 §3-2(R1~R9)와 AGENTS.md(A1~A19)를 가리킨다.

### 2-1 프론트(WP6)만으로 고칠 수 있는 것

| # | 화면 | 지금 문제(00-baseline 근거) | 검증된 패턴(근거) | 바꿀 것 | 영향 파일 | 효과 | 품 | 지켜야 할 규칙 |
|---|---|---|---|---|---|---|---|---|
| 1 | G1 | 큰 숫자 5개 중 초보에게 의미 있는 것은 `접수 가능 3`뿐이다. 그 카드를 누르면 단지 목록이 아니라 출처 패널이 열린다. 첫 줄이 "시스템이 무엇을 셌나"로 시작한다 (§2 G1 3초 테스트, ours-g1-dashboard-desktop-rea) | A2 검증된, C1 강한 | 첫 줄을 "지금 접수 가능 N곳" 큰 카드 1장(+ "단지 보기 →" 링크 = G2 `?intake_status=가능`)으로 바꾼다. 판정 대상·미분양·입주 피크·데이터 신선도는 2단 "지역 현황" 작은 카드 줄로 내린다. 숫자는 FactCell 그대로 두어 출처 패널은 숫자 클릭으로 연다 | `pages/dashboard/index.tsx`, `i18n/ko.json`, 테스트 | 상 | S | R3(FactCell), R5(라벨 유지), D10-1(저장값), A12 |
| 2 | G1·G2·G3 공통 | 모든 숫자 옆에 같은 무게의 라벨 배지가 붙는다(G3 숫자 89·라벨 46, G2 숫자 43·배지 35). 점선 밑줄이 "누르면 출처"라는 안내가 없다 (§1, §5-4, ours-g3-detail-32-desktop-rea, ours-g2-complexes-desktop-rea) | G4 검증된(값 성격이 다를 때만 강조), F1 강한(배지 설명 진입점), G1 강한(블록 단위 출처) | `확인됨`은 테두리 없는 작은 회색 글자로 낮춘다(글자는 그대로 남긴다). `추정·비공식·재가공·확인 불가·사람 확인`은 지금처럼 테두리 배지로 둔다. 각 화면 머리에 범례 한 줄("밑줄 친 숫자를 누르면 출처·확인일이 열립니다 · 라벨 뜻 ⓘ")을 둔다 | `components/LabelBadge.tsx`, `components/Badge.tsx`(tone 추가), `components/components.contract.test.tsx`, `ko.json` | 상 | S | R5(라벨 텍스트는 사라지지 않음 — 빈 라벨 테스트 유지), D7(색이 아닌 텍스트 배지), A5 |
| 3 | G1·G3·G4 | `+10% 확률 53%`가 목표 시점 없이 나온다. 초보는 이를 **당첨 확률로 오해**할 위험이 크다. `rerank 변화(이전 run 대비)`·`likely/unlikely` 같은 내부어가 노출된다 (§4 Q6, §5-7, ours-g1-dashboard-desktop-rea, ours-g3-detail-32-tab3-desktop) | A4 강한 | 이름을 "가격 +10% 상승 가능성(판정기)"로 바꾸고, 목표 시점은 데이터(사다리 horizon)에서 가져와 붙인다. 정의 한 줄 "당첨 확률이 아닙니다 · 보장 아님"을 고정한다. G1 TOP 카드의 `rerank 변화`는 G4·G5로 옮긴다(G3 2단에는 남긴다). 기준선 `likely 0.85/unlikely 0.15` 글자를 "가능성 높음 기준 0.85 / 낮음 기준 0.15"로 바꾼다 | `ko.json`(page.G1.p10, chart.C01.threshold 등), `pages/dashboard/index.tsx` | 상 | S | R4(새 판정 없음 — 이름·정의만), A3 |
| 4 | G1 | `최근 변경`이 화면 오른쪽 절반을 차지한다. 그 안에 64자리 해시 `official_popup_hash 4017…→59fd…`가 3번 나온다 (§2 G1, ours-g1-dashboard-desktop-rea) | F4 검증된(쉬운 문장), G2 강한(원문은 한 곳에서 열기) | 필드 이름을 쉬운 문장("공식 홈페이지 안내문이 바뀌었습니다")으로 바꾼다. 해시는 `<details>` "바뀐 값 보기"(1클릭) 안에 둔다. 피드는 TOP 아래 2단으로 내리고 3건 + "더 보기"로 줄인다 | `pages/_shared/index.tsx`(changeFieldText·changeValueText), `pages/dashboard/index.tsx`, `ko.json`(page.common.changeField) | 상 | S | D25-2(변경 피드는 FactCell 대상 아님), R5(값 삭제 금지 — 접기만) |
| 5 | G1 | 미분양 카드의 라벨 문구 `확인됨(인천 검단구 737·…합)`이 한 줄로 넘쳐 옆 카드를 덮는다. 페이지 폭이 1,603px(모바일 1,038px)로 늘어난다 (§2 G1 레이아웃 결함, ours-g1-dashboard-desktop-rea, ours-g1-dashboard-mobile) | G1 강한(출처 상세는 블록 한 줄 + 패널) | LabelBadge에 줄바꿈(`break-words`, `max-w-full`)을 허용한다. 사유가 40자를 넘으면 "확인됨(지역 합계 · 내역 보기)"처럼 줄이고 전문은 `title`과 출처 패널에 둔다. 숫자 클릭 1번으로 전문이 열린다 | `components/LabelBadge.tsx`, `components/Badge.tsx`, e2e(가로 넘침 검사) | 상 | S | R5(사유 전문은 1클릭), 요청 Q5(사유 문자열 길이) |
| 6 | G3 | 초보 질문의 답이 엉뚱한 탭 이름 아래 있다. 경쟁률은 `잔여 이력` 탭 아래쪽, 거주의무·재당첨·규제는 `출처 원문` 탭, `사다리`·`판정기 로그`는 내부어다 (§5-1, ours-g3-detail-32-tab2/tab6-desktop) | E1 강한(가격→거래→자금→기본정보 순서), F4 검증된 | 탭 이름을 쉬운 말로 바꾼다: 가격표→"타입별 가격", 납부 조건→"내야 할 돈·일정", 잔여 이력→"경쟁률·추가 모집", 사다리→"가격 전망(판정기)", 시세 비교→"주변 시세 비교", 호재→"개발 소식(호재)", 출처 원문→"근거 원문", 판정기 로그→"판정 기록(운영)". `경쟁률·추가 모집` 탭에서 경쟁률 표를 차트 위로 올린다. URL 해시 키는 그대로 둔다(G1 피드 링크 호환) | `ko.json`(page.G3.tab.*), `pages/complex/tabs.tsx`(EventsTab 순서) | 상 | S | ChangeEvent.tab 키 불변, R5 |
| 7 | G3 | `가격 갭`의 방향(높다/낮다)과 기준(어느 단지들의 중앙값)이 문장으로 없다. 같은 이름 `가격 갭`이 8.1%와 2.98 두 값으로 나온다 (§4 Q4, ours-g3-detail-32-tab4-desktop) | H2 검증된(비교 기준을 문장으로), C2 강한(값의 기준 명시) | 갭 수치 옆에 비교 기준 문장을 붙인다: "현재 구매가가 비교 단지 실거래 중앙값보다 {gap} {높음/낮음}"(부호 → 방향 글자, 평가어 금지). 2.98은 성분 점수이므로 "가격 갭 점수(0~10)"로 이름을 바꾼다(필드 의미는 요청 Q6으로 확인) | `pages/complex/tabs.tsx`(GapTab), `charts/C02*`, `ko.json` | 상 | S | R4("싸다/비싸다"·좋음/나쁨 금지, 방향 글자만), A3 |
| 8 | G4 | 비교표가 점수 계열 6행뿐이다. 가격·계약금·전매 종료·입주가 없다. `판정기 decide` 1위와 `선택`된 단지가 다른데 설명이 없다 (§2 G4, ours-g4-compare-desktop) | H1 검증된(사실 비교 우선), A4 강한(정의 문장) | 이미 있는 `TermsTable`(전매·거주·계약금 % ·계약금 원·필요 자기자본·중도금 조건)을 차트들보다 위, 비교표 바로 아래로 옮긴다. 비교표 머리에 한 줄 정의 "종합 점수 순위 = 성분 가중합 상대 비교, 판정기 선택 확률 = 상황 조건을 넣은 판정기 판단 — 둘은 다를 수 있습니다"를 둔다 | `pages/compare/index.tsx`, `ko.json` | 상 | S | R4(설명만, 새 판단 없음), R5 |
| 9 | G2 | 필터 10칸이 첫 화면의 1/4(모바일 2/3)를 차지한다 (§2 G2 3초 테스트, ours-g2-complexes-desktop-rea, ours-g2-complexes-mobile) | D2 강한, B3 검증된 | 단지명·접수·생활권 3칸만 펼쳐 두고 나머지 7칸은 "필터 더 보기(적용 n개)"로 접는다. 목록 위에 "지금 접수 가능 n곳만 보기" 칩을 둔다(기존 필터 `intake_status=가능` 재사용). 목록 머리에 한 문장 안내를 둔다 | `pages/complexes/FilterBar.tsx`, `pages/complexes/index.tsx`, `ko.json` | 상 | S | URL 쿼리 필터 유지, D7 모바일 읽기 전용 |
| 10 | G1·G2·G3 | `확인 불가` 사유가 내부 처리어다(`판정 미해결`, `미판정`, `발코니 표 해석 실패`). 초보는 "모른다"와 "앱 오류"를 구분하지 못한다 (§3 상태 표, §5-9, ours-g3-detail-1-desktop-rea) | I1 강한(이유를 사용자 말로 + 어디서 확인) | 알려진 사유 문자열을 쉬운 말로 바꾼다. 예: "해석 실패" → "공고문에서 자동으로 읽지 못함 — 공고문 원문 확인", "판정 미해결" → "자동 확인이 끝나지 않음", "미판정" → "점수 계산 전". 형식 `확인 불가(사유, 날짜)`는 유지한다. 원 사유는 `title`과 출처 패널에 남긴다. 모르는 사유는 그대로 둔다 | `lib/format.ts`(formatUnknown), `components/EmptyState.tsx`, `ko.json`(empty.reasonPlain.*) | 상 | S | D7 "확인 불가(사유)", R5, 요청 Q5(사유 코드) |
| 11 | G3 | 요약 8칸이 같은 크기다. 거주의무·재당첨 제한·분양가상한제·규제지역은 7번째 탭에만 있고, 계약금은 2번째 탭에만 있다. 접수 기간·당첨 발표일이 첫 화면에 없다. "접수 가능"이 일반 청약인지 무순위인지 구분이 없다 (§2 G3 3초 테스트, §4 Q1·Q2·Q3, ours-g3-detail-32-desktop-rea) | A1 강한, A3 강한, E2 강한, C4 검증된 | 머리를 3단으로 다시 짠다. 1단 "지금 상태": 접수 상태 + 현재 적용 공고 종류(본청약/무순위 — `payment[].notice_kind`·`is_current`) + 접수 일정(`header.apply_dates`·`winner_date`·`contract_dates`, D±) + 공고문 원문 버튼. 2단 "돈과 조건": 현재 구매가(구성 한 줄 포함) · 계약금 %·1차 정액 · 중도금 % · "청약 전 꼭 볼 조건" 상자(전매 종료·거주의무·재당첨 제한·규제지역·분양가상한제·특별공급/일반공급 세대수). 3단 "점수·분류": 종합 점수·순위·판정 범위·포함 분류 | `pages/complex/ComplexHeader.tsx`, 새 `pages/complex/KeyFacts.tsx`, `ko.json`, 테스트 | 상 | M | R3·R5(모든 값 FactCell + 라벨), D7(D±, 확인 불가 사유), R4(공고 값만, 해석 문장 금지) |
| 12 | G2 | 첫 뷰포트에 단지가 3행만 보인다. 이름 열이 좁아 4~5줄로 접히고 접수 열은 약 300px 넓다. 계약금 열은 기본 숨김이다 (§2 G2, ours-g2-complexes-desktop-rea) | C1 강한(큰 숫자 하나), B1 강한(상태 + 다음 일정), D4 검증된 | 기본 열을 단지(생활권은 이름 아래 회색 줄) · 접수(짧은 상태 + 사유는 작은 글씨 줄바꿈) · 현재 구매가 · 계약금 % · 전매 종료 · 입주 · 가격 갭 · 종합 점수로 둔다. 이름 열에 최소 폭을 주고 접수 열은 줄인다. `마지막 변경`은 기본 숨김으로 옮긴다 | `pages/complexes/ComplexTable.tsx`(DEFAULT_HIDDEN·열 순서·폭), `ko.json` | 상 | M | R8-JITTER의 행 실측·범위 히스테리시스를 깨지 않는다(머지 뒤 작업, renderCost·jitter e2e 유지), 열 선택 저장 키 호환 |
| 13 | G2 (모바일) | 표가 `단지·생활권·접수` 3열만 보인다. 가격·전매·점수가 하나도 안 보인다 (§2 G2 모바일, ours-g2-complexes-mobile) | J1 검증된, J2 검증된, B1 강한 | ≤768px에서는 표 대신 카드 목록을 그린다. 카드 = 생활권(회색) → 단지명 → 접수 상태 + 다음 일정 D-n → 현재 구매가 범위 / 전매 종료 / 계약금 % 한 줄. 라벨은 그대로 둔다. 비교 체크는 숨긴다(읽기 전용). 필터는 단지명 1칸 + 펼침 | 새 `pages/complexes/ComplexCards.tsx`, `pages/complexes/index.tsx`, e2e 모바일 | 상 | M | D7 모바일 읽기 전용, R5, A12 |
| 14 | 전 화면 | 설명 없는 용어가 화면마다 15~30개다(G1: 판정 대상·입주 피크·rerank, G2: 택지유형·포함 분류·판정 범위·가격 갭, G3: 전매·무순위·임의공급·해당지역·△ 등) (§2 각 화면 "설명 없는 용어") | F1 강한, F2 강한, F3 강한 | 용어 컴포넌트 `Term`(용어 + ⓘ → 한 줄 정의 팝오버 + "용어 모음에서 보기")과 용어 모음 페이지 `/glossary`를 만든다. 정의는 05-persona §7의 39개를 검수해서 쓴다(30-proposal §7) | 새 `components/Term.tsx`, 새 `pages/glossary/`, `routes.tsx`, `layout/Header.tsx`, `ko.json`(glossary.*) | 상 | M | A12(문구는 ko.json), R4(정의에 권유·판단 금지), 제도 수치는 넣지 않는다 |
| 15 | G1 | 초보에게 가장 쓸모 있는 캘린더(중도금·계약·전매 만료)가 `데이터·운영` 맨 아래에 있다. 청약 접수일은 캘린더에 없다 (§2 G7, §5-1, ours-g7-ops-desktop-rea) | E2 강한, B2 검증된 | G1 2단에 "다가오는 일정(4주)" 블록을 둔다. 단계 텍스트 표식(접수·발표·계약·중도금·전매 만료) + 날짜 + D-n + 단지 링크 5건 + "전체 일정"(G7 캘린더로) 링크. 데이터는 기존 캘린더 API를 쓴다. 접수일이 없으면 블록 머리에 "청약 접수일은 아직 일정에 없습니다" 사유를 적는다(요청 Q3) | `pages/dashboard/index.tsx`, `api/hooks.ts`(기존 훅 재사용), `ko.json` | 상 | M | D10-7(공유 토큰은 /ops 불가 → 블록에 사유 표시), R5 |
| 16 | G1 | TOP 카드가 `종합 5.50 · +10% 확률 53% · rerank 변화 0.51`만 보인다. "얼마·언제 팔 수 있나·주변 대비"가 없다 (§2 G1 3초 테스트 2번, ours-g1-dashboard-desktop-rea) | C1 강한, B1 강한 | 카드 = 이름 → 접수 상태 → 현재 구매가 범위 → 전매 종료 D-n → 가격 갭 → (작게) 종합 점수·순위. ScoreRow에 가격·전매·갭이 없으므로 같은 스냅샷 목록 API(`ComplexRow`) 값을 complex_id로 붙여 쓴다(계산 없음). WP5가 ScoreRow를 넓히면(요청 Q7) 그쪽으로 바꾼다 | `pages/dashboard/index.tsx`, `api/hooks.ts` | 상 | M | R4(값 계산 금지 — 조인만), D10-1(점수·순위는 저장값, 사실은 같은 리비전) |
| 17 | G3 | 헤더 `5억 9,850만원`을 누르면 출처 값이 `579,000,000`이다. 화면값은 "공급가 + 발코니"인데 그 설명이 가격표 탭에만 있다 (§2 G3 표시값 ≠ 출처값, ours-g3-detail-32-provenance-desktop) | C2 강한 | 머리 가격 바로 아래에 "구성: 대표 층 공급가 + 발코니 확장 + 필수 옵션" 한 줄을 둔다(기존 `price.composition` 문구 재사용). 출처 패널에도 "화면값은 아래 출처값에 발코니·옵션을 더한 값" 한 줄을 둔다 | `pages/complex/ComplexHeader.tsx`, `components/ProvenancePanel.tsx`, `ko.json` | 중 | S | R3, R5 |
| 18 | G3 | 가격표 `필수 옵션` 칸에 공고 고지문 전문이 매 행 반복돼 표 폭의 1/3을 차지한다 (§2 G3 가격표, ours-g3-detail-32-desktop-rea) | D4 검증된(각주 1회) | 같은 고지문이 여러 행에 반복되면 표 아래 각주 ①로 한 번만 보이고 셀에는 "①"만 둔다(문자열 같음 비교 — 판단 아님). 원인 수정은 요청 Q2 | `pages/complex/tabs.tsx`(PriceTab) | 중 | S | R5(문구 삭제 아님, 위치만) |
| 19 | 헤더(모바일) | 상황 토글이 `기`, `A 가점 높`처럼 잘린다. 메뉴 7개가 넘쳐 `데이터·운`에서 잘린다. 운영 화면이 같은 무게로 노출된다 (§1, ours-g1-dashboard-mobile) | J3 검증된 | 모바일(≤768px)에서는 상황을 `<select>` 하나로 바꾸고, 메뉴는 지원 화면(홈·단지 리스트)만 남긴다. D7상 나머지 화면은 모바일 미지원이다. 데스크톱 메뉴는 결정 12에 따른다 | `layout/Header.tsx`, `components/ScenarioToggle.tsx`, `ko.json` | 중 | S | D7 모바일 정책 |
| 20 | G1 | `통합 TOP 5` 제목인데 카드가 3장이다. 왜 3장인지 설명이 없다 (§2 G1, ours-g1-dashboard-desktop-rea) | I1 강한(이유 문장) | 제목을 "종합 점수 상위 단지"로 바꾸고, 5장보다 적으면 "점수가 있는 단지가 {n}곳뿐입니다(나머지는 확인 불가·참고 후보)" 한 줄을 붙인다. n은 API 행 수를 센 메타 값이다 | `pages/dashboard/index.tsx`, `ko.json` | 중 | S | D25-3(MetaValue 개수), R4 |
| 21 | 출처 패널 | 패널 첫 줄이 내부 필드명 `complex_type · floor_sample_price_won`이다. 원문 발췌가 열 이름 없는 숫자 줄이다 (§2 G3 출처 패널, ours-g3-detail-32-provenance-desktop) | F4 검증된 | 첫 줄을 쉬운 필드명("대표 층 공급가 · 타입 84C")으로 바꾸고, 원래 필드명은 작은 회색 글자로 남긴다. 발췌 위에 "공고문 표의 한 줄입니다(열 이름은 원문 보기에서)" 안내를 둔다 | `components/ProvenancePanel.tsx`, `ko.json`(provenance.fieldName.*) | 중 | S | R5(필드명 삭제 아님) |
| 22 | G8 | 보고서가 없을 때 `보고서 없음`만 나온다. `스냅샷`, `diff`, `리비전` 같은 개발 용어가 그대로 노출된다 (§2 G8, ours-g8-reports-desktop) | I1 강한 | 빈 상태에 "보고서에는 무엇이 들어가나(요약·단지 표·근거·부록) · 만드는 법(기준일 고르고 생성 버튼) · 걸리는 시간은 작업 진행에서 확인"을 적는다. 라벨은 "기준 스냅샷" → "기준일(리비전)", "비교 스냅샷(diff)" → "이전 기준일과 비교(선택)"으로 바꾼다 | `pages/reports/index.tsx`, `ko.json`(page.G8.*) | 중 | S | R5 |
| 23 | G3 | `판정기 로그` 탭에 `#851 classify … jev-1.13.0 280ms` 같은 운영 로그가 보인다. 초보 탭 줄과 같은 무게다 (§2 G3 tab7, ours-g3-detail-32-tab7-desktop) | E1 강한(탭 3~6개 권장, 13개 반례) | 탭을 `근거 원문` 안의 접힌 구획 "판정 기록(운영자용)"으로 옮긴다(1클릭 유지). 결정 1에 따라 다른 탭 묶기도 함께 정한다 | `pages/complex/index.tsx`, `pages/complex/ProvenanceTab.tsx` | 중 | M | R5(로그는 1클릭), 해시 `#judgments` 호환 |
| 24 | G2 | 하단 고정 `비교 트레이`가 표의 마지막 보이는 행을 덮는다. 표가 자기 세로 스크롤을 가져 스크롤바가 2개다 (§2 G2, ours-g2-complexes-desktop-rea) | — (결함 수정) | 트레이 높이만큼 표 컨테이너 아래 여백을 준다 | `pages/complexes/index.tsx` | 하 | S | R8-JITTER와 충돌 없게 |

범위 밖에서 발견한 것(개선 대상 G1·G2·G3·G8이 아님 — 기록만): G6 `입주 물량` 범례가 생활권 내부 ID(`la_1~la_10`)다, `미분양 추이` 범위가 `인천 부평구`로 표기되고 `차트 준비 중`에 머문다, G7 문서 높이가 모바일 147,936px다(ours-g6-market-desktop-rea, ours-g7-ops-mobile). G6 범례는 요청 Q5에 함께 넣는다.

### 2-2 요청 — 백엔드·API·계약·데이터를 바꿔야 하는 것 (UI가 직접 만들지 않음)

메타 프롬프트 §3-2 규칙 4: 프론트는 판정을 만들지 않고 새 숫자를 계산하지 않는다. 아래는 화면에 꼭 필요하지만 API에 값이 없거나 값 자체가 이상한 것이다. 계약 변경이 따르면 WP0 승인이 필요하다.

| # | 대상(주인 WP) | 지금 문제(근거) | 요청 내용 | 화면 쪽 임시 처리 | 효과 |
|---|---|---|---|---|---|
| Q1 | WP4(analysis) + WP5(api), 계약 | "계약할 때 현금 얼마"가 원 금액으로 없다. G3에는 `계약금 5%`와 1차 정액만 있다. 비교 화면 `TermsRow.down_payment_won`은 이미 산술(§6-7 `P_mid × D`)로 계산된다 (§4 Q2 ×, ours-g3-detail-32-tab1-desktop) | ① `ComplexDetail`(price 또는 payment 현재 행)과 `ComplexRow`에 `down_payment_won`(추정·산술, TermsRow와 같은 식·같은 출처 id)을 넣는다. ② 중도금·잔금 원 금액(`P_mid × interim_pct`, `× balance_pct`)은 RA §6에 없는 식이다. 넣을지 WP4·CEO가 결정한다(넣으면 §6 추가 + 라벨 '추정(산술)') | 계약금 % · 1차 정액만 보인다. 원 금액 칸은 "확인 불가(계산값 미제공)"로 두고, G4 조건 표 링크를 둔다. 프론트에서 곱하지 않는다 | 상 |
| Q2 | WP1a(notice_pdf) / WP2(normalize) | 32번 중도금 일정이 `2회차` 1행뿐이다(원문은 6회). 잔금 비율은 "해석 실패"다. 가격표 `대표 층`이 대부분 `1층`이고, `필수 옵션` 칸에 고지문 전문이 들어 있다 (00-baseline §6, ours-g3-detail-32-tab1-desktop, ours-g3-detail-32-desktop-rea) | 공고문 납부 표 파서(중도금 회차·잔금%·대표 층 선택·필수 옵션 칸 분리)를 확인한다. 회귀 픽스처는 32번 원문으로 만든다 | 있는 그대로 보인다(갭 #18 각주화만) | 상 |
| Q3 | WP1a / WP2 (apply_dates), WP7(scheduler 캘린더) | 접수 기간·마감일이 화면 어디에도 없다. G7 캘린더 종류는 `만료·중도금·계약`뿐이고 **청약 접수일이 없다** (§4 Q1, ours-g7-ops-desktop-rea). 계약에는 `Complex.apply_dates`(ScheduleItem[])가 이미 있다 | ① 실데이터에서 `apply_dates`(특공·1순위·2순위 시작·끝, 해당/기타)가 채워지는지 확인하고 빠지면 채운다. ② 캘린더(체크리스트·캘린더 API)에 "청약 접수"·"당첨자 발표" 항목을 추가한다 | `apply_dates`가 비면 "확인 불가(공고 일정 미수집)"으로 보인다 | 상 |
| Q4 | WP1a(applyhome 경쟁률) + WP5, 계약 | 경쟁률이 G3 3번째 탭에만 있다. 목록·비교에 경쟁률이 없다. 가점 정보가 전혀 없다. 청약홈 경쟁률 팝업에는 당첨가점 최저·최고·평균이 있다(applyhome-competition-rea-desktop) (§4 Q5·Q6) | ① 청약홈 경쟁률 페이지의 **당첨가점(최저·최고·평균, 가점제 당첨자만)**을 수집해 `Competition`에 넣는다. ② `ComplexRow`·`ScoreRow`에 "1순위 해당지역 최고 경쟁률·미달 여부" 요약을 넣는다. 요약 규칙은 WP4가 정한다(UI가 집계하지 않는다) | G3 경쟁률 표 위로 올림(갭 #6). 가점은 "제공하지 않음 — 청약홈 경쟁률에서 확인" + 링크 | 상 |
| Q5 | WP5(api) / WP4, 계약 | 내부 이름이 샌다. 변경 피드에 `official_popup_hash` 원문 해시가 보인다. 라벨 사유가 지역 합 나열로 길다(`확인됨(인천 검단구 737·…합)`). 확인 불가 사유가 자유 문자열이라 쉬운 말 매핑을 문자열 비교로 해야 한다. G6 범례가 `la_n`이다 (§5-5, ours-g1-dashboard-desktop-rea, ours-g6-market-desktop-rea) | ① `Fact.reason`과 함께 안정된 `reason_code`(enum: parse_failed·unresolved·unjudged·not_collected·not_published·…)를 준다. ② 집계 라벨 사유는 짧게("지역 합계")로 하고 내역은 출처 행에 둔다. ③ 해시 변경 이벤트에 사람이 읽는 `summary`를 둔다(또는 해시 필드는 `old_text/new_text` 대신 길이·앞 8자만). ④ `Market.supply[]`에 `living_area_name`을 넣는다 | 알려진 사유 문자열 매핑(갭 #10), 해시 접기(갭 #4), 라벨 줄바꿈(갭 #5) | 상 |
| Q6 | WP4 / WP5 | G3 `시세 비교` 탭에 `가격 갭` 이름이 두 값(8.1%와 2.98)으로 나온다 (00-baseline §6, ours-g3-detail-32-tab4-desktop) | 2.98이 성분 점수 `s_gap`인지, 다른 필드인지 확인한다. 성분이면 API 필드명·출처 kind를 `score_component`로 구분할 수 있게 한다 | "가격 갭 점수(0~10)"로 이름만 바꾼다(갭 #7) | 중 |
| Q7 | WP5(api), 계약 | G1 TOP 카드에 "얼마·언제 팔 수 있나·주변 대비"를 그리려면 `ScoreRow`에 그 값이 없다 | `ScoreRow`(dashboard top5·compare rows)에 `price_low/high`, `resale_end`, `gap_pct`, `move_in_ym` Fact를 추가한다(같은 리비전 사실, 출처 id 동일) | 같은 리비전 목록 API 행을 complex_id로 붙인다(갭 #16) | 중 |
| Q8 | WP3(judge) / WP2 + WP5, 계약 | 32번 "접수 가능"은 수집 메모상 **무순위·선착순 계약 안내문** 기반이다. 화면에는 그 구분이 없다. `Intake`에 공급 종류 필드가 없다 (§2 G3 3초 테스트 1번) | `Intake`에 "어느 공급의 접수인가"(`supply_kind`: 본청약 특공·1순위·2순위 / 무순위 / 임의 / 선착순 / 미상)를 둔다. 분류가 필요하면 판정기 classify로 한다(규칙 3) | 현재 적용 공고 종류(`payment[].notice_kind`)만 "현재 적용 공고: 무순위"로 보인다. 접수와 직접 연결하지 않는다 | 상 |
| Q9 | WP5(api) | G2 기본 정렬이 종합 점수인데 101곳 중 점수가 있는 단지는 3곳이다 (§2 G2) | 결정 4에서 "접수 상태 우선"을 고르면 정렬 키 `intake`(가능→미정→확인 불가→불가, 같은 상태 안에서는 마감 임박순)를 추가한다 | "지금 접수 가능만" 칩(갭 #9) | 중 |
| Q10 | WP4(analysis) + WP5, 계약 — CEO 결정 | 신혼·출산 가구(P2)의 경로는 특별공급인데 고정 시나리오에 특공 축이 없다(05-persona §5 P2) | 결정 8에 따른다. 추가한다면 특공 시나리오 가중치·요건(§6-7)을 WP4가 정의한다 | `units_special` 세대수 + "특별공급 자격·소득 기준은 공고문 확인" 링크만 보인다 | 중 |
| Q11 | WP8(reports) | 보고서 첫 장·표 크기·용어 문제(산출물이 없어 직접 진단 불가 — §2 G8). 장 제목 `§8 종합 추천`이 "추천" 단어를 쓴다 | 30-proposal §11-2 **WP8 요청서 초안** | — | 상 |
| Q12 | WP1b(rtms) — 확인 요청 | 국토부 공개시스템 이용 조건이 자동 수집을 금지한다(10-molit 노트, 근거로는 쓰지 않음) | rtms 수집기가 화면 스크래핑이 아니라 공공데이터포털 API를 쓰는지 확인한다 | — | 하(UI 무관, 위험 확인) |

---

## 3. 요약

- 강한 패턴은 15개다(A1·A3·A4·B1·C1·C2·D2·E1·E2·F1·F2·F3·G1·G2·I1). 검증된 패턴은 24개, 참고는 7개다.
- 우리 화면과 가장 크게 어긋나는 강한 패턴은 다음 세 가지다.
  - A1·A3 상세 1단(상태·일정·원문·조건 상자): 우리는 조건이 7번째 탭에 있다.
  - I1 빈 상태 사유를 사용자 말로: 우리 사유는 "해석 실패" 같은 내부어다.
  - C1 큰 숫자 하나: 우리는 모든 숫자에 같은 무게의 배지가 붙는다.
- 프론트만으로 고칠 수 있는 행은 24개다. 그중 효과 상·품 S가 10개(#1~#10), 효과 상·품 M이 6개(#11~#16)다.
- 화면만으로 답할 수 없는 초보 질문이 둘 있다. "계약할 때 현금 얼마(원)"(Q1)와 "경쟁률·가점"(Q4)이다. 이 둘은 백엔드 요청 없이는 끝까지 답할 수 없다.
