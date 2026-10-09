# 운영 runbook

RA §10 대응표를 절차로 풀어 쓴 문서. 설계 원본은 `docs/source/RA_v1.md` §10, 변경분은 `docs/design/DECISIONS.md`.
명령은 저장소 루트 기준. make 가 없으면 `make X` 대신 `python scripts/tasks.py X`.

## 0. 실행·점검

### 0-1 Docker 로 (운영)

```bash
cp infra/.env.example infra/.env        # POSTGRES_PASSWORD, API_TOKEN, READONLY_TOKEN, (있으면) DATA_GO_KR_KEY …
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml ps
curl -s http://localhost:8080/health    # {"status":"ok","version":…,"env":"prod","db":"ok"}
docker compose -f infra/docker-compose.yml logs -f worker   # JSON 한 줄 로그
```

- `/health` 가 503(`db: error`)이면 `db` 컨테이너 상태와 `DATABASE_URL` 을 본다.
- 로그에는 비밀값·전화번호·주민번호·이메일이 `[REDACTED:…]` 로 가려진다. 판정기 payload 는 input_hash·길이만 남는다.

### 0-2 Docker 없이 (개발·Docker 미설치)

```bash
cd backend
uv sync --all-extras
cp ../infra/.env.example .env           # DATABASE_URL=sqlite:///./dev.db, RAW_DIR=./data/raw 그대로
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000          # 터미널 1
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
2. 원인 확인: `npx -y @jkudish/jev-mcp@latest` 가 worker 컨테이너에서 실행되는지(`docker compose exec worker npx --version`),
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

1. `du -sh /data/raw/*` (Docker: `docker compose exec worker du -sh /data/raw/*`) 로 소스별 용량을 본다.
2. 지난달 이전 날짜 디렉터리를 월별로 압축한다: `tar -czf /data/raw/<source>/<yyyy-mm>.tar.gz /data/raw/<source>/<yyyy-mm>-*`
   → 압축 검증(`tar -tzf`) 후 원본 디렉터리 제거. 경로 규칙(`{source}/{yyyy-mm-dd}/{sha256}.{ext}`)은 압축 안에서도 유지된다.
3. DB 는 파생 테이블을 지우지 않는다. Postgres 는 `VACUUM (ANALYZE)` 만.

## 7. 스냅샷이 published 되지 않음

원인: `claim.verify_status = contradicted` 가 1건 이상 → `snapshot.publish` 가 거부한다.

1. G7 에서 contradicted 주장 목록을 본다(문장·근거 URL).
2. 사람이 문장을 고친다(보고서·설명 문구).
3. 원자 분할 재검증(`claims.py` → `jev_verify`)이 돌고 contradicted 0 이면 publish 된다.

## 8. 백업·복구

- DB: 매일 `docker compose exec -T db pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB > backup/db-$(date +%F).dump`
- 원문: `rawdata` 볼륨을 rsync (`docker run --rm -v subscription-analyzer_rawdata:/data -v $PWD/backup:/b alpine tar -czf /b/raw-$(date +%F).tgz /data`)
- 복구: 새 `db` 를 띄운 뒤 `pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean backup/db-<날짜>.dump`, 원문은 볼륨에 풀기.
  복구 후 `/health` 와 G7 신선도를 확인한다.

## 9. 비밀값

- 비밀은 `infra/.env`(Docker) 또는 `backend/.env`(로컬)에만. 커밋 금지(pre-commit `no-dotenv`·`gitleaks`).
- 공유 링크는 `READONLY_TOKEN` 으로만, 만료 30일(`SHARE_TOKEN_TTL_DAYS`).
- 키가 노출되면: 발급처에서 폐기·재발급 → `.env` 교체 → `docker compose up -d` (로그는 이미 마스킹되지만 확인).
