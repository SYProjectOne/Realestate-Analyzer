# ADR-02 DB

- 상태: 채택 (RA v1 §1, DECISIONS D1 #10)
- 결정: **SQLAlchemy 2 + Alembic, 개발 SQLite → 운영 Postgres 16**
- 버린 대안: Postgres만 / SQLite만

## 맥락

한 사람이 개발하고 운영한다. 운영에서는 스케줄러(worker)와 API 가 동시에 쓴다.

## 이유

- 한 사람 개발은 파일 DB 가 빠르다(서비스 없이 `DATABASE_URL=sqlite:///./dev.db`).
- 스케줄러와 API 가 동시에 쓰면 Postgres 가 필요하다.

## 결과

- `app/core/db.py`: SQLite 는 WAL·`foreign_keys=ON`·`busy_timeout`(기본 5초), Postgres 는 pool(`DB_POOL_SIZE`,
  `DB_MAX_OVERFLOW`, pre_ping, recycle 30분).
- 스키마는 계약 마이그레이션(`contracts/migrations/`, WP0-A)이 원본이고 `app/models` 가 거울이다.
- compose 는 Postgres 16(`pgdata` 볼륨). Docker Desktop 설치 전에는 compose 검증 보류(D1 #10).

## 바꿀 신호

SQLite `database is locked` 발생, 또는 지역 3개 이상.
