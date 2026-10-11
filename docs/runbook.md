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
| 매일 03:00 | `backup` | DB(Postgres `pg_dump -Fc`, SQLite 개발 모드 = 파일 복사) + 원문 증분 복사 → `BACKUP_DIR/<날짜>/`(compose = `backups` 볼륨, D11-8·D12-6) |
| 지역 선택 변경 시 | `region.expand` | `PATCH /regions/{id}`(선택 추가·제거) → 수집 → 새 리비전 전체 판정·rerank → publish(D11-7) |

발행된 스냅샷은 **불변**이다(D11-1). 발행 뒤의 재판정(사람 확인·생활권 편집·강등·판정기 버전 변경·지역 확장)은 같은 기준일의
새 **리비전**(`snapshot.revision`)에 쓰고, 끝나면 그 리비전이 발행된다. 화면 기본 = 가장 새 발행 리비전. 자세한 규칙은 §11.

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
   가장 새 스냅샷이 발행됐으면 같은 기준일 새 리비전에서, 미발행(리비전 1 판정 중)이면 그 자리에서 돌고 직전 발행 스냅샷이
   비교 기준(`revision_of`)으로 달린다(R3 4차 M-6).
2. `change_event(entity=judge, field=version, severity=critical)` 가 남는다(웹훅이 설정돼 있으면 알림).
3. 보고서는 비교 스냅샷을 주지 않으면 `revision_of`(바탕 리비전)와 비교해 delta 표를 붙인다
   (`python -m app.reports.cli --snapshot <리비전 id> --format html`).
4. 비용·시간이 부담되면 `JEV_MCP_CMD` 를 특정 버전(`@jkudish/jev-mcp@0.13.0`)으로 고정하고 재시작한다.

## 5. 지역 추가

절차는 [`docs/region-add.md`](region-add.md) (화면 G0). 요약: 자유 지명 입력 → 후보 선택 → `POST /regions` →
`region.bootstrap`(수집 → 판정 → 점수 → publish) → 생활권 편집(G0-2) → rerank 전체 재호출 → 보고서 "지역 추가" 장.

기존 지역에 시군구·법정동을 **더하거나 빼기**(D11-7·D11-10 — 지역끼리 합산 순위는 만들지 않는다, 함께 보려면 한 지역에 선택):
`PATCH /regions/{id}`(selections = 바뀐 뒤 전체) → change_event(critical) + `region.expand` 잡 → 추가 선택 수집 → 기준일 새 리비전
(오늘 리비전 1 이 판정 중이면 그 자리, 직전 발행 스냅샷이 비교 기준)에서 후보 전체 판정·rerank → publish → 보고서 §12 '지역 추가·변경'.
빠진 법정동의 단지는 분류와 무관하게 '범위 경계'(판정 범위 제외 — §12 '제외'에 잡힌다, R3 4차 M-4). 이름만 바꾸면 잡·이벤트 없음.
생활권 편집(`PUT /regions/{id}/living-areas`)·사람 확인 뒤 재판정은 **자동 등록**된다(D12-5 — 화면에서 따로 등록하지 않는다).

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

- 자동(D11-8·D12-6): worker 가 매일 03:00 `backup` 잡을 돌린다 — 결과(파일·크기·sha256·복사 수·실패 사유)는 `job_run.stats`(G7 잡 목록).
  - 위치 = `BACKUP_DIR`(compose: worker 의 `backups:/backups` 볼륨 — 원문 볼륨 `rawdata` 와 **다른** 볼륨). `<날짜>/db.dump`(Postgres
    `pg_dump -Fc`, worker 이미지의 `postgresql-client-16` — 서버 postgres:16 과 같은 판) 또는 `<날짜>/db.sqlite3`(개발 모드),
    원문은 `raw/` 에 증분(지우지 않는다).
  - 실패(pg_dump 없음·접속 실패·디스크 가득)는 잡 `failed` + stats 의 사유로 남는다 — 조용히 넘어가지 않는다.
    비밀번호는 URL 의 퍼센트 인코딩을 풀어 `PGPASSWORD` 로만 넘긴다(로그·stats 에 없다).
  - 보존: 기본 무기한. 수동 잡 `POST /jobs {"job_name":"backup","payload":{"keep_days":N}}`(1~3650)이면 N일보다 오래된 날짜 폴더만 지운다.
  - 백업 볼륨 꺼내기: `docker run --rm -v subscription-analyzer_backups:/b -v "$PWD":/out alpine cp -r /b /out/backups`.
