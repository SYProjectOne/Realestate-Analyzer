# WP1b 수집 어댑터 (공식 홈페이지·실거래·통계·뉴스·참조 코드) — 작업 지시

소유: `backend/app/collectors/{official_site,rtms,stats,news,reference}/`, `backend/tests/collectors/{official_site,rtms,stats,news,reference}/`, `contracts/fixtures/reference/`(참조 파일 사본). 공용 헬퍼는 각자 패키지 안에(`collectors/common/` 만들지 말 것).
참조: RA §3 `raw_document`·`intake_status`·`rtms_trade`·`supply`·`unsold` 행, §4-3 `Collector`, §5 WP1 카드, §9 T3·T17; DECISIONS D2-1(참조 테이블·세대수), D1 #5·#6(키 없음).

## 할 일
1. `official_site/`: 단지 공식 홈페이지 → httpx → 실패·동적이면 Playwright chromium 렌더 → 스크린샷 PNG + DOM 텍스트 + 팝업 이미지 해시(변경 감지는 WP7이 씀). 403·DNS 실패도 `RawDocument(http_status=…)`. 접수 상태 후보 텍스트를 메타로 남긴다(상태 판단은 WP2 파서/판정기).
2. `rtms/`: 국토부 아파트 매매 실거래 Open API(공공데이터포털, `DATA_GO_KR_KEY`; `LAWD_CD` 5자리 × 월). **키가 없으면**: 국토부 실거래가 공개시스템(rt.molit.go.kr) 웹 조회로 키 없이 공식 데이터를 받을 수 있는지 조사해 가능하면 구현(source=`official_web`, 공식 원본이므로 라벨 확인됨) — robots·이용약관 확인 결과 보고. 안 되면 재가공 폴백은 **인터페이스만**(RA). 해제(cancelled) 플래그 보존.
3. `stats/`: (a) 미분양 월별(국토부 통계누리 등 키 없는 공개 경로 조사; 합계·준공 후), (b) 입주물량 집계(공개 원천 조사; 없으면 "추정 집계" 인터페이스), (c) **행안부 주민등록 인구 및 세대현황**(jumin.mois.go.kr, 키 불필요) 행정동별 세대수 → `household_stat` 적재용.
4. `news/`: 네이버 검색 API 형식 — `NEWS_API_KEY` 없으면 비활성(빈 결과 + 상태 "비활성(키 없음)"). URL·제목·발췌만.
5. `reference/`: 행정표준코드관리시스템 **법정동코드 전체자료**, 행안부 **행정동 코드**·**행정동↔법정동 매핑**(jscode) 다운로드 → 파싱 → `legal_dong`·`admin_dong`·`admin_legal_map` 적재 함수. 다운로드 실패 대비 최신 사본을 `contracts/fixtures/reference/`에 저장하고 폴백. 2026-07 인천 검단구 분구 반영 여부 확인·보고.
6. 공통: 멱등(sha256), 실패도 행, `app.core.http`만, 실제 사이트 녹화 → respx 오프라인 테스트, 실제 접속은 `@pytest.mark.live`.

## 완료 기준
- [ ] collector마다 녹화 픽스처 테스트, 2회 실행 → `raw_document` 증가 0
- [ ] 403 픽스처 → http_status=403 행(T3), DNS 실패 → 행
- [ ] 팝업 렌더 테스트에서 PNG와 해시 생성(로컬 HTML 페이지를 Playwright로)
- [ ] rtms: Open API XML 픽스처 파싱 + 키 없는 경로 동작
- [ ] reference: 사본 파일로 legal_dong 적재, "연수구"·"김포시" 시군구 코드 조회
- [ ] 주민등록 세대수 파싱
- [ ] news: 키 없으면 비활성 상태
