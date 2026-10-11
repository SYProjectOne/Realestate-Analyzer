# R4 운영 시험 결과 — 인천·김포 실데이터 1회 실행 (2026-10-12)

RA §8-1 R4 게이트("실제 JEV 연결, 인천·김포 → 실제 1회 실행 호출 수·시간 기록; 2회차 호출 0 확인; runbook 갱신")와
RA §9 통과 기준(1회차 실제 호출 ≤ 132 — 넘으면 이유 기록, 2회차 실제 호출 0)을 사람 승인(2026-10-12) 아래 처음으로 돌린 기록이다.
절차는 `docs/runbook.md` §10 을 따랐고, 실제로 다르게 해야 했던 것은 runbook §10-6 에 적었다. 코드는 고치지 않았다 — 결함은 §9 에 보고만 한다.

## 0. 한 줄 결론

**R4 게이트 미통과.** 1회차 실제 호출 500(> 132, 이유 §3-3), 2회차 (a) 같은 스냅샷 재판정은 runbook 기준(새 `judgment_log` 행 0 ·
`judge_calls` 0)으로는 통과처럼 보이지만 **판정기 MCP 로 실제로 나간 `tools/call` 이 298건**이었다(측정 프록시, §6). 원인은
판정기 응답의 `model` 이 도구·경로마다 달라(`jev-1.13.0` / `jev-latest`) 어댑터 버전이 호출마다 뒤집히는 것(결함 C1).
그 밖에 실거래 법정동 코드 누락으로 **종합 점수가 하나도 계산되지 않았다**(TOP 5 빈 목록, C2), 잔여 공고 제목이 단지 이름으로
'확인됨' 채택(C3). critical 3 · major 6 · minor 5.

## 1. 환경

| 항목 | 값 |
| --- | --- |
| main 커밋 | `3a4141d` (docs: R3i assignments) — 브랜치 `wp/r4-live` |
| 계약 버전 | `2026-10-09.13` (`contracts/CHANGELOG.md` 최신, `/health` 응답과 일치) |
| alembic | `0013 (head)` |
| OS·도구 | Windows 11, Git Bash, Node v24.19.0, uv 0.11.29, Python 3.12, playwright 1.63.0(chromium) |
| DB | **임베디드 Postgres 16.2**(`pgserver` 번들 바이너리, backend dev 의존성) — r4 작업 폴더 안 `pgdata/`, 127.0.0.1 임의 포트(64182), DB `r4`. 방법 runbook §10-6 ① |
| ENV | `prod`(API_TOKEN·READONLY_TOKEN 임의 43자, `JUDGE_ADAPTER=jev`, `LOG_JSON=true`) |
| API | `python -m app.serve`, 127.0.0.1:**18431**(다른 에이전트 테스트와 포트 충돌 회피) |
| 판정기 | `JEV_MCP_CMD="npx -y @jkudish/jev-mcp@0.14.1"` — 실행 전 `npm view` 최신 = 0.14.1 확인 후 고정. `serverInfo.version` 0.14.1 |
| adapter_version | `0.2.0+jev-mcp@0.14.1+jev-1.13.0` **와** `0.2.0+jev-mcp@0.14.1+jev-latest` 두 개(§3-2, C1) |
| 외부 키 | `DATA_GO_KR_KEY`·`NEWS_API_PROVIDER`(ncp)·`NEWS_API_KEY` — 저장소 루트 `.env` 에서 스크립트로 옮김(값 미출력, 존재·길이만 확인). 시험 뒤 r4 `.env`·토큰 파일 삭제 |
| 데이터 위치 | 원문·보고서·참조·로그·DB 모두 저장소 밖 scratchpad `r4/` (커밋 안 함) |

JEV 연결 smoke(`uv run pytest -m live tests/judge/test_live.py -s`): 1 passed — server 0.14.1, tools 12개(계약 9개 포함),
기동 3.4초, screen 1건 311ms(ok, verdict pass), 같은 입력 2회째 cached. 단 이 테스트는 `JEV_MCP_CMD` 를 무시하고 언제나
`@latest` 로 띄운다(m1) — 이번에는 최신이 0.14.1 이라 결과가 같다.

보안 확인(`leakscan`): r4 폴더 파일 871개(로그·원문·보고서·응답 덤프)와 DB 텍스트·JSON 컬럼 240개에서 외부 키 2종·API 토큰 2종의
값(원문·URL 인코딩·ID/Secret 조각) 검색 → **0건**. 원문 URL 에서 serviceKey 는 빠져 저장된다. guard 차단(blocked) 0.

