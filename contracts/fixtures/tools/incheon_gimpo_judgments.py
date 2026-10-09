"""판정 녹화 원천 — 보고서 부록 A 호출 로그 #1~#132 (WP9).

원천: docs/source/incheon_gimpo_report.md §10 부록 A(#1~89), §12-6-1(#90~132), 각 절 판정 결과표
(§3 classify, §6-1~6-5, §8-2·8-5, §12-1-3, §12-3-4·12-3-5, §12-4-1·12-4-2, §12-5-2·12-5-5).

payload는 보고서의 '입력 요약'을 그대로 담은 재구성이다(호출 당시 원문 전체가 아님). 해시는 이 payload로
app.core.protocols.input_hash 를 계산한다. 보고서에 없는 출력 값(개별 필드 이름·주장 문장 등)은 지어내지 않고
counts·known_* 로만 남긴다. 시각·소요 시간은 보고서에 없어 created_at은 날짜만, duration_ms는 null.
"""

# ruff: noqa: E501  (원문 표기)
from __future__ import annotations

from typing import Any

THRESHOLDS = {"screen": {"block": 0.75, "review": 0.25}, "extract": {"auto_accept": 0.85, "margin": 0.5},
              "audit": {"wrong_at": 0.7}, "classify": {"auto_accept": 0.85, "margin": 0.5}, "verify": {"auto_accept": 0.8}}  # fmt: skip

Call = dict[str, Any]
CALLS: list[Call] = []


def add(seq: int, tool: str, purpose: str, payload: dict[str, Any], status: str, result: dict[str, Any],
        *, confidence: float | None = None, complex_id: int | None = None, raw_extra: dict[str, Any] | None = None,
        error_text: str | None = None, ref: str | None = None) -> None:  # fmt: skip
    raw: dict[str, Any] = {"report_result": result.get("_summary")} if "_summary" in result else {}
    result = {k: v for k, v in result.items() if k != "_summary"}
    if tool in THRESHOLDS:
        raw["thresholds"] = THRESHOLDS[tool]
    raw.update(raw_extra or {})
    CALLS.append(
        {
            "seq": seq,
            "tool": tool,
            "purpose": purpose,
            "payload": {"report_ref": f"부록 A #{seq}", **payload},
            "status": status,
            "result": result,
            "raw": raw,
            "confidence": confidence,
            "complex_id": complex_id,
            "error_text": error_text,
            "ref": ref or f"부록 A #{seq}",
        }
    )


