# ADR-07 API 스타일

- 상태: 채택 (RA v1 §1, §4)
- 결정: **contract-first REST — `contracts/openapi.yaml` 이 원본, 서버는 그에 맞추고 프론트 타입은 `openapi-typescript` 로 생성**
- 버린 대안: 서버 자동 생성(코드 → 스키마)

## 이유

프론트와 백엔드 에이전트가 같은 라운드에 병렬로 일하려면 계약이 먼저 고정돼야 한다.

## 결과

- `contracts/` 는 WP0 만 고친다. 변경은 `contracts/CHANGELOG.md`(버전 = 날짜.연번), 현재 `2026-10-09.1`.
- 백엔드 라우터는 `app/api`(WP5) 의 `router` 하나로 `app.main` 에 붙는다(접두 `API_PREFIX`, 기본 `/api`).
- 검증: schemathesis 가 `openapi.yaml` 대비 전 엔드포인트(WP5). 프론트: `npm run gen:api`.
- 작업 러너: `python scripts/tasks.py gen`.

## 바꿀 신호

없음.