## 2. 1회차 (bootstrap) — 시간

| 단계 | 시각(KST) | 소요 |
| --- | --- | --- |
| reference.refresh (잡 1) | 06:25:05 → 06:25:17 | 11.3초 (법정동 53,403 · 행정동 3,925, 대체 사본 미사용) |
| 지역 생성 `POST /regions` | 06:25:44 | 201, 법정동 106개·생활권 4개, 잡 2 = region.bootstrap |
| **region.bootstrap (잡 2) 전체** | 06:25:55 → 06:49:52 | **23분 59.7초**(worker `--once` 프로세스 1,439.7초) |
| └ 수집·정규화 | 06:25:55 → 약 06:47:36 | 약 21분 40초 (호스트당 1 req/s, 공식 홈페이지 playwright 렌더) |
| └ 판정 P1~P9 | 06:47:37 → 06:49:46 | 2분 9초 (판정기 응답 시간 합 78.8초) |
| └ 점수·발행(materialize) | 06:49:46 → 06:49:52 | 약 6초 |

## 3. 1회차 판정기 호출 수

### 3-1 도구별·상태별 (`judgment_log` 1행 = 실제 호출 1건)

| 도구 | ok | review | escaped | 계 | 용도(purpose 앞부분) | 픽스처 132 |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| screen | 210 | | | 210 | `screen:extract` 190 · `screen:catalyst` 20 | 36 |
| extract | 190 | | | 190 | 공고문 조각 47개 문서(`extract:rd<id>:<조각>`) | 28 |
| audit | 14 | | | 14 | 9개 문서 | 18 |
| classify | 19 | 15 | | 34 | 호재 20 · 호재 종류 11 · 포함 2(배치) · 접수 1(배치) | 4 |
| compare | 17 | 29 | | 46 | 단지 필드 15 · 타입 필드 31(출처 상충) | 12 |
| noul | 3 | | | 3 | 사다리 3지점 × 판정 대상 1단지 | 12 |
| rerank | 1 | | | 1 | 지역 1회(후보 54) | 2 |
| decide | | | 1 | 1 | 상황 A 1회 | 10 |
| verify | 1 | | | 1 | 단지 절 주장 4건 | 10 |
| **계** | **455** | **44** | **1** | **500** | | **132** |

- `real_calls`(status ≠ blocked) = **500**, blocked **0**, error **0**, cached(같은 실행 안 같은 입력) **3**(compare 3건, 바로 앞
  호출과 같은 hash — 정상 캐시).
- 잡 stats: `pipeline.judge_calls` 480 · `cached` 3 · `blocked` 0 · `by_tool` = {screen 190, extract 190, audit 14, classify 34,
  compare 46, noul 3, rerank 1, decide 1, verify 1}. `judgment_log` 500 과의 차이 20 = 수집 단계(assemble)의 뉴스 호재 screen
  (`screen:catalyst`)이 파이프라인 통계에 안 들어간다(m2).
- 판정기 실제 모델 사용: 응답 `provider` 기준 **typesafe(모델 호출) 351 · none(로컬 단락) 149**. 149건은 전부 extract 로,
  JEV 가 후보 문자열을 찾지 못해 모델을 부르지 않고 `not_found` 를 돌려준 것이다(이때 `model: "jev-latest"`). 추출 결과: typesafe 41건 =
  필드 54 중 추출 26(auto 16), none 149건 = 필드 251 전부 not_found.

### 3-2 adapter_version

| adapter_version | 행 | 도구 |
| --- | ---: | --- |
| `0.2.0+jev-mcp@0.14.1+jev-1.13.0` | 351 | screen 210 · extract 41 · audit 14 · classify 34 · compare 46 · noul 3 · rerank 1 · decide 1 · verify 1 |
| `0.2.0+jev-mcp@0.14.1+jev-latest` | 149 | extract 149 (provider none) |

runbook §10-3 의 "버전 1개여야 한다"를 **만족하지 않는다**. 서버 버전은 그대로이고 응답 `model` 만 경로별로 다르다(C1).
`change_event(entity=judge)` 는 생기지 않았다.

### 3-3 132 와의 차이(+368)와 이유