# ---------------------------------------------------------------- P1 screen (#1~28, #90~97)
SCREENS: list[tuple[int, int | None, str, str, str, float | None, float | None, float | None]] = [
    # seq, complex_id, purpose 꼬리, 입력 요약, verdict, relevance, substance, injection
    (
        1,
        1,
        "notice:1",
        "더샵 송도그란테르 G5-1블록 입주자모집공고 … 주택유형 해당지역 기타지역 규제지역 여…",
        "pass",
        0.92,
        0.99,
        0.01,
    ),
    (
        2,
        3,
        "notice:3",
        "송도 한내들 센트럴리버 입주자모집공고 … 주택유형 해당지역 기타지역 규제지역여부 / 민…",
        "pass",
        0.94,
        0.99,
        0.01,
    ),
    (
        3,
        3,
        "notice:3:임의",
        "민영 비규제지역 최초 당첨자 발표일(2025.12.23.)로부터 6개월 없음 미적용 …… (한내들 임의공급 공고)",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        4,
        1,
        "notice:1:무순위",
        "더샵 송도그란테르 G5-1블록 민영주택 무순위 입주자모집공고 … 주택유형 규제지역 여부…",
        "pass",
        0.97,
        0.98,
        0.01,
    ),
    (
        5,
        1,
        "news:1",
        "인천에서 처음으로 평당 3000만원 시대를 연 '더샵 송도그란테르'가 100% 계약 달… (인천일보 2026-08-05)",
        "pass",
        0.94,
        0.99,
        0.01,
    ),
    (
        6,
        12,
        "notice:12",
        "더샵 송도마리나베이(조합원 자격상실세대 3회차) 무순위(사후) 입주자모집공고 … 민영 …",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        7,
        None,
        "news:worldmeridian",
        "인천 송도국제도시 핵심 입지에 자리한 '송도 월드메르디앙'이 마지막 잔여 8세대를 대상… (kairnews, 광고성)",
        "pass",
        0.97,
        0.99,
        0.01,
    ),
    (
        8,
        None,
        "news:homingroots",
        "[헤럴드] 인천글로벌시티(IGCD)는 송도국제도시 11공구 Rc1블록(연수구 송도동 5… (홈잉루츠 송도)",
        "pass",
        0.67,
        0.99,
        0.02,
    ),
    (
        9,
        None,
        "notice:lake4",
        "힐스테이트 레이크 송도 4차 (임의공급 4차) 입주자모집공고 … 주택유형 규제지역여부 …",
        "pass",
        0.96,
        0.99,
        0.02,
    ),
    (
        10,
        15,
        "news:15",
        "반도건설이 오는 10월 인천 계양신도시 AC3·AC4블록에 '계양신도시 카이브 유보라'를 … (한경 2026-08-27)",
        "pass",
        0.74,
        0.99,
        0.02,
    ),
    (
        11,
        None,
        "news:gyeyang_a4a7",
        "[아주경제 2023-05-25] LH는 인천계양 테크노밸리 공동주택용지(A4·A7블록)…",
        "pass",
        0.88,
        0.99,
        0.02,
    ),
    (
        12,
        None,
        "notice:gyeyang_gosi",
        "국토교통부고시 제2025-937호(2025-12-30) 인천계양 테크노밸리 공공주택지구…",
        "pass",
        0.82,
        0.98,
        0.02,
    ),
    (
        13,
        None,
        "notice:jakjeon",
        "주택유형 민영 / 규제지역여부 비규제지역 / 무순위(사후) 자격요건 … (인천 작전 한라비발디 무순위 공고)",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        14,
        None,
        "news:gyeyang_price",
        "[데일리안 2026-09-07] 2024년 입주한 힐스테이트자이계양 전용 84㎡는 8억…",
        "pass",
        0.61,
        0.98,
        0.02,
    ),
    (
        15,
        None,
        "phase1:gtxd",
        "[한국경제 2025-07-18] 18일 국토교통부에 따르면… 서부권 광역급행철도 사업이… (GTX-D 예타)",
        "skip",
        0.29,
        0.98,
        0.02,
    ),
    (
        16,
        None,
        "notice:ab22",
        "더샵 검단레이크파크(AB22BL) 입주자모집공고: 주택유형 민영 / 해당지역 인천광역시…",
        "pass",
        0.9,
        0.99,
        0.01,
    ),
    (
        17,
        6,
        "notice:6",
        "더샵 검단레이크파크(AB23BL) 무순위 입주자모집공고: AB23BL, AB22BL 중…",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        18,
        None,
        "notice:paragon",
        "검단호수공원역 파라곤(AA36BL) 입주자모집공고: 재당첨제한 10년 / 전매제한 3년…",
        "pass",
        0.93,
        0.99,
        0.02,
    ),
    (
        19,
        5,
        "notice:5",
        "검단 센트레빌 에듀시티(AB8BL) 입주자모집공고: 주택유형 민영 / 해당지역 인천광역…",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        20,
        2,
        "notice:2",
        "엘리프 검단 포레듀(AA32블록) 입주자모집공고: 재당첨제한 10년 / 전매제한 3년(…",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        21,
        None,
        "notice:jungheung",
        "검단호수공원역 중흥S-클래스(AA24블록) 입주자모집공고: 주택유형 민영 / 해당지역 …",
        "pass",
        0.97,
        0.99,
        0.02,
    ),
    (
        22,
        16,
        "news:16",
        "[파이낸셜뉴스 2026-09-16] 동부건설이 오는 10월 인천 검단구 오류동 '검단 … (그랑포레)",
        "pass",
        0.87,
        0.98,
        0.02,
    ),
    (
        23,
        None,
        "phase2:geomdan_trades",
        "[검단 실거래 — dapt.kr(국토부 실거래 재가공), 2026-01~06, 전용 8…",
        "pass",
        0.46,
        0.99,
        0.02,
    ),
    (
        24,
        None,
        "phase2:geomdan_catalyst",
        "[검단 호재·공급 — 2026-10-07 기준] 인천1호선 검단연장(계양~검단, 6.8…",
        "pass",
        0.92,
        0.99,
        0.02,
    ),
    (
        25,
        None,
        "phase2:songdo_benchmark",
        "[송도 벤치마크 — 청약홈 공급금액(최고가) → dapt.kr 2026-04~09 실거…",
        "pass",
        0.77,
        0.98,
        0.02,
    ),
    (
        26,
        None,
        "phase2:songdo_market",
        "[송도 비교 시세 — dapt.kr 2026-04~09 실거래] (a) 한내들 센트럴리…",
        "pass",
        0.86,
        0.99,
        0.01,
    ),
    (
        27,
        None,
        "phase2:songdo_catalyst",
        '[송도 호재 단계 — 근거 원문] GTX-B(송도~마석 82.8km): "신한은행은 공…',
        "pass",
        0.58,
        0.99,
        0.02,
    ),
    (
        28,
        None,
        "phase2:gtxd",
        "[Phase 2 목적: 호재 단계 평가] [한국경제 2025-07-18] 서부권 광역급행철도(GTX-D) 예타 통과…",
        "pass",
        0.94,
        0.98,
        0.02,
    ),
    (90, 9, "notice:9", "한강 푸르지오 리버프론트 공고·무순위 발췌", "pass", 0.98, None, None),
    (91, 7, "notice:7", "김포 칸타빌 에디션 공고·임의공급·홈페이지 발췌", "pass", 0.98, None, None),
    (92, 11, "notice:11", "고촌센트럴자이 임의공급 13차 발췌", "pass", 0.98, None, None),
    (93, 10, "notice:10", "풍무역 롯데캐슬 시그니처 공고·임의 3차 발췌", "pass", 0.98, None, None),
    (94, 8, "notice:8", "수자인 그라센트 2차 공고·임의 3차 발췌", "pass", 0.98, None, None),
    (95, 4, "notice:4", "오퍼스 한강 스위첸 공고·무순위 발췌", "pass", 0.98, None, None),
    (96, None, "phase2:gimpo_benchmark", "김포 벤치마크·비교시세 텍스트(Phase 2)", "pass", 0.98, None, None),
    (97, None, "phase2:gimpo_policy", "김포 호재·제도·공급 텍스트(Phase 2)", "pass", 0.98, None, None),
]
for seq, cid, tail, summary, verdict, rel, subst, inj in SCREENS:
    add(
        seq,
        "screen",
        f"screen:{tail}",
        {"text": summary},
        "ok",
        {"verdict": verdict, "injection": inj, "substance": subst, "relevance": rel},
        complex_id=cid,
    )

