"""OCR (DECISIONS D5, ADR-12) — 시료 형식, 선택 의존성 없을 때의 동작, 채택 엔진의 시료 숫자 100%.

채택 엔진 테스트는 rapidocr 가 설치된 환경에서만 돈다(선택 의존성 ``ocr``).
프로젝트 .venv 를 건드리지 않고 돌리기:
    uv run --with "rapidocr==3.10.0" --with onnxruntime pytest tests/collectors/notice_pdf/test_ocr.py
"""

# ruff: noqa: E501  (한국어 docstring)

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from app.collectors.notice_pdf import extract_pdf, ocr
from app.collectors.notice_pdf.collector import error_text_for

from .ocr_bench import SAMPLES, numbers, score

FIX = Path(__file__).parent / "fixtures"


def _manifest() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
    return data


def test_samples_have_images_truth_and_price_numbers() -> None:
    items = _manifest()
    assert len(items) >= 3
    for item in items:
        assert (SAMPLES / item["image"]).stat().st_size > 10_000
        truth = (SAMPLES / item["truth_text"]).read_text(encoding="utf-8")
        assert numbers(truth) == item["numbers"]  # 정답 숫자 = 텍스트 레이어에서 같은 규칙으로
        assert len(item["numbers"]) >= 20
        assert any("," in n for n in item["numbers"])  # 금액
    assert score(["1,000", "84A층"], ["1,000"])["token_recall"] == 0.5


def test_lines_from_boxes_groups_rows_left_to_right() -> None:
    def box(x: float, y: float) -> list[list[float]]:
        return [[x, y], [x + 50, y], [x + 50, y + 20], [x, y + 20]]

    items = [
        (box(200, 102), "384,300,000"),
        (box(10, 100), "59A"),
        (box(10, 140), "84A"),
        (box(100, 99), "20층"),
    ]
    assert ocr.lines_from_boxes(items) == "59A 20층 384,300,000\n84A"


def test_without_engine_no_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".")[0] in {"rapidocr", "onnxruntime"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(ocr.importlib, "import_module", lambda name: fake_import(name))
    assert ocr.load_ocr() is None
    ex = extract_pdf((FIX / "scan_2026940062_p1p3.pdf").read_bytes(), ocr=ocr.load_ocr())
    assert error_text_for(ex) == "scan"


def test_adopted_engine_samples_numbers_100pct() -> None:
    pytest.importorskip("rapidocr")
    pytest.importorskip("onnxruntime")
    for item in _manifest():
        text = ocr.ocr_image(str(SAMPLES / item["image"]))
        s = score(item["numbers"], numbers(text))
        assert s["exact"] == s["tokens"], (item["image"], s["missing"])


def test_d5_adopted_engine_page_under_30_seconds() -> None:
    """D5 기준 '페이지당 30초 이내(CPU)'(R3 3차 RA 부분 — 테스트 없음). 엔진이 없으면 건너뛴다. 모델 내려받기·첫 로드는
    시간에서 뺀다(엔진을 한 번 깨운 뒤 시료 쪽마다 잰다)."""
    import time

    pytest.importorskip("rapidocr")
    pytest.importorskip("onnxruntime")
    items = _manifest()
    ocr.ocr_image(str(SAMPLES / items[0]["image"]))  # 워밍업(모델 로드)
    for item in items:
        start = time.perf_counter()
        ocr.ocr_image(str(SAMPLES / item["image"]))
        took = time.perf_counter() - start
        assert took <= 30.0, f"{item['image']}: {took:.1f}s > 30s(D5)"


def test_adopted_engine_reads_scan_pdf() -> None:
    pytest.importorskip("rapidocr")
    pytest.importorskip("onnxruntime")
    fn = ocr.load_ocr()
    assert fn is not None
    ex = extract_pdf((FIX / "scan_2026940062_p1p3.pdf").read_bytes(), ocr=fn)
    assert ex.ocr_pages == [0, 1] and error_text_for(ex) == "ocr"
    text_layer = extract_pdf((FIX / "notice_2026940062.pdf").read_bytes()).pages[2]
    s = score(numbers(text_layer), numbers(ex.pages[1]))  # 3쪽 가격표 숫자 전부(2026-10-09 측정 60/60)
    assert s["exact"] == s["tokens"], s["missing"]
