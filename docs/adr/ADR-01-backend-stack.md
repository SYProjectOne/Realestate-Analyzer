# ADR-01 백엔드 언어·프레임워크

- 상태: 채택 (RA v1 §1, 2026-10-09)
- 결정: **Python 3.12 + FastAPI + Pydantic v2**
- 버린 대안: Node/Nest

## 맥락

수집(Playwright·pdfplumber), MCP 클라이언트(판정기), 수치 계산(§6 수식)을 한 프로세스 묶음에서 다룬다.
여러 AI 코딩 에이전트가 병렬로 구현한다.

## 이유

- 수집·MCP·수치 계산이 한 언어로 끝난다.
- AI 코딩 도구가 가장 안정적으로 다루는 조합이다.
- Pydantic v2 + pydantic-settings 로 설정·계약 검증을 같은 도구로 한다.

## 결과

- `backend/` 하나의 uv 프로젝트(`pyproject.toml`, `uv.lock`), `requires-python = ">=3.12,<3.13"`.
- 타입: `mypy --strict`(pydantic 플러그인), 린트: `ruff`.
- 프로세스 진입점: `app.main:app`(api), `python -m app.worker`(worker).

## 바꿀 신호

없음.