# ---------------------------------------------------------------- P2 extract
EXTRACTS: list[tuple[int, int | None, str, str, int, int, list[tuple[str, str | None]]]] = [
    # seq, complex_id, purpose 꼬리, 입력 요약, auto, review, [(review 필드, 채택 원문값)]
    (
        29,
        1,
        "notice:1",
        "더샵 송도그란테르 G5-1블록 입주자모집공고(2026-05-07) 핵심 수치 · 13필드",
        12,
        1,
        [("contract_start", "2026-06-13")],
    ),
    (39, 3, "notice:3", "송도 한내들 센트럴리버 입주자모집공고(2025-12-04) · 14필드", 10, 4, []),
    (
        40,
        3,
        "notice:3:임의",
        "송도 한내들 임의공급 공고(2026-05-06)·홈페이지 안내문 · 11필드",
        10,
        1,
        [("apply_date", "2026-05-08")],
    ),
    (
        41,
        1,
        "notice:1:무순위",
        "더샵 송도그란테르 무순위 1차(2026-07-30)·2차(2026-08-24) 공고 · 13필드",
        11,
        2,
        [],
    ),
    (
        42,
        None,
        "notice:ab22",
        "더샵 검단레이크파크 AB22BL 입주자모집공고(2026-06-12)·청약홈 상세 · 15필드",
        11,
        4,
        [],
    ),
    (
        43,
        6,
        "notice:6",
        "더샵 검단레이크파크 AB23BL 무순위 공고(2026-08-07)·청약홈 경쟁률 · 14필드",
        14,
        0,
        [],
    ),
    (
        44,
        2,
        "notice:2",
        "엘리프 검단 포레듀 본공고·임의공급 3차 공고(2026-08-14) · 16필드",
        15,
        1,
        [("eligibility", None)],
    ),
    (
        45,
        5,
        "notice:5",
        "검단 센트레빌 에듀시티 본공고(2025-09-19)·임의공급 공고(2026-04-15) · 15필드",
        13,
        2,
        [],
    ),
    (
        46,
        None,
        "notice:paragon_hoban3",
        "검단호수공원역 파라곤 공고(2026-03-27)·호반써밋Ⅲ 본청약 공고 · 13필드",
        9,
        4,
        [],
    ),
    (
        47,
        None,
        "news:15_16",
        "계양신도시 카이브 유보라 보도(2026-08~09)·검단 센트레빌 그랑포레 보도 · 14필드",
        14,
        0,
        [],
    ),
    (
        48,
        12,
        "notice:12",
        "더샵 송도마리나베이 무순위 공고(2026-09-10)·월드메르디앙 송도 보도 · 14필드",
        11,
        3,
        [],
    ),
    (
        60,
        None,
        "notice:jakjeon_lotte_park",
        "인천 작전 한라비발디 무순위 공고(2026-05-22)·계양 롯데캐슬 파크시티 1단지 임의공급 · 15필드",
        14,
        1,
        [],
    ),
    (
        61,
        None,
        "notice:jungheung_lake4",
        "검단호수공원역 중흥S-클래스 공고(2025-07-04)·힐스테이트 레이크 송도 4차 임의공급 등 · 16필드",
        11,
        5,
        [],
    ),
    (
        98,
        9,
        "notice:9",
        "리버프론트 14필드(분양가·발코니·계약금·전매·입주·잔여 등)",
        10,
        4,
        [("apply_date", None), ("winner_date", None), ("resale_period", None), ("down_payment_first", None)],
    ),
    (99, 7, "notice:7", "칸타빌 15필드", 14, 1, [("move_in", "2029년 12월 예정")]),
    (100, 11, "notice:11", "고촌센트럴자이 14필드", 13, 1, [("price_84a_won", "758,400,000")]),
    (101, 10, "notice:10", "롯데캐슬 12필드", 12, 0, []),
    (102, 8, "notice:8", "그라센트 2차 12필드", 11, 1, [("move_in", "2029년 1월 예정")]),
    (103, 4, "notice:4", "스위첸 13필드", 12, 1, [("move_in", "2028년 8월 예정")]),
]
for seq, cid, tail, summary, n_auto, n_review, review_fields in EXTRACTS:
    add(
        seq,
        "extract",
        f"extract:{tail}",
        {"document": summary, "field_count": n_auto + n_review},
        "ok",
        {
            "fields": [
                {"name": n, "value_text": v, "decision": "review", "confidence": None, "excerpt": None}
                for n, v in review_fields
            ],
            "counts": {"auto": n_auto, "review": n_review, "total": n_auto + n_review},
        },
        complex_id=cid,
        raw_extra={"note": "보고서는 review 필드 이름 일부만 기재 — fields에는 기재된 것만, 나머지는 counts"},
    )

UNRECEIVED: list[tuple[int, int | None, str, str]] = [
    (30, 3, "notice:3", "송도 한내들 센트럴리버 입주자모집공고(2025-12-04) · 15필드"),
    (31, 3, "notice:3:임의", "송도 한내들 임의공급 공고(2026-05-06)·공식 홈페이지 안내 · 13필드"),
    (32, 1, "notice:1:무순위", "더샵 송도그란테르 무순위 1·2차 공고 · 14필드"),
    (33, 12, "notice:12", "더샵 송도마리나베이 3회차 무순위 공고(2026-09-10) · 13필드"),
    (34, None, "notice:ab22", "더샵 검단레이크파크 AB22BL 입주자모집공고(2026-06-12) · 16필드"),
    (35, 6, "notice:6", "더샵 검단레이크파크 AB23BL 무순위 공고(2026-08-07)·청약홈 경쟁률 · 12필드"),
    (36, None, "notice:paragon", "검단호수공원역 파라곤(AA36BL) 공고·청약홈 상세 · 15필드"),
    (37, 5, "notice:5", "검단 센트레빌 에듀시티(AB8BL) 본공고(2025-09-19)·임의공급 공고 · 16필드"),
    (38, 2, "notice:2", "엘리프 검단 포레듀(AA32BL) 본공고·임의공급 3차 공고(2026-08-14) · 17필드"),
]
for seq, cid, tail, summary in UNRECEIVED:
    fields = int(summary.rsplit("· ", 1)[1].removesuffix("필드"))
    add(
        seq,
        "extract",
        f"extract:{tail}",
        {"document": summary, "field_count": fields},
        "error",
        {},
        complex_id=cid,
        raw_extra={"reason": "응답 미수신(사용자 턴 전환)"},
        error_text="no response: 사용자 턴 전환으로 응답 미수신 → 같은 목적의 새 입력으로 재호출",
    )

