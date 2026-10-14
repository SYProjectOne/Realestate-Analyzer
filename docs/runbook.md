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

**청약홈 적재 시간 회피(D23-4)**: 청약홈 공식 API 데이터셋은 자정 직후 다시 적재되는 동안 조건 없는 전체 건수가 0(`totalCount 0`)이다(R4 4차 관측
APT 00:01~00:29 · 잔여세대 ~00:59 KST). **00:00~01:00 KST 에는 지역을 만들지(`region.bootstrap`) 말고 수동 수집도 하지 않는다.** 그 시간에 걸리면
§1-1 처럼 실패 행 + degraded 로 남고 발행하지 않은 채 30분 뒤 다시 돈다(정기 `collect.daily` 06:00 은 이 시간대 밖).

## 1. 청약홈 페이지 구조 변경

증상: 파서 테스트 실패, 또는 G7 수집 성공률 급락·필드 "확인 불가" 급증.

1. 실패한 날의 원문을 확인한다: `RAW_DIR/applyhome_list/<날짜>/` (sha256 파일명).
2. 새 HTML 을 녹화 픽스처로 저장한다(`contracts/fixtures/…` 는 WP9 소유 — CHANGELOG 에 사유).
3. 실패하는 테스트 이름 + 새 HTML 만 WP1(수집)/WP2(파서) 담당에게 준다. 다른 맥락은 주지 않는다.
4. 수정이 머지되면 `python -m app.worker --once` 또는 G7 재수집 → 다음 스냅샷에서 diff 를 확인한다.

### 1-1 청약홈 API 빈 데이터셋(`totalCount 0`) — D23-4

증상: G7 출처 상태 `applyhome_list`(·`applyhome_detail`) 실패에 `last_http_status` **200** · `last_error_text` `empty_dataset: totalCount 0`, 잡
`region.bootstrap`·`collect.daily` 가 `queued`(stats `requeue_reason` 'degraded_source: … 청약홈 API 빈 데이터셋 …', `not_before` 30분 뒤), 지역이
`bootstrapping` 에 머무름.

자동: 그 수집은 실패 행(http_status 200 · path 없음)을 남기고, 그 시도는 웹 경로로(목록)·웹 상세/경쟁률로(상세) 폴백한다. 수집 결과는 degraded
(stats `degraded_sources`)라 **판정·발행(이월 포함)을 하지 않고** 같은 잡을 30분 뒤 다시 돌린다(최대 6회 = 3시간, 넘으면 `failed`). bootstrap 이면
지역은 `bootstrapping` 그대로(발행 리비전 없음), 일일 수집이면 이전 발행 리비전이 그대로 기본이다. 재시도는 같은 원문을 멱등하게 다시
정규화한다(D23-1 — 중복 행·이벤트 없음).

사람: 3시간 넘게 `failed` 면 data.go.kr 공지(점검)를 확인하고, 데이터셋이 돌아온 뒤(`perPage=1` 조회의 `totalCount` > 0 — 키는 출력하지 않는다)
G7 에서 그 잡을 다시 등록한다. 00:00~01:00 KST 에 지역을 만들지 않는다(§0-3).

## 2. 공식 홈페이지 403·DNS 실패 지속

자동: 수집 결과가 `http_status=403`(또는 연결 실패) 행으로 남고 화면은 "확인 불가(403, 날짜)" 를 유지한다.
`core.http` 는 4xx 를 재시도하지 않고, robots.txt 가 막으면 요청 자체를 하지 않는다(`blocked_by_robots`).

사람:
1. G7 에서 해당 단지·소스의 실패 이력을 본다.
2. 전화로 확인한 내용은 요약 텍스트만 G7 사람 입력으로 남긴다(`human_check.entered_by` = 역할 "운영자", 이름·번호 금지).
3. 403 이 robots·UA 문제로 보이면 `HTTP_USER_AGENT`·`HTTP_RATE_PER_HOST` 를 낮춰 본다(우회 금지 — 공개 페이지만).

접수 '확인 불가' 사유별 처리(R6-INTAKE, `docs/design/wp/R6_TESTS_INTAKE.md`) — `SELECT reason, count(*) FROM intake_status WHERE snapshot_id = <id> GROUP BY reason;`

| 사유 | 뜻 | 사람 할 일 |
| --- | --- | --- |
| `connect` | 도메인이 풀리지 않음(분양 끝난 사이트 폐쇄가 대부분) | 시행·시공사 대표 페이지·견본주택 전화로 확인 → G7 사람 확인(field `intake_status`) |
| `TLS` | httpx·**헤드리스 브라우저 모두** 인증서 오류(만료·자체 서명·호스트 불일치 — R7-SITE: httpx 만 실패하면 브라우저가 robots.txt·본문을 다시 받는다, 검증은 끄지 않음). 경로·브라우저 오류는 원문 행 `meta.fetch` | 브라우저로 직접 보고 G7 입력(프로그램은 인증서 검증을 끄지 않는다) |
| `robots` | robots.txt 가 우리 UA 를 막음(TLS 사이트면 브라우저로 받은 robots.txt — RFC 9309) | 우회 금지. 분양 문의처 전화 등으로 확인 → G7 입력 |
| `403`·`404` | 접근 거부·페이지 없음 | 위와 같음 |
| 공식 홈페이지가 다른 단지 | 판정기가 auto 로 다른 사업 페이지라고 함(도메인 재사용) | 단지의 새 공식 페이지를 찾으면 G7 입력 |
| 공식 홈페이지 동일성 미확인 | 판정기 review·unclear(LH 청약 포털·브랜드 포털·주차 도메인 등) | note 의 `jl_<seq>` 로 G7 판정 로그 확인 → 사람 확인 |
| 문구로 판단 불가 | 같은 단지 페이지지만 본문·팝업 그림 OCR 글자(R7-SITE, 라벨 '추정(OCR)')에 접수 문구가 없음 | 스크린샷(`screenshot_path`)을 보고 G7 입력. 팝업 그림을 OCR 했는지는 스크린샷 원문 행 `meta.kind='official_site.popup_ocr'`(`status`·`reason`) |
| 판정 대상 아님(범위 경계·공공분양 …) | 범위 경계 또는 포함/제외 classify auto 제외 클래스 단지 — 동일성·접수 classify 를 하지 않는다(D26-3). 수집 실패 행도 이 사유(원인은 원문 행) | 할 일 없음(점수 대상 아님). 단지가 대상이 되면 다음 수집에서 다시 분류된다 |
| 판정 미해결 | 접수 classify review | 위와 같음 |

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
- pg_dump 위치(R5-OPS 3): 설정 `PG_DUMP_PATH`(실행 파일 또는 그 bin 폴더)가 있으면 그것만 쓴다 — 그 경로에 없으면 PATH 로
  넘어가지 않고 잡이 `failed`(사유 'PG_DUMP_PATH 의 pg_dump 없음'). 비어 있으면 PATH 의 `pg_dump`. 성공한 잡의 `job_run.stats.db` 에
  쓴 경로(`pg_dump`)와 `pg_dump --version` 첫 줄(`pg_dump_version`)이 남는다 — **서버와 같은(또는 더 새) 판**인지 여기서 본다
  (더 낮은 판 pg_dump 는 'server version mismatch' 로 실패하고 그 stderr 가 사유로 남는다).

### 8-1 Docker 없는 이 PC (D19 — 운영 DB PostgreSQL 17.9, 포트 5434)

D19-1·D19-2: Docker 를 쓰지 않고 이 PC 의 PG17 에 운영 DB(`subscription_analyzer`)를 두었다. PG17 의 `pg_dump` 는 PATH 에 없어서
(PATH 에는 다른 앱의 PG16 이 있거나 아무것도 없다) `PG_DUMP_PATH` 없이 매일 03:00 `backup` 잡이 'pg_dump 없음(PATH)' 으로 실패했다.

1. 판 확인: `& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" --version` → `pg_dump (PostgreSQL) 17.x`.
2. 운영 `.env`(`backend/.env` 또는 `ENV_FILE`)에 한 줄 — **따옴표 없이**(또는 작은따옴표). 큰따옴표 안에서는 `\b` 같은 역슬래시가
   이스케이프로 읽혀 경로가 깨진다:
   `PG_DUMP_PATH=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe` (폴더 `C:\Program Files\PostgreSQL\17\bin` 만 적어도 된다)
3. 백업 위치도 정한다: `BACKUP_DIR=D:\sa-backup` 처럼 원문(`RAW_DIR`)과 다른 디스크·폴더(D12-6). 비우면 `RAW_DIR` 상위 폴더 아래 `backup`.
4. worker 를 다시 띄운다(설정은 시작 때 읽는다). 바로 확인하려면 수동 잡 `POST /jobs {"job_name":"backup"}` 뒤
   `python -m app.worker --once` → G7 잡 목록에서 `backup` 이 `succeeded`, stats `db.kind=postgres`, `db.pg_dump_version` 이 17.x,
   `<BACKUP_DIR>\<날짜>\db.dump` 크기·sha256 을 본다.
5. 복구(PG17 도구로): `& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --list <BACKUP_DIR>\<날짜>\db.dump` 로 목록을 확인한 뒤
   `& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -h 127.0.0.1 -p 5434 -U sa -d subscription_analyzer --clean <BACKUP_DIR>\<날짜>\db.dump`
   (비밀번호는 프롬프트 또는 그 셸에서만 `$env:PGPASSWORD` — 명령 기록·문서에 남기지 않는다). 뒤이어 `alembic upgrade head`, `/health`.
- compose(Docker) 의 worker 는 이미지의 `postgresql-client-16`(PATH)을 쓴다 — `PG_DUMP_PATH` 를 비운다. 서버를 17 로 올리면
  `infra/Dockerfile.worker` 의 `PG_MAJOR` 도 같이 올린다.

## 9. 비밀값

- 비밀은 `infra/.env`(Docker) 또는 `backend/.env`(로컬)에만. 커밋 금지(pre-commit `no-dotenv`·`gitleaks`).
- 판정기 자격 증명(`TYPESAFE_API_KEY`·`OPENROUTER_API_KEY`·`JEV_API_KEY` … — `JUDGE_SECRET_ENV_NAMES`)도 같은 `.env`(또는 `ENV_FILE`)에
  둔다. 판정기 자식 프로세스에는 그 이름들만 넘어가고(사용자 환경변수가 있으면 그 값이 이긴다), 기동 실패 stderr·오류에서는 값이
  가려진다(D21-8·D19-3). 판정기와 무관한 비밀(`DATA_GO_KR_KEY` 등)은 넘기지 않는다.
- 남에게 주는 링크는 G7 '공유 링크'로 발급한다(`POST /share-links`, 쓰기 토큰만): 읽기 전용(GET 만), 만료
  `SHARE_TOKEN_TTL_DAYS`(기본 30일), 서버에는 sha256 만 남는다. 링크 `<origin>/share#<token>` 은 발급 때 한 번만 보인다.
  잃어버리거나 노출되면 같은 패널에서 회수(`DELETE /share-links/{id}`) — 그 토큰은 바로 401.
- `READONLY_TOKEN` 은 운영자 열람용 고정 토큰이다(만료 없음 — 남에게 주지 않는다).
- 키가 노출되면: 발급처에서 폐기·재발급 → `infra/.env` 교체 → `docker compose -f infra/docker-compose.yml up -d` (로그는 이미 마스킹되지만 확인).

## 10. R4 운영 시험 — 인천·김포 실데이터 1회 실행 (준비 문서, WP9 R3)

RA §8-1 R4 게이트: "실제 JEV 연결, 인천·김포 → 실제 1회 실행 호출 수·시간 기록; 2회차 호출 0 확인; runbook 갱신".
RA §9 통과 기준: 1회차 실제 호출 수 ≤ 132(캐시·원자 분할로 늘 수 있으나 이유를 기록), 2회차 실제 호출 0.
**R3 회귀(`python scripts/tasks.py regress`)의 결과와 발견 목록을 사람이 확인한 뒤에만 실행한다(DECISIONS D8).**
아래 10-1~10-5 는 R3 때 준비한 절차다. **2026-10-12 처음 실제로 돌렸고**(결과 `docs/design/wp/R4_RESULT.md`), 실제로 다르게 해야
했던 것과 결과 표는 **10-6** 에 있다 — 다시 돌릴 때는 10-6 을 먼저 읽는다. R4-FIX 뒤 재시험(같은 날, D19 로컬 PG17)의 결과 표는
**10-8**(상세 `docs/design/wp/R4_RESULT2.md`), 재시험 절차는 10-7. R4-CORE8 뒤 3차 재시험 절차는 10-9, 결과 표는 **10-10**
(상세 `docs/design/wp/R4_RESULT3.md`). R4-CORE9 뒤 4차 재시험 절차는 10-11, 결과 표는 **10-12**(상세 `docs/design/wp/R4_RESULT4.md`).
R4-CORE10 뒤 5차 재시험 절차는 10-13, 결과 표는 **10-14**(상세 `docs/design/wp/R4_RESULT5.md`). 운영 전 정리(R4-CORE11, D24-1 — N16·m-e)는 **10-15**.

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

### 10-6 R4 1차 실행 결과와 실제 절차 (2026-10-12, main `3a4141d`, 계약 `.13`) — 상세 `docs/design/wp/R4_RESULT.md`

**결과: 게이트 미통과** (critical 3: 숨은 판정기 호출 C1 · 실거래 법정동 코드 누락으로 종합 점수 전무 C2 · 잔여 공고 제목이 단지 이름 '확인됨' C3).

