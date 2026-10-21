from __future__ import annotations

import json
import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from api.calculator import calculate_comparison, calculate_forecast
from api.compute_modeler import calculate_compute_model, copilot_prompt
from api.csv_parser import MAX_CSV_BYTES, parse_hourly_cost_csv
from api.models import ForecastRequest, validate_request
from api.azure_provider import ConnectedProviderError
from api.desktop_azure import DesktopAzure
from api.reporting import (
    NAVY, PALE, SavingsReport, build_report, clean_text, collection_summary, collection_warnings,
    export_result, redacted_result, write_report,
)
from report_view import ReportView, apply_theme


APP_TITLE = "Azure Savings Plan Advisor"


def analyze_csv_file(path: Path, assumptions: dict[str, Any]) -> dict[str, Any]:
    with path.open("rb") as source:
        content = source.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise ValueError("CSV data exceeds the 2 MB limit.")
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The CSV file must use UTF-8 encoding.") from exc
    costs = parse_hourly_cost_csv(csv_text)
    request = validate_request({**assumptions, "baselineHourlyCosts": costs})
    if request["mode"] == "comparison":
        return calculate_comparison(request)
    if request["mode"] != "what-if":
        raise ValueError("The desktop app supports offline planning modes only.")
    return calculate_forecast(ForecastRequest.from_dict(request))