# ---------------------------------------------------------------- P3 audit
AUDITS: list[tuple[int, int | None, str, str, int, str, list[tuple[str, float | None, bool, str]]]] = [
    # seq, complex_id, purpose 꼬리, 대상, 건수, verdict(JEV), items[(field, p_wrong, flagged, note)]
    (
        49,
        1,
        "notice:1",
        "그란테르 G5-1 본공고",
        13,
        "escalate",
        [("contract_start", None, True, "incomplete → 계약 기간 06-13~16으로 기록")],
    ),
    (
        50,
        3,
        "notice:3",
        "한내들 본공고",
        15,
        "escalate",
        [("winner_date_jev", 0.9, True, "12.17(2순위일) 오선택 → 12.23으로 정정")],
    ),
    (
        51,
        3,
        "notice:3:임의",
        "한내들 임의공급",
        12,
        "escalate",
        [
            ("apply_date", 0.72, True, "머리글 없는 표 → 청약홈 상세로 확인"),
            ("eligibility", None, True, "절단 → 원문 보완"),
        ],
    ),
    (52, 1, "notice:1:무순위", "그란테르 무순위", 13, "pass", []),
    (53, None, "notice:ab22", "AB22 본공고", 15, "pass", []),
    (54, 6, "notice:6", "AB23 무순위", 14, "pass", []),
    (
        55,
        2,
        "notice:2",
        "엘리프",
        16,
        "escalate",
        [("eligibility", None, True, "'…세대주인 미성년자' 절단 incomplete → 원문 보완")],
    ),
    (56, 5, "notice:5", "센트레빌", 15, "pass", []),
    (
        57,
        None,
        "notice:paragon_hoban3",
        "파라곤·호반써밋Ⅲ",
        15,
        "escalate",
        [("hoban_price_84b_15f_jev", None, True, "건축비 328,524,948 오선택 → 565,900,000 정정")],
    ),
    (58, None, "news:15_16", "카이브 유보라·그랑포레 보도", 15, "pass", []),
    (59, 12, "notice:12", "마리나베이·월드메르디앙", 15, "pass", []),
    (63, None, "notice:adjacent", "한라비발디·롯데캐슬·중흥·레이크 4차 등", 24, "pass", []),
    (104, 9, "notice:9", "리버프론트 추출 레코드 vs 원문", 16, "pass", []),
    (105, 7, "notice:7", "칸타빌 추출 레코드 vs 원문", 18, "pass", []),
    (106, 11, "notice:11", "고촌센트럴자이 추출 레코드 vs 원문", 16, "pass", []),
    (107, 10, "notice:10", "롯데캐슬 추출 레코드 vs 원문", 14, "pass", []),
    (108, 8, "notice:8", "그라센트 2차 추출 레코드 vs 원문", 13, "pass", []),
    (
        109,
        4,
        "notice:4",
        "스위첸 추출 레코드 vs 원문",
        15,
        "pass",
        [("shortfall_total_350", 0.67, False, "공고 경쟁률표에서 산술한 값(최고 p_wrong)")],
    ),
]
for seq, cid, tail, target, n, verdict, items in AUDITS:
    flagged = sum(1 for _, _, f, _ in items if f)
    add(
        seq,
        "audit",
        f"audit:{tail}",
        {"records": target, "record_count": n},
        "review" if verdict == "escalate" else "ok",
        {
            "verdict": "flagged" if flagged else "pass",
            "items": [
                {"field": f, "p_wrong": p, "flagged": fl, "note": note}
                for f, p, fl, note in items
            ],
            "counts": {"records": n, "flagged": flagged},
        },
        complex_id=cid,
        raw_extra={
            "decision": verdict,
            "note": "p_wrong 미기재 항목은 null(계약 2026-10-09.2: 지어내지 않음) — note 참조",
        }
        if any(p is None for _, p, _, _ in items)
        else {"decision": verdict},
    )


# ---------------------------------------------------------------- P4 classify (배치 4회)
def classify_batch(seq: int, purpose: str, summary: str, items: list[tuple[str, int | None, str, float, str]],
                   classes: list[str], counts: dict[str, int]) -> None:  # fmt: skip
    n_auto = sum(1 for *_, d in items if d == "auto")
    add(
        seq,
        "classify",
        purpose,
        {"candidates": [name for name, *_ in items], "classes": classes, "input_summary": summary},
        "ok",
        {
            "label": "batch",
            "prob": round(n_auto / len(items), 4),
            "decision": "review" if n_auto < len(items) else "auto",
            "items": [
                {"candidate": name, "complex_id": cid, "label": label, "prob": prob, "decision": dec}
                for name, cid, label, prob, dec in items
            ],
            "counts": counts,
        },
        raw_extra={
            "note": "배치 호출 1회 — ClassifyResult 최상위 label='batch', prob=auto 비율. 후보별 값은 items(계약 변경 요청: 배치 분류 결과 모양)"
        },
    )


P = "private_sale_apt"
classify_batch(
    62,
    "classify:inclusion:incheon",
    "후보 단지 포함/제외(사업주체 명의·공급유형) · 38건",
    [
        ("더샵 송도그란테르", 1, P, 1.00, "auto"),
        ("송도 한내들 센트럴리버", 3, P, 1.00, "auto"),
        ("더샵 송도마리나베이", 12, P, 0.99, "auto"),
        ("송도 하늘채 아이비원", None, P, 0.99, "auto"),
        ("힐스테이트 레이크 송도 4차", None, P, 1.00, "auto"),
        ("계양신도시 카이브 유보라", 15, P, 0.99, "auto"),
        ("더샵 검단레이크파크 AB22·AB23", 6, P, 1.00, "auto"),
        ("엘리프 검단 포레듀", 2, P, 1.00, "auto"),
        ("검단 센트레빌 에듀시티", 5, P, 0.85, "auto"),
        ("제일풍경채 검단Ⅳ", None, P, 1.00, "auto"),
        ("호반써밋Ⅲ AB13", None, P, 1.00, "auto"),
        ("검단호수공원역 파라곤", None, P, 1.00, "auto"),
        ("검단호수공원역 중흥S-클래스", None, P, 1.00, "auto"),
        ("검단신도시 푸르지오 더 파크", None, P, 1.00, "auto"),
        ("인천 작전 한라비발디", None, P, 0.98, "auto"),
        ("계양 롯데캐슬 파크시티", None, P, 0.96, "auto"),
        ("검단 스타힐스 가현숲", None, P, 0.99, "auto"),
        ("래미안 송도역 센트리폴", None, P, 0.95, "auto"),
        ("연수 월드메르디앙 어반포레", None, P, 0.99, "auto"),
        ("월드메르디앙 송도", None, P, 0.75, "review"),
        ("검단 센트레빌 그랑포레", 16, P, 0.84, "review"),
        ("왕길역 아테라", None, P, 0.75, "review"),
        ("홈잉루츠 송도", None, "manual_review", 0.97, "auto"),
        ("송도 11공구 RC2BL", None, "manual_review", 1.00, "auto"),
        ("계양 A21 대방", None, "manual_review", 1.00, "auto"),
        ("계양 A15 신해·우미", None, "manual_review", 1.00, "auto"),
        ("계양 A5 호반", None, "manual_review", 1.00, "auto"),
        ("송도자이풍경채 그라노블", None, "manual_review", 0.83, "review"),
        ("계양 A7 한림", None, "manual_review", 0.74, "review"),
        ("계양 A4 금강", None, "manual_review", 0.75, "review"),
        ("힐스테이트 검단 웰카운티", None, "manual_review", 0.77, "review"),
        ("e편한세상 검단 웰카운티", None, "manual_review", 0.72, "review"),
        ("인천계양 A17 신혼희망타운", None, "public_sale", 1.00, "auto"),
        ("인천계양 A6 공공분양", None, "public_sale", 1.00, "auto"),
        ("iH 송도 11공구 Rc5BL", None, "public_sale", 0.96, "auto"),
        ("검암역 푸르지오 프라베뉴", None, "public_sale", 0.94, "auto"),
        ("계양 AC2-1 보편형 공공임대", None, "public_rental", 0.98, "auto"),
        ("더샵 송도그란테르 오피스텔 96실", None, "non_apartment", 1.00, "auto"),
    ],
    ["private_sale_apt", "public_sale", "public_rental", "private_rental", "non_apartment", "manual_review"],
    {
        "auto": 30,
        "review": 8,
        "private_sale_apt": 22,
        "manual_review": 10,
        "public_sale": 4,
        "non_apartment": 1,
        "public_rental": 1,
    },
)

