"""보고서 차트 ECharts option (프론트 ``src/charts/Cxx/buildOption.ts`` 규칙을 Python으로 재현).

- 순수 함수: ReportData → ``ChartSpec{option, 표}``. option 은 JSON 직렬화 가능(함수 없음),
  애니메이션 끔(PDF 인쇄).
- 색은 의미만(확정 = strong, 미판정·미해결 = grayed), 계열 구분은 Okabe-Ito(프론트 ``palette.ts``와 같은 값).
- 차트 데이터는 같은 자리의 표로 열어 볼 수 있다(D7) — 셀은 Fact 그대로(라벨 유지).
- 점수는 WP4 결과(score_component·score_total)를 읽기만 한다(ADR-11): 기여 = w × s.
"""

from __future__ import annotations

from typing import Any, Final

from app.core.contracts_gen import Fact
from app.reports.data import COMPONENT_LABELS, ChartSpec, ReportData, ScenarioBlock
from app.reports.fmt import fact_label_text, fact_value_text, fmt_score, round_half_up

__all__ = ["build_charts"]

CATEGORICAL: Final = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#999999")
FG: Final = "rgb(17 24 39)"
MUTED: Final = "rgb(75 85 99)"
BORDER: Final = "rgb(209 213 219)"
STRONG: Final = "rgb(29 78 216)"
GRAYED: Final = "rgb(156 163 175)"
VIRTUAL: Final = "가상 후보"


def _base() -> dict[str, Any]:
    return {
        "backgroundColor": "transparent",
        "textStyle": {"color": FG, "fontFamily": "sans-serif"},
        "aria": {"enabled": True},
        "animation": False,
        "legend": {"top": 0, "textStyle": {"color": MUTED, "fontSize": 11}},
        "tooltip": {"trigger": "item"},
    }


def _axis() -> dict[str, Any]:
    return {
        "axisLine": {"lineStyle": {"color": BORDER}},
        "axisLabel": {"color": MUTED, "fontSize": 10},
        "splitLine": {"lineStyle": {"color": BORDER, "type": "dashed"}},
    }


def _num(f: Fact) -> float | None:
    return float(f.v) if isinstance(f.v, (int, float)) else None


def _prob_item(
    f: Fact, *, unresolved: bool = False, suffix: str | None = None, extra: str | None = None
) -> dict[str, Any]:
    """확률 막대 한 칸: 값은 소수 2자리 반올림(ROUND_HALF_UP),
    라벨 = '0.35 추정[ · 덧말][ · 가상 후보]'(표와 같은 문자열).

    option 은 JSON 이라 formatter 함수를 못 쓴다 — 칸마다 문자열 formatter 를 둔다. 미해결이면 '미해결'."""
    v = _num(f)
    value = None if v is None else float(round_half_up(v, 2))
    if unresolved:
        text = "미해결"
    elif value is None:
        text = fact_label_text(f)
    else:
        text = " · ".join(x for x in (f"{fact_value_text(f)} {f.label}", suffix, extra) if x)
    return {"value": value, "label": {"show": True, "formatter": text}}


def _scope_item(text: str) -> dict[str, Any]:
    """판정 대상이 아닌 단지의 칸: 길이 없음 + '판정 범위: …' 라벨(확률을 그리지 않는다, D9-1)."""
    return {"value": None, "label": {"show": True, "formatter": text, "fontSize": 9}}


