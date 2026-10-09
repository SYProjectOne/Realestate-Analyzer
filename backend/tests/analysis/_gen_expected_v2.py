"""expected_scores_v2.json 생성기 (RA §9 (b)단계 draft, 사람 확인 대기).

    cd backend && uv run python tests/analysis/_gen_expected_v2.py

입력 = 인천·김포 보고서(docs/source/incheon_gimpo_report.md, 확인일 2026-10-07)의 수치. 보고서에 없는 값은
ASSUMPTIONS에 적고 그대로 파일에 남긴다. 결과는 app.analysis(§6-4 식)로 계산하고 (a)단계 대비 차이를 설명한다.
테스트(test_expected_v2.py)는 파일 안의 inputs로 다시 계산해 결과가 같은지 본다.
"""

# ruff: noqa: E501  (보고서 수치·설명 문자열)
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:  # 스크립트로 실행할 때
    sys.path.insert(0, str(BACKEND))

from app.analysis.ladder import ladder_targets  # noqa: E402
from app.analysis.scenarios import builtin  # noqa: E402
from app.analysis.score import run_detailed  # noqa: E402
from app.core.contracts_gen import ScoreInputs, Snapshot  # noqa: E402
from app.core.protocols import CONTRACT_VERSION  # noqa: E402

REPO = BACKEND.parent
FIXTURE = REPO / "contracts" / "fixtures" / "incheon_gimpo_2026-10-08"
ASOF = "2026-10-08"
EOK = 100_000_000

LA_SONGDO, LA_GEOMDAN, LA_GYEYANG, LA_GIMPO = "28185", "28260", "28245", "41570"

ASSUMPTIONS = [
    "생활권 = DECISIONS D1 #1 기본값(시군구 1개당 1개): 연수구(송도)·서구/검단구(검단)·계양구·김포시. 보고서의 하위 생활권(고촌·풍무·사우·북변·당하 등) 구분은 쓰지 않는다. 생활권 id는 미분양 scope_code(시군구 코드)와 맞추려고 시군구 코드를 그대로 썼다(계약 변경 요청 참조).",
    "생활권 세대수(U_ref = 세대수 × 8%)는 보고서에 없다 — 연수구 160,000 · 검단 90,000 · 김포시 212,500(보고서 '김포시 인구 약 51만' ÷ 가구원 2.4명)은 가정값이다. household_stat(WP1 reference) 값으로 바꿔야 한다. 계양구는 판정 대상이 없어 null.",
    "실거래는 보고서의 '범위(건수)'만 있으므로 범위 안에서 건수만큼 등간격 가격을 만들어 넣었다(건수 '10+'는 10, 미기재는 5 또는 3). 거래일은 2026-05~09로 고르게 배치(검단 §5-2의 '2026-01~06' 거래도 창 안으로 가정). 출처는 dapt 재가공 → source=reprocessed.",
    "캐슬앤파밀리에시티 2단지의 '3층 4.0억 1건(특이 저가)'은 그대로 넣었다 — 1.5×IQR 이상치 규칙(T4)이 실제로 빼는지 확인용.",
    "분양권 거래(그라노블·금강펜테리움·우미린 파크리브)는 is_presale=true로 넣어 비교군·벤치마크에서 빠지게 했다. 롯데캐슬 넥스티엘 5.8억(2026-02-02)은 기준일 전 6개월 밖이라 빠진다.",
    "2020년 이전 준공 단지(파크애비뉴·퍼스트파크·풍무 센트럴 푸르지오·사우 아이파크 등)의 거래는 세 생활권 모두 신축 거래가 3건 이상이라 대체가 일어나지 않으므로 입력에서 생략했다.",
    "벤치마크 trade_median_won = 보고서 실거래 범위의 중간값. 분양가가 '3.3㎡당'·'초반대'로만 보도된 김포 단지는 보고서의 환산값(메트로자이 4.25억·캐슬앤파밀리에 4.1억·리버시티 3.85억·풍무 센트럴 푸르지오 3.7억)을 쓰고 label 추정. 호반써밋 1차는 상충(4.07 vs 4.5억) 중 4.5억(보수적).",
    "입주 물량: 김포는 §12-3-6 공고문 입주예정월 합산(추정 집계). 검단은 '2026~2028 연 1만 내외'(§12-3-6)를 연 10,000(월 미상 → 엔진이 12개월 균등 분배)으로 넣고 더샵 AB22·23 2,857(2029-12)을 더했다. 송도는 2027년 1,017(R114 보도, 월 미상) + 한내들 501(2029-03) + 그란테르 1,544(G5-1 853은 2029-08, 나머지 691은 2030-01로 가정). 그라노블·월 미상 단지는 빠져 있다(과소 집계).",
    "한내들 계약금%: 보고서는 '1차 500만·입주 때까지 2,000만'(팝업)만 적었다 → 2,500만 ÷ P_mid 8.56억 = 2.92%로 환산.",
    "그란테르 전매: 당첨 2026-06-02 + 6개월, 등기 시 해제 아님. 마리나베이: 조합원 자격상실분 무순위·전매제한 도과 → resale_months 0. 해링턴 1BL·지엔하임은 참고(사다리 없음)라 종합 미계산이지만 성분은 계산해 둔다.",
    "사다리 p5·p10·p20·p_flat = 보고서 §6-2·§12-4-1 jev_noul 값(move_in_plus_1y만). judgment_seq는 보고서에 단지별로 적힌 김포 #118(칸타빌)·#122(그라센트)·#123(스위첸)만 넣고 나머지는 null.",
    "rerank = #124 통합 16카드의 순위(같은 relevance는 같은 순위)를 RA 식 10×(N − rank)/(N − 1), N = 16으로.",
]