classify_batch(
    64,
    "classify:catalyst:incheon",
    "호재 실현 단계(확정/계획/추진/언론보도만/manual_review) · 28건",
    [
        ("인천1호선 검단연장 개통 2025-06", None, "확정", 1.00, "auto"),
        ("검단구 신설 2026-07", None, "확정", 0.99, "auto"),
        ("셀트리온 3공장 가동", None, "확정", 0.99, "auto"),
        ("송도 워터프런트 1-2단계 2027 초 준공", None, "확정", 0.99, "auto"),
        ("계양신도시 조성·2026-12 첫 입주", None, "확정", 0.96, "auto"),
        ("롯데바이오 송도 1공장 2026-11 준공", None, "확정", 0.95, "auto"),
        ("검단~드림로 개통", None, "확정", 0.94, "auto"),
        ("GTX-D 1단계 예타 통과·기본계획 중", None, "계획", 0.93, "auto"),
        ("송도아라1초 2030-03 개교", None, "계획", 0.98, "auto"),
        ("GTX-D Y자·2호선 청라연장 5차 철도망 건의", None, "추진", 0.99, "auto"),
        ("인천2호선 고양연장 예타 중", None, "추진", 1.00, "auto"),
        ("6·8공구 랜드마크 타워 높이 조정 검토", None, "추진", 0.93, "auto"),
        ("인천1호선 송도 8공구 연장 예타 미통과", None, "추진", 0.85, "auto"),
        ("인천대입구역 복합개발", None, "언론", 1.00, "auto"),
        ("계양 S-BRT", None, "언론", 1.00, "auto"),
        ("검단 스타필드·대학병원", None, "언론", 1.00, "auto"),
        ("송도세브란스병원(지상부 미착공)", None, "미확정", 1.00, "auto"),
        ("GTX-B 개통 2030 vs 2031", None, "미확정", 0.55, "review"),
        ("삼성바이오 제3캠퍼스", None, "확정", 0.83, "review"),
        ("송도트램", None, "계획", 0.84, "review"),
        ("11-1공구 기반시설", None, "추진", 0.46, "review"),
        ("IBD 업무용지", None, "확정", 0.76, "review"),
        ("대장홍대선", None, "확정", 0.52, "review"),
        ("계양AX파크", None, "추진", 0.68, "review"),
        ("서울5호선 김포·검단 연장", None, "계획", 0.56, "review"),
        ("검단 법조타운", None, "미확정", 0.58, "review"),
        ("iH 특화구역", None, "미확정", 0.37, "review"),
        ("검단지구 5단계 준공", None, "미확정", 0.59, "review"),
    ],
    ["확정", "계획", "추진", "언론", "미확정"],
    {
        "auto": 17,
        "review": 11,
        "confirmed": 12,
        "planned": 4,
        "promoting": 6,
        "media_only": 3,
        "manual_review": 3,
    },
)

classify_batch(
    110,
    "classify:inclusion:gimpo",
    "포함/제외 24건(사업주체 명의, 7클래스)",
    [
        ("한강 푸르지오 리버프론트", 9, P, 1.00, "auto"),
        ("호반써밋 풍무Ⅲ", None, P, 1.00, "auto"),
        ("풍무역세권 수자인 그라센트 2차", 8, P, 0.99, "auto"),
        ("김포 칸타빌 에디션", 7, P, 0.97, "auto"),
        ("한강 수자인 오브센트", None, P, 0.96, "auto"),
        ("고촌센트럴자이", 11, P, 0.95, "auto"),
        ("풍무역 롯데캐슬 시그니처", 10, P, 0.95, "auto"),
        ("호반써밋 풍무Ⅱ", None, P, 0.93, "auto"),
        ("수자인 그라센트 1차", None, P, 0.87, "auto"),
        ("풍무역세권 B5블록 호반써밋", None, P, 0.87, "auto"),
        ("해링턴플레이스 풍무 1~3BL", 13, P, 0.85, "auto"),
        ("풍무역 푸르지오 더 마크", None, P, 0.74, "review"),
        ("오퍼스 한강 스위첸", 4, P, 0.72, "review"),
        ("사우역 지엔하임", 14, P, 0.70, "review"),
        ("김포 북변 우미 린 파크리브", None, P, 0.69, "review"),
        ("김포한강Cc-03 구래역 예미지", None, P, 0.67, "review"),
        ("리버프론트 오피스텔 250실", None, "non_apartment", 1.00, "auto"),
        ("호반써밋Ⅱ 오피스텔 98실", None, "non_apartment", 0.98, "auto"),
        ("김포고촌2지구 A1 공공분양", None, "public_sale", 0.96, "auto"),
        ("전호 공공지원 민간임대", None, "private_rental", 1.00, "auto"),
        ("쌍용 더 플래티넘 한강(양평군)", None, "out_of_scope", 0.99, "auto"),
        ("북변5구역 재개발", None, "manual_review", 0.88, "auto"),
        ("한강2 콤팩트시티", None, "manual_review", 0.52, "review"),
        ("한강시네폴리스 추가 블록", None, "manual_review", 0.79, "review"),
    ],
    [
        "private_sale_apt",
        "public_sale",
        "public_rental",
        "private_rental",
        "non_apartment",
        "out_of_scope",
        "manual_review",
    ],
    {
        "auto": 17,
        "review": 7,
        "private_sale_apt": 16,
        "non_apartment": 2,
        "public_sale": 1,
        "private_rental": 1,
        "out_of_scope": 1,
        "manual_review": 3,
    },
)

