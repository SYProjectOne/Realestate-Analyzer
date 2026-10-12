# R4-FIX — 실데이터 결함 수정 테스트·수정 전 실패 확인 (2026-10-12)

원문: `docs/design/wp/R4_RESULT.md` §8·§9, 결정 `docs/design/DECISIONS.md` D18. 브랜치 `wp/r4-fix`(main `8b659a4` 기준, 뒤에 main `ec6ae0b`(CORE7, 계약 `2026-10-09.14`) 병합 — 충돌 `scheduler/runner.py` 1곳), 계약 버전은 올리지 않았다(.14 그대로, 변경 요청은 §6 = .15 초안).

**방법.** 결함마다 테스트를 먼저 쓰고, `git checkout 8b659a4 -- backend/app`(수정 전 앱 코드)로 같은 테스트를 돌려 실패를 확인한 뒤 고쳤다
(아래 "수정 전" 열은 그 실행의 실제 출력 줄). 실데이터 재현은 R4 원문(scratchpad `r4/raw`, 공개 분양 정보)을 줄여 녹화 픽스처로 넣고
재생했다 — 키·토큰 검사(`serviceKey`·`authorization`·`bearer`·`api_key`·`token=` 정규식, URL 포함) 통과분만 넣었다. 실제 판정기·외부 사이트는 부르지 않았다.

## 1. 결함별 수정·테스트·수정 전 실패