| 항목 | 값 |
| --- | --- |
| 환경 | Windows 11, Docker 없음 → 임베디드 Postgres 16.2(pgserver), `ENV=prod`, API 127.0.0.1:18431 |
| JEV | `npx -y @jkudish/jev-mcp@0.14.1`(실행 전 `npm view @jkudish/jev-mcp version` = 0.14.1 → 고정) |
| adapter_version | `0.2.0+jev-mcp@0.14.1+jev-1.13.0`(351행) · `…+jev-latest`(149행, extract 로컬 단락) — **2개**(C1) |
| 1회차 시간 | bootstrap 23분 59.7초(수집 약 21분 40초 · 판정 2분 9초 · 발행 약 6초), reference.refresh 11초 |
| 1회차 실제 호출 | **500**(screen 210 · extract 190 · audit 14 · classify 34 · compare 46 · noul 3 · rerank 1 · decide 1 · verify 1), blocked 0 · error 0 · cached 3. 모델 호출(provider typesafe) 351 · 로컬 단락 149 |
| 132 대비 | +368 — 공고문 조각 단위 screen·extract(+316), 중복 단지 행·범위 밖 후보로 compare +34, 뉴스 호재 screen 20·classify 31. 판정 대상이 1단지라 noul·decide·verify 는 −27 |
| 단지·범위 | 단지 행 88, 판정 대상 1 → 3, TOP 5 없음(종합 점수 전 단지 미판정) |
| 수집 실패 | official_site TLS 2, rtms 분양권 API 403 2(활용신청 없음), 타임아웃·파싱 실패 0 |
| 2회차 (a) 같은 스냅샷 rejudge | `judgment_log` 500 → 500, `judge_calls` 0, cached 434 — **그러나 MCP `tools/call` 298건**(프록시 측정, C1) → 실패 |
| 2회차 (b) collect.daily(1시간 뒤) | 778.7초, change_event 29(1회차 빈 값이 채워진 것 — M5), 새 판정 16 + 숨은 호출 9 |
| 보고서 | `--snapshot 3 --format pdf` 성공, 172쪽(ECharts 번들 없음 경고 — 표만) |

실제로 다르게 해야 했던 절차(다음 실행은 이대로):

1. **Postgres(Docker 없음)** — backend dev 의존성 `pgserver` 의 번들 Postgres 16 을 r4 폴더 안에 띄운다(프로세스가 끝나도 서버는 남는다):

   ```python
   # r4/pg_start.py — uv run python ../r4/pg_start.py  (backend/ 에서)
   import pgserver; from pathlib import Path
   srv = pgserver.get_server(Path("../r4/pgdata").resolve(), cleanup_mode=None)
   if "1 row" not in srv.psql("SELECT 1 FROM pg_database WHERE datname='r4';"): srv.psql("CREATE DATABASE r4;")
   print(srv.get_uri())   # postgresql://postgres:@127.0.0.1:<임의 포트>/postgres → DATABASE_URL=postgresql+psycopg://postgres:@127.0.0.1:<포트>/r4
   ```

   멈춤: `.venv/Lib/site-packages/pgserver/pginstall/bin/pg_ctl.exe -D ../r4/pgdata -w stop`. 다시 띄우면 포트가 바뀔 수 있다(`.env` 갱신).
   SQLite 우회는 하지 않는다(D11-9).
2. **alembic 은 `ENV_FILE` 을 읽지 않는다**(M4) — `export ENV_FILE=…; uv run alembic upgrade head` 는 `backend/dev.db`(SQLite)를
   조용히 마이그레이션한다(출력 `Context impl SQLiteImpl`). 반드시 `DATABASE_URL=postgresql+psycopg://…/r4 uv run alembic upgrade head`
   로 하고 `PostgresqlImpl` 과 `alembic current` = `0013 (head)` 를 확인한다. 잘못 생긴 `backend/dev.db` 는 지운다.
3. **키 옮기기** — r4 `.env` 는 스크립트로 저장소 루트 `.env` 에서 `DATA_GO_KR_KEY`·`NEWS_API_PROVIDER`·`NEWS_API_KEY` 만 읽어 쓴다
   (`cp ../infra/.env.example` 후 손 편집 대신). 값은 출력하지 않고 존재·길이만 찍는다. `RAW_DIR`·`REPORT_DIR`·`REFERENCE_DIR`·
   `BACKUP_DIR` 은 절대 경로. 끝나면 r4 `.env`·토큰 파일을 지운다.
4. **smoke 는 `JEV_MCP_CMD` 를 무시한다**(m1, `tests/judge/test_live.py` 는 기본 `@latest`) — 고정 버전과 `@latest` 가 같은지
   `npm view @jkudish/jev-mcp version` 으로 따로 확인한다.
5. **실제 호출 수는 `judgment_log` 로 셀 수 없다**(C1 이 고쳐지기 전까지) — 어댑터가 판정기를 부른 뒤 다른 버전 hash 의 기존 행을
   replay 하면 행·잡 stats·로그·G7 `real_calls` 모두 '캐시'로 남는다. 2회차는 MCP `tools/call` 을 세는 stdio 프록시를 `JEV_MCP_CMD` 로
   준다(도구 이름·시각만 기록 — payload 금지; adapter_version 은 서버 버전에서 오므로 hash 는 바뀌지 않는다):

   ```python
   # r4/jev_count_proxy.py — JEV_MCP_CMD="<backend/.venv/Scripts/python.exe> <r4/jev_count_proxy.py>"
   import json, shutil, subprocess, sys, threading, time
   from pathlib import Path
   OUT = Path(__file__).resolve().parent / "logs" / "jev_calls.jsonl"
   child = subprocess.Popen([shutil.which("npx"), "-y", "@jkudish/jev-mcp@0.14.1"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, bufsize=0)
   def up():
       for line in iter(sys.stdin.buffer.readline, b""):
           try:
               m = json.loads(line)
               if m.get("method") == "tools/call":
                   with OUT.open("a") as f: f.write(json.dumps({"ts": time.time(), "tool": m["params"]["name"]}) + "\n")
           except Exception: pass
           child.stdin.write(line); child.stdin.flush()
       child.stdin.close()
   def down():
       for line in iter(child.stdout.readline, b""): sys.stdout.buffer.write(line); sys.stdout.buffer.flush()
   threading.Thread(target=up, daemon=True).start(); threading.Thread(target=down, daemon=True).start()
   sys.exit(child.wait())
   ```

   통과 = `jev_calls.jsonl` 줄 수 0. 1회차 adapter_version 이 2개 이상이면 2회차에 숨은 호출이 생긴다.
6. **API** — `uv run uvicorn app.main:app --port 8000` 대신 `.env` 의 `API_PORT`(빈 포트)로 `uv run python -m app.serve`. Git Bash 에서
   `/api/...` 를 인자로 넘기는 스크립트는 MSYS 경로 변환을 피하려고 경로 앞 `/` 없이 넘기거나 `MSYS_NO_PATHCONV=1`.
7. **집계 SQL(Postgres)** — `sqlite3` 대신 psql/psycopg. `json_extract(stats,'$.pipeline.judge_calls')` → `stats->'pipeline'->>'judge_calls'`,
   rejudge 잡은 `stats->>'judge_calls'`·`stats->>'cached'`. 추가로 볼 것: `SELECT output_json->>'provider', output_json->>'model', tool,
   COUNT(*) FROM judgment_log GROUP BY 1,2,3`(모델 호출 vs 로컬 단락), bootstrap `pipeline.judge_calls` 는 수집 단계 호재 screen 을
   빼고 센다(m2 — `judgment_log` 와 20 차이).
8. **2회차 (a)** — 발행된 스냅샷 rejudge 는 같은 기준일 **새 리비전**(스냅샷 2)을 만들고 발행한다. (b) 뒤에는 스냅샷 3. 보고서 SID 는
   가장 새 발행 리비전(`--snapshot 3` → 비교 기준 revision_of 2 자동).
9. **2회차 (b)** — `worker --once` 가 official_site 재렌더로 약 12분 막힌다. 1회차 직후에는 실제 공고 변화가 없어도 빈 값 채움·접수
   상태 변화로 재판정이 생긴다(M5) — change_event 내용을 기록한다.
10. **보고서** — worktree·Docker 없는 실행은 `frontend/node_modules` 가 없어 차트가 빠진다(m4). 차트가 필요하면
    `REPORT_ECHARTS_JS=<echarts.min.js 절대 경로>`.
11. `uv run playwright install chromium` 은 공용 `%LOCALAPPDATA%\ms-playwright` 에서 쓰지 않는 다른 버전 브라우저를 지운다 — 같은 PC 의
    다른 worktree 가 쓰는 버전이면 그쪽에서 다시 설치해야 한다.

### 10-7 R4 재시험 절차 — R4-FIX(D18·D20, 계약 .15) 뒤 바뀐 것 (`docs/design/wp/R4_FIX_TESTS.md`)

10-6 의 우회 중 아래는 코드로 고쳐졌다. 다시 돌릴 때는 이 절을 10-1~10-6 보다 먼저 따른다.

1. **마이그레이션**(M4, 계약 .15 S6): `ENV_FILE=../r4/.env uv run alembic upgrade head` — 환경변수 `DATABASE_URL` 이 없으면 env.py 가
   `ENV_FILE` 의 앱 설정 URL 을 쓴다(못 읽으면 실패 — 조용히 `backend/dev.db` 를 만들지 않는다). 출력 `Context impl PostgresqlImpl` 과
   `uv run alembic current` = `0015 (head)` 를 확인한다. (10-6 ②의 `DATABASE_URL=… alembic` 우회는 더 필요 없다.)
2. **smoke**(m1): `JEV_MCP_CMD="npx -y @jkudish/jev-mcp@<버전>" uv run pytest -m live tests/judge/test_live.py -s` — 출력 `"cmd"` 가
   고정 버전인지 확인한다.
3. **지역 조회 창**(D18-8 → D20-1, 계약 .15): 기본 창이 **지난 24개월 + 향후 12개월**이라 2025-06·07 공고(오퍼스 한강 스위첸·해링턴플레이스
   풍무)가 들어온다(첫 수집 시간·판정 호출이 늘어난다 — 기록). 다른 창이 필요하면 `POST /regions` 본문에
   `"applyhome_query": {"from_ym": "2024-10", "to_ym": "2027-10"}`(계약 .15 F3). 공고 전 단지(카이브 유보라·그랑포레)는 청약홈에 없고,
   주간 뉴스 수집 뒤 판정기가 고른 **트랙 (A) 공고 예정 후보**(`track='A'`, `applyhome_id` null, 라벨 비공식 — D20-2)로 나온다:
   `SELECT id, name, former_names, inclusion_class FROM complex WHERE track='A';` · 수집 stats `assembled.upcoming`
   (screened·rejected·names·created·existing·aliases). 공고가 나오면 같은 행에 주택관리번호가 붙는다(새 행 없음).
4. **실제 호출 수**(C1·D18-2): 잡 stats `tools_calls`(전송 계층에서 센 MCP `tools/call` 수)·`tools_calls_by_tool` 과 최상위
   `judge_calls`(JevMcpAdapter 잡은 = `tools_calls`, 수집 단계 호재 screen 포함 — m2). G7 `real_calls` 도 같은 수를 쓴다(이전 잡은
   행 수가 하한). 프록시(10-6 ⑤)는 교차 확인용으로만:

   ```sql
   SELECT id, job_name, stats->>'tools_calls' AS tools_calls, stats->'tools_calls_by_tool' AS by_tool,
          stats->>'judge_calls' AS judge_calls, stats->>'cached' AS cached FROM job_run ORDER BY id;
   SELECT adapter_version, COUNT(*) FROM judgment_log GROUP BY 1;   -- 1개여야 한다(고정 모델, D18-1)
   SELECT provider, model, COUNT(*) FROM judgment_log GROUP BY 1,2;  -- 응답의 실제 모델(계약 .15 열 — 0015 가 옛 행도 채운다)
   ```

   2회차 통과 = 재판정 잡 `tools_calls` 0 (엄격, D18-5). 모델이 바뀐 것을 본 실행은 `change_event(judge·version)` 1건을 남기고 그
   실행은 옛 키로 끝난다 — 다음 실행(등록된 전체 재판정)이 새 키로 돈다.
5. **첫 적재 요약**(m3): bootstrap 의 빈 값 → 값 변경은 `change_event(region·first_load·info)` 한 줄(`첫 적재: 단지 n개, 값 k건`)이다 —
   G1 '최근 변경'이 첫날 critical 로 차지 않는다. 수집 stats `first_load_folded` 에 건수.
6. **실거래 법정동**(C2): 수집 stats `loaded.rtms_legal_dong`(matched·unmatched·ambiguous·match_rate), 주간 bootstrap 은
   `assembled.rtms_backfill.legal_dong`. R4 DB 처럼 코드 없이 적재된 행은 다음 실거래 적재 때 자동 보정되고, 수동으로는
   `uv run python -m app.collectors.rtms.legal --region <id>`.
7. **잔여 공고**(C3·M1·M3): 무순위·임의·재공급 공고는 원 단지 행에 `remaining_event` 로 붙고 자기 번호 행을 만들지 않는다. 공고문이
   인용한 원 번호(최초 주택관리번호) 단지는 원 공고를 번호로 다시 받는다(수집 stats `loaded.originals` = {wanted, documents}).
   확인: `SELECT applyhome_id, name FROM complex WHERE applyhome_id ~ '^20[0-9]{2}9[0-9]{5}$';` → 원 단지를 못 찾은 잔여 공고만(사업의 유일한 행).
8. **보고서 차트**(m4): Docker·worktree 실행에서 `frontend/node_modules` 가 없으면 `REPORT_ECHARTS_JS=<echarts.min.js 절대 경로>` 를
   `.env` 에 둔다(없으면 차트 자리에 표만 — 경고). `cd frontend && npm ci` 를 한 체크아웃이면 `frontend/node_modules/echarts/dist/echarts.min.js`.
9. **같은 날 다시 수집**(M5·D18-6): bootstrap 직후 같은 날 `collect.daily` 의 새 판정(`tools_calls`)은 0 이어야 한다(실제 공고 변화가
   없을 때). 0 이 아니면 그 잡의 `change_events`·`rejudge_complex_ids` 와 change_event 내용을 기록한다.

### 10-8 R4 재시험 결과 (2026-10-12, main `3e89892`, 계약 `.15`) — 상세 `docs/design/wp/R4_RESULT2.md`