| 원인 | 늘어난/줄어든 호출 |
| --- | --- |
| **원자 분할(P1·P2)**: 공고문을 조각 단위로 screen → extract 한다(문서 47개 → 조각 190개, 한 문서 최대 19조각). 픽스처는 공고당 1회 | screen +154 · extract +162 |
| 그중 **extract 149건은 모델 호출 없는 로컬 단락**(provider none) — 비용은 없지만 MCP 호출이고 `judgment_log` 행이다 | (위에 포함) |
| **후보 수**: 단지 행 88개(픽스처 16) — 무순위·임의·재공급 공고가 각각 단지 행이 되고(M1), 지역 밖(범위 경계) 18·공공 등 포함. 출처 상충 compare 가 그만큼 는다 | compare +34 |
| 뉴스 호재 20건 screen 20 · 호재/호재 종류 classify 31(픽스처는 호재를 보고서에서 옮김). 포함·접수 classify 는 배치라 4 → 3 | screen +20 · classify +30 |
| **판정 대상 1단지뿐**(픽스처 16): 실제 접수 상태가 '가능·미정'인 포함 단지가 사우역 지엔하임 1개 → 사다리·decide·verify 가 크게 준다 | noul −9 · decide −9 · verify −9 · rerank −1 · audit −4 |

모델을 실제로 쓴 호출(351)만 세도 132 를 넘는다. 이유는 위 표(원자 분할 + 중복 단지 + 호재)이며 RA §9 "이유가 기록되면 됨"에
해당하는지는 사람이 판단할 일이다 — 단, 중복 단지(M1)로 늘어난 몫은 결함 때문이다.

## 4. 수집 결과 (출처별, 1회차 + 2회차 누적 `raw_document`)

| 출처 | 성공(200) | 실패 | 상태·사유 |
| --- | ---: | ---: | --- |
| applyhome_list (공식 API 1순위) | 21 | 0 | |
| applyhome_detail (API·웹) | 362 | 0 | |
| notice_pdf | 69 | 0 | OCR 경로 없음(텍스트 PDF) |
| official_site | 90 (1회차 62) | 2 | `TLS` (http_status 없음): hillstate.co.kr/SALE/941 (단지 30), www.sujain-pm.co.kr (단지 57) — 행으로 남음(규칙 7) |
| rtms (매매 실거래 API) | 144 | 2 | **403** `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` — 분양권 전매 API(`RTMSDataSvcSilvTrade`, LAWD_CD 28185 2023-11·2025-11). 키에 분양권 서비스 활용신청이 없다(사람 할 일). 매매 실거래는 48,054건 적재 |
| stats (미분양 등) | 3 | 0 | 미분양 35행(2025-10~2026-08) — 화면에는 출처 누락으로 가려짐(M2) |
| news (NCP 검색) | 1 | 0 | 기사 20건 → 호재 screen 20 |
| reference | 4 | 0 | |
| **타임아웃·파싱 실패** | | **0** | 403 2 · TLS 2 외 실패 없음 |

G7 `GET /ops/sources`: 모든 출처 enabled, failing_targets 는 위 4건과 같다.

## 5. 단지 수·판정 범위

1회차(스냅샷 1, revision 1): 단지 행 **88**. 판정 범위(기본 시나리오 score_run 1):

| 범위 | 1회차 | 2회차(b) 뒤(스냅샷 3) |
| --- | ---: | ---: |
| 판정 대상 | 1 (사우역 지엔하임) | 3 (+ 엘리프 검단 포레듀 AA32 의 잔여 공고 행 32·37) |
| 참고 | 43 | 47 |
| 보류 | 10 | 10 |
| 미해결 | 15 | 9 |
| 제외 | 19 | 19 |

- classify 포함 결과: private_sale_apt auto 54 · 범위 경계 18(주소가 선택 법정동에 안 맞음) · 미분류 review/manual_review 15 · public_sale 1.
- **종합 점수: 모든 단지 '확인 불가(미판정)', TOP 5 빈 목록** — 가격 갭 성분이 전 단지 '비교군 없음'(C2).
- 사우역 지엔하임(판정 대상) 성분: p10 4.10(추정, jl_495, 입주+1년 2030-04 p10 0.41) · rerank 5.85(추정, 23/54위, relevance 0.73,
  jl_498) · 가격 갭 확인 불가(비교군 없음) · 벤치마크 0.30(추정, 표본 1 고촌센트럴자이 +1.5%) · 공급 6.37(추정, 입주 6,049세대 /
  U_ref 16,653) · 유동성 확인 불가(계약금% 없음). decide(상황 A) = escaped → investigate(0.65). verify 주장 4건 중 verified 3 · review 1.