classify_batch(
    111,
    "classify:catalyst:gimpo",
    "호재 단계 15건(확정/계획/추진/언론보도만/미확정)",
    [
        ("풍무역세권 도시개발 6,599세대 분양·공사 중", None, "확정", 1.00, "auto"),
        ("한강시네폴리스 산단·주거 3,461세대 분양·착공", None, "확정", 0.99, "auto"),
        ("수도권 제2순환 김포~파주 한강하저터널", None, "확정", 0.99, "auto"),
        ("김포골드라인 증차", None, "확정", 0.93, "auto"),
        ("GTX-D 서부권 광역급행철도 예타 통과", None, "계획", 0.97, "auto"),
        ("인천2호선 고양 연장 예타 진행 중", None, "추진", 0.98, "auto"),
        ("인하대병원 김포 부지제공 협약", None, "추진", 0.89, "auto"),
        ("김포한강선(가칭)", None, "언론", 0.99, "auto"),
        ("김포한강2 콤팩트시티", None, "미확정", 0.90, "auto"),
        ("김포 서울 편입", None, "미확정", 1.00, "auto"),
        ("김포 사이언스파크", None, "미확정", 0.94, "auto"),
        ("서울 5호선 김포·검단 연장", None, "계획", 0.52, "review"),
        ("걸포4·감정4지구", None, "계획", 0.51, "review"),
        ("계양~강화 고속도로", None, "확정", 0.80, "review"),
        ("북변5구역 재개발", None, "확정", 0.69, "review"),
    ],
    ["확정", "계획", "추진", "언론", "미확정"],
    {
        "auto": 11,
        "review": 4,
        "confirmed": 6,
        "planned": 3,
        "promoting": 2,
        "media_only": 1,
        "manual_review": 3,
    },
)

# ---------------------------------------------------------------- P5 compare
COMPARES: list[tuple[int, int | None, str, str, str, float, bool, list[tuple[str, str, float | None]]]] = [
    (
        72,
        1,
        "payment:1",
        "그란테르 계약금 조건(공고문 vs 위키트리) · aspects 3",
        "contradicts",
        1.00,
        True,
        [
            ("계약금 비율", "contradicts", None),
            ("1차 계약금", "same_fact", None),
            ("잔금 비율", "contradicts", None),
        ],
    ),
    (
        73,
        1,
        "move_in:1",
        "그란테르 입주 시기(청약홈 vs 기사) · aspects 2",
        "same_fact",
        0.68,
        False,
        [("입주 시작", "same_fact", 1.00), ("입주 종료", "different_facts", 0.44)],
    ),
    (
        74,
        6,
        "move_in:6",
        "더샵 검단레이크파크 입주(공고문 2029-12 vs 세계일보 2028-11) · aspects 1",
        "contradicts",
        1.00,
        True,
        [("입주 시기", "contradicts", 1.00)],
    ),
    (
        75,
        None,
        "benchmark:hoban1",
        "호반써밋 1차 84㎡ 분양가(데일리안 4.07 vs 헤럴드 4.5억) · aspects 1",
        "contradicts",
        0.90,
        True,
        [("84㎡ 분양가", "contradicts", 0.90)],
    ),
    (
        76,
        None,
        "schedule:gyeyang_a21",
        "계양 A21 분양 시기(한경 vs 리치고) · aspects 3",
        "contradicts",
        0.95,
        True,
        [("시기", "contradicts", None), ("세대수", "same_fact", None), ("사업자", "same_fact", None)],
    ),
    (
        77,
        None,
        "catalyst:gtxb",
        "GTX-B 개통 목표(국토부 2030 vs 사업자 2031) · aspects 2",
        "contradicts",
        0.99,
        True,
        [("연도", "contradicts", None), ("사업 단계", "different_facts", None)],
    ),
    (
        112,
        None,
        "catalyst:line5_stations",
        "5호선 정거장 수 쿠키뉴스 9 vs 헤럴드 10 (aspects 3)",
        "contradicts",
        0.99,
        True,
        [("정거장 수", "contradicts", 1.00), ("연장", "same_fact", None), ("총사업비", "same_fact", None)],
    ),
    (
        113,
        None,
        "competition:hoban3",
        "호반써밋Ⅲ 모집가구 한경 226 vs fnnews·청약홈 266 (2)",
        "contradicts",
        0.98,
        True,
        [("모집가구", "contradicts", None), ("접수건수", "same_fact", None)],
    ),
    (
        114,
        None,
        "catalyst:hangang2",
        "한강2 지구계획 신청 연도 2024-07 vs 2025-07 (3)",
        "contradicts",
        0.99,
        True,
        [("신청 시점", "contradicts", 1.00), ("지구지정", "same_fact", None), ("현 단계", "same_fact", None)],
    ),
    (
        115,
        9,
        "resale:9",
        "리버프론트 전매 뉴시스 2년 vs 공고문 3년 (2)",
        "contradicts",
        1.00,
        True,
        [("전매제한", "contradicts", 1.00), ("거주의무", "same_fact", None)],
    ),
    (
        116,
        11,
        "price:11",
        "고촌센트럴자이 84㎡ 분양가 사전보도 8억 중반 vs 7억 초중반·공고 75,840 (2)",
        "contradicts",
        0.93,
        True,
        [("84㎡ 분양가", "contradicts", 0.91), ("3.3㎡당 가격", "different_facts", 0.94)],
    ),
    (
        117,
        None,
        "competition:b5_hoban",
        "B5 호반써밋 최고 경쟁률 14 vs 24.6 (2)",
        "contradicts",
        0.96,
        True,
        [("최고 경쟁률", "contradicts", 0.98), ("총접수", "review", 0.46)],
    ),
]
for seq, cid, tail, summary, overall, prob, auto, aspects in COMPARES:
    add(
        seq,
        "compare",
        f"compare:{tail}",
        {"pair": summary},
        "ok" if auto else "review",
        {
            "overall": overall,
            "prob": prob,
            "aspects": [{"aspect": a, "relation": r, "prob": p} for a, r, p in aspects],
        },
        confidence=prob,
        complex_id=cid,
        raw_extra={"decision": "auto" if auto else "review"},
    )

