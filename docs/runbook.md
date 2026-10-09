# 운영 runbook

RA §10 대응표를 절차로 풀어 쓴 문서. 설계 원본은 `docs/source/RA_v1.md` §10, 변경분은 `docs/design/DECISIONS.md`.
명령은 저장소 루트 기준. make 가 없으면 `make X` 대신 `python scripts/tasks.py X`.

## 0. 실행·점검

### 0-1 Docker 로 (운영)

```bash
cp infra/.env.example infra/.env        # POSTGRES_PASSWORD, API_TOKEN(필수), READONLY_TOKEN, (있으면) DATA_GO_KR_KEY …
docker compose -f infra/docker-compose.yml up -d --build   # API_TOKEN 이 비면 compose 가 기동을 거부한다(R3 M11)
docker compose -f infra/docker-compose.yml ps
curl -s http://localhost:8080/health    # {"status":"ok","version":…,"env":"prod","db":"ok"}
docker compose -f infra/docker-compose.yml logs -f worker   # JSON 한 줄 로그
```

- `/health` 가 503(`db: error`)이면 `db` 컨테이너 상태와 `DATABASE_URL` 을 본다.
- api 포트(8000)는 호스트 루프백(`API_BIND=127.0.0.1`)에만 열린다. 외부 접속은 web(8080)의 `/api` 프록시로만.
- `ENV=prod` 는 `API_TOKEN` 필수, `JUDGE_ADAPTER=mock` 금지(설정 검증이 기동을 막는다). `/docs`·`/openapi.json` 은 prod 에서 꺼진다
  — 계약 원본은 `contracts/openapi.yaml`.
- 로그에는 비밀값·전화번호·주민번호·이메일이 `[REDACTED:…]` 로 가려진다. 판정기 payload 는 input_hash·길이만 남는다.

### 0-2 Docker 없이 (개발·Docker 미설치)

```bash
cd backend
uv sync --all-extras
cp ../infra/.env.example .env           # ENV=dev 로 바꾼다(예시 기본은 prod). DATABASE_URL·RAW_DIR 은 그대로
uv run alembic upgrade head
uv run python -m app.serve                       # 터미널 1 (API_HOST·API_PORT; 토큰이 모두 비면 127.0.0.1 만 + 경고)
uv run python -m app.worker                      # 터미널 2 (점검: --once)
uv run playwright install chromium               # 동적 페이지·PDF 용, 한 번
curl -s http://127.0.0.1:8000/health
```

- SQLite 는 WAL·busy_timeout 5초로 연다. `database is locked` 가 반복되면 Postgres 로 옮긴다(ADR-2 바꿀 신호):
  `DATABASE_URL=postgresql+psycopg://…` 로 바꾸고 `alembic upgrade head`.
- 판정기는 Node 20 이 있어야 한다(`JEV_MCP_CMD="npx -y @jkudish/jev-mcp@latest"`). 없으면 `JUDGE_ADAPTER=mock` 으로
  수집·정규화만 확인한다(판정은 전부 review 로 남는다).
- 원문·보고서는 `backend/data/` 아래(`RAW_DIR`, `REPORT_DIR`) — git 에서 무시된다.

### 0-3 스케줄 (RA §10)

| 시각 | 잡 | 내용 |
| --- | --- | --- |
| 매일 06:00 | `collect.daily` | 청약홈 목록 2개 + 공식 홈페이지 팝업 → 변경 감지 → 변경 단지만 `rejudge` → contradicted 0 이면 `snapshot.publish` |
| 매주 월 06:30 | `collect.weekly` | 실거래·미분양·입주·호재 |
| 매월 1일 05:00 | `reference.refresh` | 법정동·행정동·매핑 파일 갱신 (D2-4) |
| 지역 생성 시 | `region.bootstrap` | 즉시 수집 → 판정 → 점수 → publish (D2-4) |

잡 상태는 화면 G7(운영)과 `job_run` 테이블에서 본다.

## 1. 청약홈 페이지 구조 변경

증상: 파서 테스트 실패, 또는 G7 수집 성공률 급락·필드 "확인 불가" 급증.

