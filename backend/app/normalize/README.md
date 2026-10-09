# app/normalize

- **주인**: WP2
- **읽기 허용**: WP1, WP7
- 쓰기 금지 이유(RA §2): —

## 범위 (RA §2·§5)

원문 → 필드 후보 → 상충 해결 → 출처 행. 숫자 하나도 출처 없이 남기지 않는다.
`applyhome_parser.py`, `notice_parser.py`, `resolver.py`(§3 우선순위, conflict_group), `provenance.py`,
`changes.py`(이전값 diff → change_event), `archive.py`.

- `Parser.parse(raw) -> list[FieldCandidate]`, `Resolver.resolve(candidates) -> ResolvedFields` (RA §4-3).
- 파싱 정규식은 판단이 아니다(규칙 3). 포함 여부·상충 판단은 판정기(WP3) 몫이다.
- 원문 파일은 `app.core.paths.resolve_raw_path(relpath)` 로 연다.

## 규칙

- 이 디렉터리와 `backend/tests/normalize/` 만 주인이 쓴다. 다른 WP는 읽기만 하고, 고칠 것은 요청으로 남긴다(AGENTS 규칙 1).
- 공통 도구는 `app.core` 를 쓴다(`app/core/README.md`). 모델·계약은 `app/models`, `contracts/` (WP0) — 읽기 전용.
- 지역명 하드코딩 금지(규칙 15).