### 5-1 G1 표본 확인 (API, 스냅샷 2·3)

- `GET /snapshots/{sid}/dashboard` 200, `GET /snapshots/{sid}/complexes?size=200` 200(88행), `GET /complexes/49?snapshot=2` 200,
  `GET /provenance/fp_7152?snapshot_id=2` 200(URL·확인일·라벨·발췌·raw_document_id), `GET /snapshots/3/market` 200, `GET /ops/judgments` 200.
  토큰 없이 대시보드 401.
- 단지 목록 Fact 1,320개: 라벨 확인됨 414 · 추정 162 · 확인 불가 744, **빈 라벨 0, 값이 있는데 prov 없는 Fact 0**.
- 대시보드 KPI: 판정 대상 수 1→3(추정, st_), 접수 가능 2→5(추정), 입주 정점 2029년 9,083세대(추정, fp_7152), 신선도(확인됨, rd_),
  **미분양 '확인 불가(미분양 자료 없음)'**(M2 — 실제로는 35행이 있고 공급 성분 식에 쓰였다).
- 사우역 지엔하임 상세: 기준 타입 84B 6.978억(확인됨 fp_3878, 공급가+발코니 1,520만), 입주 2029-04(확인됨), 전매 6개월(확인됨) 등
  모든 값에 라벨·출처가 붙어 있다.
- 발행 저장본 stats: `missing_provenance` 560(스냅샷 2) · 605(스냅샷 3) — 대부분 미분양(M2). 1회차 로그 경고 '출처 누락' 594줄.

## 6. 2회차 — 실제 호출 0 확인

측정: runbook 의 기준(`judgment_log` 행 수, 잡 stats `judge_calls`)에 더해, 판정기 MCP 로 나가는 `tools/call` 을 세는 stdio 프록시를
`JEV_MCP_CMD` 앞에 끼웠다(도구 이름·시각만 기록, payload 미기록, 같은 0.14.1 서버 — runbook §10-6 ⑤). adapter_version 은 서버 버전에서 오므로
프록시가 hash 를 바꾸지 않는다.

### (a) 같은 스냅샷 전체 재판정 (`rejudge` snapshot 1, 잡 3)

| 지표 | 값 | 판정 |
| --- | --- | --- |
| `judgment_log` 행 수 전/후 | 500 → 500 (새 행 0) | runbook 기준 통과 |
| 잡 stats | `judge_calls` 0 · `cached` 434(screen 190 · extract 190 · audit 14 · classify 34 · noul 3 · rerank 1 · decide 1 · verify 1) | runbook 기준 통과 |
| 로그 `judge.payload` | 434건 전부 `cached: true` | |
| **MCP `tools/call` 실제 전송(프록시)** | **298** = extract 149 · screen 148 · classify 1 | **실패 — 2회차 실제 호출 0 아님** |
| 시간 | 94.2초(rejudge 85.9초 + 발행 5.4초) | |
| 결과 | 새 리비전 스냅샷 2(revision 2, revision_of 1) 발행 | |

숨은 호출 경로(C1): 어댑터는 시작할 때 마지막 행의 모델(`jev-1.13.0`)로 버전을 정한다. screen(1.13.0 기록) → extract(1.13.0 으로 찾으면
없음 — 1회차는 `jev-latest` 로 기록) → 실제 호출 → 응답 `jev-latest` → 버전 전환 → 새 hash 로 찾으니 있음 → `_replay`(cached=true) →
다음 screen 은 `jev-latest` 로 찾아 없음 → 실제 호출 → 응답 `jev-1.13.0` → 전환 → replay … 이 반복된다. 호출은 판정기로 나가지만
행·통계·로그는 모두 '캐시'로 남는다. 숨은 298건 중 screen 148·classify 1 은 모델 호출(provider typesafe)이고 extract 149 는 로컬 단락이다.

### (b) 일일 수집 `collect.daily` (sources applyhome_list·official_site, 잡 5 → rejudge 6 → publish 7)