- 대안(호스트 cron): `infra/backup.sh /srv/backup`(예 `0 3 * * * cd <repo> && infra/backup.sh /srv/backup`) — db 컨테이너에서
  `pg_dump -Fc` 후 `pg_restore --list` 검증, 원문은 `rsync -a`(없으면 tgz).
- 복구: 새 `db` 를 띄운 뒤 `pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean <백업>/db.dump`, 원문은 볼륨에 풀기.
  복구 후 `alembic upgrade head`(코드가 더 새면), `/health` 와 G7 신선도를 확인한다.

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
| `DATABASE_URL` | Postgres 16 새 DB(예 `postgresql+psycopg://sa:<pw>@localhost:5432/r4`) — `ENV=prod` 는 SQLite 를 거부한다(D11-9). devseed DB 와 섞지 않는다 |
| `RAW_DIR` / `REPORT_DIR` / `REFERENCE_DIR` | `../r4/raw` / `../r4/reports` / `../r4/reference` — 상대 경로는 API·worker 를 **둘 다 `backend/` 에서** 띄울 때의 기준이다(K3: 보고서 잡은 `REPORT_DIR` 기준 **파일 이름**만 저장하고 다운로드도 같은 `REPORT_DIR` 로 해석한다). 두 프로세스의 작업 폴더가 다르면 절대 경로를 쓴다 |
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

## 11. 발행 리비전·강등·사람 확인 (D11·D12 운영 규칙)

**발행 스냅샷은 불변**(D11-1) — **발행 리비전 = 저장된 읽기 모델**(D13-1, 계약 .10). 발행하는 트랜잭션이 그 리비전의 화면 응답
전부(대시보드·단지 목록·단지 상세·비교 입력·시장·변경 목록·민감도·CSV 행)와 보고서 입력 데이터를 시나리오별로 `snapshot_view` 에
저장하고, 발행 리비전의 GET·보고서는 **저장본만** 읽는다(현재 사실·강등·사람 확인·생활권·호재·지역 이름이 나중에 바뀌어도 그 리비전
응답 바이트는 같다). 판정 중(building·ready) 리비전만 지금 사실로 계산한다. 리비전 목록은 `GET /regions/{id}/snapshots`.

- **저장본**(D13-1·D14·**D15**, 계약 .12): 출처 서랍(`GET /provenance/{id}?snapshot_id=`)·주장 목록도 저장본이다(D14-1). 서랍은 모든
  시나리오·모든 kind 응답의 prov 와 접수 근거 `rd_<raw_document_id>` 를 담는다(D15-2). 행마다 **저장 모양 버전**(`shape_version`,
  정수)·`sha256` 를 읽을 때 검증한다 — 다르면 500 `stored_view_mismatch`(서버 로그 `snapshot_view.sha256_mismatch`·`shape_mismatch`):
  DB 를 손으로 고쳤거나 저장 kind 의 모양을 바꾸며 변환 마이그레이션을 빠뜨린 것이다(D14-4). 계약 버전 문자열(`contract_version`)은 기록만
  — 계약만 올라간 경우 500 이 나지 않는다(D15-3). 발행 뒤 만든 시나리오·그 리비전에 없던 생활권·단지·출처는 그 리비전에서 404 다(시나리오 결과는 시나리오
  실행이 만드는 새 리비전에 있다 — 그 시나리오 보고서도 그 리비전에서, 아니면 422 `scenario_not_in_revision`).