EXPLANATION = (
    "(b) TOP 5 = 엘리프 6.38 > 한내들 6.30 > 그란테르 5.48 > 스위첸 4.99 = 센트레빌 4.94(공동 4위). (a) TOP 5(그란테르 5.87 > 엘리프 5.70 > "
    "한내들 5.33 > 스위첸 5.00 > 센트레빌 = 더샵 AB23 4.61)와 같은 단지 5개가 남고 더샵 AB23이 7위로 빠졌으며 1·3위가 바뀌었다. "
    "p10은 (a)·(b) 같은 식(10×확률)이라 차이가 없고, 차이는 다섯 성분에서 나온다. "
    "① rerank: 보고서 relevance×10(0.37~0.89 → 3.7~8.9로 좁음) 대신 RA 순위식 10×(N−rank)/(N−1)(N=16)이라 공동 1위 3곳은 10, "
    "하위(마리나베이·해링턴 0.67, 고촌 2.0, 칸타빌 4.67)는 크게 내려간다. "
    "② gap: 보고서는 하위 생활권·선별 비교 단지 대비 갭을 사람이 골랐고, RA는 시군구 생활권 전체의 2020년 이후 준공 84㎡ 6개월 거래 중앙값을 쓴다. "
    "송도 풀(중앙 9.34억)에는 IBD 고가 신축이 섞여 그란테르는 +37%(0점), 한내들·마리나베이는 −8~−13%(7.1·8.4점)가 되고, "
    "김포 풀(중앙 5.99억)에는 마산 동일스위트 4억대가 섞여 김포 신규 분양 단지는 모두 +11~+33%(0~2.3점)가 된다. 캐슬앤파밀리에시티 2단지 4.0억 1건은 이상치로 빠졌다(T4). "
    "③ benchmark: 보고서는 '2023 이후 분양분은 분양가 근처'를 감안해 4~5점을 줬지만 RA 식은 생활권 전체 사례의 중앙 gain만 본다 — 검단 +61%·김포 +49%(2017~19 저가 분양분 위주)라 10·9.88점, "
    "송도는 +18.5%라 3.71점이고 2023 이후 분양 사례가 없어 no_recent_sale_case 플래그가 붙는다. "
    "④ supply: 세대수가 보고서에 없어 가정값(연수구 16만·검단 9만·김포 21.25만 세대)을 썼으므로 사람 확인이 가장 필요한 성분이다. 검단은 연 1만 세대 입주로 엘리프·센트레빌·그랑포레가 0~0.24점, "
    "송도는 확인된 입주 물량이 적어 8.4~9.2점(보고서 5~7)이다. "
    "⑤ liquidity: 식이 보고서 등급과 대체로 비슷하나 대출 한도·즉시 입주 같은 사람 판단이 빠져 그란테르 7→8.70, 계약금 10%인 단지(스위첸·리버프론트·그라센트)는 1~1.5점 낮다. "
    "민감도(±0.10 12변형)에서 그란테르·스위첸·센트레빌·더샵 AB23·칸타빌·마리나베이가 TOP 5 경계를 오가 unstable이고, 변동 없는 성분이 없다 — "
    "(b) 순위는 (a)보다 가중치에 민감하다. 사람 확인 항목: 세대수 가정, 생활권 범위(시군구 1개 vs 하위 생활권), 거래 합성(범위→등간격), 벤치마크 분양가 환산값."
)


