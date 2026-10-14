"""같은 사업의 중복 단지 행 병합 (DECISIONS D29-2, R10 — 마이그레이션 0018 ``complex.merged_into_id``).

잔여·무순위·임의공급 공고는 원 단지(사업)의 사건이다(D18-4). 공고문의 원 공고 인용('최초 입주자모집공고 … 주택관리번호
2025-000397')을 못 읽던 때(R9-PARSE 전) 잔여 공고 자기 번호로 **두 번째 단지 행**이 생겼다(인천 도화: 원 단지 39 = 2025000397,
임의공급 번호 행 99 = 2025940268 — 목록 G2 에 같은 이름 두 줄, 점수 대상, 캘린더 같은 일정 두 번).

병합 규칙(판단 없음 — 공고문 문자열 인용·표 조회):
- **언제**: 정규화(``store._Binder``)가 잔여 공고 공고문의 원 공고 인용을 읽어 원 단지(이미 있는 행)에 묶을 때, 그 공고문의 **자기
  번호**(공고문 주소의 주택관리번호 · 납부 조건 키의 공고번호)를 주택관리번호로 가진 같은 지역의 다른 단지 행이 있으면 그 행을
  원 단지에 병합한다. 다음 ``collect.daily``(받아 둔 원문을 모두 다시 정규화 — runbook §10-22)가 이 경로를 탄다.
- **추측 금지**: 원 공고 번호가 공고문에 없거나(서해그랑블 5단지 1~4차) 오기(9자리)인 행은 인용이 없어 병합하지 않는다. 원 단지
  행이 없어 인용으로 자리표시 행을 새로 만든 경우도 병합하지 않는다(원 공고를 다시 받은 뒤 다음 수집에서).
- **D20-2 별칭 병합과 같은 모양**: 공고 예정 후보 행에 청약홈 공고가 오면 그 행에 주택관리번호를 붙이고 옛 이름을 별칭
  (``former_names``)으로 남기듯, 병합된 행의 이름이 원 단지 이름·별칭과 다르면 원 단지 ``former_names`` 에 더한다. 병합된 행의 번호는
  ``merged_into_id`` 로 원 단지를 가리켜, 그 번호로 오는 뒤 원문(청약홈 임의공급 상세·주택형·경쟁률)도 원 단지에 쓰인다(``store``
  — 원 단지의 단지 단위 값은 덮지 않는다, D11-4).
- **행은 지우지 않는다**: 발행 리비전의 점수·사다리·비교군·접수 행이 그 id 를 가리킨다(D11-1 — 발행 저장본 그대로). 대신 병합된
  행은 새 리비전의 판정·점수 대상(``scheduler.inputs.load_facts``)·목록·대시보드·시장·체크리스트·수집 대상(공식 홈페이지·원 공고
  다시 받기)·입주 물량·법정동 재배정·공고 예정 대조에서 빠진다(``live``). 그 행에 남은 사실 행(옛 납부 조건·경쟁률)은 이력으로
  남는다(원 단지는 재정규화로 같은 원문의 값을 이미 가진다).
- **change_event**: entity 'complex'·entity_id = 병합된 행·field 'merged_into'·complex_id = 원 단지, critical(재판정 — 후보군이
  바뀐다). 첫 적재(bootstrap) 안이면 다른 값 기록처럼 요약 수로 접힌다(``store`` 공통). 이미 병합됐으면 아무것도 하지 않는다(D23-1).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

from typing import Final

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, Complex
from app.normalize import changes

__all__ = ["MERGE_FIELD", "find_duplicate", "live", "merge_duplicate"]

MERGE_FIELD: Final = "merged_into"
"""change_event.field — 같은 사업 중복 단지 행 병합(D29-2)."""


def live() -> ColumnElement[bool]:
    """병합되지 않은 단지 행(현재 단지) 조건 — 지역 단지를 고르는 질의에 붙인다(D29-2)."""
    return Complex.merged_into_id.is_(None)


def find_duplicate(session: Session, region_id: int, own_no: str, original: Complex) -> Complex | None:
    """같은 지역에서 주택관리번호가 ``own_no``(잔여 공고 자기 번호)인 원 단지 아닌 행 — 아직 병합되지 않은 것."""
    if not own_no or own_no == original.applyhome_id:
        return None
    return session.scalars(
        select(Complex).where(
            Complex.region_id == region_id,
            Complex.applyhome_id == own_no,
            Complex.id != original.id,
            live(),
        )
    ).first()


def merge_duplicate(
    session: Session,
    dup: Complex,
    original: Complex,
    *,
    cited_no: str,
    snapshot_id: int | None,
    detected_at: str,
) -> ChangeEvent | None:
    """``dup`` 을 ``original`` 에 병합한다(표식·별칭). 이미 병합됐으면 None. change_event 는 호출자가 저장한다."""
    if dup.id == original.id or dup.merged_into_id == original.id:
        return None
    dup.merged_into_id = original.id
    known = {original.name, *(original.former_names or [])}
    if dup.name and dup.name not in known and dup.name != dup.applyhome_id:
        original.former_names = [*(original.former_names or []), dup.name]
    session.flush()
    return changes.make_event(
        entity="complex",
        entity_id=dup.id,
        field=MERGE_FIELD,
        old=None,
        new=(
            f"{original.applyhome_id} {original.name}에 병합 — 같은 사업"
            f"(공고 {dup.applyhome_id} 공고문이 원 공고 {cited_no} 인용)"
        ),
        snapshot_id=snapshot_id,
        complex_id=original.id,
        detected_at=detected_at,
        severity="critical",
    )