| 결함 · 결정 | 수정 | 테스트 | 수정 전(8b659a4) 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| **C1** D18-1 고정 모델 | `judge/base.py`: 캐시 키 = 서버 버전 + **모델 호출 응답(provider ≠ none)이 알려 준 모델**. provider none(로컬 단락 `jev-latest`) 무시. 실행(어댑터 수명) 중 키 불변·replay 없음, 모델 변경은 `observed_version`/`model_change_pending` → 파이프라인이 change_event 후 어댑터를 버려 다음 실행이 새 키. 빈 DB 첫 모델 확정 시 접미 없는 행을 새 hash 로 옮김. 시작 모델 = 마지막 모델 호출 응답의 `output_json.model` | `tests/judge/test_r4_fix_c1.py` (6) | `test_stdio_provider_none_mixed_second_run_sends_no_tools_call`: **`2회차 실제 tools/call 이 0 이어야 한다`**(가짜 stdio MCP 서버 쪽 계수 — R4 프록시와 같은 자리) · `…one_version…`: `고정 모델 하나(provider none 의 model 무시)` · `…learns_model…`: `'0.2.0+jev-mc....1+jev-latest' == '0.2.0+jev-mcp@0.14.1'` · `…model_change_keeps_key…`: `실행 중 키는 그대로` | 통과 |
| C1 파이프라인 | 같음 + `scheduler/pipeline.py` CountingCaller | `tests/scheduler/test_r4_fix_c1_jobs.py::test_second_rejudge_sends_no_tools_call_with_local_extract`, `::test_pipeline_model_change_event_and_next_run_rejudges` | **`2회차 tools/call 2건: ['jev_classify', 'jev_noul']`**(행·통계는 0 — R4 의 숨은 호출 재현) · `모델이 바뀐 실행은 옛 키 그대로(D18-1)` | 통과 |
| **C1** D18-2 tools/call 계수 | `judge/base.py` `CallMeter`(전송 직전 계수), `SchedulerContext.judge_meter`(어댑터를 버려도 이어짐), `runner.with_tools_calls`(잡 stats `tools_calls`·`tools_calls_by_tool`, JevMcpAdapter 잡은 최상위 `judge_calls` = tools_calls), CountingCaller 실제 호출 = 전송 수 | `test_r4_fix_c1.py::test_meter_counts_transport_calls_only`, `::test_counting_caller_counts_hidden_calls` | `ImportError: cannot import name 'CallMeter'` (계수기 없음) | 통과 |
| C1 G7 `real_calls` | `api/routers/ops.py`: real_calls = max(blocked 제외 행 수, 잡 `tools_calls` 합), 도구별도 같음 | `tests/api/test_r4_fix_ops.py` (2) | **`실제 호출 = 보낸 tools/call 수(행 수가 아니라)`** | 통과 |
| **m2** 수집 단계 판정 집계 | 위 runner 계수(잡 전체) | `test_r4_fix_c1_jobs.py::test_m2_collect_stage_screen_counts_in_job_stats` | `assert (None == 1)` — 수집 단계 호재 screen 이 잡 stats 에 없음 | 통과 |
| **m1** smoke `JEV_MCP_CMD` | `tests/judge/test_live.py`: import 시점 환경변수(`test_settings` 가 지우기 전) 사용 | `test_live.py::test_live_cmd_respects_env` | (테스트 파일 안 함수 — 수정 전에는 함수가 없었다. R4 출력 `"cmd": "npx -y @jkudish/jev-mcp@latest"` 가 근거) | 통과 |
| **C2** D18-3 실거래 법정동 | `collectors/rtms/parse.py` `sgg_code`, `collectors/rtms/legal.py`(LegalDongIndex: 같은 시군구 활성 행 + 읍면동[+리], 실패·모호 NULL+사유, `repair_legal_dong_codes`·CLI), `collector.load_trades`(매칭·매칭률 stats·거래 키 동 이름 우선·NULL 행 채움·적재 끝 보정), `scheduler/collect.py` `loaded.rtms_legal_dong`, `assemble` `rtms_backfill.legal_dong` | `tests/collectors/rtms/test_r4_fix_c2.py` (6) + 실제 응답 녹화 2개 | `'TradeRecord' object has no attribute 'sgg_code'` · **`오류동은 시군구 코드(28290)로 검단구 — 계양구 오류동 아님`**(코드 NULL) · `No module named 'app.collectors.rtms.legal'` ×2 · **`assert 8 == 0`**(재적재해도 NULL 그대로) | 통과 |
| **C3·M1·M3** D18-4 잔여 공고 | `normalize/store.py`: 잔여 공고 번호는 자기 행 전에 원 단지 탐색(`_remnant_target`: 실행 연결 `links` → 그 공고번호의 납부 조건·잔여 이력 행 → 같은 블록), 공고문 인용 판정은 원문 주소 번호 기준, 인용 원 단지는 자리표시 이름(번호) + 잔여 공고 단지 단위 값 미기록, 자리표시는 청약홈 잔여 공고 이름(회차 괄호 뗌)으로, 공식 홈페이지는 원 단지에 없을 때만, 입주월 후보는 원문 순서와 무관하게 함께 resolve. `normalize/notice_parser.py`: **제목 줄 이름 후보 삭제**, 종류 = 제목 줄 낱말(+ 인용이면 무순위). `scheduler/collect.py`: 저장 순서(일반 공고 → 인용 공고문·일반 공고문 → 잔여 공고 청약홈 원문 → 그 밖 공고문) + 원 공고 다시 받기(`ApplyhomeCollector.fetch_originals`, 공식 API, 같은 URL 성공 원문 재사용). `normalize/remaining.py`: 이력 앵커 = 정규화 연결 우선. `analysis/scope.py`: 사유 `원 공고 미수집`(번호 있고 공고일 없음) — API·보고서·파이프라인 공용 | `tests/scheduler/test_r4_fix_d18_4.py` (5) — R4 원문 재생(그란테르 G5-1·금강펜테리움·레이크 송도 4차·엘리프) | **`잔여 공고 번호로 단지 행: ['2025930054', '2025940301', '2026910139', '2026910203', '2026930020', '2026940079', '2026940173']`** · **`{'(임의공급 4차)', …, '불법행위', …}`**(제목 줄 이름) · `original_calls == []`(원 공고 안 받음) · `cannot import name 'ORIGINAL_MISSING'` · 같은 날 다시 수집에서 단지 값 변화 | 통과 |
| **M5** D18-6 같은 날 daily | 위 D18-4(원문 순서 무관 묶기) + C1(접수 분류 초기화 원인이던 버전 뒤집힘) + 공유 공식 홈페이지 URL(아래) | `tests/scheduler/test_r4_fix_d18_6.py` — R4 원문 재생 bootstrap → 같은 날 collect.daily | **`AssertionError: 2`**(같은 날 daily change_event 2건) | 통과: change_event 0 · rejudge 0 · tools/call 0 · judgment_log 행 0 |
| M5 공유 URL | `collectors/official_site/collector.py`: 돌려주는 원문에 대상 단지 id(원문 행은 sha256 로 하나), 직전 렌더 메타는 URL 로만(단지 무관) | `tests/collectors/official_site/test_r4_fix_shared_url.py` | **`같은 화면이면 같은 URL 의 직전 스크린샷을 재사용(단지와 무관)`** | 통과 |
| **D18-5** 같은 조각 1번 | `scheduler/pipeline.py`: 공고문 조각 판정 입력·purpose = 정규화 본문(줄 공백 정리)·그 해시(`chunk_text`·`chunk_tag`) — 원문 id 대신 | `tests/scheduler/test_r4_fix_d18_5.py` | **`요청 4건(원문 2개) 중 판정기 extract 는 조각마다 1번: 4`** | 통과(2요청 → extract 1 + 캐시 1) |
| **M2** 미분양 출처 | `collectors/stats/unsold.py` `write_unsold_provenance`(합계 = 2082·준공 후 = 5328 원문, URL·확인일·라벨·발췌, 멱등) | `tests/collectors/stats/test_r4_fix_m2_unsold_provenance.py` | **`unsold 1 total 출처 행 없음`** | 통과 |
| **M4** alembic `ENV_FILE` | (D20-1·계약 .15) `contracts/migrations/env.py`: `DATABASE_URL` 이 없고 `ENV_FILE` 이 있으면 앱 설정 URL(못 읽으면 실패). 1차의 `app/migrate.py` 우회는 지웠다 | `tests/contracts/test_r4fix_migrations.py::test_alembic_env_file_fallback` | **`ENV_FILE 이 가리킨 DB 를 마이그레이션해야 한다`**(그리고 `backend/dev.db` 가 조용히 생김 — 확인 뒤 지움) | 통과 |
| **M6** 신설 구 주소 | `normalize/living_area.py` `split_successor`: 주소의 구·동이 **폐지** 행과 맞고 후보 구의 활성 동 이름이 모두 옛 구 폐지 동 이름에 있으면(분구 자식) 그 후보, 여럿이면 지역 법정동으로, 하나일 때만 | `tests/normalize/test_r4_fix_m6_split.py` (3) — R4 legal_dong 실제 행 | **`(None, False, None) == ('2829010800', True, 'la_2')`**(왕길역 아테라 '범위 경계') | 통과(그 밖 2개는 회귀 방지 — 수정 전에도 통과) |
| **m3** 첫 적재 요약 | `normalize/store.py` `first_load`(빈 값 → 값 이벤트를 세기만), `normalize/remaining.py` 같은 규칙, `scheduler/collect.py` region `status='bootstrapping'` 이면 `change_event(region·first_load·info)` 한 줄 | `tests/scheduler/test_r4_fix_m3_first_load.py` (2) | **`첫 적재 빈 값 → 값 이벤트 112건: [('complex','address'), ('complex','apply_dates'), …]`** | 통과(운영 중 새 공고 이벤트는 그대로 — 가드 테스트) |
| **m4** 보고서 ECharts | runbook §10-7 ⑧(`REPORT_ECHARTS_JS`) | — (문서) | — | — |
| **D18-8** 픽스처 단지 4개 | 원인 조사(§3) → D20-1(기본 조회 창 지난 24 + 향후 12개월) · D20-2(공고 전 단지 = 트랙 A 후보) — §7 | §7 | §7 | §7 |