1. 실패한 날의 원문을 확인한다: `RAW_DIR/applyhome_list/<날짜>/` (sha256 파일명).
2. 새 HTML 을 녹화 픽스처로 저장한다(`contracts/fixtures/…` 는 WP9 소유 — CHANGELOG 에 사유).
3. 실패하는 테스트 이름 + 새 HTML 만 WP1(수집)/WP2(파서) 담당에게 준다. 다른 맥락은 주지 않는다.
4. 수정이 머지되면 `python -m app.worker --once` 또는 G7 재수집 → 다음 스냅샷에서 diff 를 확인한다.

## 2. 공식 홈페이지 403·DNS 실패 지속

자동: 수집 결과가 `http_status=403`(또는 연결 실패) 행으로 남고 화면은 "확인 불가(403, 날짜)" 를 유지한다.
`core.http` 는 4xx 를 재시도하지 않고, robots.txt 가 막으면 요청 자체를 하지 않는다(`blocked_by_robots`).

사람:
1. G7 에서 해당 단지·소스의 실패 이력을 본다.
2. 전화로 확인한 내용은 요약 텍스트만 G7 사람 입력으로 남긴다(`human_check.entered_by` = 역할 "운영자", 이름·번호 금지).
3. 403 이 robots·UA 문제로 보이면 `HTTP_USER_AGENT`·`HTTP_RATE_PER_HOST` 를 낮춰 본다(우회 금지 — 공개 페이지만).

## 3. 판정기 장애 (degraded 모드)

증상: worker 로그 `JudgeUnavailable`, 화면 배너 "미판정 모드".

1. 수집·정규화는 계속된다. 판정·점수·publish 는 보류된다.
2. 원인 확인: `npx -y @jkudish/jev-mcp@latest` 가 worker 컨테이너에서 실행되는지(`docker compose -f infra/docker-compose.yml exec worker npx --version`),
   네트워크, JEV 자체 키(JEV 환경변수).
3. 복구되면 worker 가 감지해 미처리 `rejudge` 를 자동 실행한다. 수동: G5 재판정 버튼 또는 `rejudge` 잡 등록.
4. 급할 때 `JUDGE_ADAPTER=mock` 으로 띄우면 화면은 동작하지만 판정은 모두 review 로 남는다 — 운영에서는 쓰지 않는다.

## 4. 판정기 버전 변경

JEV MCP 는 `@latest` 를 따른다(D6). `initialize` 의 `serverInfo.version` 이 바뀌면:

1. `adapter_version` 이 바뀌어 모든 `input_hash` 가 달라진다 → 전체 재판정 1회가 자동으로 돈다.
2. `change_event(entity=judge, field=version, severity=critical)` 가 남는다(웹훅이 설정돼 있으면 알림).
3. 이전 run 과의 delta 표를 보고서에 붙인다(`python -m app.reports.cli --snapshot <id> --format html`, 비교 스냅샷 지정).
4. 비용·시간이 부담되면 `JEV_MCP_CMD` 를 특정 버전(`@jkudish/jev-mcp@0.13.0`)으로 고정하고 재시작한다.

## 5. 지역 추가

절차는 [`docs/region-add.md`](region-add.md) (화면 G0). 요약: 자유 지명 입력 → 후보 선택 → `POST /regions` →
`region.bootstrap`(수집 → 판정 → 점수 → publish) → 생활권 편집(G0-2) → rerank 전체 재호출 → 보고서 "지역 추가" 장.

## 6. 디스크 부족