def format_result(result: dict[str, Any]) -> str:
    if result["mode"] == "modeler":
        return "\n".join([
            "OFFLINE COMPUTE-HOURS PLANNING ESTIMATE - NOT AN AZURE PURCHASE RECOMMENDATION",
            f"Calculated at: {result['collectedAt']}",
            f"Period: {result['periodHours']:g} elapsed hours | Compute runtime: {result['computeHours']:g} hours",
            f"Outcome: {result['outcome']}",
            f"Projected full-term PAYG cost: {result['projectedTermBaselineCost']:,.2f} {result['currencyCode']}",
            f"Projected full-term modeled cost: {result['projectedTermModeledCost']:,.2f} {result['currencyCode']}",
            f"Projected full-term net savings: {result['projectedTermSavings']:,.2f} {result['currencyCode']}",
            "Full-term projection repeats the supplied duty cycle and rates; it is not a forecast.",
            "", "BREAK-EVEN GUIDANCE (calculation-based, not Copilot-generated)",
            *result["guidance"], "", "ASSUMPTIONS",
            *result["assumptions"],
        ])
    if result["mode"] == "connected":
        lines = [
            "LIVE AZURE RECOMMENDATIONS - REVIEW IN AZURE BEFORE PURCHASE",
            f"Collected at: {result['collectedAt']}",
            f"Coverage: {result['completeness']}",
            f"Term: {result['filters']['term']} | Lookback: {result['filters']['lookbackPeriod']}",
            f"Scope: {len(result.get('context', {}).get('subscriptionIds', [None]))} selected subscription(s), independent Single scopes. No CSV was used.",
            result["notice"],
            "",
        ]
        summary = collection_summary(result)
        if summary:
            lines.extend([summary, "See the Log tab for collection details."])
        lines.extend(["", "SAVINGS PLAN HOURLY COMMITMENTS (Azure Cost Management)"])
        if not result["recommendations"]:
            lines.append("No hourly commitment is available. Review source coverage above; no estimate was substituted.")
        for recommendation in result["recommendations"]:
            details = recommendation.get("recommendationDetails", {})
            currency = recommendation.get("currencyCode", "Currency not supplied by Azure")
            lines.extend([
                f"Reference: {recommendation.get('recommendationReference', 'Not supplied')}",
                f"  Subscription: {recommendation.get('subscriptionName', 'Not supplied')} ({recommendation.get('subscriptionId', 'Not supplied')})",
                f"  Term: {recommendation.get('term', 'Not supplied')}",
                f"  Hourly commitment: {details.get('commitmentAmount', 'Not supplied')} {currency}",
                f"  Granularity: {recommendation.get('commitmentGranularity', 'Savings Plan hourly commitment')}",
                f"  Azure estimated savings: {details.get('savingsAmount', 'Not supplied')} {currency}",
                f"  Azure savings percentage: {details.get('savingsPercentage', 'Not supplied')}%",
                f"  Coverage: {details.get('coveragePercentage', 'Not supplied')}%",
                f"  Utilization: {details.get('averageUtilizationPercentage', 'Not supplied')}%",
                f"  Observation hours: {recommendation.get('totalHours', 'Not supplied')}",
            ])
            for alternative in recommendation.get("alternatives", []):
                lines.append(
                    f"  Azure alternative hourly commitment: {alternative.get('commitmentAmount', 'Not supplied')} {currency}"
                    f" | Savings: {alternative.get('savingsPercentage', 'Not supplied')}%"
                )
        lines.extend(["", "AZURE ADVISOR COST RECOMMENDATIONS (not all are Savings Plans)"])
        for recommendation in result["advisorRecommendations"]:
            lines.extend([
                f"Reference: {recommendation['recommendationReference']} | Impact: {recommendation['impact']}",
                f"  Subscription: {recommendation.get('subscriptionName', 'Not supplied')} ({recommendation.get('subscriptionId', 'Not supplied')})",
                f"  Problem: {recommendation['problem']}",
                f"  Action: {recommendation['solution']}",
                f"  Azure last updated: {recommendation['lastUpdated']}",
            ])
        lines.extend(["", "CURRENT COMPUTE INVENTORY (not attributed Savings Plan coverage)"])
        for entry in result.get("computeInventory", []):
            lines.extend([
                f"Reference: {entry.get('recommendationReference', 'Not supplied')}",
                f"  Subscription: {entry.get('subscriptionName', 'Not supplied')}",
                f"  Resource: {entry.get('name', 'Not supplied')} | Type: {entry.get('computeType', 'Not supplied')}",
                f"  Compute SKU: {entry.get('computeSku') or 'Not supplied'}",
                f"  Reported license type: {entry.get('licenseType') or 'Not supplied'}",
            ])
        lines.append(
            "Inventory covers VMs, VM scale sets and App Service plans only; check source coverage for denied or unavailable data. "
            "Current configuration does not prove historical usage, benefit coverage, eligibility or per-SKU discounts."
        )
        return "\n".join(lines)
    currency = result["currencyCode"]
    lines = [
        "OFFLINE PLANNING ESTIMATE - NOT AN AZURE PURCHASE RECOMMENDATION",
        f"Currency: {currency} | Observed hours: {result['dataHours']}",
        "Amounts below cover the supplied observation period, not the full term.",
        "",
    ]
    options = result["options"] if result["mode"] == "comparison" else [result]
    for option in options:
        lines.extend([
            option.get("name", f"{option['term']} / {option.get('scenario', '')}"),
            f"  Modeled cost: {option['modeledCostObserved']:,.2f} {currency}",
            f"  Net savings: {option['netSavingsObserved']:,.2f} {currency}",
            f"  Savings: {option['savingsPercent']:,.2f}%",
            f"  Coverage: {option['coveragePercent']:,.2f}%",
            f"  Utilization: {option['utilizationPercent']:,.2f}%",
            f"  Unused commitment: {option['unusedCommitmentCostObserved']:,.2f} {currency}",
            f"  Risk: {option['risk']} | Confidence: {option['confidence']}",
        ])
        lines.extend(f"  Warning: {warning}" for warning in option["warnings"])
        lines.extend(f"  Assumption: {item}" for item in option["assumptions"])
        lines.append("")
    lines.extend(result.get("assumptions", []) if result["mode"] == "comparison" else [])
    return "\n".join(lines)


class AdvisorWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.result: dict[str, Any] | None = None
        self.report: SavingsReport | None = None
        self.azure = DesktopAzure()
        self.busy = False
        self.events: queue.Queue[tuple[Callable[[Any], None], Any, str | None]] = queue.Queue()
        self.subscription_ids: dict[str, str] = {}
        self.selected_subscription_ids: set[str] = set()
        self.visible_subscriptions: list[str] = []
        root.title(APP_TITLE)
        root.geometry("1280x960")
        root.minsize(850, 650)
        apply_theme(root)
        viewport = tk.Canvas(root, background=PALE, highlightthickness=0)
        page_scroll = ttk.Scrollbar(root, orient="vertical", command=viewport.yview)
        viewport.configure(yscrollcommand=page_scroll.set)
        page_scroll.pack(side="right", fill="y")
        viewport.pack(side="left", fill="both", expand=True)
        frame = ttk.Frame(viewport, padding=16, style="App.TFrame")
        page = viewport.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _event: viewport.configure(scrollregion=viewport.bbox("all")))
        viewport.bind("<Configure>", lambda event: viewport.itemconfigure(page, width=event.width))
        viewport.bind("<MouseWheel>", lambda event: viewport.yview_scroll(-int(event.delta / 120), "units"))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 22, "bold"), background=PALE).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text="Read Azure recommendations for existing workloads. CSV is optional, for offline modeling only.",
            background=PALE,
            wraplength=700,
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        self.values: dict[str, tk.StringVar] = {}
        self.values["mode"] = tk.StringVar(value="connected")
        mode = ttk.Combobox(
            frame, textvariable=self.values["mode"], state="readonly",
            values=("connected", "modeler", "what-if", "comparison"),
        )
        mode.grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)
        mode.bind("<<ComboboxSelected>>", self.change_mode)
        self.context_controls: list[ttk.Widget] = [mode]
        self.azure_frame = ttk.LabelFrame(frame, text="Authentication, tenant & subscription", padding=12)
        self.azure_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.azure_frame.columnconfigure(1, weight=1)
        azure_fields = [
            ("tenantId", "Tenant GUID (blank for initial sign-in)", None, ""),
            ("azureTerm", "Savings Plan term", ("P1Y", "P3Y"), "P1Y"),
            ("lookback", "Lookback period", ("Last7Days", "Last30Days", "Last60Days"), "Last30Days"),
        ]
        for row, (key, label, choices, default) in enumerate(azure_fields):
            self.values[key] = tk.StringVar(value=default)
            ttk.Label(self.azure_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10))
            widget = ttk.Combobox(
                self.azure_frame, textvariable=self.values[key],
                values=choices or (), state="normal" if key == "tenantId" else "readonly",
            )
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.context_controls.append(widget)
            if key == "tenantId":
                self.tenant_combo = widget
        picker = ttk.LabelFrame(self.azure_frame, text="Subscriptions - select one or more", padding=8)
        picker.grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
        picker.columnconfigure(0, weight=1)
        self.subscription_filter = tk.StringVar()
        search = ttk.Entry(picker, textvariable=self.subscription_filter)
        search.grid(row=0, column=0, sticky="ew")
        ttk.Label(picker, text="Filter by name or ID; use Ctrl/Shift to select multiple").grid(row=1, column=0, sticky="w")
        self.subscription_list = tk.Listbox(
            picker, selectmode="extended", exportselection=False, height=5,
            background="white", foreground=NAVY, selectbackground="#d8eeef", selectforeground=NAVY,
        )
        self.subscription_list.grid(row=2, column=0, sticky="ew")
        scroll = ttk.Scrollbar(picker, orient="vertical", command=self.subscription_list.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.subscription_list.configure(yscrollcommand=scroll.set)
        selection_actions = ttk.Frame(picker)
        selection_actions.grid(row=3, column=0, sticky="w")
        select_all = ttk.Button(selection_actions, text="Select all shown", command=self.select_subscriptions)
        select_all.pack(side="left", padx=(0, 8))
        clear = ttk.Button(selection_actions, text="Clear selections", command=self.clear_subscriptions)
        clear.pack(side="left")
        self.subscription_count = ttk.Label(selection_actions, text="0 selected")
        self.subscription_count.pack(side="left", padx=12)
        self.context_controls.extend([search, self.subscription_list, select_all, clear])
        self.subscription_filter.trace_add("write", self.filter_subscriptions)
        self.subscription_list.bind("<<ListboxSelect>>", self.subscription_selection_changed)
        self.values["tenantId"].trace_add("write", self.invalidate_context)
        for key in ("azureTerm", "lookback"):
            self.values[key].trace_add("write", self.invalidate_result)
        for column, (label, action) in enumerate([
            ("Sign in / switch tenant", self.sign_in),
            ("Refresh context", self.refresh_context),
            ("Disconnect app", self.disconnect),
        ]):
            button = ttk.Button(self.azure_frame, text=label, command=action)
            button.grid(row=4, column=column, pady=8, padx=3)
            self.context_controls.append(button)
        ttk.Label(
            self.azure_frame, wraplength=750,
            text="Tenant switching clears previous results. Select subscriptions after refresh. "
                 "Sign-in opens your browser; Azure CLI must be installed. Disconnect clears app context, not the CLI account cache.",
        ).grid(row=5, column=0, columnspan=3, sticky="w")
        self.offline_frame = ttk.LabelFrame(frame, text="Optional offline CSV modeling", padding=8)
        self.offline_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.offline_frame.columnconfigure(1, weight=1)
        fields = [
            ("csvFile", "Hourly costs CSV", None),
            ("currencyCode", "Currency code (e.g. USD)", None),
            ("expectedChangePercent", "Expected usage change (%)", None),
            ("term", "What-if term", ("P1Y", "P3Y")),
            ("discountPercent", "What-if discount (%)", None),
            ("scenario", "What-if scenario", ("conservative", "balanced", "maximumSavings", "custom")),
            ("hourlyCommitment", "Custom hourly commitment", None),
            ("discountPercentP1Y", "Comparison P1Y discount (%)", None),
            ("discountPercentP3Y", "Comparison P3Y discount (%)", None),
        ]
        for row, (key, label, choices) in enumerate(fields):
            variable = tk.StringVar()
            self.values[key] = variable
            ttk.Label(self.offline_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            if choices:
                widget = ttk.Combobox(self.offline_frame, textvariable=variable, values=choices, state="readonly")
            else:
                widget = ttk.Entry(self.offline_frame, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            variable.trace_add("write", self.invalidate_result)
        ttk.Button(self.offline_frame, text="Browse...", command=self.browse).grid(row=0, column=2, padx=(8, 0))
        self.offline_frame.grid_remove()
        self.modeler_frame = ttk.LabelFrame(frame, text="Compute-hours modeler (no CSV or sign-in required)", padding=12)
        self.modeler_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.modeler_frame.columnconfigure(1, weight=1)
        modeler_fields = [
            ("modelPeriodHours", "Elapsed period hours (e.g. 720 for 30 days)", None),
            ("modelComputeHours", "Compute running hours within this period (one workload)", None),
            ("modelPaygRate", "Eligible PAYG cost per running hour", None),
            ("modelDiscountPercent", "Assumed Savings Plan discount (%)", None),
            ("modelCommitment", "Hourly monetary commitment (paid even while idle)", None),
            ("modelCurrency", "Currency code (e.g. USD)", None),
            ("modelTerm", "Plan term (full obligation still applies)", ("P1Y", "P3Y")),
        ]
        for row, (key, label, choices) in enumerate(modeler_fields):
            variable = tk.StringVar()
            self.values[key] = variable
            ttk.Label(self.modeler_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            widget = (
                ttk.Combobox(self.modeler_frame, textvariable=variable, values=choices, state="readonly")
                if choices else ttk.Entry(self.modeler_frame, textvariable=variable)
            )
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            variable.trace_add("write", self.invalidate_result)
        ttk.Label(
            self.modeler_frame, wraplength=950,
            text="Enter your own rate, discount and commitment; no prices are invented. "
                 "Compute hours are runtime, not elapsed billing hours. One constant-rate workload only. "
                 "Use a period that represents its duty cycle. Results include idle-hour cost and uncovered PAYG. "
                 "Guidance is calculated locally; Copy for Copilot only copies a prompt and does not send data.",
        ).grid(row=len(modeler_fields), column=0, columnspan=2, sticky="w", pady=8)
        self.modeler_frame.grid_remove()
        actions = ttk.LabelFrame(frame, text="Report scope & executive exports", padding=10)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        analyze_button = ttk.Button(actions, text="Run report", command=self.analyze)
        analyze_button.pack(side="left")
        self.context_controls.append(analyze_button)
        self.export_buttons: list[ttk.Button] = []
        for label, kind in (("Executive PDF", "pdf"), ("Executive PowerPoint", "pptx"), ("Export CSV", "csv")):
            button = ttk.Button(actions, text=label, command=lambda kind=kind: self.export_report(kind), state="disabled")
            button.pack(side="left", padx=4)
            self.export_buttons.append(button)
        self.save_button = ttk.Button(actions, text="JSON", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.copilot_button = ttk.Button(actions, text="Copy for Copilot", command=self.copy_for_copilot, state="disabled")
        self.copilot_button.pack(side="left", padx=4)
        results = ttk.LabelFrame(frame, text="Results", padding=8)
        results.grid(row=5, column=0, columnspan=3, sticky="nsew")
        self.tabs = ttk.Notebook(results)
        self.tabs.pack(fill="both", expand=True)
        self.dashboard = ReportView(self.tabs)
        detail_frame = ttk.Frame(self.tabs)
        self.output = ScrolledText(
            detail_frame, wrap="word", font=("Segoe UI", 10), state="disabled",
            background="white", foreground=NAVY, relief="flat", height=26,
        )
        self.output.pack(fill="both", expand=True)
        self.tabs.add(self.dashboard, text="Executive dashboard")
        self.tabs.add(detail_frame, text="Evidence & details")
        self.log_tab = ttk.Frame(self.tabs)
        ttk.Label(self.log_tab, text="Collection log - details are not included in report exports.").pack(
            anchor="w", padx=8, pady=8,
        )
        self.log_output = ScrolledText(
            self.log_tab, wrap="word", font=("Segoe UI", 10), state="disabled",
            background="white", foreground=NAVY, relief="flat", height=26,
        )
        self.log_output.pack(fill="both", expand=True)
        self.tabs.add(self.log_tab, text="Log")
        self.set_log("No collection log. Run a report for the current context.")
        self.tabs.select(detail_frame)
        self.set_output(
            "Azure-connected analysis is the default. No hourly-cost CSV is required.\n\n"
            "Select Sign in / switch tenant to open Entra sign-in.\n"
            "For tenant switching, select or enter your approved tenant GUID first.\n"
            "Use Refresh context if you already signed in with Azure CLI.\n"
            "Select one or more accessible subscriptions, term, and lookback, then Run report.\n\n"
            "The app reads Azure Advisor Cost recommendations and Azure Cost Management "
            "Savings Plan hourly commitment recommendations for existing usage.\n"
            "It never purchases a Savings Plan or changes Azure resources.\n\n"
            "For optional offline analysis, choose what-if or comparison and supply a CSV."
        )
        root.report_callback_exception = self.callback_error
        self.root.after(100, self.poll_events)

    def invalidate_result(self, *_args: Any) -> None:
        self.result = None
        self.report = None
        if hasattr(self, "save_button"):
            self.save_button.configure(state="disabled")
            self.copilot_button.configure(state="disabled")
            for button in self.export_buttons:
                button.configure(state="disabled")
            self.dashboard.clear()
            self.set_log("Report cleared. Run a report for the current context.")
            self.set_output("Inputs changed. Run analysis again for the selected context.")

    def invalidate_context(self, *_args: Any) -> None:
        self.azure.clear()
        self.subscription_ids = {}
        self.selected_subscription_ids.clear()
        self.filter_subscriptions()
        self.invalidate_result()

    def filter_subscriptions(self, *_args: Any) -> None:
        query = self.subscription_filter.get().strip().lower()
        self.visible_subscriptions = [
            label for label in self.subscription_ids if query in label.lower()
        ]
        self.subscription_list.delete(0, "end")
        for index, label in enumerate(self.visible_subscriptions):
            self.subscription_list.insert("end", label)
            if self.subscription_ids[label] in self.selected_subscription_ids:
                self.subscription_list.selection_set(index)
        self.subscription_count.configure(
            text=f"{len(self.selected_subscription_ids)} selected | {len(self.visible_subscriptions)} shown"
        )

    def subscription_selection_changed(self, _event: Any = None) -> None:
        if self.busy:
            return
        previous = set(self.selected_subscription_ids)
        visible_ids = {self.subscription_ids[label] for label in self.visible_subscriptions}
        selected = {
            self.subscription_ids[self.visible_subscriptions[index]]
            for index in self.subscription_list.curselection()
        }
        self.selected_subscription_ids.difference_update(visible_ids)
        self.selected_subscription_ids.update(selected)
        self.subscription_count.configure(
            text=f"{len(self.selected_subscription_ids)} selected | {len(self.visible_subscriptions)} shown"
        )
        if previous != self.selected_subscription_ids:
            self.invalidate_result()

    def select_subscriptions(self) -> None:
        self.subscription_list.selection_set(0, "end")
        self.subscription_selection_changed()

    def clear_subscriptions(self) -> None:
        self.selected_subscription_ids.clear()
        self.subscription_list.selection_clear(0, "end")
        self.filter_subscriptions()
        self.invalidate_result()

    def change_mode(self, _event: Any = None) -> None:
        self.invalidate_result()
        self.azure_frame.grid_remove()
        self.offline_frame.grid_remove()
        self.modeler_frame.grid_remove()
        if self.values["mode"].get() == "connected":
            self.azure_frame.grid()
        elif self.values["mode"].get() == "modeler":
            self.modeler_frame.grid()
        else:
            self.offline_frame.grid()

    def disconnect(self) -> None:
        self.values["tenantId"].set("")
        self.tenant_combo.configure(values=())
        self.set_output("Disconnected app context. CLI sign-in cache is unchanged; use az logout to clear it separately.")

    def run_task(self, work: Callable[[], Any], done: Callable[[Any], None], message: str) -> None:
        if self.busy:
            return
        self.invalidate_result()
        self.busy = True
        self.control_states = [str(control.cget("state")) for control in self.context_controls]
        for control in self.context_controls:
            control.configure(state="disabled")
        self.set_log(message)
        self.set_output(message)

        def worker() -> None:
            try:
                value = work()
            except (ValueError, ConnectedProviderError) as exc:
                self.events.put((done, None, str(exc)))
            except Exception as exc:
                logging.error("Azure desktop operation failed", extra={"error_type": type(exc).__name__})
                self.events.put((done, None, "Unexpected Azure operation failure. No result is available. Retry sign-in and collection."))
            else:
                self.events.put((done, value, None))
        threading.Thread(target=worker, daemon=True).start()

    def poll_events(self) -> None:
        try:
            done, value, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for control, state in zip(self.context_controls, self.control_states):
                control.configure(state=state)
            if error:
                self.set_log(error)
                self.set_output(error)
                messagebox.showerror("Azure operation failed", error, parent=self.root)
            else:
                done(value)
        self.root.after(100, self.poll_events)

    def sign_in(self) -> None:
        tenant = self.values["tenantId"].get().strip()
        self.invalidate_context()

        def work() -> dict[str, Any]:
            signed_in_tenant = self.azure.sign_in(tenant)
            return self.azure.refresh(signed_in_tenant)
        self.run_task(work, self.context_loaded, "Complete Azure Entra sign-in in your browser. Waiting for sign-in...")

    def refresh_context(self) -> None:
        tenant = self.values["tenantId"].get().strip()
        self.invalidate_context()
        self.run_task(lambda: self.azure.refresh(tenant), self.context_loaded, "Discovering accessible Azure tenants and subscriptions...")

    def context_loaded(self, context: dict[str, Any]) -> None:
        self.values["tenantId"].set(context["tenantId"])
        self.tenant_combo.configure(values=context["tenants"])
        self.subscription_ids = {
            f"{item['name']} ({item['subscriptionId']})": item["subscriptionId"]
            for item in context["subscriptions"]
        }
        self.subscription_filter.set("")
        self.filter_subscriptions()
        self.set_output(
            f"Context refreshed: {len(self.subscription_ids)} enabled subscriptions available. "
            "Select one or more subscriptions explicitly, then Run report."
            if self.subscription_ids else
            "No enabled subscriptions are accessible in this tenant. Check account membership and RBAC."
        )

    def show_result(self, result: dict[str, Any]) -> None:
        result = redacted_result(result)
        report = build_report(result)
        warnings = collection_warnings(result) if result["mode"] == "connected" else ()
        if result["mode"] != "connected":
            log_notice = "Offline model; no Azure collection was performed."
        elif collection_summary(result):
            log_notice = "Detailed collection entries are unavailable for this incomplete report."
        else:
            log_notice = "No collection warnings for this report."
        self.set_log("\n".join([
            f"Collected: {report.collected_at}", f"Scope: {report.scope}", "",
            *(warnings or (log_notice,)),
        ]))
        self.set_output(format_result(result))
        self.dashboard.show(report)
        self.result = result
        self.report = report
        self.save_button.configure(state="normal")
        for button in self.export_buttons:
            button.configure(state="normal")
        self.copilot_button.configure(state="normal" if result["mode"] == "modeler" else "disabled")
        self.tabs.select(self.dashboard)

    def callback_error(self, exception_type: type[BaseException], exception: BaseException, traceback: Any) -> None:
        logging.error("Desktop callback failed", extra={"error_type": exception_type.__name__})
        self.invalidate_result()
        self.set_output("An unexpected application error occurred. No result is available.")
        messagebox.showerror(APP_TITLE, "An unexpected application error occurred. Restart the app and retry.", parent=self.root)

    def set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")
        if self.result is None:
            self.tabs.select(1)

    def set_log(self, text: str) -> None:
        self.log_output.configure(state="normal")
        self.log_output.delete("1.0", "end")
        self.log_output.insert("1.0", clean_text(text))
        self.log_output.configure(state="disabled")

    def browse(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Select hourly costs CSV", filetypes=[("CSV files", "*.csv")])
        if path:
            self.values["csvFile"].set(path)

    def analyze(self) -> None:
        if self.busy:
            return
        if self.values["mode"].get() == "modeler":
            self.invalidate_result()
            try:
                numeric_inputs: dict[str, float] = {}
                for field, key in (
                    ("period_hours", "modelPeriodHours"), ("compute_hours", "modelComputeHours"),
                    ("payg_rate", "modelPaygRate"), ("discount_percent", "modelDiscountPercent"),
                    ("hourly_commitment", "modelCommitment"),
                ):
                    try:
                        numeric_inputs[field] = float(self.values[key].get())
                    except ValueError as exc:
                        raise ValueError(f"Enter a numeric value for {field.replace('_', ' ')}.") from exc
                result = calculate_compute_model(
                    period_hours=numeric_inputs["period_hours"], compute_hours=numeric_inputs["compute_hours"],
                    payg_rate=numeric_inputs["payg_rate"], discount_percent=numeric_inputs["discount_percent"],
                    hourly_commitment=numeric_inputs["hourly_commitment"],
                    currency_code=self.values["modelCurrency"].get().strip().upper(),
                    term=self.values["modelTerm"].get(),
                )
            except ValueError as exc:
                self.set_output("Modeling failed. Check the period, compute hours and financial assumptions.")
                messagebox.showerror("Modeling failed", str(exc), parent=self.root)
                return
            self.show_result(result)
            return
        if self.values["mode"].get() == "connected":
            tenant = self.values["tenantId"].get().strip()
            subscriptions = sorted(self.selected_subscription_ids)
            if not subscriptions:
                self.invalidate_result()
                messagebox.showerror("Azure context required", "Refresh context and select one or more accessible subscriptions.", parent=self.root)
                return
            term = self.values["azureTerm"].get()
            lookback = self.values["lookback"].get()
            self.run_task(
                lambda: self.azure.analyze_many(tenant, subscriptions, term, lookback),
                self.show_result, "Reading Azure Advisor and Savings Plan recommendations...",
            )
            return
        self.invalidate_result()
        self.set_output("")
        try:
            mode = self.values["mode"].get()
            if mode not in ("what-if", "comparison"):
                raise ValueError("Select an analysis mode.")
            csv_file = self.values["csvFile"].get().strip()
            if not csv_file:
                raise ValueError("Select an hourly costs CSV file.")
            request: dict[str, Any] = {
                "mode": mode,
                "currencyCode": self.values["currencyCode"].get().strip().upper(),
            }
            numeric_fields = ["expectedChangePercent"]
            if mode == "comparison":
                numeric_fields.extend(["discountPercentP1Y", "discountPercentP3Y"])
            else:
                request["term"] = self.values["term"].get()
                request["scenario"] = self.values["scenario"].get()
                numeric_fields.append("discountPercent")
                if self.values["hourlyCommitment"].get().strip():
                    numeric_fields.append("hourlyCommitment")
            for field in numeric_fields:
                try:
                    request[field] = float(self.values[field].get())
                except ValueError as exc:
                    raise ValueError(f"Enter a numeric value for {field}.") from exc
            result = analyze_csv_file(Path(csv_file), request)
        except (OSError, ValueError) as exc:
            self.set_output("Analysis failed. Check the selected file and assumptions.")
            messagebox.showerror("Analysis failed", str(exc), parent=self.root)
            return
        self.show_result(result)

    def copy_for_copilot(self) -> None:
        if self.result is None or self.result["mode"] != "modeler" or self.busy:
            messagebox.showerror(APP_TITLE, "Run a compute-hours model for the current inputs first.", parent=self.root)
            return
        try:
            prompt = copilot_prompt(redacted_result(self.result))
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
        except (ValueError, tk.TclError) as exc:
            logging.error("Copilot prompt copy failed", extra={"error_type": type(exc).__name__})
            messagebox.showerror(APP_TITLE, "Unable to copy the model prompt. Retry or use the JSON export.", parent=self.root)
            return
        messagebox.showinfo(
            "Copilot prompt copied",
            "Paste into your approved Copilot service for an explanation. Nothing was sent automatically. "
            "The clipboard contains your financial assumptions and estimates; review them before sharing.",
            parent=self.root,
        )

    def export_report(self, kind: str) -> None:
        if self.report is None or self.result is None or self.busy:
            messagebox.showerror(APP_TITLE, "Run a report for the current context before exporting.", parent=self.root)
            return
        if kind not in ("pdf", "pptx", "csv"):
            raise ValueError("Unsupported export format.")
        path = filedialog.asksaveasfilename(
            parent=self.root, title=f"Export executive report ({kind.upper()})",
            defaultextension=f".{kind}", initialfile=f"SavingsPlanReport.{kind}",
            filetypes=[(f"{kind.upper()} report", f"*.{kind}")],
        )
        if not path:
            return
        try:
            write_report(self.report, Path(path), kind)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self.root)
        else:
            messagebox.showinfo("Export complete", f"{kind.upper()} report saved successfully.", parent=self.root)

    def save(self) -> None:
        if self.result is None:
            messagebox.showerror(APP_TITLE, "Run an analysis before exporting.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save planning estimate", defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            try:
                Path(path).write_text(json.dumps(export_result(self.result), indent=2, allow_nan=False), encoding="utf-8")
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export failed", str(exc), parent=self.root)


def main() -> None:
    root = tk.Tk()
    AdvisorWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