- **발행 = worker 잡**(D14-5): 저장본 계산·쓰기는 `snapshot.publish` 처리 함수(`app.snapshot_view.publish_revision`)에서만 한다 — 읽기
  전용 계산 → 묶음당 ≤2MB 짧은 트랜잭션으로 나눠 쓰기 → 마지막에 published 전환. 끝날 때까지 이전 발행 리비전이 기본 화면이다. 호재
  연결 PATCH·생활권 편집·지역 확장은 202 + job_id 를 돌려준다(G7 잡 목록에서 진행). 잡 stats 의 `total_s`·`write_max_lock_s`(API 쓰기가
  기다린 최대 시간 상한)·`missing_provenance`(출처 누락 '확인 불가' 건수, D14-8)를 본다. 발행 잡이 실패하면(failed) 리비전은 ready 로
  남고 넣던 저장본 행은 지워진다 — 원인을 고친 뒤 `POST /jobs {"job_name":"snapshot.publish","payload":{"snapshot_id":N}}`.
  daily 이월·주간 마감·지역 확장·bootstrap 의 발행이 예외로 실패하면 재시도 `snapshot.publish` 잡이 자동으로 남는다(stats
  `publish_retry_job_id`, D15-6).
- **발행 single-flight**(D15-6): 리비전마다 발행은 하나만 돈다(`snapshot.publish_lease` = '<보유자>|<epoch>', 보유자 = `job:<id>`).
  겹친 발행 잡은 아무것도 지우지 않고 failed `publish_in_progress: …` — 먼저 돈 잡이 발행한다. 보유 잡이 running 이 아니거나 15분이
  지나면 다음 발행이 넘겨받는다(worker 가 죽어도 손으로 풀 필요 없음). 급할 때만: `UPDATE snapshot SET publish_lease = NULL WHERE id = N`.
- **후속 발행 잡**(D15-6): 판정 중·발행 계산 중인 리비전에 호재 연결 PATCH 가 들어오면 `snapshot.publish` `{snapshot_id, follow_up: true}`
  잡이 생긴다. 그 리비전 발행 계산이 그 쓰기를 읽었으면 전환이 잡을 done(`included_in_snapshot_id`)으로 닫고, 아니면 잡이 새 리비전을
  발행한다(`deferred_to` = 판정 중 리비전 발행 때 들어감).
- **backfill**(D14-9·**D15-3**): 마이그레이션은 앱 코드를 읽지 않는다(0010·0011·0012 = 테이블·표식만). 업그레이드 뒤
  `cd backend && uv run alembic upgrade head` → `uv run python -m app.snapshot_view backfill`(= `python scripts/tasks.py backfill`, 멱등 —
  .9 행 단위 사람 확인을 의미 묶음으로 옮기고, 발행 리비전의 **미완 단위**만 채운다). 완결성은 (리비전, kind, 시나리오) **완료 표식**
  (`snapshot_view_unit` — 그 단위의 마지막 쓰기와 같은 트랜잭션)으로 본다: 표식이 없거나 done=false 이거나 실제 행 수가 표식 rows 보다
  적으면 미완 → 그 단위 GET 503 `materialize_pending`(Retry-After 30초)·`POST /reports` 503. backfill 은 이미 있는 행을 그대로 두고 빠진
  키만 넣으며, 리비전마다 따로 실패한다(출력 `failed=[…]` — 그 리비전만 503 으로 남고 다음 실행이 이어서 채운다). worker 는 시작할 때 같은
  backfill 을 한 번 돈다. 미완 리비전 수 = `app.snapshot_view.pending_count(session)`. 0011 → 0012 업그레이드는 기존 행 묶음을 완료 표식으로
  옮기고, 0012 이전 backfill 이 중간에 멈춘 흔적(단지 상세·시장 행 수가 시나리오마다 다름, 출처 서랍 묶음 모자람, 한 시나리오 kind 통째
  없음)은 미완 표식으로 둔다.
- **'재판정 필요'**(D10-1·M6): 판정 중 리비전에서 지금 사실과 비교한다(지역 단위 변경 — 생활권 편집·지역 확장 포함). 발행 리비전은
  발행 순간 값이 저장본에 고정된다 — 사람 확인 등은 새 리비전과 자동 재판정 잡으로 나타난다.
