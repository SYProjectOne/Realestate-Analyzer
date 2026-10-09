## WP4 (R1)
1. score_inputs.json LivingAreaScoreInput: unsold_scope_codes: string[] (생활권↔미분양 시군구 매핑). 영향 WP7, WP4. → 승인 예정
2. score_inputs.json ComplexScoreInput: intake_checked_at. 영향 WP7, WP4. → 승인 예정
3. ComplexScoreInput: 공고 필드별 라벨(계약금·전매·거주의무). 영향 WP7, WP4. → 승인 예정
## WP3 제안 (WP0 처리)
- pyproject mcp>=2,<3 고정 → 승인
- adapter_version에 응답 model(jev-1.13.0 등) 포함 → 승인(D6 보강: 모델 바뀌면 재판정)
- Settings에 JUDGE_CALL_TIMEOUT_S=120, JUDGE_START_TIMEOUT_S=300 → 승인
- decide tie: WP4 score.decide_outcome이 원본, pipeline.p8_decide는 WP4 함수 호출하도록 R2(WP7)에서 정리
## WP9 (R1)
1. fixtures README/_meta adapter_version="mock-fixture-2026-10-08" 명시 + _index.json 설명 → 승인
2. judgment_envelope ClassifyResult items[] 배치 분류 공식화 → 승인
3. AuditItem p_wrong nullable → 승인
4. contracts/examples 법정동 2826011600(폐지 불노동) → 마전동 2826011300 수정 → 승인(WP0 직접)
5. CI 매트릭스에 fixtures_contract 추가 → WP0 직접
- 주의: WP9 법정동 사본은 gist 출처(비공식). WP1b 공식 사본 머지 후 교체할 것.
## WP2 (R1)
1. field_candidate entity에 intake_status 추가 → 승인
2. field_candidate observed_on(공고일) → 승인
3. field_provenance value_norm 컬럼 → 승인(마이그레이션 0002)
4. complex_type notice_type_code(공고상 주택형 '084.9582') → 승인(0002)
5. payment_terms base_price_won(임의공급 공고별 기준가, 84㎡ 판정 타입) → 승인(0002) — 또는 supply_price 테이블. 단순하게 payment_terms에 price_by_type json 추가
- core/db.py: sqlite begin 이벤트(SAVEPOINT 문제) → WP0 직접
- 미완: 16단지 중 13단지 가격 일치(카드 기준 8 충족, RA 기준 16). needs_extract 4건은 판정기 extract로 넘김 — 설계상 정상
## WP1b (R1)
1. raw_document.meta json 컬럼 (0002) → 승인
2. examples/region + 픽스처 region: 28260(서구, 폐지) → 28290(검단구) (+ 법정동 코드도 공식 사본 기준으로 WP9 픽스처 재생성) → 승인
3. .env.example NEWS_API_KEY=<ClientID>:<Secret> → WP0 직접
- core.http: FetchResult에 robots 실패 원인 / 키 인증 공식 API(data.go.kr, openapi.naver.com)는 robots 예외(크롤링 아님, 약관이 규율) → WP0 직접
- 사용자에게: rt.molit 자동수집 약관 금지 → 실거래는 DATA_GO_KR_KEY 필요(무료). 없으면 gap·benchmark 확인 불가
## WP1a (R1)
1. raw_document error_text 값 목록 명시(scan, ocr, scan_partial:<p>, ocr_partial:<p>, pdf_parse:…, not_pdf, DNS, timeout, connect, robots) → 승인
2. 표 JSON 위치: table_path 필드 신설(0002) → 승인
3. region.applyhome_query 키 정의: from_ym, areas{sido_code: 약칭} → 승인
- pyproject optional ocr = rapidocr>=3.10,<4 + onnxruntime>=1.18 → WP0 승인(D5 채택: RapidOCR PP-OCRv5 korean)
- region.bootstrap 최초 실행 ~15분 예상(일일은 10분 내)

## R2 (WP0 처리 대기)
- WP8: Dockerfile.worker에 echarts.min.js 복사 + REPORT_ECHARTS_JS → Settings로 → 승인
- WP8: tests/reports/_seed.py → WP5 devseed로 교체 (R3)
- "남은 contradicted" 정의 = 분할 자식 없는 contradicted. WP7 publish 검사와 통일 확인 (R3)
