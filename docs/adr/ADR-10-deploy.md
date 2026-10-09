# ADR-10 배포

- 상태: 채택 (RA v1 §1, §10)
- 결정: **docker compose 4 서비스 + 볼륨 2개(db, raw)**
- 버린 대안: k8s, 서버리스

## 이유

단일 호스트에서 `docker compose up` 으로 끝난다.

## 결과 (`infra/`)

| 서비스 | 이미지 | 포트·볼륨 |
| --- | --- | --- |
| `db` | postgres:16 | 5432 내부, `pgdata` |
| `api` | `Dockerfile.api` (uvicorn, 기동 시 `alembic upgrade head`) | 8000, `rawdata:/data:ro` |
| `worker` | `Dockerfile.worker` (Playwright chromium + Node/npx + 한글 글꼴) | —, `rawdata:/data` |
| `web` | `Dockerfile.web` (node 빌드 → nginx 정적, `/api/*` → api) | 8080 |

- 환경변수는 `infra/.env`(예시 `infra/.env.example`), compose 가 `DATABASE_URL`·`RAW_DIR` 등을 컨테이너 경로로 덮어쓴다.
- Docker 미설치 환경에서는 `backend/tests/core/test_repo_layout.py` 가 compose 구조를 YAML 로 검증한다. 실제
  `docker compose up` 검증은 Docker Desktop 설치 후(D1 #10). CI 의 `infra` 잡은 `docker compose config` 를 돌린다.

## 바꿀 신호

없음.
