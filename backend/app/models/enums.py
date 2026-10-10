"""열거 값 (계약 2026-10-09.4). DB는 문자열 + CheckConstraint로 강제한다(RA §3).

값은 contracts/schemas/*.json 의 enum과 같다. contracts/migrations/versions/0001_init.py 는 자립해야 하므로
같은 값을 리터럴로 다시 적는다 — 둘이 다르면 tests/contracts/test_models.py 가 실패한다.
"""

from __future__ import annotations

from collections.abc import Sequence

LABELS = ("확인됨", "추정", "비공식", "재가공", "확인 불가")
REGION_STATUS = ("resolving", "bootstrapping", "ready", "failed")
SNAPSHOT_STATUS = ("building", "ready", "published")
SNAPSHOT_STATE_ENTITY = ("region", "complex", "catalyst")  # 0009 snapshot_state.entity (D12-4)
HOUSING_TYPE = ("민영", "국민")
LAND_TYPE = ("공공택지", "민간택지")
PRICE_CAP = ("적용", "미적용")
REGULATED = ("규제", "비규제")
INCLUSION_CLASS = (
    "private_sale_apt",
    "public_sale",
    "public_rental",
    "private_rental",
    "non_apartment",
    "out_of_scope",
    "manual_review",
    "범위 경계",
    "미분류",
)
JUDGE_DECISION = ("auto", "review", "manual_review")
TRACK = ("A", "B")
SUPPLY_KIND = ("본청약", "무순위", "임의", "선착순")
INTAKE_STATUS = ("가능", "미정", "확인 불가", "불가")
INTAKE_PATH = ("human_check", "official_popup", "headless_shot", "unofficial_ref")
SOURCE_KIND = (
    "applyhome_list",
    "applyhome_detail",
    "notice_pdf",
    "official_site",
    "rtms",
    "stats",
    "news",
    "reference",
)
SALE_PERIOD = ("저가 분양기", "고가 분양기")
TRADE_SOURCE = ("openapi", "reprocessed")
CATALYST_KIND = ("교통", "개발", "학교", "상업", "생활인프라", "기타")
CATALYST_STAGE = ("확정", "계획", "추진", "언론", "미확정", "호재 아님")  # 호재 아님 = 0008(D11-2)
JUDGE_TOOL = ("screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify")
JUDGMENT_STATUS = ("ok", "review", "escaped", "blocked", "error")
VERIFY_STATUS = ("verified", "contradicted", "unsupported", "review")
COMPONENT = ("p10", "rerank", "gap", "benchmark", "supply", "liquidity", "move_in")
HORIZON = ("move_in_plus_1y", "asof_plus_3y", "asof_plus_5y")
OPTION_KEY = ("complex", "wait_new", "ask_user", "investigate", "none")
REQ_JUDGE = ("supported", "contradicted", "unknown")
# score_total.judge_scope (0003, CHECK 없음). 미해결 = 계약 2026-10-09.4 (D9-1)
JUDGE_SCOPE = ("판정 대상", "보류", "참고", "미해결", "제외")
HUMAN_CHECK_KIND = ("phone", "visit", "email")
# 계약 = 0004(F1a M7), 사실 재확인 = 0006(D10-3)
CHECKLIST_KIND = ("법적 확인", "중도금", "만료", "공고 예상", "계약", "사실 재확인")
DEMOTION_RESTORED_BY = ("human_check", "new_source")  # 0006 fact_demotion.restored_by (D10-3)
CHECKLIST_STATUS = ("open", "done", "na")
CHECKLIST_CLOSED_BY = ("auto", "human")  # 0008 checklist_item.closed_by (M-9)
CHANGE_ENTITY = (
    "complex",
    "complex_type",
    "payment_terms",
    "competition",
    "remaining_event",
    "intake_status",
    "region",
    "judge",
    "catalyst",
    "benchmark",
    "supply",
    "unsold",
    "rtms_trade",
    "checklist_item",
    "notice",
)
SEVERITY = ("info", "notice", "critical")
JOB_NAME = (
    "collect.daily",
    "collect.weekly",
    "rejudge",
    "report",
    "snapshot.publish",
    "reference.refresh",
    "region.bootstrap",
    "claim.reverify",  # 계약 2026-10-09.4 (0004 CHECK)
    "backup",  # 계약 2026-10-09.8 (0008, D11-8)
    "region.expand",  # 계약 2026-10-09.8 (0008, D11-7)
)
JOB_KIND = ("scheduled", "manual", "rejudge")
JOB_STATUS = ("queued", "running", "done", "failed")
SCENARIO_CODE = ("base", "A", "B", "C", "D")
HOUSEHOLD_SCOPE = ("admin_dong", "sigungu")
# human_check.json#/$defs/EnteredByRole (API 검증만, CHECK 없음 — 옛 행 보존)
ENTERED_BY_ROLE = ("운영자", "검토자")
# share_link.json status (조회 시각으로 계산하는 값 — 컬럼 아님)
SHARE_LINK_STATUS = ("active", "expired", "revoked")


def in_check(column: str, values: Sequence[str]) -> str:
    """CHECK 식 문자열: ``column IN ('a', 'b')``. NULL은 CHECK를 통과한다(SQL 3값 논리)."""
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"{column} IN ({quoted})"
