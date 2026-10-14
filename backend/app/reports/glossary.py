"""보고서 용어 풀이 — 본문 첫 등장 괄호 풀이 + 부록 C 용어 풀이(30-proposal §7·§11-2 (4), D28-4).

문구 원본은 ``docs/design/ui-benchmark/05-persona.md`` §7 용어집에 30-proposal §7-3 "고칠 것"을 반영한 것이다.
key 는 프론트 ``ko.json glossary.items.<key>``(30-proposal §7-2 초안)와 같다. 화면과 보고서가 한 원본을 쓰는 방식
(빌드 때 복사 또는 ``contracts/`` 파일)은 WP0 가 정한다 — 그때까지 보고서는 이 파일을 원본으로 쓴다(요청 R9-REPORT-1).

원칙: 한 줄, 정확하게, 권유 없이. 제도 수치(배점·기간·비율)는 넣지 않고 공고문·청약홈으로 보낸다.
금지어(30-proposal §1)는 ``tests/reports/test_r9_report.py`` 가 검사한다("보장 아님" 부정형만 허용).
"""

# ruff: noqa: E501  (한국어 문구)

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["CATEGORIES", "FORBIDDEN_WORDS", "GLOSSARY", "GlossaryItem", "forbidden_hits"]


@dataclass(frozen=True, slots=True)
class GlossaryItem:
    key: str
    term: str
    short: str  # 부록 C 한 줄 풀이
    cat: str
    inline: str = ""  # 본문 첫 등장 괄호 풀이(짧은 명사구). 비면 괄호 풀이 없이 부록 C 만


CATEGORIES: Final[dict[str, str]] = {
    "basic": "청약 기본",
    "who": "자격·순위",
    "money": "돈",
    "limits": "제한",
    "app": "이 보고서의 계산값·판정",
    "labels": "라벨(값 옆 작은 글자)",
}