# ---------------------------------------------------------------- P6 noul (move_in_plus_1y)
NOULS: list[tuple[int, int, str, str, str, tuple[float, float, float, float], set[str]]] = [
    # seq, complex_id, 단지, 현재 구매가(84㎡), 목표 연월(입주+1년), (p5, p10, p20, p_flat), unlikely(auto) 키
    (65, 3, "송도 한내들 센트럴리버", "8.13~8.99억", "2030-03", (0.39, 0.31, 0.16, 0.63), set()),
    (66, 1, "더샵 송도그란테르", "12.45~13.18억", "2030-08", (0.51, 0.39, 0.24, 0.49), set()),
    (67, 12, "더샵 송도마리나베이 84C 32층", "8.087억", "2027-10", (0.29, 0.21, 0.13, 0.69), {"p20"}),
    (68, 2, "엘리프 검단 포레듀 84A", "5.78~6.08억", "2029-03", (0.48, 0.45, 0.36, 0.48), set()),
    (69, 6, "더샵 검단레이크파크 AB23 84㎡", "6.51~6.68억", "2030-12", (0.39, 0.29, 0.20, 0.59), set()),
    (70, 5, "검단 센트레빌 에듀시티 84A", "6.07~6.22억", "2029-08", (0.35, 0.26, 0.16, 0.63), set()),
    (118, 7, "김포 칸타빌 에디션", "6.64~6.97억", "2030-12", (0.36, 0.29, 0.19, 0.64), set()),
    (119, 9, "한강 푸르지오 리버프론트", "6.54~7.83억", "2032-01", (0.35, 0.28, 0.18, 0.66), set()),
    (120, 11, "고촌센트럴자이", "7.584억(즉시 입주)", "2027-10", (0.17, 0.11, 0.06, 0.72), {"p10", "p20"}),
    (121, 10, "풍무역 롯데캐슬 시그니처", "7.97억", "2029-07", (0.25, 0.17, 0.11, 0.76), {"p20"}),
    (122, 8, "풍무역세권 수자인 그라센트 2차", "6.61~7.18억", "2030-01", (0.37, 0.27, 0.17, 0.65), set()),
    (123, 4, "오퍼스 한강 스위첸", "6.26~6.99억", "2029-08", (0.40, 0.33, 0.19, 0.63), set()),
]
PROP_TEXT = {
    "p5": "+5% 이상이다",
    "p10": "+10% 이상이다",
    "p20": "+20% 이상이다",
    "p_flat": "보합 또는 하락이다",
}
for seq, cid, name, price, target, probs, unlikely in NOULS:
    stem = f"{name} 입주 후 1년({target}) 실거래가가 현재 구매가({price}) 대비 "
    props = []
    for key, prob in zip(("p5", "p10", "p20", "p_flat"), probs, strict=True):
        is_unlikely = key in unlikely
        props.append({"key": key, "text": stem + PROP_TEXT[key], "prob": prob,
                      "verdict": "unlikely" if is_unlikely else "uncertain", "decision": "auto" if is_unlikely else "review"})  # fmt: skip
    add(
        seq,
        "noul",
        "noul:ladder:move_in_plus_1y",
        {
            "complex_id": cid,
            "horizon": "move_in_plus_1y",
            "target_ym": target,
            "propositions": [p["text"] for p in props],
            "context": "단지 증거 카드 + 생활권 벤치마크 + 제도",
        },
        "ok",
        {"horizon": "move_in_plus_1y", "target_ym": target, "propositions": props},
        complex_id=cid,
        raw_extra={
            "note": "보고서는 명제 '입주 후 1년'만 판정(asof_plus_3y·5y 미판정). target_ym은 입주월 + 12개월(즉시 입주는 기준일 + 12개월)"
        },
    )

# ---------------------------------------------------------------- P7 rerank
QUERY = "현재 구매가 대비 향후 3~5년 집값 상승 여력이 가장 큰 민간분양 단지"


def rerank(seq: int, purpose: str, items: list[tuple[int, float, int]], note: str) -> None:
    add(
        seq,
        "rerank",
        purpose,
        {"query": QUERY, "cards": [f"complex:{cid}" for cid, _, _ in items]},
        "ok",
        {
            "query": QUERY,
            "items": [
                {"candidate_id": f"complex:{cid}", "complex_id": cid, "relevance": rel, "rank": rank}
                for cid, rel, rank in items
            ],
        },
        raw_extra={"note": note},
    )


rerank(
    71,
    "rerank:region:incheon8",
    [
        (2, 0.91, 1),
        (3, 0.90, 2),
        (1, 0.89, 3),
        (5, 0.83, 4),
        (6, 0.77, 5),
        (16, 0.57, 6),
        (15, 0.56, 7),
        (12, 0.43, 8),
    ],
    "인천 8 증거 카드(§6-3)",
)
rerank(
    124,
    "rerank:region",
    [
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
    ],
    "인천 8 + 김포 8 = 16 카드(§12-4-2). 순위는 보고서 표기(동률 공동 순위)",
)

# ---------------------------------------------------------------- P8 decide
S_, C_, U_ = "supported", "contradicted", "unknown"
MARK = {"✓": S_, "✗": C_, "?": U_}


def checks(table: dict[str, str], order: tuple[str, str, str]) -> dict[str, dict[str, str]]:
    """table: option → '✓✗?' 3글자(보고서 요건 순서), order: 그 순서가 가리키는 (access/regulation/funds) 슬롯."""
    return {
        opt: {slot: MARK[ch] for slot, ch in zip(order, marks, strict=True)} for opt, marks in table.items()
    }


AR_F = ("access", "regulation", "funds")
AF_R = ("access", "funds", "regulation")
INCHEON_DECIDES = [
    (
        78,
        "decide:scenario_base:incheon8",
        "기본값(일반 무주택자, 실거주+시세차익 병행) TOP 5 중 1순위 · 후보 5 · 요건 3(접수 가능 / 보유기간 내 매도 / 자기자본 4억)",
        {"complex:2": 0.90, "complex:3": 0.07},
        "complex:2",
        0.89,
        AR_F,
        {"complex:1": "✗✓✗", "complex:2": "✓✓✓", "complex:3": "✓✓✓", "complex:5": "?✓✓", "complex:6": "?✗✓"},
    ),
    (
        84,
        "decide:scenario_A:incheon8",
        "상황 A 가점 높은 실수요 · 후보 6(TOP 5 + 모집공고 대기) · 요건 3",
        {"wait_new": 0.64, "investigate": 0.14, "complex:6": 0.08, "complex:2": 0.06},
        "wait_new",
        0.60,
        AR_F,
        {
            "complex:1": "✗✓✗",
            "complex:2": "✗✓✓",
            "complex:3": "✗✓✓",
            "complex:5": "?✓✓",
            "complex:6": "✗✓✓",
            "wait_new": "✓??",
        },
    ),
    (
        85,
        "decide:scenario_B:incheon8",
        "상황 B 가점 낮은 무주택 · 후보 6 · 요건 3",
        {"complex:2": 0.95, "complex:3": 0.01, "complex:5": 0.01},
        "complex:2",
        0.94,
        AF_R,
        {
            "complex:1": "✗✗✓",
            "complex:2": "✓✓✓",
            "complex:3": "✓✗✓",
            "complex:5": "?✓✓",
            "complex:6": "✓✓✗",
            "wait_new": "✗??",
        },
    ),
    (
        86,
        "decide:scenario_C:incheon8",
        "상황 C 시세차익 우선 · 후보 6 · 요건 3",
        {"complex:2": 0.98, "complex:3": 0.01},
        "complex:2",
        0.98,
        AR_F,
        {
            "complex:1": "✓✓✗",
            "complex:2": "✓✓✓",
            "complex:3": "✗✓✓",
            "complex:5": "✗✓✓",
            "complex:6": "✗✗✗",
            "wait_new": "???",
        },
    ),
    (
        87,
        "decide:scenario_D:incheon8",
        "상황 D 즉시 구매 · 후보 5 · 요건 3",
        {"complex:2": 0.88, "complex:3": 0.11},
        "complex:2",
        0.86,
        AF_R,
        {"complex:1": "✗✗✓", "complex:2": "✓✓✓", "complex:3": "✓✓✓", "complex:5": "✗✓✓", "complex:6": "✗✓✗"},
    ),
]
for seq, purpose, summary, d_probs, selected, conf, order, table in INCHEON_DECIDES:
    add(
        seq,
        "decide",
        purpose,
        {"situation": summary, "options": [*table, "ask_user", "investigate"]},
        "ok",
        {
            "selected": selected,
            "probs": d_probs,
            "checks": checks(table, order),
            "warnings": [],
            "escaped": False,
            "question": None,
        },
        confidence=conf,
        raw_extra={
            "requirement_order": list(order),
            "note": "probs는 보고서에 기재된 값만(나머지 후보 확률 미기재)",
        },
    )