수정 전 실행 기록(원문): scratchpad `r4fix/prefix_c1.txt`·`prefix_c1_jobs.txt`·`prefix_c1_ops.txt`·`prefix_c2.txt`·`prefix_rest.txt`·`prefix_d186.txt`.

## 2. 바뀐 기존 테스트·골든·픽스처와 이유 (CHANGELOG 대신 여기)

| 파일 | 바뀐 것 | 이유 |
| --- | --- | --- |
| `tests/judge/test_cache.py::test_model_change_rejudges` | 모델이 바뀐 **그 실행**은 같은 입력이 캐시, **다음 어댑터**에서 재판정 | D18-1(실행 중 키 불변). 옛 기대(바로 새 키로 재판정)가 C1 의 원인이었다 |
| `tests/normalize/test_notice_terms_archive.py::test_main_notice_terms_and_header` | 공고문 `name` 후보 없음 | D18-4: 제목 줄은 이름 후보가 아니다 |
| `tests/normalize/test_r3_f1b.py::test_c3_…` | 글자 필드 확인을 `name` → `housing_type` | 같은 이유(이름 후보가 없어짐) |
| `tests/scheduler/test_r3_f2.py::test_minor1_…` | 가짜 `store_raw_document` 가 새 키워드 인자(`links`·`first_load`)를 받음 | 저장 함수 시그니처 확장 |
| `tests/judge/fake_jev_server.py` | 설정 `local_tools`(provider none·jev-latest), `model` | C1 재현(실제 JEV 0.14.1 모양) |
| `contracts/fixtures/incheon_gimpo_2026-10-08/judgments_synth/**` (재녹화, `record_synth_judgments.py`) | extract·screen 녹화 파일 이름(hash)이 바뀜, `_meta.counts.screen` 78 → 39 | D18-5: 조각 purpose 가 원문 id 에서 정규화 본문 해시로 — 같은 본문의 조각(두 실행·두 원문)이 한 번만 판정된다. 다른 도구 녹화는 그대로 |
| `contracts/fixtures.sha256.json` | 위 재녹화 반영(`fixture_manifest.py --reason "R4-FIX D18-5 …"`) | 같음 |
| 새 `tests/normalize/fixtures/r4_remnant/` | R4 원문 38건(청약홈 API·웹 상세 30, 공고문 추출 텍스트·표 8 — PDF 바이너리 제외) + 원 공고 상세 3(R4 과거 공고 목록 원문에서 그 행 1개로 줄임) + 원 공고 주택형 2(R4 실제 응답) | D18-4·D18-6·m3 재생. HTML 은 저장소 `.gitattributes` 로 LF 정규화되어 바이트(sha256)가 녹화와 다를 수 있다(내용 동일) |
| 새 `tests/collectors/rtms/fixtures/openapi_trade_{28290,41570}_202609_trim.xml` | R4 실제 매매 응답(umdCd 없음)을 법정동마다 1건으로 줄임(totalCount 맞춤) | D18-3 실제 응답 모양 |