**결과: 게이트 기준 통과**(2회차 (a) `tools/call` 0 엄격 · 1회차 이유 기록). 단 새 critical 1(N1 공고문 '천원' 단위 표를 원으로 — 한 단지 가격이
1/1000 로 '확인됨')·major 5, 같은 날 daily 0(D18-6)·`missing_provenance` 감소는 실패 — 운영 전 수정 대상.

| 항목 | 값 |
| --- | --- |
| 환경 | Windows 11, Docker 없음, **D19 로컬 PostgreSQL 17.9(5434) DB `subscription_analyzer_r4`**, `ENV=prod`, API 127.0.0.1:18533 |
| 마이그레이션 | `ENV_FILE=… uv run alembic upgrade head` → `PostgresqlImpl`, `0015 (head)`, `dev.db` 없음 |
| JEV | `npx -y @jkudish/jev-mcp@0.14.1`(실행 전 최신 확인 후 고정), smoke 출력 `"cmd"` 고정 버전. 워커·API 는 같은 버전을 띄우는 계수 프록시 경유 |
| adapter_version | `0.2.0+jev-mcp@0.14.1+jev-1.13.0` **1개**(582행; provider none 136행 포함) |
| 1회차 시간 | bootstrap **44분 43.8초**(일일 단계 34분 44초 · 주간 단계 6분 39초 · 판정 3분 8초 · 발행 11초), reference.refresh 12초. 조회 창 지난 24 + 향후 12개월로 1차(24분)보다 길다 |
| 1회차 실제 호출 | **582** = 잡 `tools_calls` = 프록시 `tools/call` = `judgment_log` 행(screen 193 · extract 178 · compare 139 · classify 40 · noul 12 · audit 10 · decide 5 · verify 4 · rerank 1), 모델 호출 446 · 로컬 단락 136, 수집 단계 판정 64 포함, blocked·error 0 |
| 132 대비 | +450 — 공고문 조각 screen 153·extract 162(그중 136 로컬 단락), 출처 상충 compare 139, 호재 screen·classify 50, 공고 예정(D20-2) 44 |
| 단지·범위 | 단지 행 77, 판정 대상 4 → 5, **종합 점수 2단지 — TOP 5 = 사우역 지엔하임 4.75 · 엘리프 검단 포레듀 3.51**(나머지 2단지는 유동성 입력 없음) |
| 수집 | 실거래 52,163건 법정동 100%(`match_rate` 1.0), **분양권 API 137건 200**(4,109건), 미분양 KPI 2,029호(확인됨), official_site 404 1·connect 6·TLS 3, 공고문 정규화 실패 2(NUL, N2), 타임아웃·파싱 실패 0 |
| 2회차 (a) 같은 스냅샷 rejudge | **프록시 `tools/call` 0 · `tools_calls` 0 · `judgment_log` 582 → 582**, cached 467, 80.4초 → 통과 |
| 2회차 (b) 같은 날 collect.daily | 1,070.5초, change_event **19**(잔여 공고 번호 행 74·75 — N3·N4), 새 판정 15(= 프록시 15, 숨은 호출 0) → D18-6 미충족 |
| 보고서 | `--snapshot 3 --format pdf` 152쪽, `REPORT_ECHARTS_JS` 지정으로 차트 포함 |
| 보안 | 키·토큰·DB 비밀번호·접속 주소 검사 파일 3,410개·DB 컬럼 243개 0건 |

재시험에서 실제로 다르게 한 것: ① 워커는 `JEV_PROXY_OUT` 으로 실행마다 프록시 기록 파일을 나눴다(1회차·2a·2b 별도 — 1회차도 대조). ② r4 env 의
`DATABASE_URL` 은 루트 `.env` 의 `R4_DATABASE_URL`, 도우미 스크립트용 psycopg 주소 파일도 끝나고 지웠다. ③ Git Bash 에서 API 경로는 앞 `/` 없이 넘겼다(10-6 ⑥).
④ 집계 SQL 은 10-7 ④ 그대로 + `SELECT provider, model, tool, COUNT(*) FROM judgment_log GROUP BY 1,2,3`.

### 10-9 R4 재시험 3차 절차 — R4-CORE8(D21, 계약 .16) 뒤 바뀐 것 (`docs/design/wp/R4_CORE8_TESTS.md`)

10-7 은 그대로 따른다. 3차 재시험은 **새 DB**(비운 `subscription_analyzer_r4` 또는 새 DB)로 한다 — 2차 DB 에 이미 생긴 잔여 공고 번호
행(74·75 등)은 병합하지 않는다(D20-3 과 같은 이유).

1. **판정기 자격 증명**(D21-8·D19-3): 판정기 키는 r4 env(`ENV_FILE`)나 루트 `.env` 의 `TYPESAFE_API_KEY`(또는 `JUDGE_SECRET_ENV_NAMES`
   의 다른 이름)에만 두면 된다 — 사용자 환경변수(`setx`)가 없어도 판정기 자식 프로세스로 넘어간다(프로세스 환경변수가 있으면 그 값이
   이긴다). smoke 로 확인: 키를 사용자 환경변수에서 지운 셸에서 `ENV_FILE=<r4 env> JEV_MCP_CMD=… uv run pytest -m live tests/judge/test_live.py -s`.
2. **공고문 금액 단위**(N1·D21-1): `SELECT ct.complex_id, ct.type_code, ct.max_price_won FROM complex_type ct WHERE ct.max_price_won < 30000000;`
   → 0행이어야 한다(3천만원 미만 가격 없음). 2차의 중흥S-클래스(2025000253) 84A = 617,000,000. 단위 상충 보류(10배 이상):
   `SELECT entity, entity_id, field, value_text, reason FROM field_provenance WHERE reason LIKE '출처 상충%' AND field LIKE '%price_won';`
   와 그 compare 결과(G7 판정 로그 purpose `compare:complex_type:<id>:max_price_won`)를 기록한다. 단위 표기 없는 표:
   `SELECT COUNT(*) FROM field_provenance WHERE reason LIKE '%단위 표기 없음%';`
3. **NUL**(N2·D21-2): bootstrap·daily 잡 stats `store_errors` = [] (2차 rd613·rd616 `DataError` 없음). 원문 파일(.txt)은 그대로다.
4. **잔여 공고**(N3·N4·D21-3): `SELECT applyhome_id, name FROM complex WHERE applyhome_id ~ '^20[0-9]{2}9[0-9]{5}$';` → 공고문이 원 번호를
   인용하지 않은 것만(2차의 74·75·64~66·71·62·63 은 없어야 한다). 같은 날 `collect.daily`(10-7 ⑨) change_event 0 · `tools_calls` 0.
5. **실거래 출처**(N5·D21-4): `GET /snapshots/<id>/market` 의 `living_area_prices` 가 생활권마다 있고 `prov` 가 `rd_<id>`. 발행 stats
   `missing_provenance` 가 2차(5,938~5,973)보다 크게 준다(실거래 거래가 빠진다).
6. **공식 홈페이지 동일성**(N6·D21-5): 판정 로그 purpose `classify:site_identity:batch<n>` 호출 수·결과, 접수 행 사유
   `SELECT complex_id, path, reason, note FROM intake_status WHERE reason = '공식 홈페이지가 다른 단지';` — 2차의 예미지 퍼스트포레(55,
   `yemizi-firstforet.com` = 대구 동성로 페이지)가 여기 있고 판정 대상이 아니어야 한다(판정기 응답에 달렸다 — 결과 기록).
7. **동 없는 주소**(N7·D21-6): `SELECT id, name, address, legal_dong_code, inclusion_class FROM complex WHERE address NOT SIMILAR TO '%(동|읍|면|리)( |$)%';`
   — 2차 46(RC3BL)·47(396-11번지)은 잔여 공고문 공급위치로 법정동(당하동·송도동)이 채워지고 범위 경계가 아니다. 남은 행의 범위 사유
   '범위 경계(주소에 동 없음)'.
8. **첫 적재 요약**(m-b): bootstrap 의 `change_event` 중 단지·타입·납부 조건 이벤트 0(값 → 다른 값도 `first_load` 한 줄로).
9. **포함 classify**(m-c): 같은 날 daily(변화 있을 때)·rejudge 의 `classify:inclusion:*` 항목 수 = 입력이 바뀐 단지 수.
10. **보고서 §1-1**(m-d): 생활권 세대수 4칸에 값(라벨 추정, 출처 rd_) — '확인 불가(출처 누락)' 없음.
11. **공고 예정 후보**(D21-8, 계약 .16): 트랙 A 행의 공고일·가격 '확인 불가(공고 전)', 목록·상세의 `name_prov`·`name_label`('비공식').

### 10-10 R4 3차 재시험 결과 (2026-10-12, main `cfbd483`, 계약 `.16`) — 상세 `docs/design/wp/R4_RESULT3.md`

**결과: 게이트 미통과 · 운영 승인 비권고.** 2차 critical N1·major N2~N6 은 실데이터에서 해결. 그러나 2회차 (a) 같은 스냅샷 재판정 `tools/call` **1**
(N8 — 미분류(review) 단지만 새 포함 배치로 다시 보냄, D18-5 엄격 위반), 같은 날 daily 가 판정기 추출 값 6건을 '확인 불가(출처 누락)'로 조용히 바꿈
(**critical N9**), N7 은 두 번째 수집에서야 조용히 채워짐(N10).

| 항목 | 값 |
| --- | --- |
| 환경 | Windows 11, Docker 없음, D19 로컬 PostgreSQL 17.9(5434) DB `subscription_analyzer_r4`(public 테이블만 지우고 새로 시작), `ENV=prod`, API 127.0.0.1:18633 |
| 마이그레이션 | `ENV_FILE=… uv run alembic upgrade head` → `PostgresqlImpl`, `0015 (head)`, `dev.db` 없음 |
| JEV | 실행 직전 최신 `0.14.1` 확인 → `npx -y @jkudish/jev-mcp@0.14.1` 고정, smoke 출력 `"cmd"` 고정 버전. 워커·API 는 같은 버전 계수 프록시 경유 |
| 판정기 자격 증명(확인 항목 1) | **충족** — API·워커·alembic·보고서는 `TYPESAFE_API_KEY`·`OPENROUTER_API_KEY`·`JEV_*`·`CLOUDFLARE_*`·`AI_GATEWAY_API_KEY` 를 지운 환경 + `ENV_FILE` 만으로 실행, 프록시가 본 자식 env 에 키 존재(길이만 기록)·`DATA_GO_KR_KEY` 없음. 키 줄을 뺀 env 로는 smoke 실패(대조) |
| adapter_version | `0.2.0+jev-mcp@0.14.1+jev-1.13.0` **1개**(571행; provider none 136행 포함) |
| 1회차 시간 | bootstrap **53분 16.5초**(일일 단계 약 43분 · 주간 단계 약 6분 40초 · 판정 3분 22초 · 발행 10초), reference.refresh 12초 |
| 1회차 실제 호출 | **571** = 잡 `tools_calls` = 프록시 `tools/call` = `judgment_log` 행(screen 193 · extract 178 · compare 130 · classify 41 · audit 11 · noul 9 · decide 5 · verify 3 · rerank 1), 모델 호출 435 · 로컬 단락 136, 수집 단계 판정 65 포함, blocked·error 0 |
| 132 / 2차 대비 | +439 / −11(compare −9 잔여 공고 자기 행 소멸, noul −3·verify −1 판정 대상 4 → 3, classify +1 동일성 배치, audit +1) |
| 단지·범위 | 단지 행 72(잔여 공고 번호 행 5), 판정 대상 3, **TOP 5 = 사우역 지엔하임 4.76 · 엘리프 검단 포레듀 3.46**(스냅샷 4~ 3.42 — N10), 풍무역 푸르지오 더 마크는 계약금% 없음(m-a) |
| N1 금액 단위 | `max_price_won < 3천만원` 0행, 중흥S-클래스 84A 617,000,000, 단위 근거 발췌 16행, 10배 단위 상충 0, '단위 표기 없음' 13행 |
| 수집 | 실거래 52,163건 법정동 100%, 분양권 4,109건, `store_errors` [](NUL 해결), official_site 404 1·connect 7·TLS 3, 타임아웃·파싱 실패 0 |
| 출처 | 시장 생활권 시세 4블록(prov `rd_`), 발행 `missing_provenance` 스냅샷 1·2·4·5·6 **0**, 스냅샷 3 **40**(N9). Fact 빈 라벨 0 · 값 있는데 출처 없음 0(대시보드·목록·상세·시장, 스냅샷 1~4·6) |
| 2회차 (a) 같은 스냅샷 rejudge | **프록시 `tools/call` 1 · `tools_calls` 1 · `judgment_log` 571 → 572**(classify 포함 배치 [52, 64]), cached 462, 106초 → **실패**. 추가 재판정: (a2) 2 · (a3) 1 · (a4) 0 |
| 2회차 (b) 같은 날 collect.daily | 986초, change_event **0** · 판정 0(판정기 미기동) · 잔여 공고 재귀속 0 — 단 발행 스냅샷 3 에 조용한 변경(N9 · N10) |
| 보고서 | `--snapshot 6 --format pdf` 154쪽, 차트 포함, §1-1 세대수 4칸 값(m-d 해결) |
| 보안 | 키·토큰·DB 비밀번호·접속 주소 검사 파일 3,717개·DB 컬럼 243개 0건, `serviceKey=` 0, guard 차단 0 |

3차에서 실제로 다르게 한 것: ① 프로세스마다 판정기 자격 증명·`JEV_*`·`DATABASE_URL` 을 지운 환경을 만들고(남은 이름이 있으면 실패하는 단언)
`ENV_FILE` 만 줬다. ② 워커·API 는 r4 env 의 **사본**(`JEV_MCP_CMD` 만 `"<python> jev_count_proxy.py <기록 파일> <버전>"` 으로 바꿈 — 프록시 기록 경로를
환경변수가 아니라 인자로 넘겨 `JEV_*` 를 프로세스에 두지 않음)을 `ENV_FILE` 로 받고 실행 뒤 사본을 지웠다. 프록시는 자식 기동 때 자격 증명 이름의 길이만
기록했다. ③ smoke 는 `JEV_MCP_CMD` 를 프로세스 환경에서만 읽으므로(`test_live.py`) smoke 에만 고정 cmd 를 남겼다. ④ 2회차 (a) 가 0 이 아니어서
메커니즘 확인용 재판정 (a2)~(a4) 를 더 돌렸다(스냅샷 4·5·6).