def eok(x: float) -> int:
    return int((Decimal(repr(x)) * EOK).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def spread(lo: float, hi: float, n: int) -> list[int]:
    if n == 1:
        return [eok(lo)]
    step = (Decimal(repr(hi)) - Decimal(repr(lo))) / (n - 1)
    return [
        int(((Decimal(repr(lo)) + step * i) * EOK).quantize(Decimal(1_000_000), rounding=ROUND_HALF_UP))
        for i in range(n)
    ]


_tid = [0]


def trades(
    la: str,
    apt: str,
    year: int | None,
    prices: list[int],
    *,
    presale: bool = False,
    dates: list[str] | None = None,
) -> list[dict[str, Any]]:
    out = []
    start = date(2026, 5, 1)
    for i, p in enumerate(prices):
        _tid[0] += 1
        d = dates[i] if dates else (start + timedelta(days=(150 * i) // max(1, len(prices)))).isoformat()
        out.append(
            {
                "id": _tid[0],
                "living_area": la,
                "apt_name": apt,
                "completed_year": year,
                "area_m2": 84.9,
                "floor": None,
                "price_won": p,
                "deal_date": d,
                "cancelled": False,
                "source": "reprocessed",
                "is_presale": presale,
            }
        )
    return out


def build_trades() -> list[dict[str, Any]]:
    t: list[dict[str, Any]] = []
    # 연수구(송도) — 보고서 §5-1·§5-4
    for apt, year, lo, hi, n in [
        ("힐스테이트 송도 더스카이", 2024, 11.2, 13.6, 9),
        ("더샵 송도 프라임뷰 F20", 2022, 8.9, 10.4, 10),
        ("송도자이 크리스탈오션", 2024, 10.7, 11.2, 4),
        ("더샵 송도아크베이", 2025, 10.5, 10.5, 1),
        ("더샵 송도센터니얼", 2023, 9.3, 10.4, 2),
        ("힐스테이트 레이크 송도 3차", 2023, 8.2, 9.2, 10),
        ("송도자이 더 스타", 2024, 9.2, 10.4, 10),
        ("힐스테이트 레이크 송도 4차", 2025, 8.2, 9.5, 10),
        ("송도 럭스오션 SK뷰", 2025, 7.5, 8.7, 3),
        ("더샵 송도마리나베이", 2020, 5.9, 7.5, 5),
    ]:
        t += trades(LA_SONGDO, apt, year, spread(lo, hi, n))
    t += trades(LA_SONGDO, "송도자이풍경채 그라노블(분양권)", 2027, spread(7.9, 9.3, 5), presale=True)
    # 검단 — §5-2·§5-4
    for apt, year, lo, hi, n in [
        ("힐스테이트 신검단 센트럴", 2025, 8.3, 8.9, 5),
        ("검단 금호어울림 센트럴", 2021, 7.5, 7.9, 5),
        ("우미린 더시그니처", 2022, 7.4, 8.2, 5),
        ("호반써밋 1차", 2021, 7.0, 7.5, 5),
        ("검단파라곤 센트럴파크", 2022, 6.4, 6.8, 5),
        ("유승한내들 에듀파크", 2021, 5.7, 6.1, 3),
        ("디에트르 더펠리체", 2021, 5.8, 6.2, 3),
        ("호반써밋 프라임뷰", 2021, 5.7, 6.0, 3),
        ("한신더휴 캐널파크", 2021, 6.3, 6.5, 3),
        ("힐스테이트 불로 포레스트", 2025, 4.5, 5.3, 5),
    ]:
        t += trades(LA_GEOMDAN, apt, year, spread(lo, hi, n))
    t += trades(LA_GEOMDAN, "풍경채 어바니티", 2024, [eok(8.3), eok(6.0), eok(4.8)])
    t += trades(LA_GEOMDAN, "금강펜테리움 센트럴파크(분양권)", 2026, spread(4.8, 5.3, 3), presale=True)
    t += trades(LA_GEOMDAN, "롯데캐슬 넥스티엘", 2026, [eok(5.8)], dates=["2026-02-02"])
    # 김포시 — §12-3-1·§12-3-3
    for apt, year, lo, hi, n in [
        ("한강메트로자이 1단지", 2020, 6.0, 6.7, 9),
        ("한강메트로자이 2단지", 2020, 5.9, 6.8, 10),
        ("한강메트로자이 3단지", 2020, 5.9, 6.3, 10),
        ("캐슬앤파밀리에시티 1단지", 2020, 5.5, 6.0, 10),
        ("힐스테이트 리버시티 1단지", 2020, 5.8, 6.1, 8),
        ("힐스테이트 리버시티 2단지", 2020, 5.6, 6.3, 10),
        ("한강 동일스위트 The Park뷰 1단지", 2020, 4.1, 4.5, 10),
        ("한강 동일스위트 The Park뷰 2단지", 2020, 4.2, 4.5, 10),
        ("고촌 센트럴자이", 2024, 7.4, 7.8, 6),
    ]:
        t += trades(LA_GIMPO, apt, year, spread(lo, hi, n))
    t += trades(LA_GIMPO, "캐슬앤파밀리에시티 2단지", 2020, [*spread(5.8, 6.6, 8), eok(4.0)])
    t += trades(
        LA_GIMPO,
        "김포 북변 우미린 파크리브(분양권)",
        2027,
        [eok(4.8), eok(5.7), eok(5.4), eok(5.2)],
        presale=True,
    )
    return t


def bm(
    la: str,
    name: str,
    completed: int | None,
    sale_year: int,
    sale: float,
    lo: float,
    hi: float,
    label: str,
    *,
    presale: bool = False,
) -> dict[str, Any]:
    return {
        "id": None,
        "living_area": la,
        "name": name,
        "completed_year": completed,
        "sale_year": sale_year,
        "sale_price_84_won": eok(sale),
        "trade_median_won": eok((lo + hi) / 2),
        "is_presale": presale,
        "label": label,
    }


def build_benchmarks() -> list[dict[str, Any]]:
    return [
        # 연수구 §5-1 (분양가 청약홈 + 실거래 dapt → 재가공, 언론 분양가 → 비공식)
        bm(LA_SONGDO, "힐스테이트 송도 더스카이", 2024, 2020, 7.485, 11.2, 13.6, "재가공"),
        bm(LA_SONGDO, "더샵 송도 프라임뷰 F20", 2022, 2019, 5.6, 8.9, 10.4, "비공식"),
        bm(LA_SONGDO, "송도자이 크리스탈오션", 2024, 2021, 7.672, 10.7, 11.2, "재가공"),
        bm(LA_SONGDO, "더샵 송도아크베이", 2025, 2021, 8.0, 10.5, 10.5, "재가공"),
        bm(LA_SONGDO, "더샵 송도센터니얼", 2023, 2021, 8.31, 9.3, 10.4, "재가공"),
        bm(LA_SONGDO, "힐스테이트 레이크 송도 3차", 2023, 2020, 7.522, 8.2, 9.2, "재가공"),
        bm(LA_SONGDO, "송도자이 더 스타", 2024, 2021, 9.554, 9.2, 10.4, "재가공"),
        bm(LA_SONGDO, "힐스테이트 레이크 송도 4차", 2025, 2022, 8.99, 8.2, 9.5, "재가공"),
        bm(LA_SONGDO, "송도 럭스오션 SK뷰", 2025, 2022, 9.19, 7.5, 8.7, "재가공"),
        bm(LA_SONGDO, "송도자이풍경채 그라노블(분양권)", None, 2024, 8.86, 7.9, 9.3, "재가공", presale=True),
        # 검단 §5-2
        bm(LA_GEOMDAN, "검단 금호어울림 센트럴", 2021, 2019, 3.9, 7.5, 7.9, "비공식"),
        bm(LA_GEOMDAN, "우미린 더시그니처", 2022, 2020, 4.2, 7.4, 8.2, "비공식"),
        bm(LA_GEOMDAN, "호반써밋 1차", 2021, 2019, 4.5, 7.0, 7.5, "비공식"),
        bm(LA_GEOMDAN, "검단파라곤 센트럴파크", 2022, 2019, 4.162, 6.4, 6.8, "비공식"),
        bm(LA_GEOMDAN, "힐스테이트 신검단 센트럴", 2025, 2022, 4.52, 8.3, 8.9, "재가공"),
        bm(LA_GEOMDAN, "롯데캐슬 넥스티엘", 2026, 2023, 5.877, 5.8, 5.8, "재가공"),
        bm(LA_GEOMDAN, "힐스테이트 불로 포레스트", 2025, 2022, 5.29, 4.5, 5.3, "재가공"),
        bm(LA_GEOMDAN, "금강펜테리움 센트럴파크(분양권)", 2026, 2023, 4.83, 4.8, 5.3, "재가공", presale=True),
        # 김포 §12-3-1
        bm(LA_GIMPO, "한강메트로자이 1단지", 2020, 2017, 4.25, 6.0, 6.7, "추정"),
        bm(LA_GIMPO, "한강메트로자이 2단지", 2020, 2017, 4.25, 5.9, 6.8, "추정"),
        bm(LA_GIMPO, "한강메트로자이 3단지", 2020, 2017, 4.25, 5.9, 6.3, "추정"),
        bm(LA_GIMPO, "캐슬앤파밀리에시티 1단지", 2020, 2017, 4.1, 5.5, 6.0, "추정"),
        bm(LA_GIMPO, "캐슬앤파밀리에시티 2단지", 2020, 2018, 4.1, 5.8, 6.6, "추정"),
        bm(LA_GIMPO, "힐스테이트 리버시티 1단지", 2020, 2018, 3.85, 5.8, 6.1, "추정"),
        bm(LA_GIMPO, "힐스테이트 리버시티 2단지", 2020, 2018, 3.85, 5.6, 6.3, "추정"),
        bm(LA_GIMPO, "풍무 센트럴 푸르지오", 2018, 2015, 3.7, 7.2, 7.8, "추정"),
        bm(LA_GIMPO, "고촌 센트럴자이", 2024, 2023, 7.584, 7.4, 7.8, "재가공"),
        bm(LA_GIMPO, "김포 북변 우미린 파크리브(분양권)", None, 2024, 6.5, 4.8, 5.7, "추정", presale=True),
    ]


def sup(
    la: str, year: int, ym: str | None, units: int, complex_id: int | None = None, label: str = "추정"
) -> dict[str, Any]:
    return {
        "living_area": la,
        "year": year,
        "ym": ym,
        "units": units,
        "label": label,
        "complex_id": complex_id,
    }


def build_supply() -> list[dict[str, Any]]:
    return [
        sup(LA_SONGDO, 2027, None, 1_017, label="비공식"),
        sup(LA_SONGDO, 2029, "2029-03", 501, 3),
        sup(LA_SONGDO, 2029, "2029-08", 853, 1),
        sup(LA_SONGDO, 2030, "2030-01", 691, 1),
        sup(LA_GEOMDAN, 2026, None, 10_000),
        sup(LA_GEOMDAN, 2027, None, 10_000),
        sup(LA_GEOMDAN, 2028, None, 10_000),
        sup(LA_GEOMDAN, 2029, "2029-12", 2_857, 6),
        sup(LA_GIMPO, 2027, "2027-12", 1_200),
        sup(LA_GIMPO, 2028, "2028-02", 3_058),
        sup(LA_GIMPO, 2028, "2028-07", 720, 10),
        sup(LA_GIMPO, 2028, "2028-08", 1_573, 13),
        sup(LA_GIMPO, 2028, "2028-08", 1_029, 4),
        sup(LA_GIMPO, 2028, "2028-10", 956),
        sup(LA_GIMPO, 2028, "2028-11", 1_524),
        sup(LA_GIMPO, 2029, "2029-01", 1_071),
        sup(LA_GIMPO, 2029, "2029-01", 639, 8),
        sup(LA_GIMPO, 2029, "2029-04", 385, 14),
        sup(LA_GIMPO, 2029, "2029-05", 660),
        sup(LA_GIMPO, 2029, "2029-12", 612, 7),
        sup(LA_GIMPO, 2030, "2030-01", 961),
        sup(LA_GIMPO, 2031, "2031-01", 2_432, 9),
    ]


def build_unsold() -> list[dict[str, Any]]:
    rows = [
        {"ym": "2026-08", "scope_code": LA_SONGDO, "total": 505, "post_completion": 203, "label": "재가공"},
        {"ym": "2026-08", "scope_code": LA_GEOMDAN, "total": 737, "post_completion": 737, "label": "재가공"},
        {"ym": "2026-08", "scope_code": LA_GYEYANG, "total": 0, "post_completion": 0, "label": "재가공"},
    ]
    for ym, total in [
        ("2025-06", 571),
        ("2025-07", 492),
        ("2025-08", 2141),
        ("2025-12", 1536),
        ("2026-03", 1162),
        ("2026-06", 879),
        ("2026-07", 830),
        ("2026-08", 787),
    ]:
        rows.append(
            {
                "ym": ym,
                "scope_code": LA_GIMPO,
                "total": total,
                "post_completion": 52 if ym == "2026-08" else None,
                "label": "재가공",
            }
        )
    return rows


# key, id, scope, la, price(low, high 억), move_in, immediate, completed, ladder(p5,p10,p20,flat,seq),
# winner, resale_m, on_reg, residency, D%, interim, intake, path, priority
COMPLEXES: list[tuple[Any, ...]] = [
    (
        "granter",
        1,
        "판정 대상",
        LA_SONGDO,
        (12.45, 13.18),
        "2029-08",
        False,
        None,
        (0.51, 0.39, 0.24, 0.49, None),
        "2026-06-02",
        6,
        False,
        0,
        5,
        "중도금 60% 이자후불",
        "미정",
        "official_popup",
        False,
    ),
    (
        "elif",
        2,
        "판정 대상",
        LA_GEOMDAN,
        (5.78, 6.08),
        "2028-03",
        False,
        None,
        (0.48, 0.45, 0.36, 0.48, None),
        "2025-09-10",
        36,
        True,
        0,
        5,
        "중도금 60% 이자후불",
        "가능",
        "official_popup",
        False,
    ),
    (
        "hannaedeul",
        3,
        "판정 대상",
        LA_SONGDO,
        (8.13, 8.99),
        "2029-03",
        False,
        None,
        (0.39, 0.31, 0.16, 0.63, None),
        "2025-12-23",
        6,
        False,
        0,
        2.92,
        "중도금 60% 이자후불(연 4.80%)",
        "가능",
        "official_popup",
        False,
    ),
    (
        "switzen",
        4,
        "판정 대상",
        LA_GIMPO,
        (6.26, 6.99),
        "2028-08",
        False,
        None,
        (0.40, 0.33, 0.19, 0.63, 123),
        "2025-07-18",
        36,
        True,
        0,
        10,
        "중도금 60% 이자후불제",
        "확인 불가",
        None,
        False,
    ),
    (
        "centreville_educity",
        5,
        "판정 대상",
        LA_GEOMDAN,
        (5.91, 6.22),
        "2028-08",
        False,
        None,
        (0.35, 0.26, 0.16, 0.63, None),
        "2025-10-14",
        36,
        True,
        0,
        10,
        "중도금 60% 이자후불",
        "미정",
        "unofficial_ref",
        False,
    ),
    (
        "thesharp_ab23",
        6,
        "판정 대상",
        LA_GEOMDAN,
        (6.51, 6.68),
        "2029-12",
        False,
        None,
        (0.39, 0.29, 0.20, 0.59, None),
        "2026-07-03",
        36,
        True,
        36,
        5,
        "중도금 60% 이자후불",
        "미정",
        "official_popup",
        False,
    ),
    (
        "cantavil",
        7,
        "판정 대상",
        LA_GIMPO,
        (6.64, 6.97),
        "2029-12",
        False,
        None,
        (0.36, 0.29, 0.19, 0.64, 118),
        "2025-12-10",
        6,
        False,
        0,
        5,
        "중도금 60% 이자후불",
        "가능",
        "official_popup",
        False,
    ),
    (
        "gracent2",
        8,
        "판정 대상",
        LA_GIMPO,
        (6.61, 7.18),
        "2029-01",
        False,
        None,
        (0.37, 0.27, 0.17, 0.65, 122),
        "2026-04-21",
        36,
        True,
        0,
        10,
        "중도금 60% 이자 사업시행자 대납",
        "미정",
        "official_popup",
        False,
    ),
    (
        "riverfront",
        9,
        "판정 대상",
        LA_GIMPO,
        (6.54, 7.83),
        "2031-01",
        False,
        None,
        (0.35, 0.28, 0.18, 0.66, None),
        "2026-08-20",
        36,
        True,
        0,
        10,
        "중도금 60% 이자후불제",
        "미정",
        None,
        False,
    ),
    (
        "lottecastle",
        10,
        "판정 대상",
        LA_GIMPO,
        (7.97, 7.97),
        "2028-07",
        False,
        None,
        (0.25, 0.17, 0.11, 0.76, None),
        "2025-04-08",
        6,
        False,
        0,
        5,
        None,
        "미정",
        None,
        False,
    ),
    (
        "gochon_centralxi",
        11,
        "판정 대상",
        LA_GIMPO,
        (7.584, 7.584),
        None,
        True,
        2024,
        (0.17, 0.11, 0.06, 0.72, None),
        "2023-11-14",
        6,
        False,
        0,
        5,
        "중도금 없음, 잔금 95%",
        "미정",
        None,
        False,
    ),
    (
        "marinabay",
        12,
        "판정 대상",
        LA_SONGDO,
        (8.087, 8.087),
        None,
        True,
        2020,
        (0.29, 0.21, 0.13, 0.69, None),
        "2026-09-15",
        0,
        False,
        0,
        10,
        None,
        "불가",
        None,
        False,
    ),
    (
        "harrington_1bl",
        13,
        "참고",
        LA_GIMPO,
        (7.58, 7.96),
        "2028-08",
        False,
        None,
        None,
        "2025-07-23",
        6,
        False,
        0,
        5,
        "중도금 60% 이자후불",
        "확인 불가",
        None,
        False,
    ),
    (
        "gnheim",
        14,
        "참고",
        LA_GIMPO,
        (7.002, 7.17),
        "2029-04",
        False,
        None,
        None,
        "2026-01-27",
        6,
        False,
        0,
        10,
        "중도금 60% 이자후불",
        "확인 불가",
        None,
        False,
    ),
    (
        "kaive_yubora",
        15,
        "보류",
        LA_GYEYANG,
        None,
        None,
        False,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "미정",
        None,
        True,
    ),
    (
        "grandforet",
        16,
        "보류",
        LA_GEOMDAN,
        None,
        None,
        False,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "미정",
        None,
        True,
    ),
]

# #124 통합 rerank (보고서 §12-4-2) — 같은 relevance는 같은 순위
RERANK: list[tuple[int, float, int]] = [
    (3, 0.89, 1),
    (1, 0.89, 1),
    (2, 0.89, 1),
    (4, 0.87, 4),
    (5, 0.83, 5),
    (8, 0.83, 5),
    (6, 0.77, 7),
    (9, 0.75, 8),
    (7, 0.73, 9),
    (10, 0.59, 10),
    (15, 0.54, 11),
    (16, 0.54, 11),
    (11, 0.53, 13),
    (14, 0.39, 14),
    (12, 0.37, 15),
    (13, 0.37, 15),
]


def build_complexes() -> list[dict[str, Any]]:
    out = []
    names = {c["key"]: c["name"] for c in load_a()["complexes"]}
    for (
        key,
        cid,
        scope,
        la,
        price,
        move_in,
        immediate,
        completed,
        lad,
        winner,
        resale,
        on_reg,
        residency,
        d,
        interim,
        intake,
        path,
        priority,
    ) in COMPLEXES:
        ladders = []
        if lad is not None:
            tgt = ladder_targets(ASOF, move_in_ym=move_in, immediate=immediate)["move_in_plus_1y"]
            ladders.append(
                {
                    "horizon": "move_in_plus_1y",
                    "target_ym": tgt.target_ym,
                    "months_from_asof": tgt.months_from_asof,
                    "p5": lad[0],
                    "p10": lad[1],
                    "p20": lad[2],
                    "p_flat": lad[3],
                    "status": "ok",
                    "judgment_seq": lad[4],
                }
            )
        out.append(
            {
                "complex_id": cid,
                "name": names[key],
                "living_area": la,
                "judge_scope": scope,
                "price_low_won": eok(price[0]) if price else None,
                "price_high_won": eok(price[1]) if price else None,
                "price_label": "확인됨" if price else None,
                "move_in_ym": move_in,
                "immediate_move_in": immediate,
                "completed_year": completed,
                "ladders": ladders,
                "winner_date": winner,
                "resale_months": resale,
                "resale_release_on_registration": on_reg,
                "residency_months": residency,
                "down_payment_pct": d,
                "interim_terms_text": interim,
                "intake_status": intake,
                "intake_path": path,
                "regulated": False,
                "rewin_restriction_years": None,
                "has_priority_supply": priority,
                "fixed_components": None,
            }
        )
    return out


def load_a() -> dict[str, Any]:
    with (FIXTURE / "expected_scores.json").open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def build_inputs() -> ScoreInputs:
    return ScoreInputs.model_validate(
        {
            "snapshot_id": 12,
            "asof_date": ASOF,
            "region": {
                "age_premium_coef": {"c_per_year": 0.015, "cap_years": 8, "label": "추정"},
                "supply_ref_pct": 0.08,
            },
            "rerank": {
                "judgment_seq": 124,
                "status": "ok",
                "prev": None,
                "items": [
                    {"candidate_id": f"complex:{cid}", "complex_id": cid, "relevance": rel, "rank": rank}
                    for cid, rel, rank in RERANK
                ],
            },
            "living_areas": [
                {"id": LA_SONGDO, "name": "연수구(송도)", "households": 160_000},
                {"id": LA_GEOMDAN, "name": "서구·검단구(검단)", "households": 90_000},
                {"id": LA_GYEYANG, "name": "계양구", "households": None},
                {"id": LA_GIMPO, "name": "김포시", "households": 212_500},
            ],
            "trades": build_trades(),
            "benchmarks": build_benchmarks(),
            "supply": build_supply(),
            "unsold": build_unsold(),
            "complexes": build_complexes(),
        }
    )


def d2(x: float | None) -> float | None:
    return None if x is None else float(Decimal(repr(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def explain(key: str, comp: str, a_score: float, b: Any, a_note: str | None, detail: Any) -> str:
    """성분별 (a)→(b) 차이 설명."""
    delta = Decimal(repr(b.score_0_10)) - Decimal(repr(a_score))
    head = f"{a_score} → {b.score_0_10} ({'+' if delta >= 0 else ''}{delta}). "
    note = f"보고서: {a_note}. " if a_note else ""
    if comp == "rerank":
        return (
            head
            + f"보고서는 relevance×10, RA §6-4는 한 호출 안의 순위식 10×(N−rank)/(N−1)(N=16). {b.formula_text}"
        )
    if comp == "gap":
        g = detail.gaps.get(b.complex_id)
        med = "" if g is None or g.median_adjusted is None else f" 생활권 중앙 {int(g.median_adjusted):,}원"
        return (
            head
            + note
            + f"RA: 같은 생활권(시군구) 2020년 이후 준공 84㎡ 6개월 거래 전체의 중앙값 대비 갭(보고서는 하위 생활권·선별 단지·범위 중앙).{med}. {b.formula_text}"
        )
    if comp == "benchmark":
        return (
            head
            + note
            + f"RA: 생활권 비분양권 벤치마크 전체의 분양가 대비 실거래 중앙 gain/0.5(보고서는 사람 등급). {b.formula_text}"
        )
    if comp == "supply":
        return (
            head
            + note
            + f"RA: U_window(입주+1년 ±12개월 입주 세대)/U_ref(세대수 가정 × 8%) 식(보고서는 사람 등급, 세대수는 가정값). {b.formula_text}"
        )
    if comp == "liquidity":
        return (
            head
            + note
            + f"RA: 기준일→전매 종료 연수·거주의무·계약금% 식(보고서는 사람 등급; 대출 한도·즉시 입주 등은 식에 없음). {b.formula_text}"
        )
    return head + note + b.formula_text


def main() -> None:
    a = load_a()
    a_by_key = {c["key"]: c for c in a["complexes"]}
    inputs = build_inputs()
    snap = Snapshot(
        id=12,
        region_id=1,
        asof_date=ASOF,
        status="building",
        degraded=False,
        created_at=f"{ASOF}T07:00:00+09:00",
    )
    detail = run_detailed(snap, builtin("base"), inputs)
    res = detail.result
    totals = {t.complex_id: t for t in res.totals}
    comps: dict[int, dict[str, Any]] = {}
    for c in res.components:
        comps.setdefault(c.complex_id, {})[c.component] = c
    id_to_key = {c["complex_id"]: c["key"] for c in a["complexes"]}

    rows = []
    for cx in inputs.complexes:
        key = id_to_key[cx.complex_id]
        ac = a_by_key[key]
        t = totals[cx.complex_id]
        row_comps = {}
        diff = {}
        for name, c in comps[cx.complex_id].items():
            row_comps[name] = {
                "score": c.score_0_10,
                "raw": c.raw_value,
                "label": c.label,
                "reason": c.reason,
                "flags": c.flags or [],
                "formula_text": c.formula_text,
            }
            a_score = ac["components"].get(name)
            if (
                a_score is not None
                and c.score_0_10 is not None
                and abs(Decimal(repr(c.score_0_10)) - Decimal(repr(a_score))) >= Decimal("0.01")
            ):
                diff[name] = explain(key, name, a_score, c, ac.get("component_notes", {}).get(name), detail)
        gap = detail.gaps.get(cx.complex_id)
        comparable = []
        if gap is not None:
            for m in gap.members:
                comparable.append(
                    {
                        "member_apt_name": m.member_apt_name,
                        "completed_year": m.completed_year,
                        "substitute": m.substitute,
                        "adjusted": m.adjusted,
                        "coef_used": None if m.coef_used is None else float(m.coef_used),
                        "n_trades": m.n_trades,
                        "low_won": m.low_won,
                        "median_won": m.median_won,
                        "adjusted_median_won": m.adjusted_median_won,
                        "high_won": m.high_won,
                        "outliers_excluded": m.outliers_excluded,
                        "excluded_reason": m.excluded_reason,
                        "note": m.note,
                    }
                )
        if t.total is None and ac["computed_total"] is None:
            diff["total"] = "(a)·(b) 모두 종합 미계산 — 사다리(noul) 없음(보류·참고)."
        rows.append(
            {
                "key": key,
                "complex_id": cx.complex_id,
                "name": cx.name,
                "judge_scope": cx.judge_scope,
                "total": t.total,
                "total_display": d2(t.total),
                "rank": t.rank,
                "tie_group": t.tie_group,
                "unstable": t.unstable,
                "a_total": ac["computed_total"],
                "a_rank": ac["expected_rank"],
                "components": row_comps,
                "diff_vs_a": diff,
                "comparable_set": comparable,
            }
        )

    def top5(rs: list[dict[str, Any]], rank_key: str, total_key: str) -> list[dict[str, Any]]:
        sel = [r for r in rs if r[rank_key] is not None and r[rank_key] <= 5]
        return [
            {"key": r["key"], "total": r[total_key], "rank": r[rank_key]}
            for r in sorted(sel, key=lambda r: (r[rank_key], r["complex_id"]))
        ]

    sens = detail.sensitivity
    assert sens is not None
    v2 = {
        "fixture": "incheon_gimpo_2026-10-08",
        "contract_version": CONTRACT_VERSION,
        "stage": "b",
        "status": "사람 확인 대기",
        "generated_by": "backend/tests/analysis/_gen_expected_v2.py (app.analysis, 시나리오 base)",
        "inputs_source": "docs/source/incheon_gimpo_report.md §4(B)·§5·§6-2·§12-2·§12-3·§12-4 (확인일 2026-10-07)",
        "scenario": "base",
        "weights": res.weights.model_dump(exclude_none=True),
        "assumptions": ASSUMPTIONS,
        "summary": {
            "top5_a": top5(
                [{**r, "a_rank": a_by_key[r["key"]]["expected_rank"]} for r in rows], "a_rank", "a_total"
            ),
            "top5_b": top5(rows, "rank", "total"),
            "explanation": "",
            "sensitivity": {
                "unstable": sens.unstable,
                "unstable_keys": [id_to_key[i] for i in sens.unstable_complex_ids],
                "stable_components": sens.stable_components,
                "base_top5": [id_to_key[i] for i in sens.base_top5],
            },
        },
        "complexes": rows,
        "inputs": inputs.model_dump(mode="json"),
    }
    out = FIXTURE / "expected_scores_v2.json"
    v2["summary"]["explanation"] = EXPLANATION
    out.write_text(json.dumps(v2, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    for r in sorted(rows, key=lambda r: (r["rank"] or 99, r["complex_id"])):
        print(
            f"{r['rank']!s:>4} {r['key']:<20} b={r['total']!s:<10} a={r['a_total']!s:<6} "
            + " ".join(f"{k}={v['score']}" for k, v in r["components"].items())
        )


if __name__ == "__main__":
    main()