회귀 골든(`expected_scores*.json`)은 바꾸지 않았다.

## 3. D18-8 — 회귀 픽스처 단지 4개가 실제 수집에 빠진 원인 (R4 원문·API 응답 근거)

| 단지 | 원인 | 근거 | 조치 |
| --- | --- | --- | --- |
| 오퍼스 한강 스위첸 (2025000222, 공고 2025-06-27) | **조회 창** — `POST /regions` 는 `applyhome_query={}` 라 기본 창 = 기준월 −10개월(2025-12-01 ~ 2026-11-30, 계약 region.json "없으면 기준월 −10개월"). 공고가 창보다 이르다. 그 무순위(2025910122, 2025-08-11)도 창 밖 | R4 목록 원문(APT·잔여·임의, 인천·경기) 쿼리 `RCRIT_PBLANC_DE::GTE=2025-12-01`; 두 단지는 10년 과거 공고 목록(`applyhome_list/2026-10-12/6f992b8e….json`)에만 있다. 주소 필터(`AreaFilter.matches`)는 둘 다 통과 — 지역 선택·페이지 문제 아님 | 계약 변경 요청(기본 창 −24개월, meta_prompt "지난 24~36개월") + R4 재시험은 runbook §10-7 ③(`from_ym='2024-10'` — 계약 키, 회귀 픽스처 region.json 과 같은 값). 과거 공고 수집(fetch_history)은 입주월 ≤ 기준월만 받아 이 단지들(입주 2028-08)을 채우지 못한다 |
| 해링턴플레이스 풍무 1BL (2025000271, 2025-07-04) | 같음(2BL·3BL 도 같음) | 같음 | 같음 |
| 계양신도시 카이브 유보라 | **공고 전** — 2026-10-12 현재 청약홈 미등록(픽스처도 applyhome_id null·'공고 전'·출처 보도자료). 단지 행은 청약홈 번호로만 생긴다 | R4 인천 APT 목록(최신 공고 2026-10-08)에 없음, 뉴스 원문(`raw/news/…83a49780….json`) 20건 중 9건에만 언급('10월 계양신도시 반도건설 카이브 유보라 1110세대 공급 예정') | **고칠 수 없음(현 설계)**: 공고 예정 단지 수집 경로가 없다. 공고가 올라오면 다음 `collect.daily` 가 받는다(창 끝 = 기준월 +1). 뉴스 → 판정기 → 트랙 A 후보 경로는 설계 결정 필요(제안) |
| 검단 센트레빌 그랑포레 | 같음(공고 전, '이달 검단구 오류동 843세대' 보도) | 같음 | 같음 |