_ITEMS: Final[tuple[GlossaryItem, ...]] = (
    # ---- 청약 기본
    GlossaryItem(
        "cheongyak",
        "청약",
        "새 아파트를 분양받으려고 정해진 기간에 신청하는 절차입니다. 당첨자를 뽑아 계약할 수 있게 합니다.",
        "basic",
    ),
    GlossaryItem(
        "notice",
        "입주자모집공고(공고문)",
        "단지의 자격·가격·일정·제한을 적은 공식 문서입니다. 화면·보고서 내용과 다르면 공고문이 기준입니다.",
        "basic",
        "단지의 자격·가격·일정·제한을 적은 공식 문서",
    ),
    GlossaryItem(
        "move_in",
        "입주(예정월)",
        "공사가 끝나 들어가 살 수 있는 시기입니다. 공고문 기준이고 바뀔 수 있습니다.",
        "basic",
    ),
    GlossaryItem(
        "trade", "실거래가", "국토부에 신고된 실제 매매 가격입니다. 호가(부르는 값)와 다릅니다.", "basic"
    ),
    # ---- 자격·순위
    GlossaryItem(
        "general_supply",
        "일반공급",
        "특별공급을 뺀 나머지 물량입니다. 순위와 가점·추첨으로 당첨자를 정합니다.",
        "who",
    ),
    GlossaryItem(
        "special_supply",
        "특별공급(특공)",
        "신혼부부·생애최초·신생아 가구 등 정해진 조건을 갖춘 사람에게 따로 떼어 둔 물량입니다.",
        "who",
    ),
    GlossaryItem(
        "point_system",
        "가점제",
        "무주택기간·부양가족 수·통장 가입기간 점수가 높은 순으로 뽑는 방식입니다. 배점은 청약홈에서 확인하세요.",
        "who",
    ),
    GlossaryItem(
        "lottery", "추첨제", "자격을 갖춘 신청자 중에서 가점과 관계없이 무작위로 뽑는 방식입니다.", "who"
    ),
    GlossaryItem(
        "points",
        "청약 가점",
        "가점제에서 쓰는 내 점수입니다. 가점 계산은 청약홈 가점 계산기에서 합니다. 이 보고서는 가점을 계산하지 않습니다.",
        "who",
    ),
    GlossaryItem(
        "homeless_household",
        "무주택 세대구성원",
        "나와 주민등록상 같은 세대의 가족 모두가 집을 갖고 있지 않은 상태입니다.",
        "who",
    ),
    GlossaryItem(
        "householder",
        "세대주",
        "주민등록상 세대를 대표하는 사람입니다. 일부 지역·유형은 세대주만 1순위가 됩니다.",
        "who",
    ),
    GlossaryItem(
        "rank",
        "1순위·2순위",
        "통장 가입기간·예치금 같은 요건을 채운 정도에 따른 신청 순서입니다. 1순위가 먼저 뽑힙니다.",
        "who",
    ),
    GlossaryItem(
        "local_priority",
        "해당지역·기타지역",
        "단지가 있는 지역에 일정 기간 산 사람(해당지역)이 같은 순위에서 먼저 뽑힙니다.",
        "who",
    ),
    GlossaryItem(
        "account",
        "청약통장",
        "청약 신청에 필요한 저축 통장(주택청약종합저축)입니다. 가입기간이 가점과 순위에 쓰입니다.",
        "who",
    ),
    GlossaryItem(
        "deposit",
        "예치금",
        "민영주택 1순위가 되려면 통장에 들어 있어야 하는 최소 금액입니다. 지역·면적마다 다릅니다.",
        "who",
    ),
    GlossaryItem(
        "no_rank",
        "무순위(줍줍)",
        "계약 포기나 부적격으로 남은 집을 다시 모집하는 청약입니다. 자격·지역 요건은 공고마다 다릅니다.",
        "who",
        "계약 포기·부적격으로 남은 집을 다시 모집하는 청약",
    ),
    GlossaryItem(
        "arbitrary",
        "임의공급",
        "무순위 뒤에도 남은 집을 사업주체가 정한 방식으로 다시 모집하는 것입니다. 조건은 공고마다 다릅니다.",
        "who",
    ),
    GlossaryItem("first_come", "선착순", "남은 집을 먼저 신청한 순서대로 계약하는 방식입니다.", "who"),
    GlossaryItem(
        "reserve",
        "예비입주자",
        "당첨자가 계약하지 않거나 부적격일 때 순서대로 계약 차례를 받는 대기 명단입니다.",
        "who",
    ),
    GlossaryItem(
        "ineligible",
        "부적격 당첨",
        "당첨됐지만 서류 검증에서 자격이 맞지 않아 취소되는 경우입니다. 이후 청약이 제한될 수 있습니다.",
        "who",
    ),
    # ---- 제한
    GlossaryItem(
        "rewin",
        "재당첨 제한",
        "한 번 당첨된 세대가 일정 기간 다른 청약에 당첨될 수 없게 하는 제한입니다.",
        "limits",
        "한 번 당첨되면 일정 기간 다른 청약에 당첨될 수 없는 제한",
    ),
    GlossaryItem(
        "resale_limit",
        "전매제한",
        "당첨 후 정해진 기간 동안 분양권이나 집을 다른 사람에게 팔 수 없는 제한입니다.",
        "limits",
        "당첨 후 정해진 기간 동안 분양권이나 집을 팔 수 없는 제한",
    ),
    GlossaryItem(
        "resale_end",
        "전매 종료(일)",
        "전매제한이 끝나 팔 수 있게 되는 날입니다. 이 앱은 당첨자 발표일 + 전매 제한 기간으로 계산합니다(라벨 추정(산술)).",
        "limits",
    ),
    GlossaryItem(
        "residency",
        "실거주의무(거주의무)",
        "일부 주택은 입주 후 정해진 기간 동안 직접 살아야 합니다. 시작 시점에 유예 규정이 있습니다.",
        "limits",
        "입주 후 정해진 기간 동안 직접 살아야 하는 의무",
    ),
    GlossaryItem(
        "price_cap",
        "분양가 상한제",
        "분양가를 정해진 기준 이하로 묶는 제도입니다. 적용 단지는 전매·거주 제한이 붙는 경우가 많습니다.",
        "limits",
        "분양가를 정해진 기준 이하로 묶는 제도",
    ),
    GlossaryItem(
        "regulated",
        "규제지역",
        "투기과열지구·조정대상지역처럼 청약·대출·전매 규칙이 더 엄격한 지역입니다.",
        "limits",
        "청약·대출·전매 규칙이 더 엄격한 지역",
    ),
    # ---- 돈
    GlossaryItem(
        "supply_price",
        "공급금액(분양가)",
        "공고문에 적힌 타입·층별 집값입니다. 발코니 확장비와 옵션은 보통 따로입니다.",
        "money",
    ),
    GlossaryItem(
        "basis_type",
        "기준 타입(판정 타입)",
        "가격·비교에 쓰는 대표 평형입니다(보통 전용 84㎡). 다른 타입은 단지별 가격표에 있습니다.",
        "money",
    ),
    GlossaryItem(
        "exclusive_area",
        "전용면적",
        '현관 안쪽 우리 집만 쓰는 면적입니다. "84㎡"는 흔히 말하는 30평대입니다.',
        "money",
    ),
    GlossaryItem(
        "down", "계약금", "당첨 후 계약할 때 먼저 내는 돈입니다. 보통 분양가의 일정 비율입니다.", "money"
    ),
    GlossaryItem(
        "interim",
        "중도금(중도금 대출)",
        "공사 기간에 나눠 내는 돈입니다. 대출로 내는 경우가 많고 조건은 공고문에 있습니다.",
        "money",
    ),
    GlossaryItem(
        "balance",
        "잔금(잔금 대출)",
        "입주할 때 내는 나머지 돈입니다. 이때 대출 한도가 다시 적용돼 현금이 더 필요할 수 있습니다.",
        "money",
    ),
    GlossaryItem("ltv", "LTV", "집값 대비 최대 대출 비율입니다. 지역과 주택 수에 따라 다릅니다.", "money"),
    # ---- 이 보고서의 계산값·판정
    GlossaryItem(
        "intake_status",
        "접수 상태",
        "지금 이 단지에 신청할 수 있는지를 공식 자료를 판정기가 분류한 결과입니다(접수 가능·미정·불가·확인 불가).",
        "app",
        "지금 신청할 수 있는지 공식 자료를 판정기가 분류한 결과",
    ),
    GlossaryItem(
        "intake_undecided", "접수 미정", "공식 일정이 아직 확정되지 않았거나 공개되지 않은 상태입니다.", "app"
    ),
    GlossaryItem(
        "intake_unknown",
        "확인 불가(접수)",
        "공식 자료에서 상태를 찾지 못했다는 뜻입니다. 신청할 수 없다는 뜻이 아닙니다.",
        "app",
    ),
    GlossaryItem(
        "current_price",
        "현재 구매가",
        "대표 층 공급가~최고 공급가에 발코니 확장비와 필수 옵션을 더하고, 공고에 적힌 확인된 할인만 뺀 범위입니다.",
        "app",
        "대표 층~최고 공급가 + 발코니 확장비 + 필수 옵션 − 공고의 확인된 할인",
    ),
    GlossaryItem(
        "equity",
        "필요 자기자본",
        "계약금과 '구매가 − 대출한도' 중 큰 값입니다. 대출한도를 입력한 상황에서만 계산합니다(라벨 추정(산술)).",
        "app",
    ),
    GlossaryItem(
        "gap",
        "가격 갭",
        "현재 구매가 가운데값이 같은 생활권 2020년 이후 준공·전용 80~85㎡ 단지의 기준일 전 6개월 실거래 중앙값보다 몇 % 높거나(+) 낮은지(−)입니다. 거래가 3건보다 적으면 대체 단지를 쓰고 라벨이 '추정'이 됩니다.",
        "app",
        "현재 구매가가 같은 생활권 신축 실거래 중앙값보다 몇 % 높거나(+) 낮은지(−)",
    ),
    GlossaryItem(
        "living_area",
        "생활권",
        "비교 기준으로 묶은 인접 동네 범위입니다. 사용자가 편집할 수 있습니다.",
        "app",
    ),
    GlossaryItem(
        "p10",
        "+10% 확률(+10% 상승 가능성)",
        "목표 시점에 실거래가 현재 구매가보다 10% 이상일 가능성을 판정기가 매긴 값입니다. 목표 시점은 표에 함께 적습니다. 당첨 확률이 아닙니다(보장 아님).",
        "app",
        "목표 시점에 실거래가 현재 구매가보다 10% 이상일 가능성을 판정기가 매긴 값, 당첨 확률 아님",
    ),
    GlossaryItem(
        "ladder",
        "상승 가능성 사다리",
        "+5%·+10%·+20%·보합·하락 네 칸의 가능성을 판정기가 매긴 표입니다. 판정 범위 '판정 대상' 단지만 매깁니다.",
        "app",
        "+5%·+10%·+20%·보합·하락 네 칸의 가능성을 판정기가 매긴 표",
    ),
    GlossaryItem(
        "rerank",
        "판정기 순위(rerank)",
        "후보 단지 전체를 판정기가 한 번에 견줘 매긴 순서입니다. 종합 점수 성분의 하나입니다.",
        "app",
        "후보 단지 전체를 판정기가 한 번에 견줘 매긴 순서",
    ),
    GlossaryItem(
        "total",
        "종합 점수",
        "성분 점수를 상황별 가중치로 더한 상대 비교 값입니다. 성분과 가중치는 §6에 있습니다.",
        "app",
        "성분 점수를 상황별 가중치로 더한 상대 비교 값",
    ),
    GlossaryItem(
        "scenario",
        "시나리오(상황)",
        "종합 점수의 가중치를 내 상황(A~D)에 맞춰 바꾼 것입니다.",
        "app",
        "가중치를 내 상황에 맞춰 바꾼 것",
    ),
    GlossaryItem(
        "decide",
        "상황별 선택(decide)",
        "상황마다 요건(접근 가능성·규제 제약·자금)을 놓고 판정기가 고른 선택지입니다. confidence가 0.6보다 낮으면 동률로 보고 1순위를 하나로 말하지 않습니다.",
        "app",
        "상황마다 요건을 놓고 판정기가 고른 선택지",
    ),
    GlossaryItem(
        "confidence",
        "confidence",
        "판정기가 그 선택에 매긴 확신 정도(0~1)입니다. 0.6보다 낮으면 동률로 봅니다.",
        "app",
        "판정기가 그 선택에 매긴 확신 정도(0~1)",
    ),
    GlossaryItem(
        "benchmark",
        "벤치마크",
        "같은 생활권에서 먼저 분양한 단지의 분양가와 최근 실거래 중앙값을 견준 사례입니다.",
        "app",
        "먼저 분양한 단지의 분양가와 최근 실거래 중앙값을 견준 사례",
    ),
    GlossaryItem(
        "catalyst",
        "호재 단계",
        "교통·개발 계획이 어느 단계에 있는지 판정기가 분류한 것입니다. 미해결 호재는 점수 근거로 쓰지 않습니다.",
        "app",
        "교통·개발 계획이 어느 단계에 있는지 판정기가 분류한 것",
    ),
    GlossaryItem(
        "judge_scope",
        "판정 범위",
        "점수를 계산하는 단지인지(판정 대상), 순위만 보는지(참고 후보), 공고 전이라 미뤘는지(보류), 분류가 끝나지 않았는지(미해결), 빠졌는지(제외)를 나눈 것입니다. 사유는 같은 줄에 있습니다.",
        "app",
        "판정 대상·참고 후보·보류·미해결·제외 구분",
    ),
    GlossaryItem(
        "inclusion",
        "포함(단지) 분류",
        "사업주체 명의 기준으로 단지를 나눠 민간분양 아파트만 점수 대상으로 넣은 결과입니다. 분류는 판정기가 합니다.",
        "app",
        "민간분양 아파트만 점수 대상으로 넣는 분류",
    ),
    GlossaryItem(
        "judge",
        "판정기",
        "이 앱이 포함 여부·접수 상태·가격 전망을 분류할 때 쓰는 외부 판정 도구입니다. 판정 기록은 판정기 호출 기록(보고서 부록 A)에 있습니다.",
        "app",
        "포함 여부·접수 상태·가격 전망을 분류하는 외부 판정 도구",
    ),
    # ---- 라벨
    GlossaryItem(
        "label",
        "라벨",
        "모든 숫자 옆에 붙는 작은 글자입니다. 그 값을 어디서 어떻게 얻었는지 알려 줍니다(아래 다섯 가지).",
        "labels",
        "값 옆 작은 글자 — 확인됨·추정·비공식·재가공·확인 불가",
    ),
    GlossaryItem(
        "label_confirmed", "확인됨", "공식 자료(공고문·청약홈·공식 통계)에서 확인한 값입니다.", "labels"
    ),
    GlossaryItem(
        "label_estimated",
        "추정",
        "계산·가정으로 만든 값입니다. 괄호 안에 방법이 있습니다(예: 산술).",
        "labels",
    ),
    GlossaryItem(
        "label_unofficial", "비공식", "보도·블로그·홍보 같은 비공식 출처에서 얻은 값입니다.", "labels"
    ),
    GlossaryItem(
        "label_reprocessed",
        "재가공",
        "원본이 아닌 가공 데이터(실거래 재가공 사이트 등)에서 얻은 값입니다.",
        "labels",
    ),
    GlossaryItem(
        "label_unknown",
        "확인 불가",
        "값을 찾지 못했다는 뜻입니다. 괄호 안에 사유와 확인일이 있습니다.",
        "labels",
    ),
)

GLOSSARY: Final[dict[str, GlossaryItem]] = {i.key: i for i in _ITEMS}

FORBIDDEN_WORDS: Final[tuple[str, ...]] = (
    "추천",
    "유리",
    "불리",
    "좋음",
    "나쁨",
    "싸다",
    "비싸다",
    "저렴",
    "알짜",
    "기회",
    "사세요",
    "넣으세요",
    "당첨 가능",
    "확실",
    "보장",
)
_ALLOWED_NEGATIONS: Final = ("보장 아님",)


def forbidden_hits(text: str) -> list[str]:
    """새 문구 금지어(30-proposal §1). 부정형 고지 '보장 아님'만 허용한다."""
    for ok in _ALLOWED_NEGATIONS:
        text = text.replace(ok, "")
    return [w for w in FORBIDDEN_WORDS if w in text]
