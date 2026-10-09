# 지역 청약 리스트업·분석 도구 — 설계도 v1 (멀티에이전트 구현용)

Oct 9, 2026 · @라홈

## 0. 읽는 법

이 문서는 [설계 메타 프롬프트](https://claude.ai/artifact/UahoFQYg6LLYocmrHFT8CR) §1\~§2를 `[지역]=인천 계양·송도·검단 + 김포`, `[기준일]=2026-10-08`, `[판정기]=JEV MCP 1.13`, `[기술 스택]=기본값`으로 실행했을 때 나와야 할 설계 문서를 미리 써 둔 것이다. 목적은 둘: 에이전트가 이 문서만 보고 구현을 시작할 수 있고, 여러 에이전트가 동시에 일해도 서로의 파일을 건드리지 않는 것. 그래서 모든 모듈을 작업 패키지(WP0\~WP9)로 자르고, 패키지 사이의 접점은 전부 `/contracts`에 파일로 고정했다.

| 역할 | 반드시 읽음 | 참고로 읽음 | 읽지 않음 |
| --- | --- | --- | --- |
| 오케스트레이터 | 전체 | — | — |
| WP 담당 에이전트 | §2 저장소, §4 계약, 자기 WP 카드(§5), §8-4 공통 규칙 | 자기 WP 카드가 가리키는 §3·§6·§7 행 | 다른 WP 카드, §9·§10 |
| 리뷰 에이전트 | §4 계약, §9 수용 테스트, 검토 대상 WP 카드 | §6 수식 | 나머지 |
| 사람(라홈) | §1 ADR, §8-1 라운드, §11 미결 | §5 완료 기준 | 코드 수준 상세 |

용어. **WP** = 작업 패키지(한 에이전트가 한 라운드에 끝내는 단위). **계약** = `/contracts` 아래 OpenAPI·JSON Schema·SQL 마이그레이션·픽스처; 계약을 바꾸는 쪽은 오케스트레이터뿐이다. **판정기** = JEV MCP, 또는 같은 어댑터 인터페이스를 구현한 대체물. **라벨** = 확인됨·추정·비공식·재가공·확인 불가(사유) 5종, 빈칸 금지. **상황** = 기본·A(가점 높음)·B(가점 낮음·소액 자기자본)·C(시세차익 우선)·D(즉시 구매)·내 조건, 각각 요건 3개(접근 가능성·규제 제약·자금). **기준일 스냅샷** = 하루치 수집·판정·점수의 불변 묶음; 보고서와 diff의 단위.

## 1. 시스템 개요와 아키텍처 결정

프로세스는 네 개다: `web`(React 정적 번들), `api`(FastAPI), `worker`(스케줄러 + 수집 + 판정 + 점수), `db`(Postgres; 개발은 SQLite 파일). 판정기는 별도 프로세스가 아니라 `worker` 안의 클라이언트 라이브러리가 JEV MCP 서버를 stdio로 띄운다. `api`는 판정기를 직접 부르지 않고 재판정 요청을 `job_run` 행으로 넣어 `worker`가 집어가게 한다 — "판단은 판정기가, 프로그램은 수집·기록·보고만"을 프로세스 경계로 만든 것이다. 여섯 레이어(수집 → 정규화·저장 → 판정기 → 분석 → GUI·보고서 → 운영)는 메타 프롬프트 §0 그림 그대로다.

&#91;embedded content: 런타임 구성 · 프로세스 4개, 외부 소스 4종, 판정기는 worker의 자식 프로세스\]

위에서 아래로: 사람은 web만 본다, api는 읽고 잡을 등록만 한다, worker가 밖과 판정기를 전부 상대한다. 외부로 나가는 선은 worker에서 나가는 두 개뿐이다.

| # | 결정 | 선택 | 버린 대안 | 이유 | 바꿀 신호 |
| --- | --- | --- | --- | --- | --- |
| ADR-1 | 백엔드 언어·프레임워크 | Python 3.12 + FastAPI + Pydantic v2 | Node/Nest | 수집(Playwright·pdfplumber)·MCP 클라이언트·수치 계산이 한 언어; AI 코딩 도구가 가장 안정적으로 다루는 조합 | 없음 |
| ADR-2 | DB | SQLAlchemy 2 + Alembic, 개발 SQLite → 운영 Postgres 16 | Postgres만 / SQLite만 | 한 사람 개발은 파일 DB가 빠르고, 스케줄러와 API가 동시에 쓰면 Postgres가 필요 | SQLite `database is locked` 발생, 또는 지역 3개 이상 |
| ADR-3 | 스케줄·큐 | `worker` 프로세스 안 APScheduler + DB `job_run` 테이블이 큐 | Celery+Redis | 프로세스 하나를 줄이고, 작업 상태가 화면(G7)에 바로 보이게 | 일일 작업 1시간 초과 |
| ADR-4 | 수집 | httpx(정적) + Playwright chromium(팝업·동적) + pdfplumber(공고문, pypdf 폴백) + 공공데이터포털 Open API(실거래) | Selenium, OCR | 스위첸 403·리버프론트 동적 팝업은 렌더링 없이 안 읽혔다; 스캤 PDF는 "확인 불가(스캔)" 라벨로 두고 사람이 입력 | 스캔 PDF가 반 이상 |
| ADR-5 | 판정기 연결 | `JudgeAdapter` Protocol + `JevMcpAdapter`(stdio MCP) + `MockAdapter`(픽스처 재생) | HTTP 래퍼 서버 | 오프라인 테스트와 판정기 교체를 같은 인터페이스로; 호출 전 입력 해시 캐시는 어댑터 바깥에 | JEV가 HTTP를 제공할 때 |
| ADR-6 | 프론트 | React 18 + TypeScript + Vite, TanStack Query/Table(가상 스크롤), ECharts(echarts-for-react), Tailwind, React Router | Next.js, Recharts | SSR 불필요(단일 사용자); ECharts는 위스커·덤벨·스택·타임라인을 한 라이브러리로 | 없음 |
| ADR-7 | API 스타일 | contract-first REST: `/contracts/openapi.yaml`이 원본, 서버는 그에 맞추고 프론트 타입은 `openapi-typescript`로 생성 | 서버 자동 생성 | 프론트와 백엔드 에이전트가 같은 라운드에 병렬로 일하려면 계약이 먼저 고정돼야 한다 | 없음 |
| ADR-8 | 스냅샷 | 모든 파생 테이블에 `snapshot_id`(기준일); 원문은 `/data/raw/{source}/{yyyy-mm-dd}/{sha256}.{ext}` | 행 덮어쓰기 | 보고서 diff와 "어제와 무엇이 달라졌나"가 요구사항 | 없음 |
| ADR-9 | 인증 | 열람·쓰기 토큰 1개(환경변수) + 읽기 전용 공유 토큰 | 사용자 계정 | 단일 사용자; 개인정보 저장 없음 | 팀 사용 |
| ADR-10 | 배포 | docker compose 4 서비스 + 볼륨 2개(db, raw) | k8s, 서버리스 | 단일 호스트에서 `docker compose up`으로 끝 | 없음 |
| ADR-11 | 점수 계산 위치 | `worker`의 순수 함수 모듈(`analysis/`)에서만, 결과는 `score_run` 테이블에 저장; 프론트는 계산하지 않고 표시만 | 프론트 계산 | 같은 입력 = 같은 점수를 테스트로 보장하려면 한 곳에서만 | 없음 |

## 2. 저장소 구조와 소유권

모노레포 하나, 디렉터리마다 주인 WP가 하나다. 에이전트는 자기 디렉터리와 그 안의 테스트만 만들고 고친다. `/contracts`는 읽기 전용이며, 고칠 게 있으면 오케스트레이터에게 "계약 변경 요청"으로 보고한다(§8-4).

```
subscription-analyzer/
├─ contracts/                  # WP0 소유 · 나머지는 읽기 전용
│  ├─ openapi.yaml             # REST 계약 (§4-1)
│  ├─ schemas/                 # JSON Schema: complex.json, judgment_envelope.json, score_run.json …
│  ├─ migrations/              # Alembic 초기 마이그레이션 0001_init.py (§3)
│  ├─ fixtures/                # 인천·김포 회귀 데이터 (§9), 판정기 응답 녹화
│  └─ CHANGELOG.md             # 계약 변경 기록, 버전 = 날짜.연번
├─ backend/
│  ├─ app/
│  │  ├─ core/                 # WP0: 설정, DB 세션, 로깅, 스냅샷 유틸
│  │  ├─ models/               # WP0: SQLAlchemy 모델 (계약 마이그레이션과 1:1)
│  │  ├─ collectors/           # WP1: 소스별 어댑터 (applyhome/, notice_pdf/, official_site/, rtms/, stats/, news/)
│  │  ├─ normalize/            # WP2: 파서, 필드 매핑, 상충 해결, 출처 기록
│  │  ├─ judge/                # WP3: JudgeAdapter, jev_mcp.py, mock.py, cache.py, claims.py(원자 분할)
│  │  ├─ analysis/             # WP4: price.py, gap.py, ladder.py, score.py, sensitivity.py, scenarios.py (순수 함수)
│  │  ├─ api/                  # WP5: FastAPI 라우터 (regions, complexes, compare, scenarios, market, ops, reports, jobs)
│  │  ├─ scheduler/            # WP7: 잡 정의, 변경 감지(diff), 재판정 트리거, 알림
│  │  └─ reports/              # WP8: 템플릿(§1~§11), md/pdf/doc 렌더러, 32KB 분할
│  ├─ tests/                   # 각 WP가 자기 하위 디렉터리만: tests/collectors, tests/analysis …
│  └─ pyproject.toml
├─ frontend/                   # WP6
│  ├─ src/api/                 # openapi-typescript 생성 타입 + fetch 훅 (생성물, 손으로 안 고침)
│  ├─ src/pages/               # G1~G8 한 페이지 한 폴더
│  ├─ src/charts/              # C1~C10 한 차트 한 컴포넌트 (ECharts option 빌더 분리)
│  ├─ src/components/          # 라벨 배지, 출처 드릴다운, 상황 토글, 표
│  └─ src/mocks/               # MSW 핸들러 = 계약 예시 응답; API 없이 개발
├─ infra/                      # WP0: docker-compose.yml, Dockerfile.api, Dockerfile.worker, Dockerfile.web, .env.example
├─ e2e/                        # WP9: Playwright e2e, 회귀 러너
├─ docs/                       # runbook.md, region-add.md, adr/
└─ AGENTS.md                   # §8-4 공통 규칙 원문 (에이전트가 첫 번째로 읽는 파일)
```

| 디렉터리 | 주인 | 읽기 허용 | 쓰기 금지 이유 |
| --- | --- | --- | --- |
| `contracts/` | WP0(오케스트레이터) | 전체 | 계약이 바뀌면 병렬 중인 모든 WP가 깨진다 |
| `backend/app/core`, `models` | WP0 | 전체 | 모델은 마이그레이션의 거울; 다른 WP가 컬럼을 더하면 계약 위반 |
| `backend/app/collectors` | WP1 | WP2, WP7 | — |
| `backend/app/normalize` | WP2 | WP1, WP7 | — |
| `backend/app/judge` | WP3 | WP4, WP7 | 판정 로직을 다른 곳에서 흐내 내면 "같은 입력 재호출 금지"가 무너진다 |
| `backend/app/analysis` | WP4 | WP5, WP8 | 점수는 한 곳에서만(ADR-11) |
| `backend/app/api` | WP5 | WP6(계약으로만) | — |
| `backend/app/scheduler` | WP7 | — | — |
| `backend/app/reports` | WP8 | — | — |
| `frontend/` | WP6 | — | `src/api`는 생성물: 손으로 고치면 다음 생성에 사라진다 |
| `e2e/`, `contracts/fixtures` | WP9 | 전체 | 픽스처를 고치면 회귀가 맞는 것처럼 보인다; 고칠 때는 사유를 CHANGELOG에 |

공통 도구: `ruff`+`mypy --strict`(백엔드), `eslint`+`tsc --noEmit`(프론트), `pre-commit`. CI는 WP 디렉터리별로 테스트를 나눠 돌리고, `contracts/`가 바뀐 PR은 전체 테스트를 돌린다.

## 3. 데이터 모델

원칙 세 개. 금액은 원 단위 정수(`_won`), 면적은 ㎡ 소수 2자리, 날짜는 ISO 문자열; 원문 문자열은 `_text` 컬럼에 그대로 보관한다. 판정기·점수·접수 상태 같은 파생 테이블은 모두 `snapshot_id`를 가진다. 수치 필드는 예외 없이 `field_provenance`에 출처·확인일·라벨 행이 있어야 하고, 없으면 API가 그 값을 내보내지 않는다(WP5 미들웨어가 강제). 전체 DDL은 `contracts/migrations/0001_init.py`가 원본이고, 아래는 그 요약이다.

| 영역 | 테이블 | 핵심 컬럼 | 키·규칙 |
| --- | --- | --- | --- |
| 기준 | `region` | id, name, living\_areas(json: 생활권 이름·포함 법정동), age\_premium\_coef(json: 연식 대별 계수, 라벨 추정), applyhome\_query(json) | 지역 추가 = 행 1개 + 픽스처 |
| 기준 | `snapshot` | id, region\_id, asof\_date, status(building/ready/published), created\_at | (region\_id, asof\_date) 유일; 하루 1개 |
| 단지 | `complex` | id, region\_id, applyhome\_id, name, former\_names(json), address, living\_area, developer, trustee, builder, housing\_type, land\_type, price\_cap, regulated, units\_total, units\_general, units\_special, officetel\_units, notice\_date, apply\_dates(json), winner\_date, contract\_dates(json), move\_in\_ym, resale\_months, resale\_release\_on\_registration, residency\_months, rewin\_restriction\_years, inclusion\_class, inclusion\_decision, inclusion\_prob | applyhome\_id 유일; 개명은 former\_names에 추가, 행은 유지 |
| 단지 | `complex_type` | complex\_id, type\_code, area\_m2, units, max\_price\_won, floor\_sample\_price\_won, floor\_sample\_text, balcony\_won, options\_required\_won, options\_text | (complex\_id, type\_code) 유일; 판정 기준 타입은 84㎡에 가장 가까운 것 |
| 단지 | `payment_terms` | complex\_id, notice\_no, effective\_from, down\_payment\_pct, down\_payment\_first\_won, interim\_pct, interim\_terms\_text, balance\_pct, interim\_schedule(json) | 공고별 행; 최신 effective\_from이 현재 조건, 최초 대비 증감은 계산 |
| 단지 | `competition` | complex\_id, round, kind(본청약/무순위/임의/선착순), type\_code, supply, applied, ratio\_or\_shortfall\_text | 청약홈 경쟁률 페이지 원문 그대로 |
| 단지 | `remaining_event` | complex\_id, kind, notice\_no, notice\_date, apply\_dates(json), units\_by\_type(json), result\_text, raw\_document\_id | 잔여 경로 이력 = 타임라인 C8의 원천 |
| 접수 | `intake_status` | complex\_id, snapshot\_id, status(가능/미정/확인 불가/불가), path(official\_popup/headless\_shot/human\_check/unofficial\_ref), evidence\_url, screenshot\_path, http\_status, checked\_at, note, entered\_by | 같은 스냅샷에 path별 행 여러 개; 표시값 = 우선순위 human\_check > official\_popup > headless\_shot; unofficial\_ref는 판정 미사용 |
| 원문 | `raw_document` | id, source\_kind(applyhome\_list/applyhome\_detail/notice\_pdf/official\_site/rtms/stats/news), url, fetched\_at, http\_status, sha256, path, content\_type, text\_path, complex\_id? | sha256 유일 = 같은 파일 중복 저장 없음; 실패도 행(http\_status 403 등) |
| 원문 | `field_provenance` | entity, entity\_id, field, value\_text, raw\_document\_id, url, checked\_at, label(확인됨/추정/비공식/재가공/확인 불가), source\_rank, chosen(bool), conflict\_group | 한 필드에 출처가 여럿이면 행 여러 개, chosen 하나; 상충은 conflict\_group으로 묶음 |
| 시세 | `benchmark` | id, region\_id, living\_area, name, completed\_year, sale\_year, sale\_period(저가 분양기/고가 분양기), sale\_price\_84\_won, sale\_price\_label, trade\_low\_won, trade\_median\_won, trade\_high\_won, trade\_window, peak\_won, peak\_ym, is\_presale(bool) | 분양가는 자체 아카이브 공고 우선, 언론 역산은 추정 라벨; is\_presale은 벤치마크 점수 제외 |
| 시세 | `rtms_trade` | id, region\_id, apt\_name, dong, area\_m2, floor, price\_won, deal\_date, cancelled(bool), source(openapi/reprocessed), raw\_document\_id | Open API 행이 있으면 reprocessed 행은 점수에 미사용; cancelled=true 제외 |
| 시세 | `comparable_set` | complex\_id, snapshot\_id, member\_apt\_name, completed\_year, substitute(bool), adjusted(bool), coef\_used | 가격 갭 비교군 구성 기록; "대체" 배지의 근거 |
| 호재 | `catalyst` | id, region\_id, name, kind(교통/개발/학교/상업), stage(확정/계획/추진/언론/미확정), stage\_prob, expected\_ym, location\_confirmed(bool), lat, lon, raw\_document\_id | stage는 classify 결과; review면 미확정 |
| 호재 | `catalyst_link` | catalyst\_id, complex\_id, distance\_m, weight | location\_confirmed=false면 행 없음(연결 금지) |
| 시장 | `supply` | region\_id, living\_area, year, units, label, raw\_document\_id | "추정 집계"는 label에 |
| 시장 | `unsold` | region\_id, ym, total, post\_completion, source\_label | 월말 기준 |
| 판정 | `judgment_log` | seq, snapshot\_id, tool(screen/extract/audit/classify/compare/noul/rerank/decide/verify), purpose, complex\_id?, input\_hash, input\_json, output\_json, status, confidence, duration\_ms, created\_at | input\_hash 유일 = 같은 입력 재호출 금지가 DB 제약; 모든 호출은 성공·실패 불문 행 |
| 판정 | `claim` | id, snapshot\_id, section, complex\_id?, text, evidence\_text, verify\_status(verified/contradicted/unsupported/review), judgment\_seq | 원자 주장 1행 1건; contradicted가 남으면 스냅샷 published 불가 |
| 분석 | `scenario` | id, name, is\_builtin, params(json: 거주지·무주택·가점·자기자본·한도·목적·보유기간·평형·입주시기), weights(json 6개), requirements(json 3개 규칙) | builtin 5개(기본·A·B·C·D) 시드; 사용자 시나리오는 추가 |
| 분석 | `score_run` | id, snapshot\_id, scenario\_id, weights(json), rerank\_judgment\_seq, created\_at | 한 run의 rerank 값은 한 호칭에서만(§6-5) |
| 분석 | `score_component` | score\_run\_id, complex\_id, component(p10/rerank/gap/benchmark/supply/liquidity), raw\_value, score\_0\_10, formula\_text, label | formula\_text가 툴팁에 그대로 |
| 분석 | `score_total` | score\_run\_id, complex\_id, total, rank, tie\_group?, unstable(bool) | 동점은 같은 rank; unstable = 민감도에서 TOP 5 구성 변동 |
| 분석 | `ladder` | snapshot\_id, complex\_id, horizon(move\_in\_plus\_1y/asof\_plus\_3y/asof\_plus\_5y), target\_ym, p5, p10, p20, p\_flat, verdicts(json), annualized(json), judgment\_seq | noul 결과; horizon 3종 |
| 분석 | `decision` | score\_run\_id, scenario\_id, complex\_id, prob, chosen(bool), tie(bool), req\_access\_pre, req\_regulation\_pre, req\_funds\_pre(사전 계산: 충족/미충족 + 근거 숫자), req\_access\_judge, req\_regulation\_judge, req\_funds\_judge(supported/contradicted/unknown), mismatch(bool), confidence, warnings(json), judgment\_seq | mismatch = 사전 계산과 판정기 불일치 → "증거와 상이" 배지 |
| 운영 | `human_check` | id, complex\_id, field, value\_text, kind(phone/visit/email), checked\_at, entered\_by, note | G7 입력; field=intake\_status면 intake\_status에 human\_check 행 생성 |
| 운영 | `checklist_item` | id, complex\_id?, kind(법적 확인/중도금/만료/공고 예상), title, due\_date, status(open/done/na), note | 토허·대지지분·비과세 거주요건 등 추정 항목의 처리 상태 |
| 운영 | `change_event` | id, snapshot\_id, entity, entity\_id, field, old\_text, new\_text, detected\_at, severity(info/notice/critical), triggers\_rejudge(bool) | 새 공고·팝업 변경·중도금일·가격 변경은 critical |
| 운영 | `job_run` | id, job\_name, kind(scheduled/manual/rejudge), payload(json), scheduled\_at, started\_at, finished\_at, status(queued/running/done/failed), stats(json), error\_text | API가 큐로 사용; worker가 polling |

라벨 정의는 메타 프롬프트 §2-2 그대로: **확인됨**(공고문·청약홈·Open API 원문), **추정**(산술·가정), **비공식**(언론·블로그·홍보), **재가공**(원본 아닌 가공 데이터), **확인 불가(사유)**. "사람 확인"은 라벨이 아니라 `intake_status.path`·`human_check` 행으로 표현하고, 화면에서는 확인됨 배지에 "사람" 접두어를 붙인다.

| 필드 군 | 출처 우선순위(source\_rank 1→3) | 상충 처리 |
| --- | --- | --- |
| 세대수·면적·일정·경쟁률 | 청약홈 상세 > 공고문 > 언론 | rank 1 채택, 나머지 chosen=false로 보관, conflict\_group 기록; compare 미호출 |
| 가격·발코니·옵션·납부·전매·거주의무 | 공고문(최신) > 청약홈 > 언론 | 같음 |
| 접수 상태 | human\_check > official\_popup > headless\_shot > unofficial\_ref | 우선순위 채택, 더 낮은 경로는 참고 열 |
| 실거래 | Open API > 재가공 사이트 | Open API 있으면 재가공 미사용; 없으면 재가공 라벨로 사용 |
| 1차 자료 둘이 상충(청약홈 vs 공고문) | 우선순위 없음 | compare 호출; contradicts면 공고문 채택·병기, 둘 다 2차면 병기·판정 미사용 |

스냅샷 규칙: `complex`·`complex_type`·`payment_terms` 같은 사실 테이블은 현재값만 두고 변경은 `change_event`에 남긴다. 파생 테이블(intake\_status, judgment\_log, claim, score\_\*, ladder, decision)은 `snapshot_id`별로 쌓이고 삭제하지 않는다. 보고서와 diff는 두 snapshot\_id의 파생 테이블 비교로 만든다.

## 4. 인터페이스 계약

계약은 세 겹이다: 프론트↔백엔드는 REST(`contracts/openapi.yaml`), 백엔드 모듈 사이는 Python Protocol(`backend/app/core/protocols.py`, WP0 소유), 프로세스 사이는 `job_run.payload` JSON. 세 겹 모두 `contracts/schemas/`의 JSON Schema가 원본이고 Pydantic 모델과 TS 타입은 거기서 생성한다. 버전은 `2026-10-09.1`처럼 날짜.연번이며, 필드 삭제·의미 변경은 오케스트레이터만 한다.

### 4-1 공통 타입

수치는 맨값으로 나가지 않는다. 모든 수치·날짜 필드는 `Fact`로 감싸고, 화면은 `prov`로 출처 패널을 연다.

```json
{
  "Fact":    {"v": 749000000, "label": "확인됨", "prov": "fp_01HX…", "checked_at": "2026-10-08"},
  "Label":   "확인됨 | 추정 | 비공식 | 재가공 | 확인 불가",
  "Intake":  {"status": "가능 | 미정 | 확인 불가 | 불가", "path": "human_check | official_popup | headless_shot | unofficial_ref", "evidence_url": "…", "checked_at": "…", "http_status": 403},
  "JudgmentEnvelope": {
    "tool": "decide", "purpose": "scenario_B", "input_hash": "sha256:…",
    "status": "ok | review | escaped | blocked | error", "confidence": 0.48, "cached": true,
    "result": {}, "raw": {}, "duration_ms": 1830, "judgment_seq": 1187, "created_at": "…"
  },
  "Error":   {"code": "intake_unknown | judge_unavailable | contract_violation | not_found", "detail": "…"}
}
```

`JudgmentEnvelope.status`가 `review`·`escaped`·`blocked`이면 `result`는 표시만 하고 점수·추천에 쓰지 않는다(프론트가 아니라 WP4가 걸러낸다). `cached=true`는 같은 `input_hash`의 이전 행을 돌려준 것이고, 화면은 "캐시" 배지를 붙인다.

### 4-2 REST 엔드포인트

모든 요청은 `Authorization: Bearer <token>`; 읽기 전용 토큰은 GET만. 목록은 `?page&size&sort&filter[...]`, 응답은 `{items, total, snapshot_id, asof_date}`.

| 메서드 | 경로 | 용도 | 응답 스키마 | 화면 |
| --- | --- | --- | --- | --- |
| GET | `/regions` | 지역·생활권·최신 스냅샷 | `Region[]` | 전체 헤더 |
| GET | `/regions/{id}/snapshots` | 기준일 목록 | `Snapshot[]` | G1, G8 |
| GET | `/snapshots/{sid}/dashboard?scenario=` | KPI 타일, TOP 5, 최근 변경 | `Dashboard{kpis, top5: ScoreRow[], changes: ChangeEvent[]}` | G1 |
| GET | `/snapshots/{sid}/complexes` | 단지 표(필터·정렬·페이지) | `Page<ComplexRow>` (Fact 필드 20개 내외) | G2 |
| GET | `/snapshots/{sid}/complexes.csv` | 같은 필터로 CSV | text/csv | G2 |
| GET | `/complexes/{id}?snapshot=` | 단지 상세 전체 | `ComplexDetail{header, types[], payment[], events[], intake: Intake[], ladder[], gap, catalysts[], judgments: JudgmentEnvelope[]}` | G3 |
| GET | `/provenance/{prov_id}` | 출처 행 + 원문 발췌 + 상충 그룹 | `Provenance{url, checked_at, label, excerpt, raw_document_id, conflicts[]}` | 출처 패널(공통) |
| GET | `/raw/{raw_document_id}` | 원문 파일(PDF·txt·스크린샷) | 파일 | G3, G7 |
| GET | `/snapshots/{sid}/compare?ids=&scenario=` | 2\~6개 비교 | `CompareView{rows: ScoreRow[], components, ladders, gaps, terms, decisions}` | G4 |
| GET | `/snapshots/{sid}/sensitivity?scenario=` | 가중치 ±10%p 순위 변동 | `Sensitivity{cells[], unstable: bool}` | G4, G5 |
| GET/POST | `/scenarios` | 내장 5 + 사용자 시나리오 | `Scenario[]` / `Scenario` | G5 |
| GET | `/scenarios/{id}/preview?snapshot=` | 가중치·요건 사전 계산(판정기 호출 없음) | `ScenarioPreview{weights, requirements_pre: per complex, cache_hits}` | G5 |
| POST | `/jobs` | 재판정·수집·보고서 잡 등록 | `JobRun` (202) | G5, G7, G8 |
| GET | `/jobs/{id}` | 진행 상태 | `JobRun` | 공통 |
| GET | `/snapshots/{sid}/market` | 벤치마크·입주물량·미분양·호재·규제 요약 | `Market{benchmarks[], supply[], unsold[], catalysts[], regulation}` | G6 |
| GET | `/snapshots/{sid}/changes?since=` | 변경 피드 | `ChangeEvent[]` | G1, G8 |
| GET | `/ops/sources` | 소스별 최종 수집·성공·실패 | `SourceStatus[]` | G7 |
| GET | `/ops/judgments?since=` | 호출 수·실패·소요·도구별 | `JudgmentStats + JudgmentEnvelope[]` | G7 |
| GET/PATCH | `/ops/checklist`, `/ops/checklist/{id}` | 체크리스트·캘린더 | `ChecklistItem[]` | G7 |
| POST | `/ops/human-checks` | 사람 확인 입력 | `HumanCheck` → intake\_status 행 생성 + change\_event | G7 |
| POST | `/reports` | 보고서 생성(md/pdf/docx, diff 옵션) | `JobRun` | G8 |
| GET | `/reports/{id}` | 다운로드 | 파일 | G8 |

`ScoreRow` = `{complex_id, name, total: Fact, rank, tie_group, unstable, p10: Fact, components: {p10, rerank, gap, benchmark, supply, liquidity}: Fact, intake: Intake, decision?: {prob, chosen, tie, mismatch}}`. `ComplexRow`는 G2 표의 열과 1:1(이름·생활권·접수·현재 구매가 범위·전매 종료·입주·가격 갭·종합 점수·포함 분류·마지막 변경).

### 4-3 내부 프로토콜 (Python)

| Protocol | 메서드 | 규칙 | 구현 WP |
| --- | --- | --- | --- |
| `Collector` | `fetch(region, snapshot, since) -> list[RawDocument]` | 멱등: 같은 sha256이면 저장 안 함; 실패도 `RawDocument(http_status=…)`로 반환; robots·속도 제한은 `core.http`가 강제 | WP1 |
| `Parser` | `parse(raw) -> list[FieldCandidate]` | 후보는 (entity, field, value\_text, value, source\_rank, label, excerpt); 원문 발췌 필수 | WP2 |
| `Resolver` | `resolve(candidates) -> ResolvedFields` | §3 우선순위로 chosen 결정, 상충 기록, 1차·1차 상충만 `needs_compare=True` | WP2 |
| `JudgeAdapter` | `screen/extract/audit/classify/compare/noul/rerank/decide/verify(payload, purpose) -> JudgmentEnvelope` | 호출 전 `input_hash` 조회 → 있으면 cached 봉투; 없으면 호출 후 `judgment_log` 기록; 예외는 `JudgeUnavailable` 하나로 | WP3 |
| `ClaimSplitter` | `split(text) -> list[Claim]` | 1 사실 = 1 주장; 접속사·열거를 나눔; 숫자 2개 이상이면 분할 | WP3 |
| `ScoreEngine` | `run(snapshot, scenario, inputs) -> ScoreRunResult` | 순수 함수(DB 접근 없음); 같은 inputs = 같은 결과; 각 component에 formula\_text | WP4 |
| `RequirementPrecalc` | `evaluate(complex, scenario) -> {access, regulation, funds}` | §6-7 규칙로 충족/미충족 + 근거 숫자 문자열 | WP4 |
| `Exporter` | `render(snapshot, fmt, compare_snapshot=None) -> Path` | 섹션 단위 분할(32KB), 부록 URL 전수 | WP8 |

### 4-4 잡 페이로드

| job\_name | payload | 누가 넣나 | 누가 집나 |
| --- | --- | --- | --- |
| `collect.daily` | `{region_id, sources:[applyhome_list, official_site]}` | 스케줄러 06:00 | worker |
| `collect.weekly` | `{region_id, sources:[rtms, stats, news]}` | 스케줄러 월 06:30 | worker |
| `rejudge` | `{snapshot_id, scenario_id, complex_ids?: [], reason}` | 변경 감지 / G5 버튼 | worker |
| `report` | \`{snapshot\_id, format: md | pdf | docx, compare\_snapshot\_id?}\` |
| `snapshot.publish` | `{snapshot_id}` | 재판정 완료 후 자동 | worker (claim contradicted 0 검사) |

### 4-5 픽스처 계약

`contracts/fixtures/incheon_gimpo_2026-10-08/`에 `complexes.json`(단지 16개, Fact 형식), `judgments/*.json`(녹화된 봉투, tool·input\_hash별), `expected_scores.json`(§9 표의 숫자), `raw/`(공고문 txt 발췌). `MockAdapter`는 input\_hash로 녹화를 찾고, 없으면 `status=review`를 돌려준다 — 테스트가 조용히 통과하는 일은 없다.

## 5. 작업 패키지 WP0\~WP9

한 WP = 한 에이전트가 한 라운드에 끝내는 단위. 카드의 "완료 기준"은 전부 자동 테스트로 표현되어야 하고, 리뷰 에이전트는 그 테스트가 있고 통과하는지만 본다. 크기 S/M/L은 에이전트 한 명 기준 반나절/하루/이틀의 느낌이며, L은 필요하면 카드에 적힌 선으로 두 에이전트에 나눈다.

| WP | 목표 | 산출물(파일) | 의존 | 완료 기준(자동 테스트) | 크기 |
| --- | --- | --- | --- | --- | --- |
| **WP0 계약·뼈대** | 나머지 WP가 서로 기다리지 않고 시작할 수 있게 계약과 실행 뼈대를 고정 | `contracts/openapi.yaml`, `schemas/*.json`, `migrations/0001_init.py`, `fixtures/` 디렉터리와 README; `backend/app/core/`(settings, db, http 클라이언트: 재시도·백오프·속도 제한·robots, logging, snapshot 유틸), `models/`, `core/protocols.py`; `infra/`(compose, Dockerfile 3개, .env.example); `frontend/` 스캐폴드(Vite+TS+Router+TanStack+ECharts+Tailwind+MSW, openapi 예시로 핸들러 생성); `AGENTS.md`; CI | 없음 | `docker compose up` 후 `/health` 200, web이 G1 골격을 MSW로 렌더; `alembic upgrade head`가 SQLite·Postgres 둘 다 성공; `openapi-typescript` 생성 성공; 모든 WP 디렉터리에 주인을 적은 README | M |
| **WP1 수집 어댑터** | 소스 6종을 원문 그대로, 실패도 데이터로 저장 | `collectors/applyhome/`(APT 분양정보·무순위/잔여 목록 2개 POST 조회, 상세·경쟁률 페이지), `notice_pdf/`(PDF → pdfplumber txt, 스캔 감지 시 확인 불가(스캔)), `official_site/`(httpx → 실패·동적이면 Playwright 렌더 → 스크린샷+DOM 텍스트+이미지 해시; 403·DNS 실패도 행), `rtms/`(국토부 실거래가 Open API, 법정동·월 단위, 재가공 폴백은 인터페이스만), `stats/`(미분양 월별, 입주물량 집계), `news/`(뉴스 검색 API, URL·제목·발췌만) | WP0 | collector마다 녹화 HTTP 픽스처(respx) 테스트; 같은 입력 2회 실행 → `raw_document` 증가 0; 403 픽스처 → `http_status=403` 행; 팝업 렌더 테스트에서 PNG와 해시 생성; 지역 1개 일일 수집 10분 이내 | L (분할선: applyhome+notice\_pdf / official\_site+rtms+stats+news) |
| **WP2 정규화·저장** | 원문 → 필드 후보 → 상충 해결 → 출처 행까지, 숫자 하나도 출처 없이 남기지 않기 | `normalize/applyhome_parser.py`, `notice_parser.py`(가격표 타입·층·공급금액, 발코니, 옵션, 납부 조건, 전매·거주·재당첨, 입주월: 정규식+표 파서, 실패 필드는 extract 요청 payload로 넘김), `resolver.py`(§3 우선순위, conflict\_group), `provenance.py`, `changes.py`(이전값 diff → change\_event), `archive.py`(월별 목록·공고·경쟁률 스냅샷 보관) | WP0 (RawDocument 계약만; WP1 코드 불필요) | 인천·김포 공고문 발췌 16개 → `complex_type` 가격이 expected와 원 단위 일치; 해링턴 1,573 vs 1,769 → conflict\_group 1건 + chosen=청약홈; 테스트가 모든 수치 필드의 provenance 행 존재를 전수 검사; 임의공급 계약금 10%→5% 변경이 change\_event critical | L (분할선: notice\_parser / 나머지) |
| **WP3 판정기 어댑터** | 판단은 여기서만, 같은 입력 재호출은 코드가 막고, 공개 텍스트만 나간다 | `judge/base.py`(Protocol, 봉투), `jev_mcp.py`(stdio MCP 클라이언트, 도구 9개, 임계값 설정: screen block 0.75/review 0.25 · extract/classify/noul auto 0.85 · audit wrong\_at 0.7 · verify auto 0.8), `cache.py`(input\_hash = sha256(canonical JSON{tool, purpose, payload, adapter\_version})), `log.py`, `mock.py`, `claims.py`(원자 분할), `payloads.py`(증거 카드 ≤2,000자, 사다리 명제 3 horizon, decide 후보 ≤6 + 요건 사전 계산 문자열 삽입, rerank 전체 후보 1회), `guard.py`(전화번호·주민번호·이메일 패턴·환경변수 값이 payload에 있으면 거부) | WP0 | Mock 재생 시 봉투 동일; 같은 payload 2회 → 실제 호출 1회(cached=true); "3개는 unlikely이고 나머지는 uncertain" → 주장 2개 이상; guard가 전화번호 포함 payload 거부; JEV 실제 연결 smoke 1회(수동, 기록) | M |
| **WP4 분석 엔진** | §6 수식을 순수 함수로; 같은 입력 = 같은 점수 | `analysis/price.py`, `gap.py`(비교군·연식 보정·점수), `ladder.py`(명제 3 horizon, 연율), `score.py`(6 component 식 + 가중 합 + 동점·동률), `sensitivity.py`, `scenarios.py`(내장 5 + 요건 사전 계산), `types.py`(dataclass 입력) | WP0 (판정 값은 봉투 형태 입력; WP3 코드 불필요) | `expected_scores.json` 재현(소수 2자리); conf 0.48 decide → tie=true; 엘리프 전매 요건 사전 계산 = 충족 + 근거 문자열; 가중치 ±10%p 민감도에서 TOP 5 변동 감지; 모든 component에 formula\_text 비어 있지 않음 | M |
| **WP5 API 서버** | 계약을 그대로 구현, 출처 없는 숫자는 나가지 못하게 | `api/routers/*.py`(8개), `api/deps.py`(인증, 스냅샷 해석), `api/facts.py`(Fact 래핑 미들웨어: provenance 없는 수치 → dev에서 예외, prod에서 라벨 "확인 불가(출처 누락)" + 경고 로그), `api/jobs.py`(job\_run 등록), CSV·파일 서빙 | WP0; WP3·WP4 읽기만(라운드 2) | schemathesis가 `openapi.yaml` 대비 전 엔드포인트 통과; 1,000단지 픽스처 리스트 응답 1초 이내; 읽기 전용 토큰 POST → 403; provenance 없는 픽스처 → contract\_violation | M |
| **WP6 프론트 GUI** | G1\~G8·C1\~C10, 숫자는 항상 라벨과 출처 패널과 함께 | `src/pages/{dashboard,complexes,complex,compare,scenario,market,ops,reports}/`, `src/charts/C01~C10`, `src/components/`(FactCell, LabelBadge, IntakeBadge, ProvenancePanel, ScenarioToggle, CachedBadge, TieBadge, MismatchBadge, SnapshotPicker), `src/mocks/`(MSW, 계약 예시 데이터 = 인천·김포 픽스처) | WP0 (openapi + 스캐폴드); 실제 API는 라운드 3에서 연결 | 8 라우트 렌더 + Playwright(MSW) 화면별 핵심 요소; 숫자 셀 클릭 → 출처 패널; ESLint 규칙 "FactCell 밖에서 숫자 렌더 금지"; 차트 10개 각각 빈 데이터·라벨 배지 상태 스크린샷 테스트; Lighthouse 성능 80 이상 | L (분할선: pages / charts+components) |
| **WP7 스케줄러·변경 감지** | 변화가 없는 날은 판정기 호출 0, 변화가 있으면 그 단지만 재판정 | `scheduler/jobs.py`(daily 06:00, weekly 월 06:30), `runner.py`(job\_run polling, 락), `detect.py`(팝업 이미지 해시·목록 diff·새 공고), `rejudge.py`(변경 complex\_ids만, 파이프라인 P1\~P9 순서), `notify.py`(웹훅 URL 1개), `degraded.py`(JudgeUnavailable → 미판정 모드 플래그) | WP1·WP2·WP3·WP4 (라운드 2) | 변경 없는 날 시뮬레이션 → 판정기 호출 0; 팝업 이미지 변경 픽스처 → change\_event critical 1 + rejudge job 1; 동시 실행 2개 → 하나만 동작; 판정기 다운 → 수집은 성공하고 degraded 플래그 | M |
| **WP8 보고서 내보내기** | §1\~§11(+지역 추가 장) 표 중심 보고서를 md/pdf/docx로, 두 스냅샷 diff 포함 | `reports/templates/*.md.j2`(섹션 11 + 부록 A 판정 로그 · B 참고자료), `render.py`(md → weasyprint pdf → python-docx), `chunk.py`(32KB 섹션 분할), `diff.py` | WP3·WP4 읽기 (라운드 2) | 픽스처 스냅샷으로 3포맷 생성; md 청크 각 ≤32KB; URL 전수 형식 검사; 보고서 숫자 20개 샘플이 `score_total`과 일치; contradicted claim이 있으면 생성 거부 | M |
| **WP9 테스트·회귀** | 인천·김포가 영구 회귀 데이터가 되게; 통합은 여기서 검증 | `contracts/fixtures/incheon_gimpo_2026-10-08/`(§4-5), `e2e/`(Playwright, 실제 API + Mock 판정기), `make regress`, schemathesis 통합, 성능 스크립트 | 라운드 1: 픽스처(WP0만 의존) · 라운드 3: 통합(전부) | §9 전 케이스 통과; CI green; 픽스처 수정 시 CHANGELOG 사유 필수 | M |

에이전트가 카드를 받으면 첫 일은 "완료 기준을 실패하는 테스트로 먼저 쓰는 것"이다. 그 다음 구현, 마지막에 §8-5 형식의 완료 보고를 낸다. 카드에 없는 것을 만들고 싶으면 만들지 말고 보고에 "제안"으로 적는다.

## 6. 분석 규칙 수식

모든 식은 `analysis/`의 순수 함수이고, 식의 문자열이 `score_component.formula_text`로 저장돼 화면 툴팁에 그대로 보인다. 계수(연식 보정·공급 기준치)는 `region` 설정에 있고 라벨은 항상 "추정"이다. 사람이 등급을 매기는 자리는 없다.

### 6-1 현재 구매가

판정 타입은 전용 84㎡에 가장 가까운 `complex_type`. 범위의 아래는 공고문 대표층 공급금액, 위는 최고가이고 둘 다에 발코니 확장비와 필수 옵션을 더한다. 점수는 중앙값을 쓴다. 할인은 `label=확인됨`인 것만 빼고, 임의공급에서 가격이 바뀐 경우 최신 `payment_terms.effective_from`의 값을 쓰고 최초 공고 대비 증감률을 병기한다.

```latex
P_{low} = P_{floor} + B + O,\qquad P_{high} = P_{max} + B + O,\qquad P_{mid} = \tfrac{1}{2}(P_{low}+P_{high})
```

### 6-2 비교군과 가격 갭

비교군 = 같은 생활권, 준공 2020년 이후, 전용 80\~85㎡, 기준일 이전 6개월 거래, `cancelled=false`, Open API 행 우선. 3건 미만이면 준공 연도가 가장 최근인 단지로 대체하고(`substitute=true`), 대체 단지의 거래가는 연식 보정값과 미보정값을 나란히 계산한다. 점수에는 보정값을 쓰고 라벨은 "추정(대체·보정 c=…)".

```latex
T_{adj} = T \cdot \bigl(1 + c \cdot \min(Y_{ref} - Y_{built},\, 8)\bigr),\qquad
gap\% = \frac{P_{mid} - \operatorname{median}(T_{adj})}{\operatorname{median}(T_{adj})}\times 100,\qquad
s_{gap} = \operatorname{clamp}\!\bigl(5 - \tfrac{gap\%}{4},\,0,\,10\bigr)
```

`c`는 `region.age_premium_coef`(예: 0.015/년, 라벨 추정), `Y_ref`는 판정 단지 입주 연도. 화면 C2는 미보정 중앙값을 점선 점으로 같이 그린다.

### 6-3 사다리 명제 (3개 시점)

| horizon | 목표 시점 | 쓰임 |
| --- | --- | --- |
| `move_in_plus_1y` | 입주월 + 12개월 (즉시 입주면 기준일 + 12개월) | 단지 자체 판단, `s_p10`의 입력 |
| `asof_plus_3y` | 기준일 + 36개월 | 입주 시기가 다른 단지 비교 |
| `asof_plus_5y` | 기준일 + 60개월 | 장기 보유 상황 C |

명제 템플릿은 메타 프롬프트 §2-2 그대로(+5/+10/+20/보합·하락). 화면 표에는 연율 환산 열을 둔다:

```latex
r_{annual} = (1+g)^{12/m} - 1,\qquad m = \text{기준일부터 목표 시점까지의 개월 수}
```

### 6-4 구성 점수 6개 (각 0\~10)

| component | 식 | 입력 라벨 규칙 |
| --- | --- | --- |
| `p10` | `10 × P(+10%, move_in_plus_1y)` (noul 확률) | noul status가 review/escaped면 null → 종합 점수 미계산, 표시 "미판정" |
| `rerank` | `10 × (N − rank) / (N − 1)` (한 호출 안의 순위, N = 후보 수) | §6-5 고정 앞커 |
| `gap` | §6-2 | 대체·보정이면 추정 |
| `benchmark` | `clamp(10 × median(gain) / 0.5, 0, 10)`, gain = (입주 후 실거래 중앙 − 분양가)/분양가, `is_presale=false`인 벤치마크만 | 표본 3 미만이면 라벨 "추정(표본 n)"; 최근 3년 분양 사례 0건이면 플래그 `no_recent_sale_case` |
| `supply` | `clamp(10 − 10 × U_window / U_ref, 0, 10) − pen`, U\_window = 같은 생활권에서 move\_in\_plus\_1y ±12개월 입주 세대수, U\_ref = `region.supply_ref_units`(생활권 가구수의 8%, 추정), pen = 미분양 12개월 기울기 > 0 → 2, 준공 후 미분양 증가 → +1 | 입주물량이 "추정 집계"면 추정 |
| `liquidity` | `clamp(10 − 2×Y_resale − 3×[거주의무>0] − D/5, 0, 10)`, Y\_resale = 기준일부터 전매 종료까지 연수(등기 시 해제면 입주월 기준), D = 계약금 % | 전부 공고문 확인됨 |

```latex
S = \sum_{i} w_i\, s_i,\qquad \sum_i w_i = 1
```

| 상황 | p10 | rerank | gap | benchmark | supply | liquidity → 대체 | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기본 | 0.35 | 0.20 | 0.15 | 0.10 | 0.10 | 0.10 | 메타 프롬프트 기본값 |
| A 가점 높음(실거주) | 0.35 | 0.20 | 0.15 | 0.10 | 0.10 | `move_in` 0.10 | liquidity 대신 `s_movein = clamp(10 − 2×입주까지 연수, 0, 10)` |
| B 가점 낮음·소액 | 0.30 | 0.15 | 0.20 | 0.10 | 0.10 | 0.15 | 자금 요건이 더 자주 미충족 |
| C 시세차익 | 0.45 | 0.15 | 0.15 | 0.05 | 0.05 | 0.15 | 사다리 horizon은 `asof_plus_5y` |
| D 즉시 구매 | 0.35 | 0.20 | 0.15 | 0.10 | 0.10 | `move_in` 0.10 | 접수 불가 단지는 후보에서 제외 |
| 내 조건 | 사용자 입력 |  |  |  |  |  | 표 제목에 가중치 표기 |

동점·동률: `|S_i − S_j| < 0.05`면 같은 rank(공동 순위). decide `confidence < 0.6`이면 상위 2개를 `tie=true`로 표시하고 1순위를 하나로 말하지 않는다(김포 상황 B: 칸타빌 0.54 vs 엘리프 0.42, conf 0.48 → 동률).

### 6-5 rerank 고정 앞커

한 `score_run`의 rerank 값은 반드시 같은 `judgment_seq` 한 호출에서 나온 것만 쓴다. 후보군이 바뀌면(단지 추가·지역 추가) 과거 후보를 전부 포함해 1회 재호출하고, 이전 run과의 점수 차이를 `delta_rerank` 열로 낸다. 인천 8개 → 16개에서 0.02\~0.06 움직였던 것이 이 규칙의 이유다.

### 6-6 민감도

가중치 6개 각각 ±0.10을 주고 나머지를 비례로 재정규화한 12개 변형에서 TOP 5 집합을 다시 구한다. 한 번이라도 집합이 바뀌면 `score_total.unstable=true`("순위 불안정" 배지). 변동 없는 가중치는 화면에서 회색.

### 6-7 요건 사전 계산 (decide 증거에 삽입)

| 요건 | 충족 조건 | 근거 문자열 예 |
| --- | --- | --- |
| 접근 가능성 | `intake_status ∈ {가능}` and path ≠ unofficial\_ref; A: 가점제 공급 존재; B·D: 무순위·임의·선착순 접수 가능; C: 전매 종료 ≤ 목표 매도 시점 | "접수 가능(공식 팝업 2026-10-07); 전매 종료 2028-09 < 매도 시작 2030-03 → 충족" |
| 규제 제약 | 거주의무·재당첨 제한·규제지역 요건이 시나리오 params(무주택·재당첨 이력·거주 계획)와 충돌 없음 | "거주의무 0개월, 재당첨 제한 미적용(비규제) → 충족" |
| 자금 | `P_mid × D ≤ 자기자본` and `P_mid − 대출한도 − 자기자본 ≤ 0`; 중도금 조건 문자열에 무이자·이자후불제가 있으면 표기 | "계약금 7,490만 ≤ 자기자본 1억; 잔금 부족 0 → 충족 (중도금 이자후불제)" |

사전 계산 결과와 판정기의 supported/contradicted가 다르면 둘 다 저장하고 `decision.mismatch=true`. 자기자본·한도가 비어 있는 기본 상황에서 자금 요건은 "미입력"으로 보내고 unknown을 그대로 받는다.

## 7. 화면·차트 구현 명세

화면의 질문·요소·연결 데이터는 메타 프롬프트 §2-6·§2-7이 원본이고, 여기는 그것을 라우트·컴포넌트·API·ECharts 시리즈로 바꾼 구현 표다. 공통 규칙 네 개: 숫자는 `FactCell`로만 렌더(라벨 배지 + 클릭 시 `ProvenancePanel`), 상황 토글은 URL 쿼리 `?scenario=`로 전 화면 공유, 기준일은 `?snapshot=`, 차트는 뷰포트 진입 시 lazy load.

### 7-1 화면 G1\~G8

| # | 라우트 | 주요 컴포넌트 | API | 상호작용·상태 |
| --- | --- | --- | --- | --- |
| G1 홈 | `/` | `RegionPicker`, `SnapshotPicker`, `KpiTiles`(5), `Top5Cards`(ScoreRow → 종합·p10·IntakeBadge·TieBadge·unstable), `ScenarioToggle`, `ChangeFeed`, C5 작게, C6 | `/snapshots/{sid}/dashboard`, `/changes` | 상황 토글 → dashboard 재조회; 카드 클릭 → G3; 피드 항목 클릭 → G3 해당 탭 |
| G2 단지 리스트 | `/complexes` | `FilterBar`(생활권·접수·택지·전매 종료일·가격대·입주연도·포함 분류), `ComplexTable`(TanStack Table + 가상 스크롤, 열 선택 저장), `CompareTray`(체크 2\~6) | `/snapshots/{sid}/complexes`, `.csv` | 필터는 URL 쿼리; CSV는 같은 쿼리로 서버 생성; "비교" → G4 |
| G3 단지 상세 | `/complexes/:id` | `ComplexHeader`(IntakeBadge·현재 구매가 범위·전매 D-day), 탭 8개: `PriceTable`, `PaymentTerms`, C8, C1, C2, `CatalystList`(+C9 작게), `ProvenanceTab`(원문 하이라이트: raw txt + excerpt 오프셋), `JudgmentLogTab`(봉투 목록, CachedBadge) | `/complexes/{id}`, `/provenance/{id}`, `/raw/{id}` | 탭은 URL 해시; 원문 탭은 지연 로드; review/escaped 봉투는 회색 + "미해결" |
| G4 비교 | `/compare?ids=` | `CompareGrid`(열 = 단지), C6 가로, C1 overlay(점), C2 나란히, `TermsTable`(전매·거주·계약금·자기자본), `DecisionPanel`(C7, MismatchBadge, TieBadge), C10 | `/snapshots/{sid}/compare`, `/sensitivity` | ids 2\~6 검사; 상황 토글 공유 |
| G5 시나리오 | `/scenario` | `ScenarioForm`(10 필드, zod 검증), `WeightPreview`(슬라이더 6개, 합 1 제약), `RequirementPreview`(단지별 요건 3개 사전 계산 표), `RunButton`(캐시 히트 수 표시 → POST /jobs), `JobProgress`, `DiffTable`(이전 run 대비 순위·점수), C7, C10 | `/scenarios`, `/scenarios/{id}/preview`, `/jobs`, `/jobs/{id}` | 저장 → scenario 행; 실행 중 폴링 2초; escaped 봉투 → 상단 배너 "판정기가 질문을 남겼습니다" + 질문 텍스트 |
| G6 지역 시장 | `/market` | C3, C4, C5, C9 보드+타임라인, `RegulationCard`, `LivingAreaCompare`(생활권별 실거래 중앙값 표) | `/snapshots/{sid}/market` | 생활권 필터 |
| G7 데이터·운영 | `/ops` | `SourceStatusTable`(소스·최종 수집·성공/실패·http\_status·재시도 버튼), `RejudgeQueue`(job\_run), `Checklist`+`Calendar`(중도금일·만료·공고 예상), `JudgmentStats`(30일 호출 수·실패·도구별 막대), `HumanCheckForm`(단지·필드·값·종류·메모) | `/ops/*`, `/jobs` | 사람 확인 저장 → intake 배지 즉시 갱신 + 재판정 잡 제안 토스트; degraded 플래그면 전역 배너 |
| G8 보고서 | `/reports` | `SnapshotPairPicker`, `FormatSelect`(md/pdf/docx), `GenerateButton` → `JobProgress`, `ReportList`(다운로드), `SnapshotDiffTable` | `/reports`, `/reports/{id}`, `/changes` | contradicted claim 있으면 버튼 비활성 + 사유 |

### 7-2 차트 C1\~C10 (ECharts)

| # | 차트 | 시리즈 | 데이터 소스 | option 핵심 | 빈·특수 상태 |
| --- | --- | --- | --- | --- | --- |
| C1 | 상승 확률 사다리 | `bar` 가로 4개, `markLine` 0.15/0.85 | `ComplexDetail.ladder[horizon]` (p5, p10, p20, p\_flat) | xAxis 0\~1, 막대 라벨 = 확률 + verdict, 부제 = 목표 시점(연도 반기), horizon 탭 3개 | review → 회색 막대 + "미해결"; G4에서는 `scatter` overlay |
| C2 | 가격 갭 | `custom`(점+위스커) 또는 `boxplot` 1열 + `scatter` | `gap{price_low, price_high, price_mid, comps[]: {name, low, median, high, adjusted_median, substitute}}` | y축 억 단위 formatter, 배지 "신축/대체(준공년)", 보정 중앙값은 점선 테두리 점 | 비교군 0 → "비교군 없음(사유)" 플레이스홀더 |
| C3 | 벤치마크 slope | `custom` dumbbell(분양가 → 실거래 범위) + `scatter` 고점 마커 | `Market.benchmarks[]` | 행 = 벤치마크, 라벨 분양 연도, 툴팁 연율, `is_presale` 별도 마커 모양 | 표본 < 3 → "표본 n, 추정" 배지 |
| C4 | 입주 물량 | `bar` stacked(생활권) + `markPoint` 판정 단지 입주월 | `Market.supply[]` | x = 연도, y = 세대, 라벨 "추정 집계" | — |
| C5 | 미분양 추이 | `line` 2개(합계·준공 후), 24개월 | `Market.unsold[]` | 월말 기준, 출처 라벨 부제 | 결측 월은 `connectNulls=false` |
| C6 | 종합 점수 분해 | `bar` stacked 6 시리즈(가중 기여 = w×s) | `ScoreRow.components` + `score_run.weights` | 정렬 = 종합, 제목에 가중치, 툴팁 = `formula_text` + 원값 | null component → 해당 막대 빗금 + "미판정" |
| C7 | 판정기 확률 | `bar` 가로(decide prob per 후보 + escape) | `CompareView.decisions[scenario]` | confidence 텍스트, TieBadge(conf<0.6), MismatchBadge | escaped → 막대 대신 질문 텍스트 |
| C8 | 잔여 이력 타임라인 | `scatter` on time x + `custom` 라벨 | `ComplexDetail.events[]` (kind, notice\_date, units, ratio) | 마커 모양 = kind 4종, 라벨 = 잔여 세대·경쟁률 | 이벤트 0 → "본청약만" |
| C9 | 호재 단계 | 보드 = HTML 그리드(5열), 타임라인 = `scatter` time x(확정만) | `Market.catalysts[]`, `ComplexDetail.catalysts[]` | 미확정·언론 회색; `location_confirmed=false`는 단지 연결 없음 표시 | — |
| C10 | 민감도 | HTML 표(12 변형 × TOP 5) + `line` 작게(순위 변화) | `Sensitivity.cells[]` | 변동 없는 가중치 회색, `unstable` 배지 | — |

차트 컴포넌트는 데이터 → option을 만드는 순수 함수 `buildOption(data)`와 렌더를 분리해, option 빌더만 단위 테스트한다(예: C6의 기여 합 = 종합 점수 ±0.01).

## 8. 멀티에이전트 실행 계획

에이전트 최대 8명이 네 라운드에 걸쳐 일한다. 병렬이 가능한 이유는 계약이 먼저 고정되고(R0), 각 WP가 이웃 WP의 코드가 아니라 계약과 픽스처에만 의존하기 때문이다. 실행 수단은 Claude Code의 서브에이전트(worktree 격리) 또는 Cursor 백그라운드 에이전트; 어느 쪽이든 WP 하나 = 브랜치 `wp/<n>-<slug>` 하나 = PR 하나다.

### 8-1 라운드와 게이트

| 라운드 | WP (병렬 수) | 입력 | 게이트 = 다음 라운드 진입 조건 |
| --- | --- | --- | --- |
| R0 계약 | WP0 (1, 오케스트레이터 본인 또는 1명) | 이 문서 §3·§4 | WP0 완료 기준 통과; `contracts/CHANGELOG.md`에 버전 1개; AGENTS.md 커밋 |
| R1 병렬 구현 | WP1(1\~2), WP2(1\~2), WP3, WP4, WP6(1\~2), WP9-픽스처 (최대 8) | 계약 버전, 각 카드 | 각 WP 테스트 green; 계약 변경 요청 전부 처리(승인 시 버전 올리고 영향 WP 재확인); 머지 순서 자유 |
| R2 연결 | WP5, WP7, WP8 (3) | R1 산출물 + 계약 | schemathesis green; "변경 없는 날 호출 0" 통과; 보고서 3포맷 생성 |
| R3 통합·리뷰 | WP9-통합 (1) + 리뷰 에이전트 (1, 구현을 보지 않은 새 에이전트) | 전체 머지된 main | §9 전 케이스 통과; e2e green; 리뷰 critical 0 |
| R4 운영 시험 | 사람 + WP7 담당 (1) | 실제 JEV 연결, 인천·김포 | 실제 1회 실행 호출 수·시간 기록; 2회차 호출 0 확인; runbook 갱신 |

&#91;embedded content: 라운드 5개 · 게이트 4개 · 세로 선 = 왼쪽이 전부 끝나야 오른쪽이 시작\]

왼쪽에서 오른쪽으로: 세로 선이 게이트다. 게이트 왼쪽의 WP가 전부 완료 기준을 통과해야 오른쪽이 시작하고, 같은 열 안의 WP는 서로를 기다리지 않는다. WP별 세부 의존은 §5 카드의 "의존" 열이 원본이다.

### 8-2 오케스트레이터 지시 (그대로 붙여 넣는 프롬프트)

```markdown
당신은 이 저장소의 오케스트레이터다. 설계도(이 문서)는 바꾸지 않고, 다음만 한다.
1. R0: §3·§4대로 /contracts와 뼈대를 만들고 WP0 완료 기준을 통과시킨다. 버전을 CHANGELOG에 적는다.
2. R1~R2: 각 WP에 §8-3 지시서를 채워 서브에이전트를 띄운다. 한 에이전트에는 AGENTS.md, §2, §4, 자기 카드, 참조 행만 준다. 설계도 전체를 주지 않는다.
3. 완료 보고(§8-5)를 받으면 테스트를 직접 돌려 확인한다. 보고만 믿지 않는다.
4. 계약 변경 요청은 하루 한 번 모아 판단한다. 승인하면 버전을 올리고, 영향받는 WP 에이전트에 변경점만 재전달한다. 거절하면 이유를 적어 돌려보낸다.
5. 게이트 조건이 전부 참일 때만 다음 라운드로 간다. 못 참은 WP는 같은 에이전트에 실패한 테스트 이름만 주고 계속시킨다.
6. 당신이 직접 고치는 코드는 /contracts와 WP0 범위뿐이다. 다른 WP 코드는 그 WP 에이전트에게 재지시한다.
7. R3 리뷰 에이전트에게는 구현 과정을 주지 않고 §4, §9, 카드와 머지된 코드만 준다.
8. 매 라운드 끝에 사람에게 10줄 이내로 보고한다: 통과한 WP, 막힌 WP와 이유, 계약 변경, 다음 라운드의 에이전트 수. §11 미결 사항은 시작 전에 묻는다.
```

### 8-3 WP 지시서 템플릿

```markdown
# WP{n} {이름} — 작업 지시 (계약 버전 {YYYY-MM-DD.k})
역할: 당신은 WP{n} 담당 에이전트다. 소유 디렉터리: {경로 목록}. 밖은 읽기만.
읽을 것(순서): AGENTS.md → 설계도 §2, §4 → §5의 WP{n} 카드 → 참조: {§3 테이블 행 / §6 절 / §7 행}
산출물: {카드의 산출물 그대로}
완료 기준: {카드의 완료 기준 그대로} — 첫 커밋은 이것을 실패하는 테스트다.
금지: 소유 밖 수정 · /contracts 수정 · 판정 로직 자체 구현 · 라벨 없는 수치 · 개인정보·키·비공개 자료 전송 · 픽스처 임의 수정
막히면: 계약 변경 요청(§8-5 양식)을 보고에 적고, 현재 계약으로 가능한 부분은 계속한다. 기다리지 않는다.
브랜치 wp/{n}-{slug}, PR 1개, 커밋 접두 [WP{n}]. 끝나면 §8-5 완료 보고.
```

### 8-4 공통 규칙 (AGENTS.md 원문)

1. 소유 디렉터리와 그 테스트만 쓴다. 다른 곳이 필요하면 요청으로 남긴다.
2. `/contracts`는 읽기 전용. 계약 버전은 지시서의 것 하나만 가정한다.
3. 판단은 판정기만 한다. 상승 확률·포함 여부·호재 단계·출처 상충을 LLM 호출이나 휴리스틱으로 대체하지 않는다. 파싱 정규식과 §6 수식은 판단이 아니다.
4. 같은 입력 재호출 금지는 코드가 강제한다(`judge/cache.py`). 판정기를 직접 부르는 코드는 `judge/` 밖에 없다.
5. 모든 수치는 출처 URL·확인일·라벨과 함께 저장하고 표시한다. 빈 라벨은 테스트 실패다.
6. 외부로 나가는 것은 공개 분양 정보뿐이다. 개인정보·API 키·비공개 자료는 판정기·웹훅·로그 어디에도 보내지 않는다. 판정기 payload는 `judge/guard.py`를 통과해야 한다.
7. 실패도 데이터다. 403·타임아웃·파싱 실패는 상태 코드와 함께 행으로 남기고 예외로 삼키지 않는다.
8. 테스트를 먼저 쓴다. 완료 기준은 전부 자동 테스트로 존재해야 한다.
9. 타입은 엄격하게: `mypy --strict`, `tsc --noEmit` 통과가 PR 조건.
10. 비밀은 환경변수로만. `.env`는 커밋 금지, `.env.example`만 갱신.
11. 새 라이브러리는 보고의 "제안"에 적고 WP0 승인 후 추가한다. `pyproject.toml`·`package.json`은 WP0 소유.
12. 화면 문자열은 `frontend/src/i18n/ko.json` 한 곳. 숫자 포맷(억·만·%)은 `FactCell`이 한다.
13. 로그에 판정기 payload 원문을 남기지 않는다. input\_hash와 길이만.
14. 완료 보고는 양식대로. 하지 않은 것, 못 한 것, 끌 맞춘 것을 숨기지 않는다.

### 8-5 보고 양식

```markdown
## 완료 보고 — WP{n} (계약 {버전}, 브랜치 wp/{n}-{slug})
산출물: {파일 목록}
테스트: `{명령}` → {통과/전체}, 커버 필드: {…}
완료 기준: [x] … [x] … [ ] …(사유)
하지 않은 것 / 가정한 것: …
제안(새 라이브러리·설계 개선): …
계약 변경 요청: 대상 파일 · 변경 내용 · 이유 · 영향 WP · 없으면 "없음"

## 리뷰 보고 — WP{n}
[ ] 완료 기준마다 테스트가 있고 내가 직접 돌려 통과
[ ] 소유 디렉터리 밖 변경 0 (git diff --stat로 확인)
[ ] 라벨·출처 없는 수치 경로 0
[ ] judge/ 밖에서 판정기 호출·LLM 호출 0
[ ] guard 우회 경로 0, 로그에 payload 원문 0
[ ] 성능·멱등성 기준(카드) 재현
발견: critical {n} / major {n} / minor {n} — 각각 파일:줄, 재현 방법
```

### 8-6 컨텍스트 예산

에이전트 한 명에게 들어가는 것은 AGENTS.md(약 2KB) + §2 + §4 + 카드 1장 + 참조 행 ≈ 15\~20KB다. 설계도 전체나 다른 WP의 코드는 넣지 않는다; 필요한 이웃 정보는 계약에 이미 있어야 하고, 없으면 그것이 계약 변경 요청의 신호다. 리뷰 에이전트는 반대로 구현 대화를 전혀 보지 않고 코드와 계약만 본다.

## 9. 수용 테스트와 회귀 데이터

회귀 데이터는 [인천·김포 보고서](https://claude.ai/code/artifact/69e8852b-1054-403c-a80a-4ebe8c35366f)(기준일 2026-10-08, 단지 16개)에서 가져온다. 점수 재현은 두 단계다: (a) 보고서의 구성 점수를 입력으로 고정하고 가중 합·순위·동점만 검증(손 등급 시절의 숫자를 그대로), (b) §6-4 식으로 다시 계산한 값은 R1에서 WP4가 만들고 사람이 확인한 뒤 `expected_scores_v2.json` 골든 파일로 고정한다. (b)가 (a)와 다른 것은 정상이며, 차이가 설명되면 된다.

| # | 케이스 (실제 있었던 일) | 픽스처 | 기대 결과 | WP |
| --- | --- | --- | --- | --- |
| T1 | 통합 TOP 5 재현 | 구성 점수 6개 고정 + 기본 가중치 | 그란테르 5.87 > 엘리프 5.70 > 한내들 5.33 > 스위첸(김포) 5.00 > 센트레빌 = 더샵 AB23 4.61 (±0.01, 공동 5위) | WP4, WP9 |
| T2 | 상황 B 동률 | decide 봉투: 칸타빌 0.54, 엘리프 0.42, confidence 0.48 | `tie=true`, 두 단지 모두 chosen 표시, C7에 TieBadge | WP4, WP6 |
| T3 | 스위첸 홈페이지 403 | official\_site 403 응답 녹화 | `intake_status=확인 불가`, `http_status=403`, 화면 "확인 불가(403, 날짜)"; 상황 후보 제외; G7에서 사람 확인 "가능" 입력 → intake 행 추가 + rejudge job 1 → 후보 포함 | WP1, WP5, WP7 |
| T4 | 메트로자이 2단지 "11억" 타입 오류 의심 | rtms 픽스처에 84㎡ 거래 중 1건만 크게 벗어남 | `gap.py` 이상치 규칙(중앙값 대비 1.5×IQR 밖) → 비교군에서 제외 + `comparable_set`에 "이상치 제외" 기록; 원본 행은 삭제 안 함 | WP4 |
| T5 | 해링턴 세대수 1,573 vs 1,769 | 청약홈 상세와 공고문 발췌이 다른 값 | `conflict_group` 1건, chosen = 청약홈 상세 값, 다른 값 chosen=false 보관, compare 미호출(1차 vs 1차가 아닐 때만), 출처 패널에 둘 다 표시 | WP2 |
| T6 | verify 복합 주장 contradicted(0.35) | "3개는 unlikely이고 나머지는 uncertain" | `ClaimSplitter` → 주장 ≥2개, 각각 verify 입력; 복합 문장 그대로 verify에 보내면 테스트 실패 | WP3 |
| T7 | rerank 8 → 16 후보 | 인천 8 녹화 + 인천·김포 16 녹화 | 후보 변경 시 호출 1회(16개 전부), `delta_rerank` 열 생성, 종합 점수는 새 호출 값만 | WP3, WP4 |
| T8 | 변경 없는 날 | 어제와 동일한 목록·팝업 해시 | `change_event` 0, rejudge job 0, 판정기 실제 호출 0 | WP7 |
| T9 | 임의공급 계약금 10% → 5% | 같은 단지 공고 2건 | `payment_terms` 행 2개, 현재 조건 = 최신, `change_event` critical, 유동성 점수 D/5 항 2 → 1로 +1 | WP2, WP4 |
| T10 | 사다리 시점 불일치 | 고촌(2027 입주) vs 리버프론트(2032) | horizon 3종 명제 생성, `asof_plus_3y` 목표 시점이 두 단지 동일, 연율 열 계산 | WP3, WP4 |
| T11 | 스위첸 비교군 대체 | 신축 0건, 리버시티·센트럴자이 거래 | `substitute=true`, 보정·미보정 중앙값 둘 다, 라벨 "추정(대체·보정 c=0.015)", C2에 점선 점 | WP4, WP6 |
| T12 | 민감도 | T1 입력 | 12 변형 계산, TOP 5 집합 변동 여부가 골든 파일과 일치, `unstable` 플래그 | WP4 |
| T13 | 출처 없는 수치 | provenance 행을 지운 픽스처 | dev: `contract_violation` 500; prod: 라벨 "확인 불가(출처 누락)" + 경고 로그; 프론트 lint가 FactCell 밖 숫자 렌더 감지 | WP5, WP6 |
| T14 | 보안 guard | payload에 전화번호·이메일·환경변수 값 삽입 | 호출 거부, `judgment_log`에 status=blocked 행, 로그에 원문 없음 | WP3 |
| T15 | 보고서 | 픽스처 스냅샷 2개 | md 청크 각 ≤32KB, URL 전수 형식 유효, §8 숫자 20개 = `score_total`, diff 표 생성, pdf·docx 열림 | WP8 |
| T16 | 성능 | 합성 1,000단지 | `/complexes` 첫 페이지 1초 이내, G2 스크롤 60fps(가상화) | WP5, WP6 |
| T17 | 멱등성 | 수집 2회, 재판정 2회 | `raw_document` 증가 0; 판정기 실제 호출 1회, 두 번째는 cached=true | WP1, WP3 |
| T18 | 판정기 다운 | MockAdapter가 `JudgeUnavailable` | 수집·정규화 성공, `degraded=true`, 점수 미계산, G1·G7 배너, 복구 후 재판정 job 자동 등록 | WP7 |

통과 기준: T1\~T18 전부 green이고, R4에서 실제 JEV로 인천·김포를 1회 돌렸을 때 호출 수가 132회보다 적거나 같고(캐시·원자 분할로 증가할 수 있으나 이유가 기록되면 됨), 2회차 실행의 호출이 0이면 통과다.

## 10. 운영·보안·배포

단일 호스트에서 `docker compose up -d`로 끝난다. 밖으로 나가는 데이터는 공개 분양 정보뿐이고, 비밀은 환경변수에만 있으며, 개인정보는 어디에도 저장하지 않는다.

| 서비스 | 이미지 | 포트·볼륨 | 역할 |
| --- | --- | --- | --- |
| `db` | postgres:16 | 5432(내부), `pgdata` | 운영 DB; 개발은 `DATABASE_URL=sqlite:///./dev.db`로 서비스 없이 |
| `api` | Dockerfile.api (uvicorn) | 8000, `rawdata`(읽기) | REST, 파일 서빙 |
| `worker` | Dockerfile.worker (Playwright 포함) | —, `rawdata`(쓰기) | 스케줄러·수집·판정·점수·보고서; JEV MCP를 자식 프로세스로 |
| `web` | Dockerfile.web (nginx + 정적 번들) | 8080 | `/api/*` → api 프록시 |

| 환경변수 | 예 | 주의 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://…` | — |
| `RAW_DIR` | `/data/raw` | sha256 경로 |
| `API_TOKEN`, `READONLY_TOKEN` | 32자 랜덤 | 공유 링크는 READONLY만 |
| `JEV_MCP_CMD` | `npx jev-mcp` | stdio 실행 명령; 키는 JEV 자체 환경변수 |
| `DATA_GO_KR_KEY` | 공공데이터포털 키 | 실거래 Open API |
| `NEWS_API_KEY` | 뉴스 검색 API 키 | 없으면 news collector 비활성 |
| `WEBHOOK_URL` | 알림 URL 1개 | critical change\_event만 |
| `JUDGE_ADAPTER` | `jev` / `mock` | 테스트는 mock |
| `ENV` | `dev` / `prod` | dev는 출처 누락 시 예외 |

보안 규칙: (1) 판정기·웹훅·뉴스 API로 나가는 payload는 `judge/guard.py`와 같은 필터를 통과한다(전화번호·주민번호·이메일·환경변수 값 패턴 → 거부). (2) `human_check.entered_by`는 이름이 아니라 역할 문자열("운영자")만. (3) 원문 파일은 공고문·공개 페이지만; 전화 통화 내용은 요약 텍스트만. (4) 로그는 input\_hash·길이·상태만. (5) 공유 링크는 읽기 전용 토큰으로만, 만료 30일.

스케줄: 매일 06:00 `collect.daily`(청약홈 목록 2개 + 공식 홈페이지 팝업), 매주 월 06:30 `collect.weekly`(실거래·미분양·입주·호재), 각 수집 후 변경 감지 → 변경 단지만 `rejudge` → contradicted 0이면 `snapshot.publish`. 백업은 `pg_dump` 일 1회 + `rawdata` rsync; 복구 절차는 runbook에.

| 상황 | 대응 (docs/runbook.md) |
| --- | --- |
| 청약홈 페이지 구조 변경 | 파서 테스트 실패로 감지 → 녹화 픽스처 갱신 → WP1/WP2 에이전트에 "실패 테스트 이름 + 새 HTML"만 주고 수정 |
| 공식 홈페이지 403·DNS 실패 지속 | 자동: "확인 불가(403, 날짜)" 유지; 사람: G7에서 전화 확인 입력 |
| 판정기 장애 | `degraded` 모드: 수집·정규화만, 화면 배너, 복구 감지 시 미처리 rejudge 자동 실행 |
| 판정기 버전 변경 | `adapter_version` 올림 → 모든 input\_hash 변경 → 전체 재판정 1회, 이전 run과 delta 표 보고 |
| 지역 추가 | `region` 행 + 생활권 정의 + 계수 → 수집 → rerank 전체 재호출(§6-5) → 보고서에 "지역 추가" 장 + 통합 순위 재산출 |
| 디스크 부족 | rawdata 월별 압축(삭제 금지), DB는 파생 테이블 유지 |
| 스냅샷 published 안 됨 | `claim.verify_status=contradicted` 목록을 G7에 표시 → 문장 수정(사람) → 원자 분할 재검증 |

## 11. 미결 사항과 결정 요청

R0를 시작하기 전에 사람이 답해야 하는 것들이다. 답이 없으면 괄호 안의 기본값으로 진행하고 설계도에 "기본값 사용"을 적는다.

- [ ] 생활권 정의: 계양·송도·검단·김포(풍무·사우·고촌·운양·장기 등)의 법정동 목록과 기존 가구수 출처 (기본값: 보고서 §1의 구분 그대로, 가구수는 통계청 주민등록 가구 연도 최신)
- [ ] 연식 보정 계수 c와 상한 (기본값: 0.015/년, 8년, 라벨 추정)
- [ ] 공급 기준치 U\_ref (기본값: 생활권 가구수의 8%)
- [ ] 상황 B·C 가중치와 A·D의 liquidity → move\_in 대체 (기본값: §6-4 표)
- [ ] 공공데이터포털 실거래 API 키 발급 — 사람이 해야 함; 없으면 재가공 폴백만으로 시작(모든 실거래 라벨 재가공)
- [ ] 뉴스 검색 API (기본값: 키 없으면 news collector 비활성, 호재는 사람이 URL 입력)
- [ ] 알림 채널 웹훅 1개 (기본값: 없음, G1 피드만)
- [ ] 보고서 Doc 내보내기: v1은 md·pdf·docx 파일만, Claude Doc은 md를 붙여 넣는 방식 (기본값: 그렇게)
- [ ] 실행 수단과 병렬 상한: Claude Code 서브에이전트 vs Cursor, 동시 8명 비용 허용 여부 (기본값: Claude Code, R1 병렬 6)
- [ ] DB: 처음부터 Postgres로 갈지 (기본값: 개발 SQLite, compose는 Postgres)
- [ ] 스캔 PDF 비중 확인 후 OCR 추가 여부 (기본값: 추가 안 함, "확인 불가(스캔)" + 사람 입력)
- [ ] 판정기 임계값 기본값 유지 여부 (기본값: JEV 1.13 기본값 그대로)
- [ ] 사용자 1명 확정 (기본값: 예; 팀 사용이면 ADR-9 재검토)
- [ ] 보존 기간: 원문 아카이브·스냅샷 (기본값: 무기한, 삭제 없음)

이 문서의 숫자 중 보고서에서 온 것(T1·T2·호출 132회)은 확인된 값이고, 계수·기준치·가중치는 전부 제안값이다. 투자 권유가 아니며, 프로그램은 판단을 하지 않고 판정기의 판단을 기록·표시한다.