## 4. R4 재시험 때 확인할 항목

1. `SELECT adapter_version, COUNT(*) FROM judgment_log GROUP BY 1` → **1개**. `output_json->>'provider'` none 행이 있어도 버전은 같다.
2. 2회차 (a) rejudge 잡 `stats->>'tools_calls'` = **0**, `judgment_log` 새 행 0. (교차 확인: 10-6 ⑤ 프록시 `jev_calls.jsonl` 0줄.)
3. 1회차 bootstrap 잡 `tools_calls` = `judgment_log`(blocked 제외) 행 수(± error 재시도), 수집 단계 호재 screen 포함(m2). 도구별 수와 132 대비 이유 기록(D18-5 — 조각 단위 screen·extract 는 유지, 같은 조각은 1번).
4. `SELECT COUNT(*), COUNT(legal_dong_code) FROM rtms_trade` → 거의 같음. 수집 stats `loaded.rtms_legal_dong.match_rate`(R4 원문 47쌍 전부 매칭 예상). 종합 점수가 계산되고 TOP 5 가 있다(C2).
5. 잔여 공고 번호(`^20..9.....$`) 단지 행 = 원 단지를 못 찾은 것만. 이름에 '불법행위'·'(임의공급 n차)'·'민영 비규제지역' 없음. `loaded.originals` = {wanted, documents}, 원 단지 공고일 채워짐. 보류 사유 '분양가 미공개(공고 전)' 가 이미 공고된 단지에 없다(M3 — '원 공고 미수집'은 원 공고 API 응답이 비었을 때만).
6. bootstrap 의 change_event: `region·first_load` 1줄 + 값 → 다른 값 변경만(빈 값 → 값 critical 없음).
7. 같은 날 `collect.daily`(applyhome_list·official_site): `change_events` 0, `tools_calls` 0, rejudge 없음(실제 공고 변화가 없을 때). 변화가 있으면 그 이벤트 내용 기록.
8. 대시보드 KPI 미분양 = 값(라벨 확인됨), 발행 stats `missing_provenance` 가 R4(560~605)보다 크게 준다(M2).
9. 왕길역 아테라(주소 '서구 … 오류동') 법정동 = 검단구 오류동, 범위 경계 아님(M6). 계양·김포 공공 택지 '…일원' 다동 주소는 여전히 NULL(§5).
10. `ENV_FILE=… uv run alembic upgrade head` 출력 `PostgresqlImpl`, `alembic current` = 0015(M4·S6). smoke 출력 `"cmd"` = 고정 버전(m1).
11. 기본 조회 창(지난 24 + 향후 12개월)으로 오퍼스·해링턴 단지가 수집된다(D18-8·D20-1) — 호출 수·수집 시간 증가를 기록.
13. 트랙 (A): 주간 뉴스 수집 뒤 `complex.track='A'` 후보(카이브 유보라·그랑포레가 기사에 있으면), `assembled.upcoming` 통계, 상황 A decide 근거
    `[wait_new]` 블록·보고서 §8-2 에 그 이름(D20-2). 실제 판정기가 기사에서 이름을 못 고르거나 review 면 후보 0 — 그때 수를 기록.
14. `judgment_log.model`·`provider` 열이 채워짐(0015), G7 판정 로그 items 의 model·provider.
12. 판정기 모델이 실행 중 바뀌면 `change_event(judge·version)` 1건, 그 실행은 옛 키, 다음 rejudge 가 새 키(재판정 호출 > 0 이 정상).

## 5. 하지 않은 것 / 가정 / 남은 위험