def c06_score_breakdown(data: ReportData) -> ChartSpec | None:
    """C6 종합 점수 분해: 가중 기여 stacked bar(정렬 = 종합 점수), 부제 = 가중치, 미판정 = 회색."""
    rows = [s for s in data.scores if s.rank is not None]
    if not rows:
        return None
    keys = [k for k in COMPONENT_LABELS if k in data.weights]
    names = [
        f"{s.name}\n{fmt_score(s.total.v)}" if isinstance(s.total.v, (int, float)) else s.name for s in rows
    ]
    series = []
    for i, k in enumerate(keys):
        values: list[Any] = []
        for s in rows:
            comp = s.components.get(k)
            if comp is None or comp.contribution is None:
                # 미판정: 길이 0 + 라벨만(최대 기여 w×10 으로 스택을 부풀리지 않는다 — R3 minor 26)
                values.append(
                    {
                        "value": 0,
                        "itemStyle": {"color": GRAYED, "opacity": 0.5},
                        "label": {"show": True, "formatter": "미판정", "fontSize": 9},
                    }
                )
            else:
                values.append(round(comp.contribution, 4))
        series.append(
            {
                "type": "bar",
                "id": k,
                "name": COMPONENT_LABELS[k],
                "stack": "score",
                "barMaxWidth": 36,
                "itemStyle": {"color": CATEGORICAL[i % len(CATEGORICAL)]},
                "data": values,
            }
        )
    option = _base() | {
        "grid": {"left": 40, "right": 16, "top": 48, "bottom": 96},
        "xAxis": {
            "type": "category",
            "data": names,
            **_axis(),
            "axisLabel": {"color": MUTED, "fontSize": 9, "interval": 0, "width": 70, "overflow": "break"},
        },
        "yAxis": {"type": "value", "min": 0, **_axis()},
        "series": series,
    }
    subtitle = "가중치 " + " · ".join(f"{COMPONENT_LABELS[k]} {data.weights[k]:.2f}" for k in keys)
    cols = ["순위", "단지", "종합", *[COMPONENT_LABELS[k] for k in keys]]
    table = [
        [f"{s.rank}위", s.name, s.total, *[s.components[k].score if k in s.components else "—" for k in keys]]
        for s in rows
    ]
    return ChartSpec(
        id="c06",
        title="종합 점수 분해(C6)",
        subtitle=subtitle,
        option=option,
        columns=cols,
        rows=table,
        height=380,
    )


def c01_ladder(data: ReportData) -> ChartSpec | None:
    """C1 상승 확률 사다리(입주 후 1년): TOP 5 단지 막대 4개(+5/+10/+20/보합·하락), 임계선 0.15·0.85.

    '판정 대상'이 아닌 TOP 5 단지(참고·보류·미해결·제외)는 확률 없이 '판정 범위: <표시 문구>' 칸만(D9-1)."""
    top_ids = [s.complex_id for s in data.top5]
    ladders = [lad for cid in top_ids for lad in data.ladders if lad.complex_id == cid]
    out_ids = {c.id for c in data.ladder_scoped_out}
    scoped = [data.complex_by_id[cid] for cid in top_ids if cid in out_ids and cid in data.complex_by_id]
    if not ladders and not scoped:
        return None
    cats = ["+5%", "+10%", "+20%", "보합·하락"]
    series: list[dict[str, Any]] = []
    for i, lad in enumerate(ladders):
        unresolved = lad.status != "ok"
        vals = [
            _prob_item(lad.p5, unresolved=unresolved),
            _prob_item(lad.p10, unresolved=unresolved, suffix=lad.verdict_p10),
            _prob_item(lad.p20, unresolved=unresolved),
            _prob_item(lad.p_flat, unresolved=unresolved),
        ]
        series.append(
            {
                "type": "bar",
                "name": lad.name + (" (미해결)" if unresolved else ""),
                "itemStyle": {"color": GRAYED if unresolved else CATEGORICAL[i % len(CATEGORICAL)]},
                "label": {"show": True, "position": "right", "fontSize": 9},
                "data": vals,
                **(
                    {
                        "markLine": {
                            "silent": True,
                            "symbol": "none",
                            "lineStyle": {"color": STRONG, "type": "dashed"},
                            "label": {"formatter": "{b}", "fontSize": 9},
                            "data": [
                                {"xAxis": 0.15, "name": "unlikely 0.15"},
                                {"xAxis": 0.85, "name": "likely 0.85"},
                            ],
                        }
                    }
                    if i == 0
                    else {}
                ),
            }
        )
    for cx in scoped:
        label = f"판정 범위: {cx.judge_scope_text}"
        series.append(
            {
                "type": "bar",
                "name": f"{cx.name} ({label})",
                "itemStyle": {"color": GRAYED},
                "label": {"show": True, "position": "right", "fontSize": 9},
                "data": [_scope_item(label) for _ in cats],
            }
        )
    option = _base() | {
        "grid": {"left": 80, "right": 40, "top": 56, "bottom": 24},
        "xAxis": {"type": "value", "min": 0, "max": 1, **_axis()},
        "yAxis": {"type": "category", "data": cats, "inverse": True, **_axis()},
        "series": series,
    }
    cols = ["단지", "목표 시점", "+5%", "+10%", "+20%", "보합·하락", "판정"]
    table: list[list[Any]] = [
        [lad.name, lad.target_ym, lad.p5, lad.p10, lad.p20, lad.p_flat, lad.status] for lad in ladders
    ]
    table += [[cx.name, "—", cx.scope_note, "—", "—", "—", "사다리 미실행"] for cx in scoped]
    return ChartSpec(
        id="c01",
        title="상승 확률 사다리(C1) — 입주 후 1년",
        subtitle="명제 시점 = 입주월 + 12개월",
        option=option,
        columns=cols,
        rows=table,
        height=420,
    )