삭제 금지(D1 #14 보존 기간 무기한).

1. `du -sh /data/raw/*` (Docker: `docker compose -f infra/docker-compose.yml exec worker du -sh /data/raw/*`) 로
   소스별 용량을 본다.
2. 지난달 이전 날짜 디렉터리를 월별로 압축한다(저장소 루트에서): `bash infra/raw_archive.sh <RAW_DIR> <source> <yyyy-mm>`
   — RAW_DIR 은 상대 경로여도 된다(스크립트가 절대 경로로 바꾼다).
   Docker: `docker compose -f infra/docker-compose.yml exec worker /app/infra/raw_archive.sh /data/raw <source> <yyyy-mm>`
   (worker 이미지에 실행 권한으로 `/app/infra/raw_archive.sh` 가 들어 있다 — 작업 디렉터리가 `/app/backend` 라 상대 경로
   `infra/…` 는 없다). 결과 `<source>/<yyyy-mm>.tar.gz` 는 RAW_DIR 기준 상대 경로(`tar -C`)로 넣어
   구성원 이름이 DB `raw_document.path` 와 같다 — 스크립트가 `tar -tzf` 목록과 디스크 파일을 대조한 뒤에만 원본을 지운다.
   API `GET /raw/{id}` 는 원본이 없으면 이 압축에서 읽는다(R3 minor 34). 손으로 `tar -czf … /data/raw/…`(절대 경로)로 묶으면
   구성원 이름이 달라져 읽지 못한다 — 스크립트만 쓴다.
3. DB 는 파생 테이블을 지우지 않는다. Postgres 는 `VACUUM (ANALYZE)` 만.

## 7. 스냅샷이 published 되지 않음

원인: 남은 contradicted 주장(분할 재검증 자식이 없는 `claim.verify_status = contradicted`)이 1건 이상 →
`snapshot.publish`·보고서 생성이 거부한다(`judge.claims.remaining_contradicted`).

1. G7 '주장 검증' 패널에서 contradicted 주장 목록을 본다(`GET /snapshots/{sid}/claims?status=contradicted` — 문장·근거·판정 로그).
2. 사람이 문장을 고쳐 저장한다(`PATCH /claims/{id}` → `claim.reverify` 잡 202). 원 주장 행은 그대로 남는다.
3. worker 가 고친 문장을 원자 주장으로 나눠(T6) 원 주장 근거로 `jev_verify` 하고 `parent_claim_id` 자식 행을 만든다.
   자식이 모두 contradicted 가 아니고 남은 contradicted 가 0 이면 `snapshot.publish` 를 등록한다.
   자식이 다시 contradicted 면 그 자식이 목록에 남는다 — 같은 절차를 반복한다.

## 8. 백업·복구

- 자동화: `infra/backup.sh /srv/backup` 을 cron 으로 매일(예 `0 3 * * * cd <repo> && infra/backup.sh /srv/backup`).
  - DB: `pg_dump -Fc` → `db-<날짜>.dump`, 곧바로 `pg_restore --list` 로 검증(실패하면 종료 코드 ≠ 0).
  - 원문: `rawdata` 볼륨을 `rsync -a`(증분, 삭제 전파 없음)로 `raw/` 에. rsync 가 없으면 `raw-<날짜>.tgz` + `tar -tzf` 검증.
- 복구: 새 `db` 를 띄운 뒤 `pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean backup/db-<날짜>.dump`, 원문은 볼륨에 풀기.
  복구 후 `/health` 와 G7 신선도를 확인한다.

## 9. 비밀값

- 비밀은 `infra/.env`(Docker) 또는 `backend/.env`(로컬)에만. 커밋 금지(pre-commit `no-dotenv`·`gitleaks`).
- 남에게 주는 링크는 G7 '공유 링크'로 발급한다(`POST /share-links`, 쓰기 토큰만): 읽기 전용(GET 만), 만료
  `SHARE_TOKEN_TTL_DAYS`(기본 30일), 서버에는 sha256 만 남는다. 링크 `<origin>/share#<token>` 은 발급 때 한 번만 보인다.
  잃어버리거나 노출되면 같은 패널에서 회수(`DELETE /share-links/{id}`) — 그 토큰은 바로 401.
- `READONLY_TOKEN` 은 운영자 열람용 고정 토큰이다(만료 없음 — 남에게 주지 않는다).
- 키가 노출되면: 발급처에서 폐기·재발급 → `infra/.env` 교체 → `docker compose -f infra/docker-compose.yml up -d` (로그는 이미 마스킹되지만 확인).

## 10. R4 운영 시험 — 인천·김포 실데이터 1회 실행 (준비 문서, WP9 R3)

RA §8-1 R4 게이트: "실제 JEV 연결, 인천·김포 → 실제 1회 실행 호출 수·시간 기록; 2회차 호출 0 확인; runbook 갱신".
RA §9 통과 기준: 1회차 실제 호출 수 ≤ 132(캐시·원자 분할로 늘 수 있으나 이유를 기록), 2회차 실제 호출 0.
**R3 회귀(`python scripts/tasks.py regress`)의 결과와 발견 목록을 사람이 확인한 뒤에만 실행한다(DECISIONS D8).**
아래 명령은 준비만 해 둔 것이다 — 실행하지 않았다.

### 10-1 준비

```bash
cd backend
uv sync --all-extras && uv run playwright install chromium     # 공식 홈페이지 렌더·보고서 PDF
node --version                                                 # Node 20+ (npx 로 JEV MCP 기동)
mkdir -p ../r4 && cp ../infra/.env.example ../r4/.env
```

`r4/.env` 에 넣을 것(커밋 금지, 규칙 10):

| 키 | 값 |
| --- | --- |
| `ENV` | `prod` (출처 없는 수치는 500 이 아니라 '확인 불가(출처 누락)' + 경고 로그) |
| `DATABASE_URL` | `sqlite:///../r4/r4.db` (새 파일 — devseed DB 와 섞지 않는다) |
| `RAW_DIR` / `REPORT_DIR` / `REFERENCE_DIR` | `../r4/raw` / `../r4/reports` / `../r4/reference` |
| `API_TOKEN` / `READONLY_TOKEN` | 32자 이상 임의값 |
| `JUDGE_ADAPTER` | `jev` |
| `JEV_MCP_CMD` | 기본 `npx -y @jkudish/jev-mcp@latest` (재현이 중요하면 실행 전 버전 고정 `@jkudish/jev-mcp@<버전>` — 1·2회차 사이에 버전이 바뀌면 전체 재판정이 돈다, §4) |
| `DATA_GO_KR_KEY` | 사람이 발급한 키(청약홈 API·실거래, D1 #5·5a) |
| `NEWS_API_PROVIDER` / `NEWS_API_KEY` | `ncp` / `<ID>:<Secret>` (D1 #6) |
| `LOG_JSON` | `true` (실행 기록용) |

```bash
export ENV_FILE=../r4/.env
uv run alembic upgrade head                                      # 스키마 + 내장 시나리오 5개
uv run pytest -m live tests/judge/test_live.py -s                # JEV 연결 smoke(1건 호출 + 캐시 확인)
uv run uvicorn app.main:app --port 8000 &                        # API (다른 터미널 권장)
H="Authorization: Bearer <API_TOKEN>"
```

### 10-2 참조 표 → 지역 생성 → 1회차

```bash
# 참조 표(법정동·행정동·매핑·주민등록 세대) — 실패하면 contracts/fixtures/reference 사본으로 적재된다
curl -s -X POST localhost:8000/api/jobs -H "$H" -H 'Content-Type: application/json' \
     -d '{"job_name":"reference.refresh","payload":{}}'
uv run python -m app.worker --once

# 지역 = 회귀 픽스처 지역 정의(D3)와 같은 선택 — contracts/fixtures/incheon_gimpo_2026-10-08/region.json 의 selections
uv run python - <<'PY' > ../r4/region_request.json
import json; r = json.load(open("../contracts/fixtures/incheon_gimpo_2026-10-08/region.json", encoding="utf-8"))
print(json.dumps({"name": r["name"], "query_text": r["query_text"], "selections": r["selections"]}, ensure_ascii=False))
PY
curl -s -X POST localhost:8000/api/regions -H "$H" -H 'Content-Type: application/json' \
     --data-binary @../r4/region_request.json | tee ../r4/region_created.json   # region.id, job_id(region.bootstrap)

# 1회차: bootstrap(수집 → 정규화 → 판정 P1~P9 → 점수 → publish). 시간을 잰다.
date -Iseconds | tee ../r4/run1_start.txt
time uv run python -m app.worker --once 2>&1 | tee ../r4/run1.log
date -Iseconds | tee ../r4/run1_end.txt
```

### 10-3 판정기 호출 수 집계 (SQLite: `sqlite3 ../r4/r4.db`, Postgres 는 `json_extract` → `->>`)

`judgment_log` 는 **실제로 판정기에 간 호출 1건 = 1행**이다(같은 input_hash 재호출은 행을 만들지 않고 cached 봉투,
guard 차단은 `status='blocked'` 행이지만 판정기로 가지 않음, 오류는 `status='error'` 행을 같은 hash 로 UPDATE).

```sql
-- 1회차 실제 호출 수(도구별·상태별). blocked 는 판정기로 가지 않았으므로 따로 센다.
SELECT tool, status, COUNT(*) AS n FROM judgment_log GROUP BY tool, status ORDER BY tool, status;
SELECT COUNT(*) AS real_calls FROM judgment_log WHERE status <> 'blocked';          -- 게이트: ≤ 132 (넘으면 이유 기록)
SELECT adapter_version, COUNT(*) FROM judgment_log GROUP BY adapter_version;         -- 버전 1개여야 한다(§4)
-- 잡별 집계(파이프라인 stats: judge_calls = 실제 호출, cached = 캐시 적중, blocked = guard 차단) + 시간
SELECT id, job_name, status, started_at, finished_at,
       json_extract(stats, '$.pipeline.judge_calls') AS judge_calls,
       json_extract(stats, '$.pipeline.cached')      AS cached,
       json_extract(stats, '$.pipeline.blocked')     AS blocked,
       json_extract(stats, '$.pipeline.by_tool')     AS by_tool,
       json_extract(stats, '$.judge_calls')          AS rejudge_calls          -- rejudge 잡은 최상위에 있다
FROM job_run ORDER BY id;
-- 실패(오류) 행과 사유 — 실패도 데이터(규칙 7)
SELECT tool, purpose, error_text FROM judgment_log WHERE status = 'error';
```

화면으로는 G7 '판정 로그'(`GET /api/ops/judgments`)에서 같은 수를 본다. 기록할 것: 실제 호출 수(도구별),
cached·blocked·error 수, 1회차 소요 시간(run1_start~end), 132 와의 차이와 이유(원자 분할로 verify 가 늘어난 수 등),
`adapter_version`(서버 버전 + model).

### 10-4 2회차 — 실제 호출 0 확인

```bash
SQL='SELECT COUNT(*) FROM judgment_log;'
sqlite3 ../r4/r4.db "$SQL" | tee ../r4/before_run2.txt
# (a) 같은 스냅샷 전체 재판정: 모든 payload 가 같으므로 전부 cached
SID=$(curl -s localhost:8000/api/regions/<region_id> -H "$H" | uv run python -c "import json,sys;print(json.load(sys.stdin)['latest_snapshot']['id'])")
curl -s -X POST localhost:8000/api/jobs -H "$H" -H 'Content-Type: application/json' \
     -d "{\"job_name\":\"rejudge\",\"payload\":{\"snapshot_id\":$SID,\"scenario_id\":null,\"complex_ids\":null,\"reason\":\"R4 2회차\"}}"
time uv run python -m app.worker --once 2>&1 | tee ../r4/run2.log
sqlite3 ../r4/r4.db "$SQL" | tee ../r4/after_run2.txt            # before 와 같아야 한다(새 행 0)
sqlite3 ../r4/r4.db "SELECT id, json_extract(stats,'$.judge_calls'), json_extract(stats,'$.cached') FROM job_run WHERE job_name='rejudge' ORDER BY id DESC LIMIT 1;"
#   → judge_calls = 0, cached = 1회차 호출 수와 비슷(같은 입력 재호출 금지, 규칙 4)
# (b) 다음 날 일일 수집(변경 없는 날, T8): collect.daily → 변경 0 이면 판정 0 + 이전 판정 복사 + publish
curl -s -X POST localhost:8000/api/jobs -H "$H" -H 'Content-Type: application/json' \
     -d '{"job_name":"collect.daily","payload":{"region_id":<region_id>,"sources":["applyhome_list","official_site"]}}'
uv run python -m app.worker --once && sqlite3 ../r4/r4.db "$SQL"      # 실제로 바뀐 공고가 없으면 여전히 같은 수
```

통과: (a)에서 새 `judgment_log` 행 0 · `judge_calls` 0. (b)는 실제 사이트 변화가 있으면 그 단지만 재판정된다(호출 > 0 이
정상) — 그때는 `change_event` 목록(G1 '최근 변경')과 호출 수가 맞는지 기록한다.

### 10-5 끝난 뒤

- 결과(호출 수·시간·버전·2회차 0 여부)를 이 절 아래 표로 남기고 `docs/adr/ADR-05-judge-smoke.md` 에 링크한다.
- 보고서: `uv run python -m app.reports.cli --snapshot <SID> --format pdf` (부록 A 에 도구별 임계값·호출 로그).
- (제안, WP9) 1회차 `judgment_log`(input_json·output_json)를 Mock 녹화로 내보내면 e2e·회귀의 Mock 판정기가 파이프라인
  payload 를 재생할 수 있다(현재 픽스처 녹화는 보고서 재구성이라 파이프라인 payload 와 hash 가 달라 Mock 재판정이 전부
  review — R3 발견). 내보낼 때 hash 는 `input_hash(tool, purpose, input_json, <픽스처 _meta adapter_version>)` 로 다시 계산한다.