### 10-11 R4 재시험 4차 절차 — R4-CORE9(D22, 계약 .17) 뒤 바뀐 것 (`docs/design/wp/R4_CORE9_TESTS.md`)

10-7·10-9 는 그대로 따른다. 4차 재시험도 **새 DB**(비운 `subscription_analyzer_r4`)로 한다. 2회차는 3차와 같은 순서로 돌린다 — (a) 같은 스냅샷
재판정 → (b) 같은 날 `collect.daily` → (a2) 재판정(3차의 (a2)~(a4) 와 같은 메커니즘 확인 재판정을 1회 이상 더). 확인 항목:

1. **2회차 `tools/call` 0**(N8·D22-2, 게이트): (a)·(a2)·(a3) 모두 프록시 `tools/call` = 잡 `tools_calls` = `judgment_log` 새 행 = **0**. 1회차에 포함/제외
   classify 가 review 로 남긴 단지(`SELECT id, name FROM complex WHERE inclusion_class = '미분류' AND inclusion_decision IN ('review','manual_review');`)
   가 있어도 다시 보내지 않는다. 새 `classify:inclusion:*` 행이 생겼으면 그 항목(input_json items)의 단지 입력이 실제로 바뀌었는지 기록.
2. **같은 날 daily 뒤 판정기 추출 값 유지**(N9·D22-1, critical): (b) 발행 리비전의 `missing_provenance` = (a) 리비전과 같다(3차 0 → 40 이 없어야 한다).
   `SELECT fp.entity_id, fp.field, fp.label, fp.chosen, left(fp.reason, 40) FROM field_provenance fp WHERE fp.entity = 'payment_terms' AND fp.reason LIKE '판정기 추출%';`
   → (b) 전후 모두 chosen = true. `GET /complexes/<id>?snapshot=<(b) 리비전>` 의 `down_payment_pct`·`balance_pct` 가 '확인됨'(3차 단지 12·18·25·27·34·38).
3. **법정동 보정이 1회차 안에서**(N10·N7·D22-3): bootstrap 직후 3차 46·47(2021000189 'RC3BL' · 2021000830 '396-11번지')의 `legal_dong_code` =
   당하동(2829010400)·송도동(2818510600), 범위 경계 아님. (b) 뒤 `legal_dong_code` 변경 이벤트 0(이미 정해짐). 운영 중 수집에서 보정되면
   `SELECT * FROM change_event WHERE entity = 'complex' AND field = 'legal_dong_code';` 행이 있다(critical — 그 단지 재판정).
4. **첫 적재 요약**(m-b·D22-4): bootstrap 의 `change_event` 중 단지·타입·납부 조건 이벤트 **0**(판정 단계 추출 적용·compare 채택 포함 — 3차 13건),
   `first_load` 는 **한 줄**, 잡 stats `pipeline.first_load_folded` > 0.
5. **동일성 사유**(N11·D22-4): `SELECT reason, count(*) FROM intake_status GROUP BY reason;` — '공식 홈페이지가 다른 단지'는 노트가 `other_complex·auto`
   인 행만, review·unclear 는 '공식 홈페이지 동일성 미확인'.
6. **원 공고 인용 변형**(N12·D22-4): 월드메르디앙 송도(3차) 임의공급 2024940118 은 단지 행이 아니라 원 2023000463 단지의 잔여 공고 이력이고, 원 공고를
   다시 받는다(`loaded.originals` wanted 에 2023000463).
7. **FE10 보고**(D22-5, 계약 .17): `GET /snapshots/<id>/complexes` 행·`GET /complexes/<id>` 머리의 `judge_scope_reason`(예 '범위 경계(주소에 동 없음)'),
   공고 예정 후보 이름 출처 서랍 `GET /provenance/<name_prov>?snapshot_id=<발행 리비전>` **200**, 기준 타입 가격 채택 보류 단지의 현재 구매가 사유
   '출처 상충 — compare 대기'(`SELECT … FROM field_provenance WHERE reason LIKE '출처 상충%' AND field LIKE '%max_price_won';` 의 단지).
8. **1회차 호출 수**: 3차(571) 대비 차이를 도구별로 기록 — 포함 classify 는 첫 실행이라 전체 배치(변화 없음 예상), 법정동이 1회차에 정해져 3차
   (a2) 의 classify 1 · rerank 1 이 1회차로 옮겨 온다(46·47 포함 배치·rerank 후보).

### 10-12 R4 4차 재시험 결과 (2026-10-13 KST, main `903abf0`, 계약 `.17`) — 상세 `docs/design/wp/R4_RESULT4.md`

**결과: 게이트 미통과 · 운영 승인 비권고(critical 1).** 3차 N8·N9·N10·N11·N12·m-b·D22-5 는 실데이터에서 해결 — (a)·(a2)·(a3) `tools/call` 0·0·0, 같은 날
daily 뒤 판정기 추출 납부 조건 '확인됨' 유지. 그러나 같은 날 daily 가 같은 경쟁률 원문을 다시 정규화하며 **중복 경쟁률 행 70개**를 '확인됨'으로 조용히 발행했고
(**critical N13**), compare 채택 표식 47 필드를 지워 (b) 뒤 재판정이 compare 4회를 불렀다(N14). 00:01 첫 시도는 청약홈 API 데이터셋이 비어(`totalCount 0`)
단지 24개 스냅샷이 경고 없이 발행돼(N15) 무효로 하고 DB 를 비워 01:01 에 다시 시작했다.

| 항목 | 값 |
| --- | --- |
| 환경 | Windows 11, Docker 없음, D19 로컬 PostgreSQL 17.9(5434) DB `subscription_analyzer_r4`(public 테이블만 지우고 새로 시작 — 무효 첫 시도 뒤 한 번 더), `ENV=prod`, API 127.0.0.1:18733 |
| 마이그레이션 | `ENV_FILE=… uv run alembic upgrade head` → `PostgresqlImpl`, `0015 (head)`, `dev.db` 없음 |
| JEV | 실행 직전 최신 `0.14.1` 확인 → `npx -y @jkudish/jev-mcp@0.14.1` 고정, smoke 출력 `"cmd"` 고정 버전, 키 줄 뺀 env 대조 smoke 실패. 워커·API 는 같은 버전 계수 프록시 경유(자식 env 에 `TYPESAFE_API_KEY` 108자, `DATA_GO_KR_KEY`·`DATABASE_URL` 없음) |
| adapter_version | `0.2.0+jev-mcp@0.14.1+jev-1.13.0` **1개**(564행; provider none 136행 포함) |
| 1회차 시간 | bootstrap **40분 16초**(일일 단계 31분 18초 · 주간 단계 6분 29초 · 판정 2분 22초 · 발행 7초), reference.refresh 12초 |
| 1회차 실제 호출 | **564** = 잡 `tools_calls` = 프록시 `tools/call` = `judgment_log` 행(screen 193 · extract 178 · compare 129 · classify 41 · audit 10 · noul 6 · decide 4 · verify 2 · rerank 1), 모델 호출 428 · 로컬 단락 136, 수집 단계 판정 65 포함, blocked·error 0 |
| 132 / 3차 대비 | +432 / −7(noul −3·verify −1·decide −1 판정 대상 3 → 2 — 엘리프 접수 classify review, compare −1, audit −1). 46·47 이 1회차 포함 배치·rerank 에 들어가 3차 (a2) 형 추가 호출 없음 |
| 단지·범위 | 단지 행 72(잔여 공고 번호 행 4 — 2024940118 자기 행 없음), 판정 대상 2(사우역 지엔하임 가능 · 풍무역 푸르지오 더 마크 미정), **TOP 5 = 사우역 지엔하임 4.72**(1개 — 풍무역 푸르지오 더 마크 계약금% 없음 m-a) |
| 수집 | 실거래 52,163건 법정동 100%, 분양권 4,109건, `store_errors` [], official_site 404 1·connect 7·TLS 3, 타임아웃·파싱 실패 0 |
| 출처 | 발행 `missing_provenance` 리비전 1~6 모두 **0**, Fact 빈 라벨 0 · 값 있는데 출처 없음 0(대시보드·목록·상세 72·시장, 리비전 1~6), 시장 생활권 4블록(prov `rd_`) |
| 2회차 (a)·(a2)·(a3) | **프록시 `tools/call` 0 · `tools_calls` 0 · `judgment_log` 564 → 564**(세 번 모두), cached 456, 약 60초씩 → 통과. 미분류 review 4단지 재전송 없음 |
| 2회차 (b) 같은 날 collect.daily | 984초, 실제 새 임의공급 공고 1건(2026940221, 데이터셋 674 → 676) → change_event 5(그 단지만)·재판정 `tools/call` 0. 판정기 추출 '확인됨' 유지·`missing_provenance` 0. **그러나 바뀐 원문 없는 단지 10곳에 중복 경쟁률 Fact 124 생김(N13) · compare 채택 근거 47 필드 소실(N14)** |
| (b) 뒤 재판정 | `tools/call` **4**(compare 입주 예정월 13·51·60·66 — N14) → 실패 |
| 보고서 | `--snapshot 6 --format pdf` 152쪽, 차트 포함, §1-1 세대수 4칸, 중복 경쟁률이 보고서에도 보임 |
| 보안 | 키·토큰·DB 비밀번호·접속 주소 검사 파일 4,684개·DB 컬럼 243개 0건, `serviceKey=` 0, guard 차단 0 |

4차에서 실제로 다르게 한 것: ① bootstrap 이 자정을 넘지 않게(기준일 하나) 00:00 뒤에 시작했는데, **청약홈 API 데이터셋이 자정 직후 다시 적재되는 동안
`totalCount 0` 을 낸다**(관측: APT 00:01~00:29, 잔여 ~00:59 KST). 다음 재시험은 이 시간대를 피하고, 시작 전 `getAPTLttotPblancDetail`·
`getRemndrLttotPblancDetail`·`getOPTLttotPblancDetail` 을 `perPage=1` 로 한 번씩 불러 `totalCount` > 0 을 확인한다(키는 출력하지 않는다). ② 발행 불변
확인은 `missing_provenance` 만이 아니라 리비전 간 단지 목록·상세 72개·대시보드·시장의 모든 Fact(`v`·`label`·`reason`)를 경로별로 비교했다 — 기준선은
수집 없는 연속 재판정 리비전 쌍(Fact 차이 0, 파생 행 id 만 다름).

### 10-13 R4 재시험 5차 절차 — R4-CORE10(D23, 계약 .18) 뒤 바뀐 것 (`docs/design/wp/R4_CORE10_TESTS.md`)

10-7·10-9·10-11 은 그대로 따른다. 5차도 **새 DB**(비운 `subscription_analyzer_r4`)로 하고 `alembic upgrade head` = **`0016 (head)`** 를 확인한다.
**00:00~01:00 KST 를 피해 시작**하고, 시작 전 청약홈 API 3종(`getAPTLttotPblancDetail`·`getRemndrLttotPblancDetail`·`getOPTLttotPblancDetail`)을
`perPage=1` 로 한 번씩 불러 `totalCount` > 0 을 확인한다(키 출력 금지). 2회차는 4차와 같은 순서 — (a)(a2)(a3) 같은 스냅샷 재판정 → (b) 같은 날
`collect.daily` → (b) 뒤 재판정 1회 이상. 확인 항목:

1. **중복 경쟁률 0**(N13·D23-2, critical): (b) 뒤 아래 SQL → **0행**(4차 70). 같은 경쟁률(단지·구분·회차·공급·접수·경쟁률 문구)이 **원 면적 코드**
   ('84.9939')와 **그 정수부 표시 코드**('84'·'84A') 또는 '확인 불가(타입 모호)'로 두 번 저장된 짝만 센다(R4-CORE11 정정 — m-e, 아래 5차 주).

   ```sql
   SELECT n.id, n.complex_id, n.kind, n.round, o.type_code AS raw_code, n.type_code AS dup_code, n.supply, n.applied
   FROM competition n JOIN competition o
     ON o.complex_id = n.complex_id AND o.kind = n.kind AND o.round = n.round AND o.id <> n.id
    AND o.supply IS NOT DISTINCT FROM n.supply AND o.applied IS NOT DISTINCT FROM n.applied
    AND o.ratio_or_shortfall_text IS NOT DISTINCT FROM n.ratio_or_shortfall_text
   WHERE o.type_code ~ '^[0-9]+\.[0-9]+$'
     AND (n.type_code = '확인 불가(타입 모호)'
          OR n.type_code ~ ('^0*' || ltrim(split_part(o.type_code, '.', 1), '0') || '[A-Za-z]*$'));
   ```

   `competition.type_code` 는 원문 코드(API 원 면적 코드 '84.9939' 등 · API·웹이 주는 '84A' 같은 주택형 코드)이고 단지 상세 `competition[].type_code` 는
   표시 주택형('84' · '확인 불가(타입 모호)')이다 — 저장 행에 표시 코드가 원 면적 코드와 같은 숫자로 함께 있으면 N13 중복이다(웹 폴백 경쟁률 '84A' 행과 API
   '84.9582' 행이 같은 회차에 함께 있으면 이 SQL 에 걸린다 — 그 행의 `raw_document_id` 원문이 웹이면 N13 이 아니라 R4_CORE10_TESTS §5 의 표시 겹침이다).
   (b) 전후 `SELECT count(*) FROM competition;` 이 바뀐 공고의 새 행만큼만 는다(바뀐 원문 없는 단지는 0) — 판정에는 (b) 전후 `competition` 행 diff
   (새 행·바뀐 칸)를 함께 본다.
2. **발행 결과 불변**(D22-1·D11-1·D23-1): 4차 §6-3 과 같이 리비전 (a3) ↔ (b) ↔ (b) 뒤 재판정의 모든 Fact(`v`·`label`·`reason`) 비교 — 차이는 실제로 바뀐
   공고의 단지와 신선도 KPI 뿐, '경쟁률 Fact 생김'·'사유만 바뀜(compare 채택 근거 소실)' **0**.