- **기존(R4) DB 의 잔여 공고 단지 행은 합치지 않는다.** 이미 생긴 자기 번호 행(R4 의 15~73)은 `applyhome_id` 로 다시 찾히므로 그대로 남는다 — 재시험은 새 DB 로 한다. 옛 행 병합 마이그레이션은 만들지 않았다.
- **옛 판정 행과 키**: 이 수정 뒤 처음 도는 실행에서 공고문 조각 screen·extract·audit 는 purpose 가 바뀌어(D18-5) 한 번 다시 판정된다. R4 DB 를 이어 쓰면 `…+jev-latest` 로 기록된 extract 행(149)도 고정 모델 키가 아니라 한 번 다시 판정된다(로컬 단락이라 모델 비용 없음).
- 잔여 공고의 공고문이 그 공고의 청약홈 원문보다 **다음 실행**에 들어오면(같은 실행이 아니면) 원 번호를 모른 채 자기 번호 행이 먼저 생길 수 있다 — 같은 날 공고문 단계가 같은 잡에서 돌므로 실데이터에서는 드물다. 이후 인용이 오면 원 번호 행이 따로 생긴다(병합 없음).
- 원 공고 다시 받기는 **공식 API 키가 있을 때만**(웹 목록은 번호 조회 불가). 키 없으면 '원 공고 미수집'.
- 원 단지 접수 상태: 원 단지 행에 공식 홈페이지 주소가 없으면 잔여 공고의 주소로 채워 그 사이트의 접수 행이 원 단지에 붙는다. "열린 잔여 사건으로 갱신"을 날짜 규칙(잔여 공고 접수일)으로 접수 상태를 바꾸는 것으로 구현하지는 않았다(접수 분류는 판정기 몫 — 규칙 3).
- M6: 다동 '…일원' 주소(계양 공공 A6·A9·A17, 김포 고촌2지구)는 고치지 않았다(공공이라 분류에서 제외되는 행, D18-7 범위는 신설 구 표기).
- M4: `uv run alembic upgrade head` 자체는 여전히 `ENV_FILE` 을 모른다(계약 디렉터리 env.py) — 계약 변경 요청.
- `scheduler/handlers.py` `_since` 가 bootstrap 잡을 보지 않는 문제(첫 daily 가 전부 다시 받음)는 CORE7 파일이라 고치지 않았다 — 결과는 같아야 하므로(멱등) 재시험 시간만 늘어난다.
- `normalize/rtms_parser.py`(store 경로)는 umdCd 가 있을 때만 코드를 낸다 — 실데이터 실거래는 수집기 적재(`load_trades`) 경로라 영향 없다.
- 동시 작업(CORE7) 파일 변경: `scheduler/runner.py`(잡 stats 계수 — `execute` 에 3줄 + `with_tools_calls`), `scheduler/pipeline.py`(CORE7 목록 아님), `normalize/store.py`(잔여 공고 묶기·첫 적재 — 사람 확인 퍼짐 부분은 건드리지 않음). `handlers.py`·`persist.py`·`snapshot_view.py`·`api/demotion.py` 는 바꾸지 않았다.

## 6. 계약 변경 요청 (.15 초안 — D20-1 로 승인되어 계약 .15 로 냈다, §7)

| 대상 | 변경 | 이유 | 영향 WP |
| --- | --- | --- | --- |
| `contracts/migrations/env.py` | `DATABASE_URL` 이 없으면 앱 설정(`app.core.settings.load_settings()` — `ENV_FILE`)의 URL | M4. 지금은 `python -m app.migrate` 로 우회 | WP0 |
| `contracts/schemas/region.json` `ApplyhomeQuery.from_ym` 설명 | 기본 "기준월 −10개월" → "기준월 −24개월"(meta_prompt "지난 24~36개월") | D18-8(2025-06·07 공고 누락) — 수집 시간·판정 호출 증가 | WP0·WP1a·WP5 |
| `contracts/openapi.yaml` `POST /regions` 요청 | 선택 필드 `applyhome_query`(ApplyhomeQuery) | 운영자가 창을 정할 수 있게(지금은 `{}` 고정) | WP0·WP5·WP6 |
| (선택) `judgment_log` | `model`·`provider` 열 | D18-1 "행에 따로 기록" — 지금은 `output_json`(원응답)에 그대로 있다 | WP0·WP3 |

