# tests/normalize/fixtures (WP2)

| 경로 | 출처 | 비고 |
| --- | --- | --- |
| `notice/*.txt` | 청약홈 첨부 입주자모집공고문 PDF(실제, 2026-10-09 `app.core.http`로 수집) → pdfplumber 텍스트 → **발췌** | 머리 표·단지 유의사항 핵심 문장·공급대상/공급금액 표·발코니 표·중도금 이자/선택품목 문장만 남겼다. 생략 구간은 `[…]`. 원본 URL·PDF sha256·남긴 줄 범위는 `notice/manifest.json` |
| `notice/expected_complex_types.json` | 위 발췌를 사람이 확인한 기대값(원 단위) | 타입별 최고가·최저층 공급금액·발코니·전용면적·세대수. 단지별 최고가는 `docs/source/incheon_gimpo_report.md`(§4·§12-2-2)의 '최고가(만원)'와도 대조한다(`test_notice_prices.py` 의 `REPORT_MAX_MANWON`) |
| `applyhome/*.html` | 청약홈 상세(`selectAPTLttotPblancDetail.do`)·경쟁률(`selectAPTCompetitionPopup.do`) 팝업, APT 분양정보 목록 표(실제, 2026-10-09 수집) | 목록은 결과 `<table>`만 발췌. 줄바꿈 LF로 정규화 |
| `reference/*.csv` | **테스트용 소형 참조표(가상 포함)** | 법정동·행정동 이름은 실제 지명이지만 코드·매핑·세대수 일부는 형식 예시용 가상값이다. 검단구(28265)는 2026-07 분구 이후 새 코드를 흉내 낸 가상 코드이고, 옛 서구 코드와 함께 둬서 D3(둘 다 후보) 경우를 만든다 |
| `rtms/*.xml` | **형식 예시(가상)** — 국토부 아파트 매매 실거래가 Open API 응답 모양 | API 키가 없어(D1-5) 실제 응답을 받지 못했다. 태그 이름은 공개 명세(신규 영문 태그) 그대로, 값은 가상 |
| `stats/*.csv` | **형식 예시(가상)** — 미분양주택현황 표 모양 | 값은 가상 |
| `official_site/*.txt` | **형식 예시(가상)** — 공식 홈페이지 DOM 텍스트 모양 | 문구는 보고서(§4·§12-2-3)에 인용된 팝업 문구를 옮겼다 |
| `r9_parse/notice_*.txt` | 청약홈 첨부 입주자모집공고문 PDF(실제, 운영 수집 2026-10-13) → pdfplumber 텍스트 → **발췌**(R9-PARSE Q2·G7 중복) | 남긴 줄 범위·원문 텍스트 sha256 은 `r9_parse/manifest.json`. 납부 계좌 줄은 뺐다 |
| `r9_parse/api_*.json` | 청약홈 공식 API 응답(실제, 운영 수집 2026-10-13, 키 없음) 원문 그대로(R9-PARSE Q3·Q4) | 상세·주택형·경쟁률 |
| `r9_parse/web_competition_*.html` | 청약홈 웹 경쟁률 팝업(실제, 2026-10-14 `app.core.http` 로 수집) — 당첨가점 최저·최고·평균(R9-PARSE Q4) | 줄바꿈 LF로 정규화 |

T5(해링턴 1,573 vs 1,769)는 RA §9 표의 합성 케이스라 원문에 그대로 없다. 테스트가 실제 청약홈 상세(670세대)와
실제 공고문 발췌를 읽어 공급규모 문구만 RA 값으로 바꿔 쓴다(`test_store.py`).
