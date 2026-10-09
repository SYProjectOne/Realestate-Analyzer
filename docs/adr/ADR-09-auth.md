# ADR-09 인증

- 상태: 채택 (RA v1 §1, DECISIONS D1 #13 사용자 1명)
- 결정: **열람·쓰기 토큰 1개(환경변수 `API_TOKEN`) + 읽기 전용 공유 토큰(`READONLY_TOKEN`)**
- 버린 대안: 사용자 계정

## 이유

단일 사용자이고 개인정보를 저장하지 않는다.

## 결과

- 토큰은 `SecretStr` 설정(`core.settings`), 로그에서 자동 마스킹(`core.logging`).
- `ENV=prod` 에서 `API_TOKEN` 이 없으면 설정 검증이 실패한다(기동 거부).
- 인증 의존성은 WP5(`app/api/deps.py`)가 만든다. 읽기 전용 토큰으로 POST → 403(WP5 완료 기준).
- 공유 링크는 읽기 전용 토큰으로만, 만료 30일(`SHARE_TOKEN_TTL_DAYS`).

## 바꿀 신호

팀 사용.
