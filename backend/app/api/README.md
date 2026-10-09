# app/api

- **주인**: WP5
- **읽기 허용**: WP6 (계약 `contracts/openapi.yaml` 으로만)
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§5, DECISIONS D2-3)

FastAPI 라우터: regions(+resolve·living-areas), complexes, compare, scenarios, market, ops, reports, jobs.
`deps.py`(인증·스냅샷 해석), `facts.py`(Fact 래핑), `jobs.py`(job_run 등록).

## 연결 방법 (WP0 뼈대와의 접점)

- 이 패키지(`app/api/__init__.py`)에 `router: fastapi.APIRouter` 를 두면 `app.main.create_app()` 이
  `settings.api_prefix`(기본 `/api`) 아래에 붙인다. **라우터 경로에는 `/api` 를 쓰지 않는다.**
  `router` 가 없으면 건너뛴다.
- nginx(web)는 `/api/*` 를 경로 그대로 `api:8000` 으로 넘긴다 → 개발·운영 경로가 같다.
- 인증 의존성(ADR-9: `API_TOKEN` 쓰기·열람, `READONLY_TOKEN` 읽기 전용)은 이 패키지가 만든다.
- DB 세션: `Depends(app.core.db.session_dependency)` (commit 은 라우터가 명시적으로).
- `/health` 는 `app.main` 이 이미 제공한다(`{status, version, env, db}`).
- api 는 판정기를 직접 부르지 않는다 — 재판정은 `job_run` 행으로 넣는다(RA §1).

## 규칙

- 이 디렉터리와 `backend/tests/api/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