| 지표 | 값 |
| --- | --- |
| 시간 | 778.7초(수집 711.9초 — official_site 129건 재렌더, rejudge 58.0초, 발행 5.8초) |
| 변경 감지 | change_event 29(수집 26 + 접수 상태 3), `rejudge_complex_ids` [17, 35, 46, 48, 56, 59, 63], 판정 대상 7 |
| `judgment_log` | 500 → **516 (새 행 16)**: classify 2(접수·포함 배치) · noul 6(단지 32·37 × 3지점) · rerank 1 · decide 5(시나리오 5개) · verify 2 |
| 잡 stats | `judge_calls` 16 · `cached` 54 |
| MCP `tools/call`(프록시) | **25** = 위 16 + 숨은 9(extract 5 · screen 4, C1) |
| 결과 | 새 리비전 스냅샷 3("같은 기준일 재수집") 발행 |

변경 29건의 내용: 실제 공고 변화가 아니라 **1회차에 비어 있던 값이 1시간 뒤 채워진 것**이다 — 잔여 공고 단지 행(17·20~23·31·35·56·63)의
`official_site_url`·`developer`·`apply_dates`(이미 지난 2026-03~09 접수일) null → 값(info/notice), 그리고 같은 공식 홈페이지 URL 의 접수
상태가 '확인 불가' → '가능'(단지 32·37, 엘리프 검단 포레듀 AA32 잔여 공고)·'미정'(단지 36) critical 3건. runbook §10-4 는 "실제로 바뀐 공고가
없으면 같은 수"를 기대하지만 1회차 수집이 불완전해 같은 날 재수집에서 호출 16(+숨은 9)이 생겼다(M5). change_event 목록(G1 '최근 변경')과
재판정 대상은 일치한다.

## 7. 보고서 (§10-5)

`uv run python -m app.reports.cli --snapshot 3 --format pdf` → exit 0,
`report_r1_2026-10-12-r3_vs_2026-10-12-r2.pdf`(4.57MB, **172쪽**, 비교 스냅샷 2 자동 — revision_of). 목차 §1~§12·부록 A(판정기 호출 로그·
도구별 임계값) 포함, "투자 권유 아님" 고정 문구 있음. 경고: worktree 에 `frontend/node_modules` 가 없어 ECharts 번들 없음 → 차트 자리에 표만
(`REPORT_ECHARTS_JS` 미설정). 보고서에도 잘못된 단지 이름 '불법행위' 24회 · '민영 비규제지역' 10회가 나온다(C3), '확인 불가(출처 누락)' 74회.

## 8. 회귀 기준(픽스처 `incheon_gimpo_2026-10-08`)과 실제 결과의 주요 차이

픽스처는 보고서(2026-10-07) 재구성이고 실제는 2026-10-12 수집이다. 실제 값은 기본 시나리오, 스냅샷 3.

| 픽스처 # · 단지 | 픽스처 (b) 종합 / 순위 | 실제 단지 행(id) · 범위 · 접수 | 실제 기준가(라벨·출처) · 종합 |
| --- | --- | --- | --- |
| 1 더샵 송도그란테르 (2026000164) | 5.38 / 3 | 10 · 참고 · 접수 행 없음 (+ 블록별 5~9, 무순위 공고 행 20~24) | 13.18억(추정, fp_1531) · 미판정 |
| 2 엘리프 검단 포레듀 (2025000302) | **6.38 / 1** | 80 · 참고 (+ 잔여 공고 행 32·37 = **판정 대상**, 접수 가능) | 5.9314억(추정, fp_5642) · 미판정 |
| 3 송도 한내들 센트럴리버 (2025000582) | 6.16 / 2 | 14 · 참고 · 확인 불가 (+ 잔여 35 미해결) | 8.758억(추정, fp_1900) · 미판정 |
| 4 오퍼스 한강 스위첸 (2025000222) | 4.97 / 5 | **수집되지 않음** | — |
| 5 검단 센트레빌 에듀시티 (2025000435) | 5.15 / 4 | 82 · **보류(분양가 미공개 — 사유 틀림, M3)** (+ 잔여 38 참고) | 확인 불가 · 미판정 |
| 6 더샵 검단레이크파크 AB23 | 4.76 / 7 | 3 · 참고 · 확인 불가 (+ 18 미해결) | 6.2432억(추정, fp_4815) · 미판정 |
| 7 김포 칸타빌 에디션 (2025000573) | 4.84 / 6 | 84 · 보류(M3) (+ 55·70 참고, 66 미해결) | 확인 불가 · 미판정 |
| 8 풍무역세권 수자인 그라센트 2차 (2026000073) | 4.53 / 8 | 48 · 참고 · 불가 | 6.8944억(추정, fp_6698) · 미판정 |
| 9 한강 푸르지오 리버프론트 (2026000367) | 4.12 / 9 | 45 · 참고 · 확인 불가 | 7.24억(추정, fp_6074) · 미판정 |
| 10 풍무역 롯데캐슬 시그니처 (2025000076) | 3.67 / 11 | 88 · 보류(M3) (+ 62·64·67 미해결) | 확인 불가 · 미판정 |
| 11 고촌센트럴자이 | 3.16 / 12 | 87 · 보류(M3) (+ 잔여 9~13차 60·65·68·71·73 참고) | 확인 불가 · 미판정 |
| 12 더샵 송도마리나베이 | 4.14 / 9 | 15(조합원 자격상실세대 3회차 공고 행) · 참고 | 미판정 |
| 13 해링턴플레이스 풍무 1BL (2025000271) | 판정 제외 | **수집되지 않음** | — |
| 14 사우역 지엔하임 (2025000656) | 판정 제외 | **49 · 판정 대상 · 가능** (유일한 1회차 판정 대상) | 6.978억(확인됨 fp_3878 / 중간값 추정) · 미판정 |
| 15 계양신도시 카이브 유보라 (A) | — | 수집되지 않음 | — |
| 16 검단 센트레빌 그랑포레 (A) | — | 수집되지 않음 | — |

