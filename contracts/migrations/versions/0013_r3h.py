"""0013 r3h — 계약 2026-10-09.13 (R3 8차 리뷰 · DECISIONS D16-1·D16-2)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-11

계약 마이그레이션 — 계약 .13 소유자(R3h CORE6)가 추가한다. contracts/CHANGELOG.md 2026-10-09.13 항목.
**앱 코드를 import 하지 않는다**(D14-9). 스키마 변경 없음 — 데이터만.

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot_view_unit 데이터 | **모든 표식 done=false**(표식 재검증). .12 DB 에서는 0012 가 행 수 추정으로 찍은 done 표식(일부만 쓴 기본 시나리오 단위·.11 범위 출처 서랍)과 발행이 찍은 표식을 구분할 수 없다 — 전부 미완으로 내리고 backfill 이 단위마다 빠진 키만 채운 뒤 완료로 닫는다(이미 있는 행 바이트 그대로, 출처 서랍은 D15-2 범위로 빠진 id). 그 사이 발행 리비전 GET 은 503 ``materialize_pending``(worker 시작·``python -m app.snapshot_view backfill`` 이 끝내면 200) | D16-2 · N-M1·N-M2 |
| field_provenance 데이터 | 공고문 파서가 낸 할인 출처 행(``discount_by_type.*``, 원문 있음 = ``raw_document_id`` NOT NULL)의 라벨 '확인됨' → **'추정'**(reason '공고문 자동 추출 — 조건 확인 필요'). 사람 확인 행(원문 없음, reason '사람 확인(…)')은 그대로. 녹화 공고 59건에는 할인 줄이 없어 실데이터 영향 없음 | D16-1 · N-C1 |

R3i(계약 .14, 9차 리뷰 m1) 수정: 사유를 통째로 덮어쓰지 않는다 — 있던 사유(compare 채택 표식 '판정기 compare 채택'·'병기' 등)
뒤에 붙이고, 바뀐 행에 표지 ``(0013 확인됨→추정)`` 을 남긴다. 앱 backfill(``app.api.demotion.announce_relabelled_discounts``)이 표지가
붙은 채택 할인마다 critical·재판정 change_event 를 한 번 등록한다(마이그레이션은 앱 코드를 쓰지 않는다 — D14-9). 이미 .13 원래
0013 을 거친 DB 는 해당 없음(녹화 공고 할인 줄 0건 — 실데이터 영향 0).

downgrade: 데이터 되돌림 없음(미완 표식은 backfill 이 다시 닫는다, '추정' 할인은 0012 스키마에서도 유효한 값).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISCOUNT_REASON = "공고문 자동 추출 — 조건 확인 필요"
"""파서 할인 후보의 '추정' 사유(``app.normalize.notice_parser.DISCOUNT_REASON`` 과 같은 문자열 — 앱 import 금지라 복사)."""
RELABEL_MARK = "(0013 확인됨→추정)"
"""R3i m1: 이 마이그레이션이 라벨을 내린 행 표지(``app.api.demotion.RELABEL_0013_MARK`` 와 같은 문자열)."""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE snapshot_view_unit SET done = :f").bindparams(f=False))
    # R3i m1: 사유를 통째로 덮어쓰면 compare 채택 표식('판정기 compare 채택'·'병기' — resolver 가 사유로 읽는다)이 지워졌다 →
    # 사유가 있으면 뒤에 붙인다. 바뀐 행에는 0013 표지를 남겨 backfill 이 change_event·재판정을 한 번 등록한다(앱 코드 몫 —
    # ``app.api.demotion.announce_relabelled_discounts``)
    conn.execute(
        sa.text(
            "UPDATE field_provenance SET label = '추정', "
            "reason = CASE WHEN reason IS NULL OR reason = '' THEN :reason ELSE reason || '; ' || :reason END "
            "WHERE field LIKE 'discount_by_type.%' AND label = '확인됨' AND raw_document_id IS NOT NULL"
        ).bindparams(reason=f"{DISCOUNT_REASON} {RELABEL_MARK}")
    )


def downgrade() -> None:
    pass
