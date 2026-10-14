"""Jinja2 → 단일 자립 HTML (DECISIONS D4). CSS·ECharts 번들·차트 option 을 모두 인라인 — 외부 URL 리소스 0.

ECharts 번들(`echarts.min.js`) 찾는 순서: 인자 → Settings ``report_echarts_js`` → 저장소
``frontend/node_modules/echarts/dist/echarts.min.js``. 없으면 차트 자리에 '차트 번들 없음' 문구와
같은 데이터의 표만 남긴다(보고서는 계속 생성, ``RenderResult.charts_inlined=False``).

R9-REPORT(D28-4): 첫 장 = 결론 요약 + 메타 상자(``cover.build_cover``), 용어 첫 등장 괄호 풀이(``cover.TermState``),
부록 C 용어 풀이(``glossary``)·부록 D 전체 표. 쪽수는 PDF 인쇄 때 채운다(``pdf.html_to_pdf`` — ``data-pages`` 칸).
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Final

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from app.core.contracts_gen import Fact
from app.core.time import kst_day
from app.reports.charts import build_charts
from app.reports.cover import TermState, build_cover, delta_mark, diff_mark, intake_counts_text, rank_move
from app.reports.data import COMPONENT_LABELS, ReportData
from app.reports.diff import SnapshotDiff
from app.reports.fmt import (
    MISSING_REASON,
    count_missing,
    fact_label_text,
    fact_value_text,
    fmt_score,
    unknown_fact,
)
from app.reports.glossary import CATEGORIES, GLOSSARY
from app.reports.sections import (
    APPENDIX_C_TITLE,
    APPENDIX_D_TITLE,
    DISCLAIMER,
    EXTRA_TITLE,
    SECTION_TITLES,
)

__all__ = ["RenderResult", "find_echarts_bundle", "render_html"]

HERE: Final = Path(__file__).resolve().parent
TEMPLATES: Final = HERE / "templates"
ECHARTS_ENV: Final = "REPORT_ECHARTS_JS"
_REPO: Final = HERE.parents[2]


@dataclass(frozen=True, slots=True)
class RenderResult:
    html: str
    charts: int
    charts_inlined: bool


def find_echarts_bundle(explicit: Path | None = None) -> Path | None:
    """인자 → Settings ``report_echarts_js``(환경변수 REPORT_ECHARTS_JS) → 저장소 frontend 번들."""
    from app.core.settings import get_settings

    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    configured = get_settings().report_echarts_js
    if configured is not None:
        candidates.append(configured)
    env = os.environ.get(ECHARTS_ENV)  # Settings 를 읽은 뒤 바뀐 환경(테스트·CLI)도 본다
    if env:
        candidates.append(Path(env))
    candidates.append(_REPO / "frontend" / "node_modules" / "echarts" / "dist" / "echarts.min.js")
    for c in candidates:
        if c.is_file():
            return c
    return None


@cache
def _read_bundle(path: Path, mtime: float) -> str:
    text = path.read_text(encoding="utf-8")
    return text.replace("</script", "<\\/script")


def _json_script(obj: Any) -> Markup:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return Markup(text.replace("</", "<\\/"))


def _as_fact(obj: Any, unit: str | None = None) -> Fact:
    """json 컬럼 안의 Fact 모양(region.living_areas[].households 등) → Fact. 아니면 '확인 불가(출처 누락)'."""
    if isinstance(obj, Fact):
        return obj
    if isinstance(obj, dict) and "label" in obj and "v" in obj:
        try:
            f = Fact.model_validate(
                {k: obj.get(k) for k in ("v", "label", "reason", "prov", "checked_at", "unit")}
            )
        except ValueError:
            return unknown_fact("형식 오류", unit=unit)
        return f if f.unit or unit is None else f.model_copy(update={"unit": unit})
    count_missing()
    return unknown_fact(MISSING_REASON, unit=unit)


def _extract_audit_rows(data: ReportData) -> list[dict[str, Any]]:
    """§4 extract/audit 결과: 단지별 screen·extract·audit 상태 집계."""
    agg: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    for c in data.calls:
        if c.tool in ("screen", "extract", "audit") and c.complex_name != "—":
            agg[c.complex_name][c.tool][c.status] += 1
    out = []
    for name in sorted(agg):
        row: dict[str, Any] = {"name": name}
        for tool in ("screen", "extract", "audit"):
            cnt = agg[name].get(tool, Counter())
            row[tool] = " · ".join(f"{k} {v}" for k, v in sorted(cnt.items())) or "호출 없음"
        out.append(row)
    return out


@cache
def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"], default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["fv"] = fact_value_text
    env.filters["fl"] = fact_label_text
    env.filters["as_fact"] = _as_fact
    env.filters["score"] = fmt_score
    env.filters["json_script"] = _json_script
    env.filters["kst_day"] = kst_day  # 시각 문자열 → KST 날짜(D14-6)
    env.filters["delta"] = delta_mark  # 부호 있는 값 옆 ▲▼ + 글자(R9-REPORT)
    env.filters["diff_mark"] = diff_mark
    env.filters["intake_counts"] = intake_counts_text
    env.globals.update(
        COMPONENT_LABELS=COMPONENT_LABELS,
        DISCLAIMER=DISCLAIMER,
        SECTION_TITLES=SECTION_TITLES,
        EXTRA_TITLE=EXTRA_TITLE,
        APPENDIX_C_TITLE=APPENDIX_C_TITLE,
        APPENDIX_D_TITLE=APPENDIX_D_TITLE,
        GLOSSARY=GLOSSARY,
        GLOSSARY_CATEGORIES=CATEGORIES,
        rank_move=rank_move,
    )
    return env


def render_html(
    data: ReportData,
    *,
    diff: SnapshotDiff | None = None,
    echarts_js: Path | None = None,
    revision: int | None = None,
    compare_revision: int | None = None,
) -> RenderResult:
    """``revision``·``compare_revision`` = 스냅샷 리비전 번호(첫 장 메타 상자, 없으면 '기록 없음')."""
    bundle_path = find_echarts_bundle(echarts_js)
    bundle = _read_bundle(bundle_path, bundle_path.stat().st_mtime) if bundle_path else ""
    data.charts = build_charts(data)
    css = (TEMPLATES / "report.css").read_text(encoding="utf-8")
    init_js = (TEMPLATES / "charts_init.js").read_text(encoding="utf-8")
    html = (
        _env()
        .get_template("report.html.j2")
        .render(
            data=data,
            diff=diff,
            css=Markup(css),
            echarts_js=Markup(bundle),
            init_js=Markup(init_js),
            has_echarts=bool(bundle),
            charts={c.id: c for c in data.charts},
            ea_rows=_extract_audit_rows(data),
            cover=build_cover(data, diff, revision=revision, compare_revision=compare_revision),
            term=TermState(),
        )
    )
    return RenderResult(html=html, charts=len(data.charts), charts_inlined=bool(bundle))