- 픽스처 TOP 5(b) = 엘리프 6.38 > 한내들 6.16 > 그란테르 5.38 > 센트레빌 5.15 > 스위첸 4.97. **실제 TOP 5 = 없음**(C2).
- 픽스처 판정 대상 16(B 14 · A 2) ↔ 실제 1→3. 실제는 오늘 접수 상태가 '가능·미정'인 단지만 판정 대상이다(D9-1 범위 규칙 그대로 —
  픽스처는 보고서 시점 상태). 픽스처에 없던 단지: 호반써밋 풍무Ⅱ·Ⅲ, 검단호수공원역 파라곤, 제일풍경채 검단Ⅳ, 금강펜테리움 센트럴파크,
  인천 작전 한라비발디, 수자인 그라센트 1차, 풍무역세권 B5 호반써밋, 힐스테이트 레이크 송도 4차 등.
- 그란테르 84㎡ 가격: 보고서 12.45~13.18억(무순위 동일가) ↔ 실제 G5-1 13.18억·G5-11 12.40억(추정 중간값) — 범위 안.
- 사다리(사우역 지엔하임 84B, 6.98억): 입주+1년(2030-04) p10 0.41 · 기준일+3년(2029-10) 0.40 · +5년(2031-10) 0.46, 모두 uncertain.

## 9. 발견한 결함

심각도 기준(과제 지시): critical = 틀린 수치·판정이 '확인됨'으로 보임 / 발행 결과가 조용히 바뀜 / 데이터 손실·보안 노출 / 주 흐름 실패.

