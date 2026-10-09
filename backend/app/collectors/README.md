# app/collectors

- **주인**: WP1 (a: applyhome·notice_pdf / b: official_site·rtms·stats·news·reference)
- **읽기 허용**: WP2, WP7
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§5, DECISIONS D2-1·D5)

소스별 어댑터: `applyhome/`, `notice_pdf/`, `official_site/`, `rtms/`, `stats/`, `news/`, `reference/`(법정동·행정동·세대수 참조 파일).
`Collector.fetch(region, snapshot, since) -> list[RawDocument]` — 멱등(같은 sha256 이면 저장 안 함), 실패도
`RawDocument(http_status=…)` 로 반환, robots·속도 제한은 `core.http` 가 강제한다.

- HTTP 는 `app.core.http.HttpClient`/`AsyncHttpClient` 만 쓴다. 결과는 항상 `FetchResult`(예외 없음) — 403·타임아웃·robots 차단도 그대로 행으로 남긴다(규칙 7).
- 원문 저장은 `app.core.snapshot.store_raw(content, source=…, day=…, ext=…)` → `{RAW_DIR}/{source}/{yyyy-mm-dd}/{sha256}.{ext}` (ADR-8). DB 에는 `relpath` 를 저장한다.
- 기준일은 `app.core.time.today_kst()`.
- 테스트는 녹화 픽스처 + respx 로 오프라인. 실제 접속 테스트는 `@pytest.mark.live`(기본 건너뜀).

## 키 인증 공식 API (R2X, 2026-10-09)

| 수집기 | 엔드포인트 | 키 | 실패 시 |
| --- | --- | --- | --- |
| applyhome | `api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/get{APT,Remndr,OPT}LttotPblanc{Detail,Mdl}` (data.go.kr 15098547) | `DATA_GO_KR_KEY` | 시도 목록 실패 → 웹 경로, 공고 상세 실패 → 웹 상세 |
| applyhome | `…/ApplyhomeInfoCmpetRtSvc/v1/get{APT,Remndr,OPT}LttotPblancCmpet` (data.go.kr 15098905, 별도 활용신청) | `DATA_GO_KR_KEY` | 401 → 웹 경쟁률 팝업 |
| rtms | `apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade` | `DATA_GO_KR_KEY` | 실패 행 |
| news | `naverapihub.apigw.ntruss.com/search/v1/news` (NAVER Cloud API HUB, 기본) / `openapi.naver.com/v1/search/news.json` (레거시) | `NEWS_API_PROVIDER`·`NEWS_API_KEY` | 실패 행 |

키는 쿼리·헤더로만 가고 `raw_document.url`·녹화 픽스처에 남지 않는다. 실제 호출 테스트:
`ENV_FILE=<메인 체크아웃>/.env uv run pytest -m live tests/collectors` (worktree 에는 .env 가 없다).

## 규칙

- 이 디렉터리와 `backend/tests/collectors/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15). 지역은 `region` 행에서 온다.
