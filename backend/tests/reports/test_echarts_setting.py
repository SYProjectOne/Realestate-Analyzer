"""ECharts 번들 찾기: 인자 → Settings.report_echarts_js → 저장소 frontend (계약 2026-10-09.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.settings import Settings, set_settings
from app.reports.render import ECHARTS_ENV, find_echarts_bundle


def test_settings_path_is_used(
    tmp_path: Path, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ECHARTS_ENV, raising=False)
    bundle = tmp_path / "echarts.min.js"
    bundle.write_text("/* echarts */", encoding="utf-8")
    set_settings(test_settings.model_copy(update={"report_echarts_js": bundle}))
    try:
        assert find_echarts_bundle() == bundle
        other = tmp_path / "explicit.js"
        other.write_text("/* x */", encoding="utf-8")
        assert find_echarts_bundle(other) == other  # 인자가 먼저
        missing = tmp_path / "none.js"
        set_settings(test_settings.model_copy(update={"report_echarts_js": missing}))
        assert find_echarts_bundle() != missing  # 없는 파일은 건너뛰고 다음 후보(저장소 번들 또는 None)
    finally:
        set_settings(test_settings)
