# subscription-analyzer — 지역 청약 리스트업·분석 도구

사용자가 입력한 지역(자유 지명 → 시군구·법정동 묶음)의 민간분양 단지를 수집·정규화하고, 판단은 판정기(JEV MCP)에
맡기고, 결과를 기록·점수화·화면 표시·보고서(HTML·PDF)로 내보낸다. 단일 사용자용, 투자 권유 아님.

- 설계도: [`docs/source/RA_v1.md`](docs/source/RA_v1.md) · 설계 변경분(우선): [`docs/design/DECISIONS.md`](docs/design/DECISIONS.md)
- 에이전트 규칙·소유권: [`AGENTS.md`](AGENTS.md) · 아키텍처 결정: [`docs/adr/`](docs/adr/)
- 운영 절차: [`docs/runbook.md`](docs/runbook.md) · 지역 추가: [`docs/region-add.md`](docs/region-add.md)

## 구성

| 프로세스 | 코드 | 역할 |
| --- | --- | --- |
| `web` | `frontend/` (React + Vite → nginx) | 화면 G0~G8. `/api/*` 를 api 로 프록시 |
| `api` | `backend/app/main.py` + `app/api` (FastAPI) | REST(읽기·잡 등록만), `/health` |
| `worker` | `backend/app/worker.py` + `app/scheduler` | 스케줄러·수집·판정(JEV MCP 를 자식 프로세스로)·점수·보고서 |
| `db` | Postgres 16 (개발은 SQLite 파일) | 스냅샷 단위 저장 |

원문 파일은 `RAW_DIR/{source}/{yyyy-mm-dd}/{sha256}.{ext}` 에 쌓인다(삭제 없음).

## 빠른 시작 — 로컬 (Docker 없이)

필요: Python 3.12, [uv](https://docs.astral.sh/uv/), (판정기·프론트용) Node 20.

```bash
cd backend
uv sync --all-extras                       # .venv 생성
cp ../infra/.env.example .env              # 값 채우기 — 커밋 금지. 기본 DB = sqlite:///./dev.db
uv run alembic upgrade head                # 스키마 (계약 마이그레이션이 들어온 뒤)
uv run uvicorn app.main:app --reload       # http://127.0.0.1:8000/health
uv run python -m app.worker                # 다른 터미널: worker (점검은 --once)
uv run playwright install chromium         # 동적 페이지 렌더·PDF 가 필요할 때 한 번
```

프론트(스캐폴드가 들어온 뒤): `cd frontend && npm ci && npm run dev`.

작업 러너 — make 가 없으면 `python scripts/tasks.py <작업>`, 있으면 `make <작업>`:

| 작업 | 내용 |
| --- | --- |
| `test [모듈…]` | `uv run pytest tests/<모듈>` (없으면 전체) |
| `lint` / `typecheck` | ruff + mypy --strict (+ eslint / tsc) |
| `gen` | 계약 → 코드 생성(백엔드 contracts_gen, 프론트 `gen:api`) |
| `migrate` | `alembic upgrade head` |
| `dev` | api + worker (+ web) 동시 실행 |
| `regress` | 회귀(RA §9): `pytest -m regress` (+ e2e) |
| `check` | lint + 전체 테스트 (커밋 전) |
| `compose-config` | `docker compose config` (Docker 없으면 구조 테스트) |

`--dry-run` 을 붙이면 명령만 출력한다.

## 빠른 시작 — Docker

```bash
cp infra/.env.example infra/.env          # POSTGRES_PASSWORD, API_TOKEN 등 채우기 (ENV=prod 면 API_TOKEN 필수)
docker compose -f infra/docker-compose.yml up -d --build
curl http://localhost:8080/health          # web(nginx) → api
```

- 서비스 4개 `db`·`api`(:8000)·`worker`·`web`(:8080), 볼륨 2개 `pgdata`·`rawdata`(/data — api 읽기 전용, worker 쓰기).
- api 컨테이너가 시작할 때 `alembic upgrade head` 를 돌린다(alembic.ini 가 있을 때). worker 는 api 가 healthy 가 된 뒤 뜬다.

## 개발 규칙 요약

- 테스트 먼저, `mypy --strict`·`tsc --noEmit` 통과가 조건. 테스트는 오프라인(respx 녹화·MockAdapter).
- 판단은 판정기만(`app/judge`). 모든 수치는 출처 URL·확인일·라벨과 함께.
- 비밀은 환경변수로만(`.env` 커밋 금지, `infra/.env.example` 만 갱신). 지역명 하드코딩 금지.
- pre-commit: `uv run --directory backend pre-commit install`.
