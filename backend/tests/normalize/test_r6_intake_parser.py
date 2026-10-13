"""R6-INTAKE — 공식 홈페이지 접수 문구 후보 파서(파싱 규칙, 판단 아님).

인천 첫 실행(운영 DB 스냅샷 1): 접수 classify 43건 중 9건의 입력이 '마감재리스트' 한 줄이었다. 파서가 '마감재'(마감 자재)의
'마감'을 접수 문구 후보로 잡았고, 후보가 있으면 페이지 문구 대신 후보 줄만 보냈기 때문이다. 운영시간 '마감 17:30'·'기본 마감
외의 시설'도 같은 거짓 후보였다. 아래 줄은 모두 그 실행의 공개 분양 페이지 문구다.
"""

# ruff: noqa: E501  (한국어 docstring·문구)

from __future__ import annotations

import pytest

from app.normalize.official_site_parser import GAP, intake_context, scan_text, unique_lines

NOT_INTAKE = [
    "마감재리스트",
    "마감재 리스트",
    "마감재",
    "운영시간 : 입장 10:00 ~ 마감 17:30",
    "주민공동시설의 기본 마감 외의 시설 운영을 위한 내부 소모품 및 집기류(이동 가구, 비품, 서적, 스탠드 등) 등은 제공되지 않으니 유의하시기 바랍니다.",
    "세대 내 마감자재 목록",
]
STILL_INTAKE = [
    ("청약 마감", "마감"),
    ("계약 마감되었습니다", "마감"),
    ("전 타입 마감임박", "마감임박"),
    ("분양 마감 감사합니다", "마감"),
    ("일부세대 선착순 분양중", "선착순"),
]


@pytest.mark.parametrize("line", NOT_INTAKE)
def test_finishing_material_and_hours_are_not_intake_phrases(line: str) -> None:
    assert [h.keyword for h in scan_text(line) if h.keyword.startswith("마감")] == []


@pytest.mark.parametrize(("line", "keyword"), STILL_INTAKE)
def test_real_intake_phrases_still_found(line: str, keyword: str) -> None:
    assert keyword in {h.keyword for h in scan_text(line)}


def test_unique_lines_drops_repeated_carousel_lines() -> None:
    text = "포레나\n 다채로운 생활 중심 인프라 \n\n특화 설계\n다채로운 생활 중심 인프라\n특화 설계\n현장"
    assert unique_lines(text) == ["포레나", "다채로운 생활 중심 인프라", "특화 설계", "현장"]


def test_intake_context_keeps_neighbours_and_gaps() -> None:
    # e편한세상 동인천 베이프런트(인천 첫 실행) 렌더 문구 앞부분 — 후보 '분양중공사중' 하나만 보내면 판정기 review 0.61
    text = "\n".join(
        ["컨텐츠 바로가기", "e편한세상", "로그인e편한세상 찾기", "분양중공사중", "신포역 초역세권과",
         "오션뷰를 누리는 프리미어 라이프", "e편한세상 동인천 베이프런트", "관심고객 등록", "분양 일정",
         "2025.01.02 ~ 01.04", "정당계약(아파트, 오피스텔)", "* 인허가에 따라 일정은 변경될 수 있습니다.",
         "잔여세대 선착순 계약중"]
    )  # fmt: skip
    ctx = intake_context(text)
    assert ctx == [
        "로그인e편한세상 찾기", "분양중공사중", "신포역 초역세권과",
        GAP, "* 인허가에 따라 일정은 변경될 수 있습니다.", "잔여세대 선착순 계약중",
    ]  # fmt: skip
    assert intake_context("마감재리스트\n사업안내") == [], "거짓 후보만 있으면 후보 없음(페이지 문구로)"