3. **compare 표식 보존·(b) 뒤 재판정 `tools/call` 0**(N14·D23-3, 게이트): `SELECT count(*) FROM field_provenance WHERE reason LIKE '판정기 compare 채택%';`
   가 (b) 전후 같다(4차 (b) 뒤 7). (b) 뒤 재판정 프록시 `tools/call` = 잡 `tools_calls` = `judgment_log` 새 행 = **0**(4차 4).
4. **빈 데이터셋**(N15·D23-4): 정상 시간대면 `SELECT count(*) FROM raw_document WHERE error_text LIKE 'empty_dataset%';` = 0 이고 잡 stats 에
   `degraded_sources` 가 없다. (선택) 적재 시간대를 일부러 맞췄다면 bootstrap 잡이 `queued`(`requeue_reason` 'degraded_source …')·지역 `bootstrapping`·
   발행 리비전 0·판정기 `tools/call` 0 인지, 01:00 뒤 재시도가 처음부터 다시 수집해 발행하는지 기록(기본 절차는 이 시간대를 피한다).
5. **재정규화 멱등성(로컬, 선택)**: 5차 원문 전부로 재생 — `REPLAY_DATABASE_URL=<R4 DB — 스크립트로 .env 에서 읽고 출력 금지> uv run python
   scripts/replay_manifest.py --raw-root <r4 RAW_DIR> --out <폴더>`(읽기 전용) → `R4_REPLAY_MANIFEST=<폴더>/docs.json uv run pytest -p no:randomly
   "tests/scheduler/test_core10_idempotency.py::test_renormalize_is_idempotent[r4d-full]"` → 통과(DB 스냅샷 동일·사실 이벤트 0·`tools/call` 0, 약 3분).
6. 4차 확인 항목 1~8(§10-11)은 그대로 다시 본다(회귀 방지) — 특히 (a)(a2)(a3) `tools/call` 0, 판정기 추출 납부 조건 '확인됨' 유지, 46·47 법정동.

(5차 주: 5차 때 ① 의 SQL 은 `o.type_code <> n.type_code` 만으로 짝을 지어 같은 회차에 공급·접수 수가 우연히 같은 **다른 주택형**(2순위 접수 0 등, 예 '100A'·'124H'
27/0)도 셌다 — 5차의 깨끗한 데이터에서 87행(10-14 m-e). **R4-CORE11 에서 위 SQL 로 정정**했다: 5차 R4 DB(경쟁률 1,906행 — 원 면적 코드 163 · 주택형 코드 1,743)에서
옛 SQL 87행 → 새 SQL **0행**, 4차 중복 모양 합성 행(원 면적 코드 ↔ '84'·'122'·'66A'·'확인 불가(타입 모호)' 4쌍 + 다른 주택형 우연 일치 3쌍 + '845' 함정, 읽기 전용
CTE)에서 옛 9 → 새 **4**(중복 4쌍만). `docs/design/wp/R4_CORE11_TESTS.md` §3.)

### 10-14 R4 5차 재시험 결과 (2026-10-13 KST, main `7bb3e15`, 계약 `.18`) — 상세 `docs/design/wp/R4_RESULT5.md`

