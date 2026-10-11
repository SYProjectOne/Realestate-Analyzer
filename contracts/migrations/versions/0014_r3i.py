"""0014 r3i — 계약 2026-10-09.14 (R3 9차 리뷰 · DECISIONS D17-2 · m5)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-12

계약 마이그레이션 — 계약 .14 소유자(R3i CORE7)가 추가한다. contracts/CHANGELOG.md 2026-10-09.14 항목.
**앱 코드를 import 하지 않는다**(D14-9).

| 변경 | 내용 | 결정·리뷰 |
| --- | --- | --- |
| snapshot_view_unit.backfilled_at (새 열, NULL 가능) | 그 단위에 backfill 이 **새로 계산해 채운** 행(발행 순간 값이 아닌 업그레이드 때 계산)이 있으면 그 시각(KST ISO). 발행이 쓴 단위·표식만 다시 쓴 단위는 NULL. 리비전 응답 메타(``Snapshot.backfilled_at``)가 이 값의 최댓값 | D17-2 · major 2 |
| 데이터: 보고서 저장본 점수 prov id 변환 | .13 이전에 저장한 ``report``·``report_diff`` 본문의 점수 prov ``sc_<성분 행 id>``·``st_<합계 행 id>``(서랍 없음, KPI ``st_<실행>`` 과 부딪힘) → API 서랍 id ``sc_<실행>_<단지>_<성분>``·``st_<실행>_<단지>``(score_component·score_total 행에서 — 실행마다 불변). 본문·sha256 다시 쓰고(저장 모양 그대로 — 값만 바뀐 변환, D14-4), 바꾼 리비전의 출처 서랍 단위는 미완(done=false — backfill 이 새 id 서랍만 더한다, 이미 있는 서랍 바이트 그대로) | m5 · D14-4 |

downgrade: backfilled_at 열 삭제. id 변환은 되돌리지 않는다(새 id 는 .13 코드에서도 유효한 서랍 id).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import hashlib
import re
import zlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ZLIB_LEVEL = 1
"""저장본 압축 수준(``app.snapshot_view.ZLIB_LEVEL`` 과 같은 값 — 앱 import 금지라 복사)."""
_OLD_RE = re.compile(rb'"prov":(\{"\$v":)?"(sc|st)_(\d+)"')
"""옛 모양 점수 prov(행 id 하나) — 새 모양은 ``_`` 로 이어진 숫자 둘 이상이라 겹치지 않는다. 시나리오 patch 행의 ``{"$v": …}`` 잎도."""


def upgrade() -> None:
    op.add_column("snapshot_view_unit", sa.Column("backfilled_at", sa.String(length=32), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, snapshot_id, body FROM snapshot_view WHERE kind IN ('report', 'report_diff')")
    ).all()
    if not rows:
        return
    comp = {
        int(i): (int(r), int(cx), str(k))
        for i, r, cx, k in conn.execute(sa.text("SELECT id, score_run_id, complex_id, component FROM score_component"))
    }
    tot = {int(i): (int(r), int(cx)) for i, r, cx in conn.execute(sa.text("SELECT id, score_run_id, complex_id FROM score_total"))}

    def new_id(m: re.Match[bytes]) -> bytes:
        wrap, kind, rid = m.group(1), m.group(2), int(m.group(3))
        if kind == b"sc":
            got = comp.get(rid)
            if got is None:
                return m.group(0)
            pid = f"sc_{got[0]}_{got[1]}_{got[2]}".encode()
        else:
            got2 = tot.get(rid)
            if got2 is None:
                return m.group(0)
            pid = f"st_{got2[0]}_{got2[1]}".encode()
        inner = b'"' + pid + b'"'
        return b'"prov":' + (b'{"$v":' + inner if wrap else inner)

    touched: set[int] = set()
    for vid, sid, body in rows:
        raw = zlib.decompress(bytes(body))
        new = _OLD_RE.sub(new_id, raw)
        if new == raw:
            continue
        conn.execute(
            sa.text("UPDATE snapshot_view SET body = :b, sha256 = :h WHERE id = :i").bindparams(
                b=zlib.compress(new, ZLIB_LEVEL), h=hashlib.sha256(new).hexdigest(), i=int(vid)
            )
        )
        touched.add(int(sid))
    for sid in sorted(touched):
        conn.execute(
            sa.text(
                "UPDATE snapshot_view_unit SET done = :f WHERE snapshot_id = :s AND kind = 'provenance' AND scenario = ''"
            ).bindparams(f=False, s=sid)
        )


def downgrade() -> None:
    op.drop_column("snapshot_view_unit", "backfilled_at")
