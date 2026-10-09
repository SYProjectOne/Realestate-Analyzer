"""완료 기준: schemathesis 가 contracts/openapi(.bundled).yaml 대비 전 엔드포인트 통과 (devseed DB 위에서).

``contracts/openapi.bundled.yaml`` 은 ``openapi.yaml`` 의 외부 $ref 를 푼 생성물(같은 계약)이다.
operation 마다 hypothesis 예시를 만들어 ASGI 앱을 직접 부르고 schemathesis 기본 검사(5xx 없음·상태 코드·
Content-Type·응답 스키마 등)를 돌린다. 쓰기 토큰을 쓰고, DB 는 모듈 단위 복사본이다.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from typing import Any

import pytest
import schemathesis
from hypothesis import HealthCheck, settings

from app.core.db import reset_engine
from app.core.settings import set_settings

from ._support import OPENAPI_BUNDLED, WRITE, WRITE_TOKEN
from .conftest import Seeded, make_settings

schema = schemathesis.openapi.from_path(OPENAPI_BUNDLED)


@schemathesis.auth()
class _WriteToken:
    """bearerAuth = 쓰기 토큰. 인증 자체를 빼는 음성 사례(401 기대)는 schemathesis 가 알아서 만든다."""

    def get(self, case: Any, ctx: Any) -> str:
        return WRITE_TOKEN

    def set(self, case: Any, data: str, ctx: Any) -> None:
        case.headers = {**(case.headers or {}), "Authorization": f"Bearer {data}"}


@pytest.fixture(scope="module")
def st_app(seeded_db: Seeded, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    from app.main import create_app

    base = tmp_path_factory.mktemp("schemathesis")
    db = base / "st.db"
    shutil.copyfile(seeded_db.db, db)
    s = make_settings(db, seeded_db.raw_dir, base / "reports")
    set_settings(s)
    mp = pytest.MonkeyPatch()
    _catalyst_double(mp)
    try:
        yield create_app(s)
    finally:
        mp.undo()
        set_settings(None)
        reset_engine()


def _catalyst_double(mp: pytest.MonkeyPatch) -> None:
    """POST /catalysts 의 후보 함수(F1a ``app.normalize.catalyst.catalyst_from_url``)가 아직 없으면
    대역을 쓴다.

    있으면 실제 함수를 그대로 검사한다(머지 후 자동)."""
    from app.api.routers import catalysts
    from app.models import Catalyst

    try:
        catalysts.candidate_factory()
        return
    except catalysts.CandidateUnavailable:
        pass

    def fake(session: Any, region_id: int, *, url: str, title: str, excerpt: str | None = None) -> Any:
        row = Catalyst(
            region_id=region_id, name=title, kind="기타", stage="미확정", location_confirmed=False,
            source_url=url, note=excerpt,
        )  # fmt: skip
        session.add(row)
        session.flush()
        return row

    mp.setattr(catalysts, "candidate_factory", lambda: fake)


BASE_URL = "http://testserver/api"
MAX_EXAMPLES = int(os.environ.get("ST_MAX_EXAMPLES", "30"))  # 깊게 돌릴 때 ST_MAX_EXAMPLES=300

# 계약 설명이 '스키마는 맞지만 의미가 틀린 본문 → 422'를 명시한 operation
# (가중치 합≠1, 생활권 누락·중복, 참조에 없는
# 지역 코드). schemathesis positive_data_acceptance 는 스키마만 보므로 이 operation 에서는 뺀다.
# createCatalyst: guard(개인정보·비밀값)·호재 후보 조건(CatalystInputError) → 422 (계약 2026-10-09.4)
SEMANTIC_422 = {"createScenario", "updateLivingAreas", "createRegion", "createCatalyst"}


# /health 는 servers 가 루트('/')라 이 테스트(base_url /api)에서 빼고 test_health_contract 로 본다.
# POST /jobs 의 JobCreate(job_name 별 if/then payload)는 schemathesis 가 생성하지 못한다(UnsupportedSchema)
# → test_contract_create_job 이 계약 예시 + job_name 8종 본문으로 같은 검사를 돌린다.
@schema.exclude(path="/health").exclude(operation_id="createJob").parametrize()
@settings(max_examples=MAX_EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
def test_contract(case: Any, st_app: Any) -> None:
    from schemathesis.checks import positive_data_acceptance

    case.operation.app = st_app
    case.operation.schema.app = st_app  # 재전송 검사(ignored_auth 등)도 같은 ASGI 앱으로
    response = case.call(base_url=BASE_URL)
    op_id = case.operation.definition.raw.get("operationId")
    excluded = []
    if op_id in SEMANTIC_422 and response.status_code == 422:
        excluded.append(positive_data_acceptance)
    case.validate_response(response, excluded_checks=excluded, transport_kwargs={"base_url": BASE_URL})


CREATE_JOB_BODIES: list[dict[str, Any]] = [
    {
        "job_name": "rejudge",
        "payload": {"snapshot_id": 12, "scenario_id": 3, "complex_ids": None, "reason": "G5"},
    },
    {"job_name": "collect.daily", "payload": {"region_id": 1, "sources": ["official_site"]}},
    {"job_name": "collect.weekly", "payload": {"region_id": 1, "sources": ["rtms", "stats", "news"]}},
    {"job_name": "report", "payload": {"snapshot_id": 12, "format": "pdf", "compare_snapshot_id": 11}},
    {"job_name": "snapshot.publish", "payload": {"snapshot_id": 12}},
    {"job_name": "reference.refresh", "payload": {}},
    {"job_name": "region.bootstrap", "payload": {"region_id": 1}},
    {"job_name": "claim.reverify", "payload": {"snapshot_id": 12, "claim_id": 1, "text": "고친 문장"}},
    {"job_name": "rejudge", "payload": {"snapshot_id": 12}},  # 필수 누락 → 422
    {"job_name": "report", "payload": {"snapshot_id": 12, "format": "md"}},  # enum 밖 → 422
    {"job_name": "nope", "payload": {}},  # 잡 이름 밖 → 422
]


@pytest.mark.parametrize("body", CREATE_JOB_BODIES, ids=lambda b: f"{b['job_name']}")
def test_contract_create_job(body: dict[str, Any], st_app: Any) -> None:
    op = schema["/jobs"]["POST"]
    op.app = st_app
    op.schema.app = st_app
    case = op.Case(body=body, media_type="application/json", headers=dict(WRITE))
    response = case.call(headers=dict(WRITE), base_url=BASE_URL)
    case.validate_response(response, headers=dict(WRITE), transport_kwargs={"base_url": BASE_URL})
    assert response.status_code in (202, 422)


def test_all_operations_covered() -> None:
    """openapi 의 operation 수와 앱 라우트가 맞는지(빠진 엔드포인트 없음)."""
    from app.main import create_app

    ops = {(op.method.upper(), op.path) for op in (r.ok() for r in schema.get_all_operations())}
    assert len(ops) == 37  # 31 + 계약 2026-10-09.4 의 6개
    app = create_app()
    routes = {
        (method.upper(), path.removeprefix("/api") if path != "/health" else path)
        for path, item in app.openapi()["paths"].items()
        for method in item
    }
    missing = sorted(o for o in ops if o not in routes)
    assert not missing, missing


def test_health_contract(st_app: Any) -> None:
    """GET /health(루트·/api 둘 다) = 계약 Health(2026-10-09.3)."""
    from fastapi.testclient import TestClient

    from ._support import validate

    with TestClient(st_app) as client:
        for path in ("/health", "/api/health"):
            r = client.get(path)
            assert r.status_code == 200
            validate("getHealth", 200, r.json())


def test_operations_document_422_for_query_params() -> None:
    """계약 2026-10-09.3: 조회 파라미터가 있는 목록 GET 5개는 422 를 문서화한다."""
    ops = {o.definition.raw.get("operationId"): o for o in (r.ok() for r in schema.get_all_operations())}
    for op_id in ("listJobs", "getJudgmentOps", "listChecklist", "listSourceStatus", "listReports"):
        assert "422" in ops[op_id].definition.raw["responses"], op_id