**결과: R4 게이트 통과(critical 0) · 운영 승인 권고(단서: 새 major N16).** 4차 critical N13·게이트 위반 N14 는 실데이터에서 해결 — 같은 날 daily 가 경쟁률 행을
새로 만들지 않았고(1,906 → 1,906) compare 채택 표식이 그대로였으며(59 → 59), 정규화 테이블이 (a3) → (b) → (b) 뒤 재판정 동안 바뀐 칸 0. (a)(a2)(a3)·(b) 뒤 재판정
`tools/call` 모두 0. 남은 것: **N16**(major) — bootstrap 의 체크리스트 동기화가 일일 단계에서만 돌아 주간 단계(트랙 A 후보)·판정(포함 classify) 결과를 반영하지 않고,
첫 같은 날 daily 가 체크리스트 8행을 이벤트 없이 바꿔 발행 리비전 5 보고서 체크리스트가 달라짐(Fact·수치·판정은 그대로). CEO 가 이를 critical('발행 결과가 조용히
바뀜')로 보면 미통과.

| 항목 | 값 |
| --- | --- |
| 환경 | Windows 11, Docker 없음, D19 로컬 PostgreSQL 17.9(5434) DB `subscription_analyzer_r4`(public 테이블 38개만 지우고 새로 시작), `ENV=prod`, API 127.0.0.1:18833, 실행 05:18~06:33 KST(적재 시간대 회피) |
| 시작 전 데이터셋 | 청약홈 API 3종 `perPage=1` `totalCount` 2,900 · 1,714 · 676(> 0) |
| 마이그레이션 | `ENV_FILE=… uv run alembic upgrade head` → `PostgresqlImpl`, **`0016 (head)`**, `dev.db` 없음 |
| JEV | 실행 직전 최신 `0.14.1` 확인 → `npx -y @jkudish/jev-mcp@0.14.1` 고정, smoke 출력 `"cmd"` 고정 버전, 키 줄 뺀 env 대조 smoke 실패. 워커는 같은 버전 계수 프록시 경유(자식 env 에 `TYPESAFE_API_KEY` 108자, `DATA_GO_KR_KEY`·`DATABASE_URL` 없음) |
| adapter_version | `0.2.0+jev-mcp@0.14.1+jev-1.13.0` **1개**(565행; provider none 136행 포함) |
| 1회차 시간 | bootstrap **45분 44초**(일일 단계 35분 52초 · 주간 단계 7분 11초 · 판정 2분 32초 · 발행 9초), reference.refresh 15초 |
| 1회차 실제 호출 | **565** = 잡 `tools_calls` = 프록시 `tools/call` = `judgment_log` 행(screen 193 · extract 178 · compare 129 · classify 41 · audit 11 · noul 6 · decide 4 · verify 2 · rerank 1), 모델 호출 429 · 로컬 단락 136, 수집 단계 판정 65 포함, blocked·error 0 |
| 132 / 4차 대비 | +433 / +1(audit — 4차 (b) 에서야 나타난 임의공급 공고문 2026940221 이 이번엔 1회차에 있음, 추정) |
| 단지·범위 | 단지 행 72(잔여 공고 번호 행 4 · 트랙 A 2), 판정 대상 2(사우역 지엔하임 가능 · 풍무역 푸르지오 더 마크 미정), **TOP 5 = 사우역 지엔하임 4.80**(1개 — m-a) |
| 수집 | 실거래 52,274건 법정동 100%, 분양권 4,118건, `store_errors` [], official_site 404 1·connect 7·TLS 3, **`empty_dataset` 0 · `degraded_sources` 없음**, 타임아웃·파싱 실패 0 |
| 출처 | 발행 `missing_provenance` 리비전 1~6 모두 **0**, Fact 빈 라벨 0 · 값 있는데 출처 없음 0(대시보드·목록·상세 72·시장, 리비전 1~6), 시장 생활권 4블록(prov `rd_`) |
| 2회차 (a)·(a2)·(a3) | **프록시 `tools/call` 0 · `tools_calls` 0 · `judgment_log` 565 → 565**(세 번 모두), cached 457, 약 60초씩 → 통과 |
| 2회차 (b) 같은 날 collect.daily | 956초, 실제 바뀐 공고 없음 → change_event 0 · 판정기 미기동. 경쟁률 1,906 → 1,906(중복 0), compare 채택 59 → 59, 정규화 테이블 바뀐 칸 0, Fact 차이는 신선도 KPI 뿐. **체크리스트 6행 생김 · 2행 na(N16)** |
| (b) 뒤 재판정 | `tools/call` **0** → 통과 |
| 재생(선택) | 5차 원문 매니페스트(청약홈 563 · 원 공고 77 · 공고문 138 · 공식 홈페이지 90) → `test_renormalize_is_idempotent[r4d-full]` **통과**(144.6초) |
| 보고서 | `--snapshot 6 --format pdf` 149쪽, 차트 포함, 중복 경쟁률 0('타입 모호' 39 = 상세 39행) |
| 보안 | 키·토큰·DB 비밀번호·접속 주소 검사 파일 3,930개·DB 컬럼 243개 0건, `serviceKey=` 0, guard 차단 0, 로그 `judge.payload` 는 hash·길이만 |

5차에서 실제로 다르게 한 것: ① 05:18 에 시작(적재 시간대 밖)하고 (b) 직전에 데이터셋 건수를 한 번 더 확인했다(같음 → (b) 는 "변화 없는 같은 날 재수집"). ② 발행 불변을
API Fact 비교에 더해 **정규화 테이블 전체 행 비교**(`complex`·`complex_type`·`payment_terms`·`competition`·`remaining_event`·`field_provenance`·`checklist_item`·`catalyst`·
`fact_demotion`, SELECT 만)와 **report 저장본 최상위 키 비교**(압축 본문을 풀어서)로 했다 — N16 은 이 비교로만 보인다(Fact 아님). ③ 중복 경쟁률은 ① 의 SQL 대신 (b) 전후 행
diff + '원 면적 코드 ↔ 정수부 표시 코드' 짝으로 셌다(위 5차 주).

### 10-15 R4-CORE11(D24-1) 뒤 바뀐 것 — 운영 전 정리 (`docs/design/wp/R4_CORE11_TESTS.md`)

- **N16 수정**: 판정 파이프라인(`run_pipeline`)이 판정 뒤·`ready` 전에 지역 체크리스트를 다시 맞춘다(`normalize.checklist.sync_checklist`, 스냅샷 기준일). bootstrap
  (일일 단계 → 주간 단계 → 판정 → 발행)의 발행 보고서 체크리스트에 주간 단계가 만든 트랙 A 후보의 '모집공고 예정'·법적 확인 항목이 있고, 판정이 제외한 단지의 자동
  항목은 na(auto)다 — 같은 날 첫 `collect.daily` 가 체크리스트를 바꾸지 않는다(잡 stats `assembled.checklist` 의 inserted·updated·closed·reopened 0). 같은
  규칙이 주간 수집·daily 뒤 재판정·지역 확장에도 적용된다(판정 결과 stats `pipeline.checklist`). 그 지역에 더 새 기준일 스냅샷이 있는 옛 기준일 재판정은 체크리스트를
  건드리지 않는다(`pipeline.checklist` = null).
- 다음 R4 재시험·운영 첫 지역에서 확인: bootstrap 잡 stats `pipeline.checklist`(트랙 A 후보·제외 단지가 있으면 inserted·closed > 0) → 같은 날 `collect.daily` 잡 stats
  `assembled.checklist` 의 inserted·updated·closed·reopened **0**, 두 발행 리비전 report 저장본 `checklist` 같음.
- 재생 속성 테스트(로컬, 선택): `scripts/replay_manifest.py` 가 주간 단계 뉴스 원문(`docs.news`)도 담는다. `R4_REPLAY_MANIFEST=<폴더>/docs.json uv run pytest -p no:randomly
  "tests/scheduler/test_core11_bootstrap_idempotency.py::test_full_bootstrap_then_same_day_daily_is_idempotent[r4d-full]"`.
- 운영 문서 단서(10-14 '고치기 전에는 지역을 만든 날의 보고서 체크리스트가 불완전')는 이 수정으로 없어졌다. 이미 발행된 리비전(R4 5차 리비전 1~4)의 저장본은 그대로다(D11-1).

### 10-16 R5-PIPE(D25) 배포 뒤 1회 — P6·P7·P8 전체 재판정 (`docs/design/wp/R5_TESTS_PIPE.md`)

- R5-PIPE 로 P6 사다리(noul) 입력에 지역 벤치마크·제도 컨텍스트·가격 갭이 들어가고, 증거 카드의 벤치마크·공급·호재·비고(제도) 줄이
  채워졌다(meta §2-1 P6). 카드는 rerank·decide 에도 들어가므로 **noul·rerank·decide 의 input_hash 가 전부 바뀐다**. 판정기 버전 변경(§4)이
  아니므로 `change_event(judge·version)` 는 생기지 않고, 그냥 캐시 미스다.
- 그래서 운영 DB(`subscription_analyzer`, D19)에서는 배포 뒤 **처음 도는 재판정 1회**에서 그 세 도구가 전부 다시 판정된다: noul =
  판정 대상 단지 × 사다리 시점(최대 3), rerank 1, decide = 시나리오 수(내장 5 + 사용자 정의), 그리고 지역 벤치마크 P1 screen 1(skip 이면
  재screen 1 더). P1~P5(screen·extract·audit·classify·compare)·P9 verify 는 입력이 그대로라 캐시다. 같은 스냅샷을 한 번 더 재판정하면
  `tools/call` 0(§10-4 (a))으로 돌아온다.
- 사실 변경이 없는 날의 `collect.daily` 는 이월(carry_forward — 이전 판정 복사)이라 이 재판정을 일으키지 않는다. 새 맥락으로 판정된 점수가
  필요하면 배포 직후 지역마다 전체 재판정을 한 번 등록한다(§10-4 (a) 의 `rejudge` 잡, 사유 예 `"R5-PIPE P6 맥락 반영 1회 재판정"`). 이 잡의
  stats `judge_calls`·`by_tool` 이 위 수와 맞는지 기록하고, 이어서 같은 잡을 한 번 더 돌려 `judge_calls` 0 을 확인한다.
- 미리보기(G5 `/scenarios/{id}/preview`)의 `cache_misses` 는 이 재판정 전까지 noul·rerank·decide(+ screen 1)를 미스로 센다 — 정상이다.

### 10-17 R6-DONG 배포 뒤 — 저장된 단지 법정동 다시 맞추기 (`docs/design/wp/R6_TESTS_DONG.md`)

- 운영 첫 실행(인천, 스냅샷 1, 단지 101)에서 18 단지의 `complex.legal_dong_code` 가 틀리거나 비어 생활권 NULL·'범위 경계'였다. 원인: 2026-07 분구·통합 전
  구 이름(중구·동구·서구) + 동 나열, 행정동 이름(간석1동), 여러 시도에 걸친 주소(계양구 … 경기도 부천시 대장동 → 지역 밖 동 선택), 동 없는 주소.
  주소 → 법정동 규칙은 `normalize/dong_match.py` 로 바뀌었다(지명 하드코딩 없이 참조 표의 폐지 행·행정동 매핑으로).
- **적용 경로**: 주소가 그대로면 저장 경로는 다시 배정하지 않으므로, 모든 `collect.daily`·`collect.weekly`(그리고 bootstrap·지역 확장의 수집) 끝에
  `living_area.rederive_region_dongs` 가 지역 단지 전체(주소 있는 것)를 지금 규칙으로 다시 맞춘다. 법정동이 바뀐 단지마다
  `change_event(complex·legal_dong_code, critical)` → 그 단지만 재판정(P4 포함 classify 등). 바뀐 것이 없으면 아무것도 쓰지 않는다(D23-1).
- **운영 DB 에 적용하는 절차**(배포 = main 머지 + worker 재시작 뒤, 00:00~01:00 KST 피함 — D23-4):
  1. (선택, 읽기 전용) 적용 전 상태 기록:
     `SELECT id, name, legal_dong_code, living_area, inclusion_class FROM complex WHERE region_id=<id> AND (legal_dong_code IS NULL OR living_area IS NULL OR inclusion_class='범위 경계') ORDER BY id;`
  2. 다음 정기 `collect.daily`(06:00)를 기다리거나 바로 한 번 등록한다(§10-4 (b) 와 같은 명령):
     `curl -s -X POST localhost:8000/api/jobs -H "$H" -H 'Content-Type: application/json' -d '{"job_name":"collect.daily","payload":{"region_id":<id>}}'` → `uv run python -m app.worker --once`
  3. 확인: `SELECT complex_id, old_text, new_text, severity FROM change_event WHERE entity='complex' AND field='legal_dong_code' ORDER BY id DESC;` —
     R6-DONG 건식 실행(운영 DB 읽기 전용, `R6_TESTS_DONG.md` 표) 기준 **9 단지**(계양 테크노밸리 A17·A6·A9 `4119610600 → 2824511100`, 검암역세권 B-1BL,
     가정2 B2, 간석1동, 영종 A24, 산곡1동, 학익2동)가 바뀌고 9 단지 모두 '범위 경계' → '미분류' → 그 잡의 재판정이 포함 classify 를 한다(판정 호출 > 0 이 정상).
     나머지 92 단지는 (법정동·생활권·분류) 그대로여야 한다.
  4. 같은 날 `collect.daily` 를 한 번 더 돌리면 새 `legal_dong_code` 이벤트 0.
- 그대로 남는 것(추측하지 않음, D2-6·D21-6): 동·구가 복구되지 않는 주소 4건(옛 중구 + 도로명 '자연대로 667' — 옛 중구가 제물포구·영종구로 갈려 구도 못 정함,
  '중구 영종국제도시 A26BL', '인천경제자유구역 영종지구 … A-42BL', '용현ㆍ학익 1블록 …' — 시군구 없음)은 '범위 경계'. 주소가 빈 5 단지(2018·2019 공고, 원 공고
  주소 미수집)는 매칭할 주소가 없어 바뀌지 않는다(분류 '미분류' 유지 — 원 공고 미수집 경로, D18-4).

### 10-18 R6-INTAKE 배포 뒤 1회 — 접수 동일성·접수 classify 다시 판정 (`docs/design/wp/R6_TESTS_INTAKE.md`)

- 동일성 항목에 홈페이지 주소·HTML 제목·설명·시공·시행·청약홈 공급 세대수와 페이지 꼬리말이, 접수 항목에 단지 이름·후보 앞뒤 줄이
  들어가 **`classify:site_identity:*`·`classify:intake:*` 의 input_hash 가 모두 바뀐다**(판정기 버전 변경 아님 — change_event 없음).
- 분류 복사(D10-2)는 직전 분류의 판정 입력(judgment_log.input_json 의 그 행 항목 텍스트)이 지금 조립과 같을 때만 한다. 그래서 배포 뒤 첫
  `collect.daily` 의 새 스냅샷에서 접수 행이 복사되지 않고 판정기로 간다 — 인천 기준 동일성 2배치 + 접수 1배치 ≈ `tools/call` 3. 같은 날
  다시 돌리면 0. 이미 발행된 스냅샷 1 의 행은 그대로(D11-1).
- 확인: `SELECT reason, count(*) FROM intake_status WHERE snapshot_id = <새 스냅샷> GROUP BY reason;` — 재생 예상(R6_TESTS_INTAKE §4):
  동일성 미확인 19 → 약 12, 가능·미정 6 → 약 8. 남는 확인 불가는 §2 표대로 사람 확인.

### 10-19 R7-SITE 배포 뒤 1회 — 팝업 그림 OCR·TLS 브라우저 경로·판정 대상 아님 (`docs/design/wp/R7_TESTS_SITE.md`)

- 선택 의존성 `ocr`(rapidocr·onnxruntime, D5)이 깔려 있어야 팝업 그림을 읽는다(`uv sync --all-extras`). 한국어 인식 모델은 처음 쓸 때
  rapidocr 가 내려받는다(이후 캐시). 없으면 스크린샷 원문 행 meta `status='unavailable'` 사유만 남고 동작은 예전과 같다.
- 첫 `collect.daily`: 렌더한 팝업 그림을 OCR(인천 ≈ 32장, 장당 0.2~2.6초 — 페이지당 예산 30초), TLS 실패 사이트는 브라우저로
  robots.txt·본문(인증서 검증 켬, robots 준수, `core.http` 호스트 간격). 접수 항목이 바뀐 행(DOM 에 접수 문구가 없고 그림 글자가 있음)과
  브라우저로 새로 받은 행만 판정기로 간다 ≈ `tools/call` 2. 같은 날 다시 돌리면 0(같은 그림은 다시 읽지 않는다 — 그림 해시 캐시).
- 포함/제외 classify 가 접수 classify 보다 먼저 돈다 — 범위 경계·민간분양 아닌 단지의 접수 행은 '판정 대상 아님(<구분>)'.
- 확인: `SELECT reason, count(*) FROM intake_status WHERE snapshot_id = <새 스냅샷> GROUP BY reason;` — 재생 예상(R7_TESTS_SITE §4):
  TLS 9 → 1, 문구로 판단 불가 33 → 약 26, 판정 대상 아님 15, 접수 확정(가능·미정·불가, 민간) 7 → 약 11. R6-DONG(§10-17)이
  범위 경계 단지 상당수를 미분류로 되돌리므로 '판정 대상 아님(범위 경계)'는 줄고, 포함/제외 classify 결과에 따라 '(공공분양)' 또는 일반 접수 판정으로 옮겨 간다. 브라우저 경로는
  `SELECT id, url, meta->'fetch' FROM raw_document WHERE source_kind='official_site' AND meta ? 'fetch';`.

### 10-20 R7-FIX 배포 뒤 — 어제 실패 접수 행이 오늘 성공 행을 이기던 결함 (`docs/design/wp/R7_TESTS_FIX.md`)

- 증상(스냅샷 2): 오늘 공식 홈페이지를 받았는데(TLS 브라우저 경로·403 → 성공) 표시 접수 행이 어제 실패('TLS'·'403') — `copy_intake` 가
  경로가 다른 어제 행을 복사하고 표시 규칙(official_popup > headless_shot)이 그것을 골랐다. 이제 오늘 수집 행이 있는 단지는 어제 수집
  실패 행(경로 official_popup·headless_shot, 원문 있음, 응답 200 아님)을 복사하지 않는다(성공 행·사람 확인·비공식 참고·적재 행은 그대로 복사).
- 첫 `collect.daily`: 인천 해당 8단지(7·8·22·37·38·72·75·87)의 표시 행이 오늘 관측으로 — status 는 모두 '확인 불가' 그대로라 change_event·
  판정 범위 변화 없음, 사유만 실제 사유로. 72·75·87 은 근거 주소가 `/s/GI59` → `/s/` 로 바로잡혀 동일성 classify 1배치 ≈ `tools/call` 1.
  같은 날 다시 돌리면 0. 발행된 스냅샷 2 는 그대로(D11-1).
- 확인: `SELECT complex_id, path, reason, raw_document_id FROM intake_status WHERE snapshot_id = <새 스냅샷> AND complex_id IN
  (7,8,22,37,38,72,75,87) ORDER BY 1, 2;` — 오늘 원문 행만, 'TLS'·'403' 없음(오늘도 실패했으면 오늘 실패 행).

### 10-21 R7-FIX2 배포 뒤 — 같은 기준일 리비전의 낡은 실패 행·공동 순위 표시 순서 (`docs/design/wp/R7_TESTS_FIX2.md`)

- 증상(스냅샷 3·4 — 2026-10-14 리비전 2·3, '같은 기준일 재수집'): 리비전 1(스냅샷 2, R7-FIX 전 수집)이 물려받은 어제 실패 행
  ('403' 1221·1234·1257, 'TLS' 1258·1303)이 리비전마다 그대로 복사돼 표시됐다. 같은 기준일 재수집은 `new_revision` 이 앞 리비전 행을
  전부 복사한 뒤 수집하는데, 수집이 (단지, 경로)가 이미 있으면 오늘 행을 만들지 않았다. 이제 오늘 관측이 있는 단지는 리비전 안의 이른
  수집 실패 행(어느 경로든)·같은 경로의 이른 행을 지우고 오늘 행을 쓴다(새 기준일과 같은 결과). 표시 규칙도 수집 실패 행이 그보다 나중의
  수집 성공 행을 경로 우선만으로 이기지 못한다(사람 확인은 늘 먼저).
- 배포 직후(재수집 전): 발행된 스냅샷 4 의 저장본(대시보드·목록·상세·보고서)은 그대로(D11-1). 저장 행을 바로 읽는 G7 사람 확인 대기열
  (`/ops/intake-queue`)은 표시 규칙이 바뀌어 8단지 사유가 '403'·'TLS' → '판정 미해결'·'공식 홈페이지 동일성 미확인'·'문구로 판단 불가'로
  바로 바뀐다(status 는 모두 '확인 불가' 그대로 — 묶음 category 만 collect_failed → identity·unresolved·no_phrase).
- 다음 `collect.daily`(새 기준일이든 같은 기준일 리비전이든): 8단지 행에서 'TLS'·'403' 이 빠진다. status 가 같아 intake change_event·판정 범위
  변화 없음, 분류 복사(D10-2)라 접수 classify 호출 0. 확인: 10-20 의 SQL 을 새 스냅샷으로.
- 공동 순위 표시 순서(CEO 결정): 같은 rank 안은 종합 점수 높은 순 → complex_id 로 대시보드 TOP 5·단지 목록 `sort=rank`·민감도·보고서가
  같다(`analysis._ranking.display_order_key`). 단지 목록은 읽을 때 정렬해 배포 즉시 바뀐다(인천 공동 2위: 41 엘리프 4.6714 → 16 힐스테이트
  4.6404). 대시보드·민감도·보고서는 발행 때 저장본이라 다음 발행부터 같은 순서 — 그 사이 스냅샷 4 대시보드는 16 → 41 그대로다.

### 10-22 R9-PARSE 배포 뒤 1회 — 납부 표·청약 일정·당첨가점·도화 캘린더 중복 (`docs/design/wp/R9_TESTS_PARSE.md`)

- 바뀐 것(저장·파싱만, 판단 규칙 그대로): 공고문 중도금 회차(갈라진 표 머리 '1회 … 6회' + '10% …')·잔금 비율 산술('추정'), 필수 옵션 설명에서
  고지문 제거(null), 청약 일정 `complex.apply_dates` = 순위 × 거주지역마다 `{kind, start, end}`, 웹 경쟁률 팝업의 **당첨가점**
  (`competition.winning_score_*` — 새 열, 마이그레이션 **0017**), 원 공고 인용 변형('최초 입주자모집공고일 주택관리번호 2025-000397' — 조사 없음).
- **운영 DB 에 적용하는 절차**(배포 = main 머지 + worker 재시작 뒤, 00:00~01:00 KST 피함 — D23-4):
  1. (선택, 읽기 전용) 적용 전 기록:
     `SELECT id, complex_id, notice_no, balance_pct, interim_schedule FROM payment_terms WHERE complex_id IN (32,39,99) ORDER BY id;` ·
     `SELECT complex_id, title, due_date, status FROM checklist_item WHERE complex_id IN (39,99) AND kind='중도금' ORDER BY due_date, complex_id;`
  2. 마이그레이션: `ENV_FILE=… uv run alembic upgrade head` → **`0017 (head)`**(열 추가만, 데이터 변경 없음 — 몇 초). R9-API 가 마이그레이션을
     따로 냈으면 CEO 가 정한 순서로(이 마이그레이션은 0016 다음, 스키마 추가만이라 순서를 바꿔도 된다).
  3. `collect.daily` 한 번(정기 06:00 을 기다리거나 §10-17 ② 명령으로 등록 → `uv run python -m app.worker --once`). 이 잡이 받아 둔 원문을 모두
     다시 정규화한다(원문 재다운로드 없음) — 별도 재정규화 명령은 없다. 새로 받는 것은 **APT 공고의 웹 경쟁률 팝업**뿐(지역 APT 단지 수 × 1회,
     인천 ≈ 92 GET, `core.http` 1 req/s ≈ 1.5분, 다음부터는 받아 둔 것을 쓴다).
  4. 확인(읽기 전용):
     - 단지 32: `SELECT notice_no, balance_pct, jsonb_array_length(interim_schedule::jsonb) FROM payment_terms WHERE complex_id=32;` → 두 행 모두
       잔금 35·회차 6. `SELECT label, reason FROM field_provenance WHERE entity='payment_terms' AND field='balance_pct' AND chosen AND entity_id IN
       (SELECT id FROM payment_terms WHERE complex_id=32);` → '추정' · '산술(100-계약금-중도금)'.
     - 필수 옵션: `SELECT count(*) FROM complex_type WHERE options_text LIKE '%선택품목%미포함%';` → 0.
     - 청약 일정: `SELECT apply_dates FROM complex WHERE id=32;` → `[{"kind":"특별공급","start":"2025-12-01","end":"2025-12-01"}, {"kind":"1순위 해당지역",…}, …]`.
     - 당첨가점: `SELECT round, type_code, winning_score_min, winning_score_max, winning_score_avg FROM competition WHERE complex_id=32 AND winning_score_avg IS NOT NULL;`
       → 예 '1순위 해당지역' 59.9801 = 42 / 63 / 48.5.
     - 도화 캘린더: 1 의 두 번째 SQL → 단지 99 의 중도금 항목 status 'na'(closed_by 'auto'), 39 만 'open'. `SELECT notice_no FROM payment_terms
       WHERE complex_id=39;` → 2025000397·2025940268.
  5. 같은 날 `collect.daily` 를 한 번 더 돌리면 위 값 그대로·새 change_event 0·판정 0(D23-1).
- 예상 이벤트·판정(R9_TESTS_PARSE §5): 잔금 비율 NULL → 산술 ≈ 32 공고(critical → 그 단지 재판정 잡, 점수 입력은 계약금%뿐이라 판정기 입력
  그대로 = 캐시 적중 예상), 중도금 회차 4 공고(critical), apply_dates ≈ 96 단지(notice), options_text 276 행(info), 도화 새 공고 1. 당첨가점의
  첫 수집은 이벤트 없음(지난 결과 — `QUIET_FIRST_FIELDS`). 잔금 산술은 판정기 extract 요청을 그대로 남겨(같은 요청 — 캐시) 새 요청은 도화
  임의공급 공고문 1건(단지 키가 원 단지로 바뀜) — 첫 수집 `tools/call`(extract) **≈ 1**, 같은 날 다시 돌리면 0. 판정기가 잔금을 읽어 둔
  단지는 그 '확인됨' 값이 그대로 채택된다. 발행된 리비전 저장본은 그대로(D11-1) — 다음 발행부터.
- 그대로 남는 것: 도화 두 번째 단지 행 99 자체(목록에 같은 이름 두 줄 — D29-2 로 R10 이 병합한다, §10-23), 원 번호 인용이 없는 잔여 공고 행
  (연수 서해그랑블 5단지 1~4차 96~98·100, 9자리 오기 인용 101). '대표 층'은 정의대로 최저 공급금액 행(화면 이름 문제).

### 10-23 R10-FOLLOW 배포 뒤 1회 — 청약 접수·당첨자 발표 일정, 도화 중복 단지 행 병합, 당첨 가점 '-' 사유 (`docs/design/wp/R10_TESTS_FOLLOW.md`)

- 바뀐 것(계약 **.21**, 마이그레이션 **0018**): 체크리스트 kind '청약 접수'·'당첨자 발표'(단지 `apply_dates`·`winner_date` 에서, D29-3),
  같은 사업 중복 단지 행 병합 표식 `complex.merged_into_id`(D29-2), 청약홈 경쟁률 팝업 당첨가점 칸 '-' 를 값 없는 '확인 불가' 출처 행
  (사유 `가점 당첨자 없음(청약홈 '-')`)으로 저장 — 화면은 '가점 당첨자 없음(미달)'·'발표 전'·'가점 미수집'으로 나눈다.
- **운영 DB 에 적용하는 절차**(배포 = main 머지 + worker 재시작 뒤, 00:00~01:00 KST 피함 — D23-4):
  1. (선택, 읽기 전용) 적용 전 기록 — 병합 대상 확인(인천 2026-10-14: 단지 99 = 2025940268, 원 단지 39 = 2025000397)과 그 행에 사람이 넣은
     자료(있으면 병합 뒤 옮기지 않는다 — 원 단지에 다시 입력):
     `SELECT id, applyhome_id, name FROM complex WHERE id IN (39, 99);` ·
     `SELECT 'human_check', count(*) FROM human_check WHERE complex_id = 99 UNION ALL SELECT 'catalyst_link', count(*) FROM catalyst_link WHERE complex_id = 99 UNION ALL SELECT 'checklist_human', count(*) FROM checklist_item WHERE complex_id = 99 AND closed_by = 'human';`
     → 2026-10-14 읽기 전용 확인 0 · 0 · 0.
  2. 마이그레이션: `ENV_FILE=… uv run alembic upgrade head` → **`0018 (head)`**(CHECK 값 추가 + 열 추가, 데이터 변경 없음 — 몇 초).
  3. `collect.daily` 한 번(정기 06:00 을 기다리거나 §10-17 ② 명령 → `uv run python -m app.worker --once`). 받아 둔 원문을 모두 다시 정규화하므로
     **별도 병합 명령은 없다** — 도화 임의공급 공고문(2025940268, '최초 입주자모집공고일 주택관리번호 2025-000397' 인용)을 다시 읽는 순간
     자기 번호 행 99 가 원 단지 39 에 병합된다(change_event `complex`·`merged_into`·critical → 39 재판정 잡). 같은 잡의 체크리스트 동기화가
     새 종류 항목을 만든다.
  4. 확인(읽기 전용):
     - 병합: `SELECT id, merged_into_id FROM complex WHERE id IN (39, 99);` → 99 만 39. `SELECT entity_id, complex_id, new_text, severity FROM change_event WHERE entity='complex' AND field='merged_into';`
       → 1행(99 → 39, critical). 다른 잔여 번호 행(연수 서해그랑블 5단지 96~98·100, 부평 보류지 101)은 `merged_into_id` NULL 그대로(공고문에 원 번호 인용 없음·오기
       — 추측하지 않음, D29-2).
     - 목록: 재판정이 끝나 새 리비전이 발행되면 G2 에 '두산위브 더센트럴 도화' 한 줄(39). 이미 발행된 리비전(스냅샷 1~5)은 저장본 그대로(D11-1 — 그 리비전을 열면
       두 줄이 보이는 것이 정상). `SELECT count(*) FROM score_total st JOIN score_run sr ON sr.id = st.score_run_id WHERE sr.snapshot_id = <새 스냅샷> AND st.complex_id = 99;` → 0.
     - 체크리스트: `SELECT complex_id, kind, title, due_date FROM checklist_item WHERE kind IN ('청약 접수','당첨자 발표') AND status='open' ORDER BY due_date;`
       → 건식 실행(기준일 2026-10-15, 읽기 전용) 기준 단지 1(산곡역자이힐스테이트앤하늘채) 4항목: 특별공급 청약 접수 10-19 · 1순위 청약 접수(해당지역·기타지역) 10-20 ·
       2순위 청약 접수(해당지역·기타지역) 10-21 · 당첨자 발표 10-27. 단지 2·4(공공분양 — 제외 확정)는 없다. 이후 새 공고가 나오면 그 일정이 들어온다.
     - 당첨 가점 '-': `SELECT count(*) FROM field_provenance WHERE entity='competition' AND field='winning_score_min' AND label='확인 불가' AND reason LIKE '가점 당첨자 없음%' AND chosen;`
       → 받아 둔 팝업 58개 기준 '-' 묶음 약 350(읽기 전용 원문 집계 — 미달 행 222 · 미달 아님 128, 같은 행에 묶이는 칸은 1행). 화면 G3 경쟁률 탭 가점 칸이
       '가점 미수집' 대신 '가점 당첨자 없음(미달)' 등으로 보인다(새로 발행하는 리비전부터).
  5. 같은 날 `collect.daily` 를 한 번 더 돌리면 병합·체크리스트·가점 출처 행 그대로·새 change_event 0·판정 0(D23-1·D24-1).
- 예상 이벤트·판정: 병합 change_event 1(critical → 단지 39 재판정 — 후보군에서 99 가 빠져 rerank 1회가 캐시 미스, P8 decide 도 후보가 바뀐 시나리오는 다시 판정 ≈
  시나리오 수). 당첨 가점 '-' 출처 행은 값이 없어 사실 값·이벤트 변화 없음(첫 관측 — D29-1 과 같은 규칙). 체크리스트는 change_event 를 만들지 않는다.
- 되돌리기: `alembic downgrade 0017` 은 새 kind 항목을 지우고 `merged_into_id` 를 뺀다 — 99 가 다시 목록·점수 대상이 된다(0017 동작). 병합 change_event 는 남는다.
- **주의(R10-FIX 전)**: 위 5 는 R10-FIX 배포 전에는 지켜지지 않았다 — 같은 날 다시 돌린 `collect.daily` #20(스냅샷 7)이 `complex.apply_dates`
  change_event 92건(46 단지 × 새 → 옛 → 새)을 냈다. 원인·절차는 §10-24.

### 10-24 R10-FIX 배포 뒤 — 같은 원문의 옛 파싱 출처 행이 다른 원문 정규화에서 되살아나던 결함 (`docs/design/wp/R10_TESTS_FIX.md`)

- 증상(인천, 읽기 전용 2026-10-14): 스냅샷 6(R9-PARSE 뒤 첫 수집) `apply_dates` 62건(옛 → 새, 정상)에 이어 스냅샷 7(같은 날 다시) 92건 = 46 단지 × 2
  (새 `[{kind,start,end}]` → 옛 `[{kind,date}]` → 새). 최종 값은 새 모양이지만 **매 수집마다 반복**(D23-1 위반, G1 변경 피드 홍수).
- 원인: 출처 행 갱신은 값 표기가 바뀌면 새 행을 만들고 옛 행을 지우지 않는다. 청약홈 공식 API 원문과 웹 상세 원문이 둘 다 단지 일정을 쓰는데
  (같은 출처 종류), 원문 A 를 다시 정규화할 때 **원문 B 의 옛 파서 행**이 후보로 되살아나 원문 번호가 큰 쪽(웹 상세)의 옛 값이 이겼다. 쓰는 코드가
  옛 모양을 내는 것이 아니다(두 파서 모두 새 모양 — 운영 원문을 지금 파서로 다시 읽어 확인).
- 고친 것(`normalize.store`): ① 원문을 정규화하면 그 원문이 이번에 다시 만들지 않은 같은 묶음의 파서 행에 reason 머리 '옛 파싱(같은 원문을 지금
  파서로 다시 읽어 대체됨)'·chosen false·conflict_group 없음 — 지우지 않는다(옛 발행 리비전의 출처 근거). ② 다른 원문이 같은 묶음에 파서 행을 둘 이상
  남겼으면 그 원문을 지금 파서로 다시 읽어 지금 파싱 행만 후보로(나머지 같은 표식) — 배포 직후 첫 수집에서도 뒤집히지 않는다. ③ 사람 확인·가격 다시
  보기·판정 결과 반영 경로도 표식 행을 후보로 쓰지 않는다. 계약·마이그레이션·새 라이브러리 없음.