## 7. D20 — 계약 .15(D20-1)·트랙 (A) 공고 예정 단지(D20-2) (main `5547f7c` 병합 뒤)

수정 전 = D20 직전 커밋(`61c983e`+main 병합)의 `backend/app`·`contracts/{migrations,schemas,openapi*}` 로 되돌려 같은 테스트를 돌린 실제 출력
(scratchpad `r4fix/prefix_d201.txt`·`prefix_d202.txt`).

| 결정 | 수정 | 테스트 | 수정 전 실제 실패 | 수정 후 |
| --- | --- | --- | --- | --- |
| D20-1 계약 버전 | `CONTRACT_VERSION`·`openapi info.version`·`DECISIONS.md`·CHANGELOG 맨 위 = `2026-10-09.15` | `tests/api/test_r4fix_contract15.py::test_contract_version_is_15`, `tests/contracts/test_{openapi,protocols}.py` 버전 단언 .14 → .15, `test_migrations.py` head 0014 → 0015 | `assert '2026-10-09.14' == '2026-10-09.15'` | 통과 |
| D20-1 env.py `ENV_FILE` | `contracts/migrations/env.py` 폴백(위 §1 M4 행) · `app/migrate.py`·그 테스트 삭제 · runbook §10-7 ① | `tests/contracts/test_r4fix_migrations.py::test_alembic_env_file_fallback` | **`ENV_FILE 이 가리킨 DB 를 마이그레이션해야 한다`** + `backend/dev.db` 생김 | 통과(dev.db 없음) |
| D20-1 기본 조회 창 | `collectors/applyhome/collector.py` `PAST_MONTHS=24`·`FUTURE_MONTHS=12`, `to_ym`, 생성자 `window`(녹화 재생용), `scheduler/context.recorded_window`(replay 는 녹화 zip 의 창) | `test_r4fix_contract15.py::test_default_window_is_past_24_future_12`·`::test_query_window_overrides` | `('202512' == '202410'` · `('202506', '202611') == ('202506', '202703')` | 통과 |
| D20-1 `POST /regions` `applyhome_query` | `region.json` `RegionCreate.applyhome_query`·`ApplyhomeQuery.to_ym`, `regions.py` 저장 | `::test_create_region_accepts_applyhome_query`·`::test_create_region_rejects_bad_from_ym` | **`Additional properties are not allowed ('applyhome_query' was unexpected)`** | 통과 |
| D20-1 `judgment_log.model`·`provider` | 마이그레이션 `0015_r4fix.py`(열 + 원응답에서 채움, 앱 import 없음), 모델·`judge/log.py`(행마다 기록, blocked·error NULL), 봉투·`envelope_view` | `test_r4fix_migrations.py::test_{sqlite,postgres}_0015_…`, `test_r4fix_contract15.py::test_envelope_carries_model_and_provider` | `no such column: model`(SQLite) · `column "model" does not exist`(Postgres) · `'model' is an invalid keyword argument` | 통과(왕복·diff 0) |
| D20-1 CHANGELOG 픽스처 사유 | `contracts/CHANGELOG.md` .15 `### fixtures` 에 매니페스트 사유 문장 | `tests/contracts/test_fixture_manifest.py::test_manifest_reason_is_in_changelog` | **`매니페스트 사유가 CHANGELOG 에 없다: 'R4-FIX D18-5 …'`**(1차 보고의 남은 실패 1건) | 통과 |
| **D20-2** 트랙 (A) 후보 | `judge/payloads.py`(`UPCOMING_SCREEN_TASK`·`UPCOMING_CLASSES`·이름 extract 필드), `judge/pipeline.py`(`p1_screen_upcoming`·`p2_extract_upcoming`·`p4_classify_upcoming`·`p5_same_complex`), `normalize/upcoming.py`(후보 행·별칭·출처 '비공식'·change_event), `scheduler/assemble.py` 뉴스 단계 `upcoming`, `normalize/store.py` `_upcoming_row`(청약홈 공고 → 같은 이름 키 후보에 주택관리번호), `scheduler/pipeline._p4`(공고 전 후보 재분류 안 함) | `tests/scheduler/test_r4_fix_d20_2.py`(3) — R4 녹화 뉴스 원문 4항목(`tests/scheduler/fixtures/r4_news_2026-10-12.json`) | **`AssertionError: set()`**(후보 0) · **`assert 0 == 2`**(공고 예정 0곳 — wait_new 근거) · `KeyError: '검단 센트레빌 그랑포레'`(합칠 후보 없음) | 통과: 후보 2(그랑포레·계양신도시 카이브 유보라 + 별칭 '카이브 유보라' — 판정기 compare), 오피스텔 기사 제외, 재수집 판정 호출 0, 범위 '보류 — 공고 후 재판정', 상황 A `[wait_new]`·보고서 §8-2 근거에 두 이름, 청약홈 공고가 오면 같은 행 |