| # | 심각도 | 위치 | 내용 | 재현 |
| --- | --- | --- | --- | --- |
| C1 | **critical** | `backend/app/judge/base.py:223-233`(`_observe_model`), `:322`·`:333`(현재 버전으로 hash), `:366-372`(호출 뒤 버전 전환 → replay) | JEV 0.14.1 은 `jev_extract` 가 모델을 부르지 않을 때(provider none) `model: "jev-latest"`, 그 밖에는 `"jev-1.13.0"` 을 준다. 어댑터가 응답 모델마다 전역 adapter_version 을 바꾸므로 버전이 호출마다 뒤집히고, 캐시 조회가 빗나가 **실제 MCP 호출을 한 뒤** 새 hash 의 기존 행을 replay 한다. `judgment_log`·잡 stats·G7 `real_calls`·로그가 모두 '캐시'로 기록해 **2회차 실제 호출이 0 이 아닌데 0 으로 보고된다**(RA §9 게이트 측정 신뢰 불가, 같은 입력 재호출 금지 규칙 4 위반). 1회차 adapter_version 도 2개. | 1회차 후 같은 스냅샷 `rejudge` → `judgment_log` 새 행 0·`judge_calls` 0 인데 `tools/call` 프록시 298건(§6 a). `SELECT output_json->>'provider', output_json->>'model', COUNT(*) FROM judgment_log WHERE tool='extract' GROUP BY 1,2` |
| C2 | **critical** | `backend/app/collectors/rtms/parse.py:135-136` → `backend/app/scheduler/inputs.py:406`(`living_area_of`) | 실제 국토부 매매 실거래 API 응답에는 `umdCd` 가 없다(`sggCd`·`umdNm` 만). 파서가 `sggCd+umdCd` 일 때만 법정동 코드를 만들어 **48,054건 전부 `legal_dong_code` NULL** → 거래의 생활권이 None → 모든 단지 가격 갭 '비교군 없음' → **종합 점수 전 단지 미판정, TOP 5 빈 목록**(주 흐름 실패). 녹화 픽스처에는 umdCd 가 있어 테스트가 못 잡았다. | `SELECT COUNT(*), COUNT(legal_dong_code) FROM rtms_trade` → 48054, 0. 원문 `raw/rtms/2026-10-12/*.xml` 에 `<umdCd>` 없음 |
| C3 | **critical** | `backend/app/normalize/notice_parser.py:60-63`(`_TITLE_RE`), `:302-304`(제목 → complex.name 후보) | 잔여·재공급 공고문 PDF 가 '최초 주택관리번호'로 원 단지 키에 묶이고, 제목 줄(또는 본문 줄)을 단지 이름으로 뽑아 원 단지에 **'확인됨'으로 채택**한다(원 단지에 상세 이름 행이 없을 때). 화면·보고서에 단지 이름 **'불법행위'(75)·'불법행위재공급(계약취소주택)'(77)·'민영 비규제지역'(86)·'(임의공급 4차)'(83)** 이 확인됨으로 보인다. D11-4(잔여 공고는 원 단지 단위 필드를 덮어쓰지 않는다) 위반. | `SELECT entity_id, value_text, chosen, label, url FROM field_provenance WHERE entity='complex' AND field='name' AND entity_id IN (75,77,83,86)` |
| M1 | major | 설계 `backend/app/normalize/remaining.py:1-20`(잔여 공고 = 별도 단지 행), `backend/app/normalize/store.py:224`(`complex_for`) | 무순위·임의·재공급 공고(2026910xxx·2026940xxx·2026930xxx)가 각각 단지 행이 되어 판정 범위·rerank·사다리에 원 단지와 함께 들어간다. 88행 중 같은 사업 중복이 다수(그란테르 G5-1 = 10·24, 엘리프 AA32 = 80·37·32). 2회차(b)에서 판정 대상 2개가 같은 엘리프 사업이라 noul·verify 가 두 번 돈다. rerank 후보 54, 포함 classify·compare 호출 증가. | `SELECT name, COUNT(*) FROM complex GROUP BY 1 HAVING COUNT(*)>1` |
| M2 | major | `backend/app/collectors/stats/unsold.py:217`(Unsold 행만 쓰고 field_provenance 없음), `backend/app/api/routers/snapshots.py:766-767` | 미분양 35행이 `raw_document_id`·라벨을 갖고 저장되지만 출처 행이 없어 사실 뷰가 '확인 불가(출처 누락)'로 가린다(prod). 대시보드 KPI 는 '미분양 자료 없음'이라고 **틀린 사유**를 보이는데 공급 성분 식은 같은 데이터(기울기 −73.7/월, 준공 후 114→52)를 쓴다. 발행 stats `missing_provenance` 560~605. | 대시보드 `kpis.unsold`, 1회차 로그 '출처 누락: unsold N field total' 경고 |
| M3 | major | 범위 규칙 `backend/app/analysis/scope.py:133-134` 의 입력(가격 없음) | 잔여 공고의 '최초 주택관리번호'로만 생긴 옛 원 단지 행(2022~2025 공고, 상세·공고문 미수집 — 보류 10행 74·76·79·82·83·84·85·86·87·88)이 '보류 — 분양가 미공개(공고 전)'로 표시된다. 실제로는 이미 공고·분양된 단지라 사유가 틀린다(픽스처 #5·7·10·11). | 단지 목록 `judge_scope='보류'` 행의 notice_date(2022-03~2025-11) |
| M4 | major | `contracts/migrations/env.py:42` · runbook §10-1 | alembic 은 `DATABASE_URL` 환경변수만 읽고 `ENV_FILE` 을 보지 않는다. runbook 대로 `export ENV_FILE=../r4/.env; uv run alembic upgrade head` 하면 **조용히 `backend/dev.db`(SQLite)를 마이그레이션**하고 r4 Postgres 는 빈 채로 남는다(이번에 그렇게 됐고 dev.db 를 지운 뒤 `DATABASE_URL=… alembic upgrade head` 로 다시 함). | 출력 `Context impl SQLiteImpl` |
| M5 | major | 수집 순서(bootstrap 1회차) — `backend/app/scheduler/collect.py` 계열 | 실제 공고 변화 없이 같은 날 `collect.daily` 가 change_event 29 · 재판정 7단지 · 새 판정 16(+숨은 9)을 만들었다. 1회차에 잔여 공고 단지의 공식 홈페이지 URL·시행사·접수일과 접수 상태가 비어 있다가 2회차에 채워졌다(같은 URL 의 접수 상태 확인 불가 → 가능). bootstrap 이 완전하지 않아 "변경 없는 날 판정 0"(T8) 이 실데이터에서 성립하지 않는다. | §6 (b) 의 change_event 823~851 |
| M6 | major | 주소 → 법정동 매칭 `backend/app/normalize/living_area.py`(184 이후 토큰 매칭) | 선택된 검단구 왕길동 단지 '왕길역 아테라'(34·39·40·41·81, 민영)가 법정동 코드 NULL 로 '범위 경계' → 제외. 계양구·김포 공공 단지(1·2·11·50)도 코드 NULL. 지역 안 민영 후보가 조용히 빠진다. | `SELECT id, name, address, legal_dong_code FROM complex WHERE inclusion_class='범위 경계' AND legal_dong_code IS NULL` |
| m1 | minor | `backend/tests/judge/test_live.py:28-29` | smoke 가 `test_settings`(환경변수 삭제)의 기본 `@latest` 를 써서 `JEV_MCP_CMD` 고정 버전을 시험하지 않는다. | 출력 `"cmd": "npx -y @jkudish/jev-mcp@latest"` |
| m2 | minor | `backend/app/scheduler/assemble.py:162` | 수집 단계 호재 screen(20건)이 bootstrap 잡 `pipeline.judge_calls`(480)에 안 들어간다 — runbook §10-3 의 잡별 집계와 `judgment_log`(500)가 어긋난다. | §3-1 |
| m3 | minor | 변경 감지(bootstrap 첫 적재) | 지역 첫 적재인데 null → 값 change_event 가 critical 로 326건(옵션 93·평형 샘플가 54·발코니 45·공고번호 88 …) — G1 '최근 변경'이 첫날부터 critical 로 가득하다(잔여 공고 이벤트만 info 로 낮춘다). | `SELECT field, severity, COUNT(*) FROM change_event WHERE snapshot_id=1 GROUP BY 1,2` |
| m4 | minor | 보고서 ECharts 경로 | worktree·Docker 없는 실행에서 `frontend/node_modules` 가 없으면 PDF 에 차트가 빠진다(경고만). runbook 에 `REPORT_ECHARTS_JS` 지정이 없다. | §7 |
| m5 | minor(환경) | data.go.kr 활용신청 | 분양권 전매 실거래(`RTMSDataSvcSilvTrade`) 403 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` — 사람이 활용신청해야 한다. 실패는 행으로 남았다. | §4 |

보안 노출·데이터 손실은 찾지 못했다(§1 leakscan, guard blocked 0, 발행 리비전 3개 모두 published · 저장본 sha 검증 오류 없음).

## 10. 하지 않은 것 / 가정

- 코드·계약·픽스처는 고치지 않았다. C1~C3 는 R4 재실행 전에 고쳐야 게이트를 다시 잴 수 있다.
- 프론트는 띄우지 않았다(API 응답으로 G1·G2·G3 표본만 확인).
- 2회차 (b)는 "다음 날"이 아니라 1회차 약 1시간 뒤 같은 기준일에 돌렸다.
- JEV 의 `jev-latest`/`jev-1.13.0` 구분은 응답의 `provider` 와 함께 관찰한 것이다 — JEV 쪽 의도(로컬 단락의 모델 표기)는 확인하지 않았다.
- `playwright install chromium` 이 다른 버전의 `chromium_headless_shell-1248` 을 '사용하지 않음'으로 지웠다(공용
  `%LOCALAPPDATA%\ms-playwright`). 같은 PC 의 다른 worktree 가 그 버전을 쓰면 다시 설치해야 한다.
- 원문·DB·로그는 scratchpad `r4/` 에 남겨 두었다(커밋 안 함). r4 `.env`·토큰 파일은 지웠고 임베디드 Postgres 는 멈췄다.
