# infra — 배포·운영 파일

단일 호스트 배포(RA §10, ADR-10). 운영 절차는 [`docs/runbook.md`](../docs/runbook.md), 설계 결정은
[`docs/design/DECISIONS.md`](../docs/design/DECISIONS.md)(D11-8·D11-9·D12-6).

| 파일 | 내용 |
| --- | --- |
| `docker-compose.yml` | 서비스 4개(`db` postgres:16 · `api` · `worker` · `web` nginx), 볼륨 3개(`pgdata` DB · `rawdata` 원문·참조·보고서 · `backups` 백업). `API_TOKEN`·`POSTGRES_PASSWORD` 가 비면 기동을 거부한다 |
| `Dockerfile.api` | FastAPI(`python -m app.serve`). 원문 볼륨은 읽기 전용(`rawdata:/data:ro`) |
| `Dockerfile.worker` | 스케줄러·수집·판정·점수·보고서·백업(`python -m app.worker`). Playwright chromium, Node(판정기 `npx @jkudish/jev-mcp`), 한글 글꼴, ECharts 번들, **`postgresql-client-16`**(PGDG — backup 잡의 `pg_dump`, 서버와 같은 판) |
| `Dockerfile.web` | 프론트 빌드 → nginx(`nginx.conf` — `/api/` 를 `api:8000` 으로 프록시, SPA 라우팅) |
| `nginx.conf` | 위 프록시·정적 파일 설정. 내부망(`INTERNAL_SUBNET`)만 `X-Forwarded-For` 를 믿는다(`FORWARDED_ALLOW_IPS`) |
| `.env.example` | 환경변수 예시(기본 `ENV=prod` + Postgres — prod+SQLite 는 거부, D11-9). `cp infra/.env.example infra/.env` 후 값 채우기. `.env` 는 커밋 금지 |
| `backup.sh` | 호스트 cron 대안 백업(db 컨테이너 `pg_dump -Fc` + `pg_restore --list` 검증, 원문 `rsync`). 기본은 worker 의 `backup` 잡 |
| `raw_archive.sh` | 원문 월별 압축(디스크 부족 — 삭제가 아니라 `tar.gz`, runbook §6). worker 이미지에 `/app/infra/raw_archive.sh` 로 들어 있다 |

## 백업 (D11-8 · D12-6)

worker 가 매일 03:00 `backup` 잡을 넣고 실행한다(결과 = `job_run.stats`).

- 위치: worker 환경변수 `BACKUP_DIR=/backups` = 볼륨 `backups`(원문 볼륨 `rawdata` 와 **분리** — 원문 볼륨이 망가져도 백업이 남는다).
- DB: `pg_dump -Fc` → `/backups/<날짜>/db.dump`. 이미지의 클라이언트 판(`ARG PG_MAJOR=16`)은 compose 의 서버(`postgres:16`)와 같아야
  한다 — 서버를 올리면 이 값도 같이 올린다(`pg_dump` 는 더 새 서버를 덤프하지 않는다).
- 원문: `RAW_DIR` → `/backups/raw/` 증분(지우지 않는다). 보존 기본 무기한(`keep_days` 1~3650 을 주면 오래된 날짜 폴더만 지운다).
- 확인: `docker compose -f infra/docker-compose.yml exec worker ls -la /backups` · G7 잡 목록의 `backup` 행.

## 점검 명령

```bash
docker compose -f infra/docker-compose.yml config -q            # 구문 검증(Docker 없으면 python scripts/tasks.py compose-config)
docker compose -f infra/docker-compose.yml up -d --build
curl -s http://localhost:8080/health
docker compose -f infra/docker-compose.yml exec worker pg_dump --version
```

compose 구조(서비스·볼륨·환경변수·이미지 내용)는 Docker 없이도 `backend/tests/core/test_repo_layout.py` 가 YAML·Dockerfile 을 읽어 검사한다.