**연결 확인(이미 있던 것 — 고치지 않음).** `scheduler.payloads.wait_new_evidence` 는 `track='A'`·공고 전·제외/미해결 아님 행을 쓰고(그대로),
보고서 §8-2(`reports/data.wait_new_evidence` → `s08.html.j2`)는 decide 입력의 `[wait_new]` 블록을 다시 읽는다 — 새 후보가 두 곳에 나오는 것을
`test_candidates_flow_to_scope_wait_new_and_report` 가 확인한다. 체크리스트 '공고 예상'(`normalize/checklist.py`, applyhome_id 없는 단지)도 그대로 생긴다.

**바뀐 기존 테스트·골든(이유)**

| 파일 | 바뀐 것 | 이유 |
| --- | --- | --- |
| `tests/collectors/applyhome/test_applyhome_{api,collector}.py`, `tests/collectors/test_daily_budget.py`, `tests/regress/test_flow_g0_bootstrap.py`, `tests/scheduler/test_bootstrap_e2e.py` | `ApplyhomeCollector(window=("2025-12","2026-11"))` | 청약홈 녹화(2026-10-09)는 옛 기본 창(−10~+1개월)으로 받았다 — 계약 .15 기본 창(−24~+12) 요청은 녹화에 없다. 녹화 때 창으로 재생(앱의 replay 모드는 `recorded_window` 로 같은 일을 자동으로 한다 — e2e G0 흐름) |
| `tests/api/snapshots/list_r3c.json`(`UPDATE_GOLDEN=1`) | 단지 상세 18개 응답 바이트(판정 봉투에 `model`·`provider`) | 계약 .15 F1. 목록·CSV 응답은 그대로 |
| `tests/scheduler/test_r3b_g2.py::NewsJev` | 호재 screen 만 센다 | D20-2 뉴스 항목마다 공고 예정 screen 이 하나 더 돈다(호재 판정은 그대로) |
| `tests/scheduler/test_r4_fix_c1_jobs.py::test_m2_…` | 잡 tools_calls 1 → 3(호재 screen + 공고 예정 screen + 이름 extract) | 같음 |
| `tests/contracts/test_{openapi,protocols,migrations}.py` | 버전 .15·head 0015 | 계약 .15 |

**D20 하지 않은 것 / 남은 위험**

- 트랙 (A) 신호는 **뉴스만** 쓴다. 공식 홈페이지는 주소(청약홈 HMPG)가 있는 단지에서만 수집되므로 공고 전 후보에 쓸 수 없다(공고 뒤에는 기존 접수
  classify 'pending'). 후보의 주소·세대수·예정월은 뽑지 않았다(법정동·생활권 비어 있음) — 청약홈 공고와의 합치기는 이름 키(옛 이름 포함)가
  **같을 때만**(D20-2 '이름 키·주소' 중 주소는 없음). 이름이 조금 다르게 공고되면 후보와 공고 단지가 둘로 남는다.
- 실제 JEV 가 기사 발췌(300자)에서 이름을 얼마나 고를지, classify 가 auto 를 낼지는 녹화 재생으로 알 수 없다(가짜 판정기) — R4 재시험 항목 13.
- 뉴스 항목마다 판정 호출이 늘어난다(screen 1 + 이름 extract 1 + classify 1, 이름 포함 쌍마다 compare 1 — 같은 입력은 캐시).
- 기존 R4 DB 의 잔여 공고 행 병합 마이그레이션은 만들지 않았다(D20-3).