def c07_decision(data: ReportData, block: ScenarioBlock | None = None) -> ChartSpec | None:
    """C7 판정기 확률(시나리오 decide): 선택지별 확률 막대, confidence < 0.6 이면 동률 표시.

    ``block`` 생략 = 보고서 시나리오(id ``c07``), 그 밖 시나리오는 id ``c07_<코드>``.
    가상 후보 '모집공고 대기'(wait_new, 계약 .5)는 단지 후보처럼 선택·확률을 보이고
    '가상 후보' 표시를 단다(프론트 C07 과 같음)."""
    main = block is None
    if block is None:
        block = next((b for b in data.scenarios if b.code == data.scenario_code), None)
    if block is None or not block.decisions:
        return None
    items = [d for d in block.decisions if _num(d.prob) is not None]
    if not items:
        return None
    option = _base() | {
        "grid": {"left": 140, "right": 48, "top": 24, "bottom": 24},
        "xAxis": {"type": "value", "min": 0, "max": 1, **_axis()},
        "yAxis": {"type": "category", "inverse": True, "data": [d.option for d in items], **_axis()},
        "series": [
            {
                "type": "bar",
                "name": "decide 확률",
                "label": {"show": True, "position": "right", "fontSize": 9},
                "data": [
                    _prob_item(d.prob, suffix="동률" if d.tie else None, extra=VIRTUAL if d.virtual else None)
                    | {"itemStyle": {"color": STRONG if d.chosen else GRAYED}}
                    for d in items
                ],
            }
        ],
    }
    conf = fmt_score(block.confidence.v) if isinstance(block.confidence.v, (int, float)) else "미제공"
    sub = f"confidence {conf}" + (" · 동률(confidence < 0.6 → 상위 2개 함께 선택)" if block.tie else "")
    cols = ["선택지", "확률", "선택", "동률", "구분"]
    table: list[list[Any]] = [
        [d.option, d.prob, "선택" if d.chosen else "", "동률" if d.tie else "", VIRTUAL if d.virtual else ""]
        for d in items
    ]
    return ChartSpec(
        id="c07" if main else f"c07_{block.code}",
        title=f"판정기 확률(C7) — {block.name}",
        subtitle=sub,
        option=option,
        columns=cols,
        rows=table,
        height=320,
    )


def c07_by_scenario(data: ReportData) -> list[ChartSpec]:
    """보고서 시나리오 밖 상황별 C7(§8-2 상황마다 하나)."""
    out = [c07_decision(data, b) for b in data.scenarios if b.code != data.scenario_code]
    return [c for c in out if c is not None]


def c04_supply(data: ReportData) -> ChartSpec | None:
    """C4 입주 물량: 연도별 막대, 생활권 스택, '추정 집계'는 라벨 표 그대로."""
    if not data.supply:
        return None
    years = sorted({s.year for s in data.supply})
    las = list(dict.fromkeys(s.living_area_name for s in data.supply))
    series = []
    for i, la in enumerate(las):
        vals: list[float | None] = []
        for y in years:
            nums = [_num(s.units) for s in data.supply if s.year == y and s.living_area_name == la]
            known = [n for n in nums if n is not None]
            vals.append(sum(known) if known else None)
        series.append(
            {
                "type": "bar",
                "stack": "units",
                "name": la,
                "data": vals,
                "itemStyle": {"color": CATEGORICAL[i % len(CATEGORICAL)]},
            }
        )
    option = _base() | {
        "grid": {"left": 56, "right": 16, "top": 48, "bottom": 32},
        "xAxis": {"type": "category", "data": [str(y) for y in years], **_axis()},
        "yAxis": {"type": "value", "min": 0, **_axis()},
        "series": series,
    }
    cols = ["생활권", "연도", "세대"]
    table = [[s.living_area_name, str(s.year), s.units] for s in data.supply]
    return ChartSpec(
        id="c04",
        title="입주 물량(C4)",
        subtitle="세대 단위 · 라벨은 표 참조(추정 집계·비공식)",
        option=option,
        columns=cols,
        rows=table,
        height=320,
    )


def build_charts(data: ReportData) -> list[ChartSpec]:
    out = [c(data) for c in (c04_supply, c01_ladder, c06_score_breakdown, c07_decision)]
    return [c for c in out if c is not None] + c07_by_scenario(data)
