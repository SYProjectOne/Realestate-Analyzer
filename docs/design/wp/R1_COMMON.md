## 공통 (R1 모든 에이전트)

역할: 당신은 {WP} 담당 에이전트다. CEO 오케스트레이터가 지시한다. 같은 라운드에 다른 에이전트 7명이 병렬로 일한다 — 그들의 코드에 의존하지 말고 **계약(`contracts/`)과 `backend/app/core/protocols.py`·픽스처에만** 의존한다.

작업 디렉터리: 현재 worktree(저장소 루트, main 최신에서 분기). 브랜치 `{BRANCH}`를 만들어 거기 커밋(접두 `[{WP}]`).

읽을 것(순서): `AGENTS.md` → `docs/design/DECISIONS.md`(RA보다 우선) → `contracts/README.md`, `contracts/CHANGELOG.md` → `docs/source/RA_v1.md` §2, §4, §5의 자기 카드 → 아래 "참조" → `backend/app/core/protocols.py`(구현할 Protocol의 docstring이 규칙이다) → 관련 `contracts/schemas/*.json`.

환경: Windows + Git Bash. 백엔드는 `cd backend && uv sync` 후 `uv run pytest tests/<자기 디렉터리>`. 프론트는 `cd frontend && npm ci`. Docker 없음(SQLite).

진행 규칙:
1. 첫 커밋 = 완료 기준을 실패하는 테스트로.
2. 그 다음 구현. 커밋은 작게 자주.
3. 끝나기 전에 자기 테스트 + `uv run ruff check app/<모듈> tests/<모듈>` + `uv run mypy app/<모듈>`(strict) 통과 확인. (프론트: lint·typecheck·test)
4. 소유 밖 파일이 필요하면 만들지 말고 보고의 "계약 변경 요청"/"제안"에 적는다. 새 라이브러리도 제안만(pyproject·package.json은 WP0 소유) — 단, 꼭 필요해서 막히면 `uv add`/`npm i` 후 보고에 명시(CEO가 머지 시 판단).
5. 작업 트리를 깨끗하게(전부 커밋) 하고 AGENTS.md의 완료 보고 양식으로 보고. 맨 위에 브랜치명·worktree 절대 경로·테스트 명령과 통과/전체 숫자. 간결하게.
