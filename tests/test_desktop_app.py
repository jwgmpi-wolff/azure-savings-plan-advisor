import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop_app import AdvisorWindow, analyze_csv_file, format_result
from api.csv_parser import MAX_CSV_BYTES


SAMPLE = Path(__file__).parents[1] / "samples" / "hourly-costs.csv"


def assumptions(mode="what-if"):
    common = {"mode": mode, "currencyCode": "USD", "expectedChangePercent": 0}
    if mode == "comparison":
        return {**common, "discountPercentP1Y": 15, "discountPercentP3Y": 25}
    return {**common, "term": "P1Y", "discountPercent": 20, "scenario": "balanced"}


@pytest.mark.parametrize("mode", ["what-if", "comparison"])
def test_desktop_uses_existing_calculator_and_exports_finite_json(mode):
    result = analyze_csv_file(SAMPLE, assumptions(mode))
    assert result["mode"] == mode
    assert result["dataHours"] > 0
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    text = format_result(result)
    assert "OFFLINE PLANNING ESTIMATE" in text
    assert "Net savings:" in text
    assert "Assumption:" in text
    if mode == "comparison":
        assert len(result["options"]) == 3
        assert "No Commitment" in text


@pytest.mark.parametrize("field", ["expectedChangePercent", "currencyCode", "discountPercent", "scenario"])
def test_desktop_requires_explicit_assumptions(field):
    request = assumptions()
    del request[field]
    with pytest.raises(ValueError, match=field):
        analyze_csv_file(SAMPLE, request)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -101])
def test_desktop_rejects_invalid_usage_change(invalid):
    with pytest.raises(ValueError):
        analyze_csv_file(SAMPLE, {**assumptions(), "expectedChangePercent": invalid})


def test_desktop_rejects_oversize_csv_before_decoding(tmp_path):
    path = tmp_path / "large.csv"
    path.write_bytes(b"x" * (MAX_CSV_BYTES + 1))
    with pytest.raises(ValueError, match="2 MB"):
        analyze_csv_file(path, assumptions())


def test_desktop_handles_bom_and_invalid_encoding(tmp_path):
    path = tmp_path / "costs.csv"
    path.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert analyze_csv_file(path, assumptions())["dataHours"] > 0
    path.write_bytes(b"\xff\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        analyze_csv_file(path, assumptions())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
def test_desktop_window_analysis_and_export(tmp_path):
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        for key, value in {**assumptions(), "csvFile": str(SAMPLE)}.items():
            window.values[key].set(value)
        window.analyze()
        assert window.result is not None
        assert "Net savings:" in window.output.get("1.0", "end")
        destination = tmp_path / "result.json"
        with patch("desktop_app.filedialog.asksaveasfilename", return_value=str(destination)):
            window.save()
        assert json.loads(destination.read_text()) == window.result
        window.values["expectedChangePercent"].set("")
        with patch("desktop_app.messagebox.showerror") as error:
            window.analyze()
        error.assert_called_once()
        assert window.result is None
        assert str(window.save_button["state"]) == "disabled"
        assert "Analysis failed" in window.output.get("1.0", "end")
    finally:
        root.destroy()
