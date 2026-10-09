"""SQLAlchemy 선언 기반 (계약 2026-10-09.1).

원칙(RA §3): 금액 ``*_won``은 BigInteger(원 단위 정수), 면적은 Numeric(8,2)(㎡), 날짜는 ISO 문자열
(날짜 String(10), 연월 String(7), 시각 String(32) ISO 8601 +09:00), json은 SQLAlchemy JSON,
열거는 문자열 + CheckConstraint. 파생 테이블은 snapshot_id를 가진다.

모델은 contracts/migrations/versions/0001_init.py 와 1:1이다(테스트가 autogenerate diff 0을 강제).
컬럼을 바꾸려면 오케스트레이터가 새 마이그레이션과 함께 바꾼다.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