# #125~129: contracts/fixtures/.../expected_scores.json decide_integrated(WP0-A 시드)와 같은 값 — build 스크립트가 시드에서 읽어 채운다.
INTEGRATED_DECIDES = {
    "base": (
        125,
        "decide:scenario_base",
        "기본값 재판정, 후보 6(그란테르·엘리프·한내들·스위첸·칸타빌·센트레빌), 요건 3",
    ),
    "A": (126, "decide:scenario_A", "상황 A 재판정, 후보 6(+wait_new)"),
    "B": (127, "decide:scenario_B", "상황 B 재판정, 후보 6"),
    "C": (128, "decide:scenario_C", "상황 C 재판정, 후보 6"),
    "D": (129, "decide:scenario_D", "상황 D 재판정, 후보 6(+고촌센트럴자이)"),
}

# ---------------------------------------------------------------- P9 verify
VERIFIES: list[tuple[int, str, str, int, int, dict[str, int], list[tuple[str, str, float | None, str]]]] = [
    # seq, section, 입력 요약, claims, evidence, 집계, [(verdict, action, confidence, 보고서가 적은 주장 내용)] — review·contradicted 만 개별
    (
        79,
        "7-1",
        "7-1 그란테르 claims 15 · evidence 9",
        15,
        9,
        {"verified": 15},
        [("verified", "review", None, "GTX-B 착공계 제출 2025-08(기사 '지난달' 표현)")],
    ),
    (80, "7-2", "7-2 엘리프 claims 15 · evidence 2", 15, 2, {"verified": 15}, []),
    (
        81,
        "7-3",
        "7-3 한내들 claims 15 · evidence 3",
        15,
        3,
        {"verified": 14, "unsupported": 1},
        [("unsupported", "review", None, "연수구 미분양 귀속")],
    ),
    (
        82,
        "7-4",
        "7-4 센트레빌 claims 13 · evidence 2",
        13,
        2,
        {"verified": 13},
        [("verified", "review", None, "2028 입주 열거(전수 아님)")],
    ),
    (
        83,
        "7-5",
        "7-5 더샵 검단 claims 13 · evidence 3",
        13,
        3,
        {"verified": 13},
        [("verified", "review", None, "재당첨제한(당첨 경로별)")],
    ),
    (
        88,
        "8-F1",
        "최종 F1 claims 16 · evidence 4(공고 발췌·접수 현황·JEV 기록)",
        16,
        4,
        {"verified": 16},
        [("verified", "review", 0.77, "상황 A 요약: 센트레빌 unknown 제외 4곳 contradicted")],
    ),
    (
        89,
        "8-F2",
        "최종 F2 claims 16 · evidence 3(공고·기사·1·6장 기록)",
        16,
        3,
        {"verified": 16},
        [
            ("verified", "review", 0.48, "그란테르 전매 도과일 2026-11-28(산술)"),
            ("verified", "review", 0.41, "전매 해제 '등기 시 해제'(AB23 포함 표기)"),
        ],
    ),
    (130, "12-1·12-2", "12-1·12-2 주장 16 vs 전수조사 표·JEV 출력", 16, 0, {"verified": 16}, []),
    (
        131,
        "12-3·12-4",
        "12-3·12-4 주장 16",
        16,
        0,
        {"verified": 15, "contradicted": 1},
        [
            (
                "contradicted",
                "review",
                0.35,
                "고촌센트럴자이 +10%·+20%와 롯데캐슬 +20%만 unlikely, 나머지 전부 uncertain",
            ),
            ("verified", "review", 0.66, "호재 classify 집계"),
            ("verified", "review", 0.49, "noul 수치 나열"),
        ],
    ),
    (
        132,
        "12-5",
        "12-5 주장 + 분할 재표현 주장 16",
        16,
        0,
        {"verified": 16},
        [("verified", "review", 0.61, "엘리프 전매 종료→매도 가능 해석")],
    ),
]
for seq, section, summary, n_claims, n_evidence, totals, flagged_claims in VERIFIES:
    claims: list[dict[str, Any]] = []
    known: dict[str, str] = {}
    for i, (v_verdict, v_action, v_conf, v_text) in enumerate(flagged_claims, start=1):
        claim_id = f"c{seq}-{i:02d}"
        claims.append({"claim_id": claim_id, "verdict": v_verdict, "confidence": v_conf, "action": v_action})
        known[claim_id] = v_text
    remaining = dict(totals)
    for c in claims:
        remaining[c["verdict"]] -= 1
    i = len(claims)
    for v_verdict, count in remaining.items():
        for _ in range(count):
            i += 1
            claims.append(
                {"claim_id": f"c{seq}-{i:02d}", "verdict": v_verdict, "confidence": None, "action": "auto"}
            )
    assert len(claims) == n_claims, seq
    status = (
        "review" if any(c["action"] == "review" or c["verdict"] == "contradicted" for c in claims) else "ok"
    )
    add(
        seq,
        "verify",
        f"verify:section_{section}",
        {
            "section": section,
            "claim_count": n_claims,
            "evidence_count": n_evidence,
            "input_summary": summary,
            "known_claims": known,
        },
        status,
        {"claims": claims},
        raw_extra={"note": "보고서가 문장을 적은 주장만 known_claims, 나머지는 집계로 생성한 id"},
    )