- **운영 DB 절차**: 배포(main 머지 + worker 재시작) 뒤 다음 `collect.daily` 를 그대로 기다린다(별도 명령 없음). 원문 파일은 worker 의 `RAW_DIR`
  (`backend/data/raw`)에서 다시 읽는다.
  1. 건식 확인(읽기 전용, 2026-10-14 — 운영 원문을 지금 파서로 다시 읽음): 표식될 옛 파싱 행 = `apply_dates` 112(옛 모양 112) · `options_text` 276 ·
     `balance_pct` 32 · `interim_schedule` 4 — 원문·묶음마다 정확히 1행, 남는 행 1. 정상 다중 행(같은 원문이 같은 칸을 여러 자리에서 냄 — 경쟁률
     36 · 주택형 12 묶음)은 그대로.
  2. 첫 수집 뒤 확인(읽기 전용):
     `SELECT field, count(*) FROM change_event WHERE snapshot_id = <새 스냅샷> GROUP BY field;` → `apply_dates` 없음(0). ·
     `SELECT count(*) FROM field_provenance WHERE reason LIKE '옛 파싱%';` → 다시 받은 원문 기준 ≈ 424(위 1 의 합 — 그날 수집이 받은 원문만큼). ·
     `SELECT count(*) FROM field_provenance WHERE reason LIKE '옛 파싱%' AND (chosen OR conflict_group IS NOT NULL);` → 0.
  3. 같은 날 한 번 더 → 새 change_event 0 · 판정 0(D23-1).
- 그대로 남는 것: **지난 공고 33 단지(+ 병합된 99)의 `apply_dates` 는 옛 모양**이다(단지 57~94, 2020~2024 공고). 그 원문(과거 공고 상세)은 일일 수집이
  다시 받지 않아 다시 정규화되지 않았다 — 결함이 아니라 재정규화 범위. 화면 일정·체크리스트는 옛 모양도 읽는다(접수가 이미 끝난 단지라 체크리스트 항목은
  없다). 새 모양으로 바꾸려면 그 원문 재정규화가 필요하다(지금은 명령 없음 — 제안).

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
  전용 계산 → 묶음당 ≤0.5MB 짧은 트랜잭션(R3g — 2MB 에서 줄임)으로 나눠 쓰기 → 마지막에 published 전환. 끝날 때까지 이전 발행 리비전이 기본 화면이다. 호재
  PATCH(연결·위치 확인·좌표·예정월 중 하나라도 바뀌면 — D16-4)·생활권 편집·지역 확장은 202 + job_id 를 돌려준다(G7 잡 목록에서
  진행, 호재 PATCH 가 바꾼 것이 없으면 200 + job_id null). 잡 stats 의 `total_s`·`write_max_lock_s`(API 쓰기가
  기다린 최대 시간 상한)·`missing_provenance`(출처 누락 '확인 불가' 건수, D14-8)를 본다. 발행 잡이 실패하면(failed) 리비전은 ready 로
  남고 넣던 저장본 행은 지워진다 — 원인을 고친 뒤 `POST /jobs {"job_name":"snapshot.publish","payload":{"snapshot_id":N}}`.
  daily 이월·주간 마감·지역 확장·bootstrap 의 발행이 예외로 실패하면 재시도 `snapshot.publish` 잡이 자동으로 남는다(stats
  `publish_retry_job_id`, D15-6). **`snapshot.publish` 잡 자신**(이월 carry·후속 포함)이 예외로 끊기면(SQLite 단계 사이 잠금 실패·임대
  잃음·worker 재시작 뒤) 실패가 아니라 **지연 재큐잉 재시도**다(D17-3, 계약 .14): queued + stats `error_retries`(1~5)·`requeue_reason`
  `publish_error: …`. 다시 돌면 이어 채운 이월이 끝났으면 building → ready → 발행까지 간다(멱등 — 마지막 시나리오까지 쓰고 ready 직전에
  죽은 리비전도). 5번 넘으면 failed 이고, 그 리비전으로 미뤄졌던 쓰기(후속 잡 `deferred_to`)는 새 후속 발행 잡으로 다시 등록된다
  (미뤄진 잡 stats `redeferred_job_id`). 체크리스트 상태·메모·기한 PATCH 와 지역 **이름만** 바꾸는 PATCH 도 발행 리비전 보고서 본문에
  들어가므로 202 + job_id(snapshot.publish)다(D17-5). 스냅샷이 없는 지역의 호재 PATCH 는 발행할 것이 없어 200 + job_id null.