- **강등(검증 모순)**(D11-3·D12-2): contradicted 주장을 사람이 고치면 그 사실이 '확인 불가(검증 모순)'가 된다. 강등은
  (단지, 의미 필드, 모순 값)에 걸린다 — 같은 모순 가격·계약금을 실은 **새 공고**가 와도 계속 가려진다. 풀리는 길은 두 가지:
  사람 확인(G7) 또는 새 원문이 **다른 값**을 낼 때(같은 값 재수집·값 없는 행·출처 상충 보류는 풀지 않는다). 풀린 뒤 모순 값이
  다시 채택되면 다시 강등된다(critical change_event). 체크리스트 '사실 재확인'은 강등이 남아 있는 동안 닫아도 다시 열린다.
- **사람 확인**(D11-3·D12-1·D12-5·**D13-2**): 사람 확인은 강등과 같은 **(단지, 의미 필드)** 단위다 — 가격은 그 타입의 공고문
  타입 행과 모든 공고의 그 타입 가격, 계약금은 모든 공고의 계약금. 사람 확인 이전에 관측된 출처는 어느 공고 행이든(무순위 새 공고·
  기준 타입 칸 없는 공고·시행일만 늦은 공고) 사람 확인 값에 진다. 사람 확인 **이후** 관측된 공고문·청약홈이 **다른 값**을 내면 그 값이
  채택되고 critical change_event + 체크리스트 `사람 확인 재검토: <필드>` 가 생긴다(새 공고 행이어도) — 원문을 보고 다시 사람 확인하거나
  항목을 닫는다(같은 필드를 다시 사람 확인하면 그 항목은 자동으로 닫힌다 — D14-6). 확인 시각은 **시간대가 붙은 RFC3339**
  (`2026-10-09T10:20:00+09:00`)이고 10분 넘게 미래면 422, 날짜 비교는 KST 달력 날짜다. 이미 수집된 공고가 **다른 값**인데 그보다
  **이른 확인일**의 사람 확인은 422 로 거절된다(같은 값이면 받는다). 사람 확인·생활권 편집·강등은 그 지역 가장 새 기준일의 리비전에 재판정을 **자동 등록**한다
  (G7 잡 목록에서 진행을 본다). 다음 날 변경 없는 수집도, 이전 판정 뒤 사실이 바뀐 단지는 이월 대신 재판정한다.
- **할인**(D11-6·D12-3·**D14-2**): 공고문에 금액이 명시된 할인만, 출처 라벨이 '확인됨'일 때만 구매가에서 뺀다 — 상세·목록 정렬·필터·비교·
  보고서·점수 모두 같은 규칙(`analysis.price_view.current_price`). '확인됨'은 **그 줄 전체**(금액 앞뒤·괄호·각주)에 조건(층·동·호·라인·
  '~시'·한정·최대·조건·선착순·특별공급·잔금·완납·기간·까지·※·단)이 없을 때만이다. 추정·OCR 할인은 표시만. '할인 없음' 줄·취득세·
  중도금 이자·발코니·옵션 지원은 할인이 아니다.
- **보고서**: 발행 전(판정 중) 리비전은 만들 수 없다(409). 파일 이름에 지역·리비전·잡 id 가 들어가 같은 기준일 리비전끼리 덮어쓰지 않는다.
- **prod + SQLite 거부**(D11-9): `ENV=prod` 는 Postgres `DATABASE_URL` 만 받는다.

## 12. 회귀 실행 순서

`python scripts/tasks.py regress` 는 frontend `node_modules` 가 없으면 `npm ci` 를 **먼저** 하고 pytest 회귀 → e2e 순으로 돈다.
같은 frontend 에서 `npm ci` 가 도는 동안 회귀(T13 프론트 lint 검사)를 돌리면 eslint 가 모듈을 못 찾는다 — 설치를 끝낸 뒤 돌린다
(R3 4차 리뷰가 확정한 간헐 실패 원인. 실패 메시지에 eslint stderr 가 나온다).
