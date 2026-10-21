import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop_app import AdvisorWindow, analyze_csv_file, format_result
from api.csv_parser import MAX_CSV_BYTES
from api.azure_provider import ConnectedProviderError


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


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
def test_connected_window_defaults_to_azure_without_csv_and_clears_on_tenant_change():
    import tkinter as tk

    tenant = "00000000-0000-0000-0000-000000000001"
    other = "00000000-0000-0000-0000-000000000002"
    subscription = "00000000-0000-0000-0000-000000000003"
    result = {
        "mode": "connected", "collectedAt": "2026-01-01T00:00:00Z",
        "completeness": "complete", "filters": {"term": "P1Y", "lookbackPeriod": "Last30Days"},
        "coverage": {"advisor": {"status": "empty"}, "savingsPlan": {"status": "ok"}},
        "notice": "Synthetic Azure fixture", "advisorRecommendations": [],
        "recommendations": [{
            "currencyCode": "USD", "term": "P1Y",
            "recommendationDetails": {"commitmentAmount": 4.25},
        }],
    }
    root = tk.Tk()
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        assert window.values["mode"].get() == "connected"
        assert window.values["csvFile"].get() == ""
        window.context_loaded({
            "tenantId": tenant, "tenants": [tenant, other],
            "subscriptions": [{"subscriptionId": subscription, "name": "Synthetic subscription"}],
        })
        window.values["subscription"].set(next(iter(window.subscription_ids)))
        with patch.object(window.azure, "analyze", return_value=result) as analyze:
            window.analyze()
            deadline = time.monotonic() + 5
            while window.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            assert not window.busy
        analyze.assert_called_once_with(tenant, subscription, "P1Y", "Last30Days")
        assert "Hourly commitment: 4.25 USD" in window.output.get("1.0", "end")
        assert window.result == result
        window.values["tenantId"].set(other)
        assert window.result is None
        assert window.subscription_ids == {}
        assert window.values["subscription"].get() == ""
        assert str(window.save_button["state"]) == "disabled"
        assert "4.25" not in window.output.get("1.0", "end")
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
def test_connected_error_reenables_controls_without_stale_export():
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        def fail():
            raise ConnectedProviderError("Access denied. Request read permission.", status="denied")
        with patch("desktop_app.messagebox.showerror") as error:
            window.run_task(fail, window.show_result, "Collecting...")
            deadline = time.monotonic() + 5
            while window.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
        error.assert_called_once()
        assert not window.busy
        assert window.result is None
        assert str(window.tenant_combo["state"]) == "normal"
        assert "Access denied" in window.output.get("1.0", "end")
    finally:
        root.destroy()
