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


@pytest.fixture(scope="module")
def tk_interpreter():
    if sys.platform != "win32":
        pytest.skip("Windows desktop interaction test")
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def tk_root(tk_interpreter):
    import tkinter as tk
    window = tk.Toplevel(tk_interpreter)
    window.withdraw()
    yield window
    for identifier in tk_interpreter.tk.call("after", "info"):
        window.after_cancel(identifier)
    if window.winfo_exists():
        window.destroy()


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

@pytest.mark.parametrize("mode", ["what-if", "comparison", "modeler", "connected"])
def test_row_details_click_keyboard_and_invalidation(tk_root, mode):
    from tkinter.scrolledtext import ScrolledText
    from api.reporting import build_report
    from api.compute_modeler import calculate_compute_model
    from report_view import ReportView

    if mode == "connected":
        result = {
            "mode": "connected", "collectedAt": "2026-01-01T00:00:00Z",
            "coverage": {"advisor": {"status": "denied"}}, "advisorRecommendations": [],
            "recommendations": [{
                "kind": "SavingsPlan", "armSkuName": "Synthetic_Plan_SKU",
                "recommendationReference": "synthetic-evidence", "currencyCode": "USD",
                "recommendationDetails": {"benefitCost": 17, "savingsPercentage": 12},
                "alternatives": [{"benefitCost": 9, "savingsPercentage": 8}],
            }],
            "computeInventory": [{
                "name": "synthetic-vm", "computeType": "Virtual machine", "computeSku": "Standard_D2s_v5",
                "source": "Azure Resource Manager", "recommendationReference": "synthetic-inventory",
            }],
        }
    elif mode == "modeler":
        result = calculate_compute_model(
            period_hours=100, compute_hours=90, payg_rate=10, discount_percent=20,
            hourly_commitment=8, currency_code="USD", term="P1Y",
        )
    else:
        result = analyze_csv_file(SAMPLE, assumptions(mode))
    view = ReportView(tk_root)
    view.pack(fill="both", expand=True)
    view.show(build_report(result))
    tk_root.geometry("1000x850")
    tk_root.deiconify()
    tk_root.update()
    assert view.table.bind("<ButtonRelease-1>")
    assert view.table.bind("<Return>")
    view.table.event_generate("<ButtonRelease-1>", x=20, y=5)
    assert view.details_window is None
    bounds = view.table.bbox("0")
    assert bounds
    x, y, _, height = bounds
    view.table.event_generate("<ButtonRelease-1>", x=x + 10, y=y + height // 2)
    popup = view.details_window
    assert popup is not None

    def popup_text():
        frame = view.details_window.winfo_children()[0]
        widget = next(
            widget for child in frame.winfo_children() for widget in child.winfo_children()
            if isinstance(widget, ScrolledText)
        )
        assert str(widget["state"]) == "disabled"
        return widget.get("1.0", "end")

    text = popup_text()
    assert "Compute type: Not supplied" in text
    assert "Compute SKU: Not supplied" in text
    assert "SOURCE COVERAGE" in text
    assert "per-SKU discount" in text
    if mode == "connected":
        assert "Synthetic_Plan_SKU" in text and "synthetic-evidence" in text
        assert "Benefit cost (report period): 17.00" in text
        assert "Assumed discount (%): Not supplied" in text
        assert "denied" in text
        assert "Standard_D2s_v5" in text and "not attributed benefit coverage" in text
    elif mode == "modeler":
        assert "Assumed discount (%): 20.00" in text
    elif mode == "what-if":
        assert "User-supplied modeled discount" in text
        assert "Assumed discount (%): 20.00" in text
    else:
        assert "No Commitment" in text
    view.table.focus("1" if mode == "connected" else view.table.get_children()[-1])
    view.table.focus_force()
    tk_root.update()
    view.table.event_generate("<Return>")
    assert not popup.winfo_exists()
    assert view.details_window is not None
    if mode == "modeler":
        assert "Assumed discount (%): 20.00" in popup_text()
    if mode == "connected":
        assert "Benefit cost (report period): 9.00" in popup_text()
        view.show_row_details("2")
        assert "Compute SKU: Standard_D2s_v5" in popup_text()
        assert "Compute type: Virtual machine" in popup_text()
        assert "Savings (%): Not supplied" in popup_text()
    view.details_window.focus_force()
    tk_root.update()
    view.details_window.event_generate("<Escape>")
    assert view.details_window is None
    view.show_row_details("0")
    popup = view.details_window
    view.clear()
    assert not popup.winfo_exists()
    assert view.details_window is None
    view.show_row_details("0")
    assert view.details_window is None


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
def test_desktop_window_analysis_and_export(tmp_path, tk_root):
    import tkinter as tk

    root = tk_root
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        for key, value in {**assumptions(), "csvFile": str(SAMPLE)}.items():
            window.values[key].set(value)
        window.analyze()
        assert window.result is not None
        assert window.report is not None
        assert len(window.dashboard.table.get_children()) == 1
        assert str(window.tabs.select()) == str(window.dashboard)
        assert all(str(button["state"]) == "normal" for button in window.export_buttons)
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
        assert all(str(button["state"]) == "disabled" for button in window.export_buttons)
        assert window.report is None
        assert not window.dashboard.table.get_children()
        assert "Analysis failed" in window.output.get("1.0", "end")
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
def test_connected_window_defaults_to_azure_without_csv_and_clears_on_tenant_change(tk_root):
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
    root = tk_root
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        assert window.values["mode"].get() == "connected"
        assert window.values["csvFile"].get() == ""
        window.context_loaded({
            "tenantId": tenant, "tenants": [tenant, other],
            "subscriptions": [{"subscriptionId": subscription, "name": "Synthetic subscription"}],
        })
        window.select_subscriptions()
        with patch.object(window.azure, "analyze_many", return_value=result) as analyze:
            window.analyze()
            deadline = time.monotonic() + 5
            while window.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            assert not window.busy
        analyze.assert_called_once_with(tenant, [subscription], "P1Y", "Last30Days")
        assert "Hourly commitment: 4.25 USD" in window.output.get("1.0", "end")
        assert window.result == result
        assert window.report.metrics[0][1] == "1"
        window.values["tenantId"].set(other)
        assert window.result is None
        assert window.subscription_ids == {}
        assert window.selected_subscription_ids == set()
        assert str(window.save_button["state"]) == "disabled"
        assert "4.25" not in window.output.get("1.0", "end")
        assert window.report is None
        assert not window.dashboard.table.get_children()
    finally:
        root.destroy()


def test_multiple_subscription_selection_filtering_and_invalidation(tk_root):
    tenant = "00000000-0000-0000-0000-000000000001"
    subscriptions = [
        {"subscriptionId": "00000000-0000-0000-0000-000000000002", "name": "Finance"},
        {"subscriptionId": "00000000-0000-0000-0000-000000000003", "name": "Engineering"},
    ]
    window = AdvisorWindow(tk_root)
    window.select_subscriptions()
    assert window.selected_subscription_ids == set()
    window.context_loaded({"tenantId": tenant, "tenants": [tenant], "subscriptions": subscriptions})
    assert window.selected_subscription_ids == set()
    window.select_subscriptions()
    assert window.selected_subscription_ids == {item["subscriptionId"] for item in subscriptions}
    window.subscription_filter.set("Finance")
    assert window.subscription_list.size() == 1
    assert len(window.selected_subscription_ids) == 2
    window.subscription_list.selection_clear(0, "end")
    window.subscription_selection_changed()
    assert window.selected_subscription_ids == {subscriptions[1]["subscriptionId"]}
    window.subscription_filter.set("")
    window.select_subscriptions()
    with patch.object(window, "run_task") as task, patch.object(window.azure, "analyze_many") as analyze:
        window.analyze()
        task.call_args.args[0]()
        analyze.assert_called_once_with(
            tenant, sorted(item["subscriptionId"] for item in subscriptions), "P1Y", "Last30Days",
        )
    connected = {
        "collectedAt": "2026-01-01T00:00:00Z", "notice": "Synthetic fixture",
        "filters": {"term": "P1Y", "lookbackPeriod": "Last30Days"},
        "mode": "connected", "context": {"tenantId": tenant, "subscriptionIds": [
            item["subscriptionId"] for item in subscriptions
        ]}, "completeness": "complete", "coverage": {}, "advisorRecommendations": [],
        "recommendations": [
            {**item, "term": "P1Y", "currencyCode": "USD", "subscriptionName": item["name"],
             "recommendationDetails": {"commitmentAmount": 4.25, "savingsPercentage": 20}}
            for item in subscriptions
        ],
    }
    window.show_result(connected)
    assert len(window.dashboard.table.get_children()) == 2
    first = window.dashboard.table.item("0", "values")
    assert subscriptions[0]["name"] in first and subscriptions[0]["subscriptionId"] in first
    assert "4.25" in first
    chart_text = " ".join(
        window.dashboard.chart.itemcget(item, "text")
        for item in window.dashboard.chart.find_all() if window.dashboard.chart.type(item) == "text"
    )
    assert "Savings percentage" in chart_text and "Hourly commitment" in chart_text
    assert "Finance" in chart_text and "Engineering" in chart_text
    window.show_result(analyze_csv_file(SAMPLE, assumptions()))
    window.clear_subscriptions()
    assert window.result is None
    assert window.selected_subscription_ids == set()
    assert all(str(button["state"]) == "disabled" for button in window.export_buttons)
    window.select_subscriptions()
    window.values["tenantId"].set("00000000-0000-0000-0000-000000000004")
    assert window.subscription_list.size() == 0
    assert window.selected_subscription_ids == set()
    tk_root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
@pytest.mark.parametrize("kind", ["pdf", "pptx", "csv"])
def test_dashboard_export_actions_write_requested_format(tmp_path, kind, tk_root):
    import tkinter as tk

    root = tk_root
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        window.show_result(analyze_csv_file(SAMPLE, assumptions("comparison")))
        path = tmp_path / f"report.{kind}"
        with patch("desktop_app.filedialog.asksaveasfilename", return_value=str(path)), \
             patch("desktop_app.messagebox.showinfo") as info:
            window.export_report(kind)
        info.assert_called_once()
        assert path.stat().st_size > 100
        window.values["tenantId"].set("context-changed")
        with patch("desktop_app.filedialog.asksaveasfilename") as save, \
             patch("desktop_app.messagebox.showerror") as error:
            window.export_report(kind)
        error.assert_called_once()
        save.assert_not_called()
    finally:
        root.destroy()


def test_compute_modeler_needs_no_csv_or_azure_and_copies_only_current_model(tk_root):
    window = AdvisorWindow(tk_root)
    window.values["mode"].set("modeler")
    window.change_mode()
    assert window.modeler_frame.winfo_manager() == "grid"
    assert window.offline_frame.winfo_manager() == ""
    assert window.azure_frame.winfo_manager() == ""
    inputs = {
        "modelPeriodHours": "100", "modelComputeHours": "90", "modelPaygRate": "10",
        "modelDiscountPercent": "20", "modelCommitment": "8", "modelCurrency": "USD", "modelTerm": "P1Y",
    }
    for key, value in inputs.items():
        window.values[key].set(value)
    with patch.object(window.azure, "analyze_many") as azure, patch("desktop_app.analyze_csv_file") as csv:
        window.analyze()
        azure.assert_not_called()
        csv.assert_not_called()
    assert window.result["savingsAmount"] == 100
    assert window.result["breakEvenHours"] == 80
    assert str(window.copilot_button["state"]) == "normal"
    assert len(window.dashboard.table.get_children()) == 6
    assert "80.00" in window.dashboard.table.item("0", "values")
    assert "calculation-based" in window.output.get("1.0", "end")
    text = " ".join(
        window.dashboard.chart.itemcget(item, "text")
        for item in window.dashboard.chart.find_all() if window.dashboard.chart.type(item) == "text"
    )
    assert "Net savings / loss" in text and "-800.00 USD" in text
    with patch.object(tk_root, "clipboard_clear") as clear, \
         patch.object(tk_root, "clipboard_append") as append, \
         patch("desktop_app.messagebox.showinfo") as info:
        window.copy_for_copilot()
        clear.assert_called_once()
        assert '"breakEvenHours": 80.0' in append.call_args.args[0]
        info.assert_called_once()
    window.values["modelComputeHours"].set("10")
    assert window.result is None
    assert str(window.copilot_button["state"]) == "disabled"
    with patch.object(tk_root, "clipboard_append") as append, patch("desktop_app.messagebox.showerror") as error:
        window.copy_for_copilot()
        append.assert_not_called()
        error.assert_called_once()
    window.analyze()
    assert window.result["outcome"] == "Loss"
    window.values["modelComputeHours"].set("101")
    with patch("desktop_app.messagebox.showerror") as error:
        window.analyze()
        error.assert_called_once()
    assert window.result is None
    assert all(str(button["state"]) == "disabled" for button in window.export_buttons)
    tk_root.destroy()


def test_compute_modeler_rejects_missing_prices_instead_of_inventing_savings(tk_root):
    window = AdvisorWindow(tk_root)
    window.values["mode"].set("modeler")
    window.change_mode()
    window.values["modelComputeHours"].set("720")
    with patch("desktop_app.messagebox.showerror") as error:
        window.analyze()
    assert "Enter a numeric value for period hours" in error.call_args.args[1]
    assert window.result is None
    tk_root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
def test_export_write_error_is_visible_not_success(tmp_path, tk_root):
    import tkinter as tk

    root = tk_root
    root.withdraw()
    try:
        window = AdvisorWindow(root)
        window.show_result(analyze_csv_file(SAMPLE, assumptions()))
        path = tmp_path / "nonexistent" / "report.csv"
        with patch("desktop_app.filedialog.asksaveasfilename", return_value=str(path)), \
             patch("desktop_app.messagebox.showinfo") as info, \
             patch("desktop_app.messagebox.showerror") as error:
            window.export_report("csv")
        error.assert_called_once()
        info.assert_not_called()
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop interaction test")
def test_connected_error_reenables_controls_without_stale_export(tk_root):
    import tkinter as tk

    root = tk_root
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
