# AGENTS.md — 모든 에이전트가 첫 번째로 읽는 파일

프로젝트: 지역 청약 리스트업·분석 도구 (`subscription-analyzer`). 사용자가 입력한 지역의 민간분양 단지를 수집·정규화하고, 판단은 판정기(JEV MCP)에 맡기고, 결과를 기록·점수화·표시·보고한다.

- 설계도 원본: `docs/source/RA_v1.md` (이하 RA)
- 설계 변경분(우선): `docs/design/DECISIONS.md` — RA와 충돌하면 이쪽이 이긴다
- 메타 프롬프트(화면·판정 규칙 원본): `docs/source/meta_prompt.md`
- 회귀 데이터 원천(인천·김포 보고서): `docs/source/incheon_gimpo_report.md`
- 계약 버전: `contracts/CHANGELOG.md`의 최신 항목 하나만 가정한다

## 공통 규칙 (RA §8-4 원문)

1. 소유 디렉터리와 그 테스트만 쓴다. 다른 곳이 필요하면 요청으로 남긴다.
2. `/contracts`는 읽기 전용. 계약 버전은 지시서의 것 하나만 가정한다.
3. 판단은 판정기만 한다. 상승 확률·포함 여부·호재 단계·출처 상충을 LLM 호출이나 휴리스틱으로 대체하지 않는다. 파싱 정규식과 §6 수식은 판단이 아니다.
4. 같은 입력 재호출 금지는 코드가 강제한다(`judge/cache.py`). 판정기를 직접 부르는 코드는 `judge/` 밖에 없다.
5. 모든 수치는 출처 URL·확인일·라벨과 함께 저장하고 표시한다. 빈 라벨은 테스트 실패다.
6. 외부로 나가는 것은 공개 분양 정보뿐이다. 개인정보·API 키·비공개 자료는 판정기·웹훅·로그 어디에도 보내지 않는다. 판정기 payload는 `judge/guard.py`를 통과해야 한다.
7. 실패도 데이터다. 403·타임아웃·파싱 실패는 상태 코드와 함께 행으로 남기고 예외로 삼키지 않는다.
8. 테스트를 먼저 쓴다. 완료 기준은 전부 자동 테스트로 존재해야 한다.
9. 타입은 엄격하게: `mypy --strict`, `tsc --noEmit` 통과가 PR 조건.
10. 비밀은 환경변수로만. `.env`는 커밋 금지, `.env.example`만 갱신.
11. 새 라이브러리는 보고의 "제안"에 적고 WP0 승인 후 추가한다. `pyproject.toml`·`package.json`은 WP0 소유.
12. 화면 문자열은 `frontend/src/i18n/ko.json` 한 곳. 숫자 포맷(억·만·%)은 `FactCell`이 한다.
13. 로그에 판정기 payload 원문을 남기지 않는다. input_hash와 길이만.
14. 완료 보고는 양식대로. 하지 않은 것, 못 한 것, 끝 맞춘 것을 숨기지 않는다.

## 추가 규칙 (이 저장소)

15. 지역명(인천·김포·송도 등)을 코드에 하드코딩하지 않는다. 지역은 사용자 입력(`region` 행)이다. 지역명은 픽스처·테스트에만 나온다.
16. 커밋 접두 `[WP{n}]`, 브랜치 `wp/{n}-{slug}`. 커밋은 자기 worktree 브랜치에만. main에 직접 커밋하지 않는다(CEO만 머지).
17. 커밋 전 자기 디렉터리 테스트·ruff·mypy(또는 eslint·tsc)를 돌린다. 실패한 채 "완료"라고 쓰지 않는다.
18. 실제 외부 사이트 접속은 허용(공개 페이지만, `core.http`의 속도 제한·robots 준수). 녹화한 응답은 픽스처로 저장해 테스트는 오프라인으로 돈다.
19. Windows 개발 환경이다(Git Bash/PowerShell). 경로는 `pathlib`, 줄바꿈은 LF(.gitattributes), 파일 인코딩 UTF-8.

## 개발 명령

```bash
# 백엔드 (backend/)
uv sync --all-extras            # 의존성 설치 (.venv)
uv run pytest tests/<자기 디렉터리>
uv run ruff check app tests && uv run mypy app
uv run alembic upgrade head     # DATABASE_URL 기본 sqlite:///./dev.db

# 프론트 (frontend/)
npm ci
npm run gen:api                 # contracts/openapi.yaml → src/api/schema.d.ts
npm run dev | npm test | npm run lint | npm run typecheck | npm run e2e
```

## 디렉터리 소유권 (RA §2 + DECISIONS D8)

| 디렉터리 | 주인 |
| --- | --- |
| `contracts/` (fixtures 제외), `backend/app/core`, `backend/app/models`, `backend/pyproject.toml`, `infra/`, `frontend/package.json`, CI | WP0 (CEO) |
| `backend/app/collectors` | WP1 (a: applyhome·notice_pdf / b: official_site·rtms·stats·news·reference) |
| `backend/app/normalize` | WP2 |
| `backend/app/judge` | WP3 |
| `backend/app/analysis` | WP4 |
| `backend/app/api` | WP5 |
| `frontend/` (package.json 제외) | WP6 (a: pages / b: charts·components) |
| `backend/app/scheduler` | WP7 |
| `backend/app/reports` | WP8 |
| `e2e/`, `contracts/fixtures/` | WP9 |

테스트는 `backend/tests/<자기 모듈>/`에만 둔다.

## 완료 보고 양식 (RA §8-5)

```markdown
## 완료 보고 — WP{n} (계약 {버전}, 브랜치 wp/{n}-{slug})
산출물: {파일 목록}
테스트: `{명령}` → {통과/전체}, 커버 필드: {…}
완료 기준: [x] … [x] … [ ] …(사유)
하지 않은 것 / 가정한 것: …
제안(새 라이브러리·설계 개선): …
계약 변경 요청: 대상 파일 · 변경 내용 · 이유 · 영향 WP · 없으면 "없음"
```