- **발행 single-flight**(D15-6·**D16-3**): 리비전마다 발행은 하나만 돈다(`snapshot.publish_lease` = '<보유자>|<epoch>', 보유자 =
  `job:<id>` — daily 이월·지역 확장·bootstrap 의 그 자리 발행도 그 잡 id). 겹친 `snapshot.publish` 잡은 아무것도 지우지 않고 **지연
  재큐잉**된다: 상태 queued 로 돌아가고 stats `requeue_count`·`not_before`(그 시각 전에는 worker 가 집지 않는다, 2·4·8·16·30초…)·
  `requeue_reason`(`publish_in_progress: …`) — 먼저 돈 발행이 끝난 뒤 다시 돌아 그 발행이 못 읽은 변경을 새 리비전으로 이어 발행하거나
  '이미 발행됨'으로 닫는다. 40번(약 18분) 넘게 바쁘면 failed `publish_in_progress`. 그 자리 발행이 바쁘면 `snapshot.publish` 잡을
  남긴다(stats `publish_retry_job_id` = `publish_job_id`). 실패 정리 DELETE 는 '발행 전' 상태 + **임대를 아직 든 동안**만 지운다(멈췄던
  보유자가 깨어나도 넘겨받은 새 보유자의 행을 지우지 않는다). 보유 잡이 running 이 아니거나 15분이 지나면 다음 발행이 넘겨받는다(worker 가
  죽어도 손으로 풀 필요 없음). 급할 때만: `UPDATE snapshot SET publish_lease = NULL WHERE id = N`.
- **후속 발행 잡**(D15-6): 판정 중·발행 계산 중인 리비전에 호재 연결 PATCH 가 들어오면 `snapshot.publish` `{snapshot_id, follow_up: true}`
  잡이 생긴다. 그 리비전 발행 계산이 그 쓰기를 읽었으면 전환이 잡을 done(`included_in_snapshot_id`)으로 닫고, 아니면 잡이 새 리비전을
  발행한다(`deferred_to` = 판정 중 리비전 발행 때 들어감). 그 판정 중 리비전을 끝낼 잡(같은 리비전 판정·발행 잡, 그 지역 수집·확장 잡)이
  하나도 살아 있지 않으면 = 멈춘 리비전 — 후속 잡이 이어 간다(이월이 끝났으면 ready → 발행, 덜 됐으면 이어 채움, 그 뒤 사실 변경·실패한
  재판정이 있으면 재판정 등록 — stats `resumed_snapshot_id`·`rejudge_job_id`, D17-3).
- **backfill**(D14-9·**D15-3**): 마이그레이션은 앱 코드를 읽지 않는다(0010·0011·0012 = 테이블·표식만). 업그레이드 뒤
  `cd backend && uv run alembic upgrade head` → `uv run python -m app.snapshot_view backfill`(= `python scripts/tasks.py backfill`, 멱등 —
  .9 행 단위 사람 확인을 의미 묶음으로 옮기고, 발행 리비전의 **미완 단위**만 채운다). 완결성은 (리비전, kind, 시나리오) **완료 표식**
  (`snapshot_view_unit` — 그 단위의 마지막 쓰기와 같은 트랜잭션)으로 본다: 표식이 없거나 done=false 이거나 실제 행 수가 표식 rows 보다
  적으면 미완 → 그 단위 GET 503 `materialize_pending`(Retry-After 30초)·`POST /reports` 503. backfill 은 이미 있는 행을 그대로 두고 빠진
  키만 넣으며, 리비전마다 따로 실패한다(출력 `failed=[…]` — 그 리비전만 503 으로 남고 다음 실행이 이어서 채운다). 사람 확인 이전·0013
  할인 전환 알림 단계도 따로 실패한다(`failed[].step`, R3i m6). worker 는 시작할 때 같은 backfill 을 돌고, 실패·`busy` 가 남으면 **5분마다
  다시** 돈다. 미완 리비전 수 = `app.snapshot_view.pending_count(session)`. **행은 있는데 표식이 없는 단위도 미완**이다(D16-2 — 404 가
  아니라 503, backfill 이 표식을 쓴다).
- **backfill 은 발행과 같은 임대를 잡는다**(**D17-1**, 계약 .14): 리비전마다 `snapshot.publish_lease`(보유자 `backfill:<pid>:<tid>`)를
  잡고, 다른 발행·backfill 이 들고 있으면 그 리비전을 건너뛴다(출력 `busy=[…]` — 다음 실행·worker 5분 주기가 다시). 그래서 compose 의
  자동 마이그레이션·backfill(worker 시작)과 CLI backfill 이 겹쳐도 한 쪽만 쓴다. 출처 서랍은 '옛 행 삭제 → 새 행 넣기 → 완료 표식'을
  **한 트랜잭션**으로 바꾸고, 빠진 키 행은 지우지 않고 더하기만 하므로 Ctrl+C·worker 재시작·디스크 오류로 어디서 끊겨도 이미 저장된
  본문·서랍(발행 순간 값)이 지워지거나 지금 사실로 다시 계산되지 않는다(예전: 서랍 DELETE 를 먼저 커밋해 그 사이 끊기면 다음 실행이 지금
  사실로 다시 만들었다). 끊긴 backfill 은 다시 돌리면 이어서 채운다(임대는 끊긴 프로세스가 놓고, 못 놓았으면 15분 뒤 넘겨받는다).
- **backfill 이 지금 사실로 계산하는 것**(**D17-2**): 빠진 단위·키는 발행 순간 값이 남아 있지 않으므로 backfill 할 때의 사실로 계산한다.
  그래서 발행 뒤 사실이 바뀐 상태(예: 계약금 10% → 20%)에서 일부만 쓴 단위를 채우면 **한 리비전 안에 시점이 다른 값이 섞일 수 있다**
  (상세 시나리오 2 는 20, 기본 목록은 10). 그런 단위에는 `snapshot_view_unit.backfilled_at`(새로 계산해 채운 시각)이 남고, 그 리비전
  응답 메타 `Snapshot.backfilled_at`(리비전 목록·`latest_snapshot`)으로 화면이 '업그레이드 때 다시 계산한 값 포함'을 안내한다. 범위는
  그 리비전 것만: 단지 상세 키·단지 목록 본문·비교 입력 = 그 리비전 단지 목록 저장본의 단지(발행 뒤 생긴 단지 제외), 시장 = 그 리비전
  생활권. 표식만 다시 쓴 단위(행 그대로)는 `backfilled_at` 이 없다.
- **업그레이드 뒤 backfill 절차**(**D16-2**·**D17-1**, 계약 .13·.14): 0012 이전에 만든 저장본 단위는 마이그레이션이 **전부 미완**으로
  표시한다(행 수를 추정하지 않는다 — 일부만 쓴 기본 시나리오 단위·.11 범위 출처 서랍이 '완료'로 숨지 않게). .12 DB 는 `0013` 이 모든
  표식을 미완으로 내려 다시 확인한다. `0014`(.13 → .14)는 `backfilled_at` 열을 더하고 .13 이전에 저장한 보고서 본문의 점수 출처 id
  (`sc_<행>`·`st_<행>` — 서랍 없음)를 API 서랍 id(`sc_<실행>_<단지>_<성분>`·`st_<실행>_<단지>`)로 바꾼 뒤 그 리비전 출처 서랍 단위를
  미완으로 둔다(backfill 이 새 id 서랍만 더한다). 순서:
  1. worker 를 멈춘다(필수는 아니다 — 겹쳐도 임대로 한 쪽만 쓴다(D17-1). 다만 발행 잡·backfill 이 번갈아 기다려 끝이 늦어진다).
     compose 는 api·worker 시작 때 자동 마이그레이션·backfill 이 돈다 — CLI 를 함께 돌려도 안전하다(`busy` 리비전은 다른 쪽이 채운다).
  2. `cd backend && uv run alembic upgrade head`(0013·0014).
  3. `uv run python -m app.snapshot_view backfill` — 출력 `snapshots=[…] rows=N failed=[]` 를 본다. 리비전마다 계산 1회(1000 단지면 수십 초)라
     발행 리비전이 많으면 몇 분 걸린다. 그동안 그 리비전 GET 은 503 `materialize_pending`(화면은 기다렸다 다시 읽는다).
  4. 다시 `backfill` → `snapshots=[]`·`busy=[]`(멱등) · `pending_count == 0` 을 확인하고 worker 를 켠다(worker 시작도 같은 backfill 을
     돈다). 3 이 중간에 끊겼으면(Ctrl+C 등) 그냥 다시 돌린다 — 이미 쓴 것은 그대로, 남은 것만 채운다.
  backfill 은 **이미 있는 행 바이트를 바꾸지 않고 빠진 키만** 넣는다. 출처 서랍은 D15-2 범위(모든 시나리오·kind·`rd_`)로 빠진 id 를 채우고
  이미 있던 서랍 본문은 그대로 둔다. 발행 뒤 생긴 단지·생활권은 옛 리비전의 키가 되지 않는다(그 리비전 단지 목록·시장 저장본의 키만).
  `failed` 가 있으면 그 리비전만 503 으로 남는다 — 로그 `snapshot_view.backfill_failed` 의 원인을 고치고 3을 다시.
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
- **할인**(D11-6·D12-3·**D16-1**, D14-2·D15-1 대체): 공고문 파서가 찾은 할인은 **언제나 '추정'**(표시만 — 사유 '공고문 자동 추출 — 조건
  확인 필요')이다. 조건 문구는 앞뒤 줄·떨어진 각주·표 머리에 흩어져 있어 줄 단위 규칙으로 '조건 없음'을 증명할 수 없다. 구매가에서 빠지는
  할인은 **사람 확인으로 '확인됨'이 된 할인**뿐이다: G7 사람 확인(`POST /ops/human-checks` field `discount`, 값 = 기준 타입 할인 원 단위
  정수, 0 = 할인 없음 확인)을 넣으면 현재 공고의 그 타입 할인 칸이 라벨 확인됨이 되고 상세·목록 정렬·필터·비교·보고서·점수가 같은
  값으로 뺀다(`analysis.price_view.current_price`). 의미 단위(D13-2)라 그 단지 다른 공고의 같은 타입 할인 칸에도 퍼진다. 할인 사람 확인
  뒤에 관측된 공고문이 **다른** 할인 금액을 내면 그 값('추정', 차감 없음)이 채택되고 '사람 확인 재검토: 기준 타입 할인'이 생긴다 —
  다시 확인한다. '할인 없음' 줄·0원·경품·취득세·중도금 이자·발코니·옵션 지원은 할인 후보도 아니다. 0013 마이그레이션이 예전 파서가
  '확인됨'으로 저장한 할인 출처 행을 '추정'으로 바꾼다(녹화 공고에는 할인 줄이 없어 실데이터 영향 없음 — R3i 뒤 0013 을 거치는 DB 는
  compare 채택 표식을 남기고, backfill 이 바뀐 채택 할인마다 critical change_event·재판정을 한 번 등록한다).
  **D17-4**(계약 .14): 할인 사람 확인은 **기준 타입** 칸이다(응답 `basis_type_code`, 폼에 '기준 타입 84C 할인' 표시). 그 뒤 할인을
  **싣지 않은** 새 공고(무순위·정정)가 현재 공고가 되어도 사람 확인 값이 그 공고 칸에 그대로 들어가 차감이 유지된다(값 없음 ≠ 다른 값 —
  계약금 사람 확인도 같다). 옛 공고 행을 지정한 할인 사람 확인도 현재 공고에 들어간다. 84㎡에 더 가까운 타입이 생겨 기준 타입이 바뀌면
  옛 타입 할인은 그 칸 표시만 남고 빠지지 않는다 — 새 기준 타입으로 다시 사람 확인한다. 값 형식: ASCII 숫자, 쉼표는 세 자리마다, 끝 '원'은
  붙여서('10,000,000원'), 0 ~ 1천억 — 어기면 422 `discount_format`. 할인이 기준 타입 차감 바탕(대표층가·최고가 중 낮은 값) 이상이면 422
  `discount_not_below_price`.
- **보고서**: 발행 전(판정 중) 리비전은 만들 수 없다(409). 파일 이름에 지역·리비전·잡 id 가 들어가 같은 기준일 리비전끼리 덮어쓰지 않는다.
- **prod + SQLite 거부**(D11-9): `ENV=prod` 는 Postgres `DATABASE_URL` 만 받는다.

## 12. 회귀 실행 순서

`python scripts/tasks.py regress` 는 frontend `node_modules` 가 없으면 `npm ci` 를 **먼저** 하고 pytest 회귀 → e2e 순으로 돈다.
같은 frontend 에서 `npm ci` 가 도는 동안 회귀(T13 프론트 lint 검사)를 돌리면 eslint 가 모듈을 못 찾는다 — 설치를 끝낸 뒤 돌린다
(R3 4차 리뷰가 확정한 간헐 실패 원인. 실패 메시지에 eslint stderr 가 나온다).
