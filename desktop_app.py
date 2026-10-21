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
from api.csv_parser import MAX_CSV_BYTES, parse_hourly_cost_csv
from api.models import ForecastRequest, validate_request
from api.azure_provider import ConnectedProviderError
from api.desktop_azure import DesktopAzure


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
    if result["mode"] == "connected":
        lines = [
            "LIVE AZURE RECOMMENDATIONS - REVIEW IN AZURE BEFORE PURCHASE",
            f"Collected at: {result['collectedAt']}",
            f"Coverage: {result['completeness']}",
            f"Term: {result['filters']['term']} | Lookback: {result['filters']['lookbackPeriod']}",
            "Scope: selected subscription (Single). No CSV was used.",
            result["notice"],
            "",
        ]
        for source, coverage in result["coverage"].items():
            lines.append(
                f"{source}: {coverage['status']} - {coverage.get('message', '')} "
                f"[{coverage.get('source', source)} / API {coverage.get('apiVersion', 'not supplied')}]"
            )
        lines.extend(["", "SAVINGS PLAN HOURLY COMMITMENTS (Azure Cost Management)"])
        if not result["recommendations"]:
            lines.append("No hourly commitment is available. Review source coverage above; no estimate was substituted.")
        for recommendation in result["recommendations"]:
            details = recommendation.get("recommendationDetails", {})
            currency = recommendation.get("currencyCode", "Currency not supplied by Azure")
            lines.extend([
                f"Reference: {recommendation.get('recommendationReference', 'Not supplied')}",
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
                f"  Problem: {recommendation['problem']}",
                f"  Action: {recommendation['solution']}",
                f"  Azure last updated: {recommendation['lastUpdated']}",
            ])
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
        self.azure = DesktopAzure()
        self.busy = False
        self.events: queue.Queue[tuple[Callable[[Any], None], Any, str | None]] = queue.Queue()
        self.subscription_ids: dict[str, str] = {}
        root.title(APP_TITLE)
        root.geometry("1000x780")
        root.minsize(760, 600)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text="Read Azure recommendations for existing workloads. CSV is optional, for offline modeling only.",
            wraplength=700,
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        self.values: dict[str, tk.StringVar] = {}
        self.values["mode"] = tk.StringVar(value="connected")
        mode = ttk.Combobox(
            frame, textvariable=self.values["mode"], state="readonly",
            values=("connected", "what-if", "comparison"),
        )
        mode.grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)
        mode.bind("<<ComboboxSelected>>", self.change_mode)
        self.context_controls: list[ttk.Widget] = [mode]
        self.azure_frame = ttk.LabelFrame(frame, text="Azure Entra context (Azure CLI user sign-in)", padding=8)
        self.azure_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.azure_frame.columnconfigure(1, weight=1)
        azure_fields = [
            ("tenantId", "Tenant GUID (blank for initial sign-in)", None, ""),
            ("subscription", "Subscription", (), ""),
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
            if key == "subscription":
                self.subscription_combo = widget
        self.values["tenantId"].trace_add("write", self.invalidate_context)
        for key in ("subscription", "azureTerm", "lookback"):
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
            text="Tenant switching clears previous results. Select a subscription after refresh. "
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
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=10)
        analyze_button = ttk.Button(actions, text="Analyze", command=self.analyze)
        analyze_button.pack(side="left")
        self.context_controls.append(analyze_button)
        self.save_button = ttk.Button(actions, text="Save result as JSON...", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.output = ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        self.output.grid(row=5, column=0, columnspan=3, sticky="nsew")
        self.set_output(
            "Azure-connected analysis is the default. No hourly-cost CSV is required.\n\n"
            "Select Sign in / switch tenant to open Entra sign-in.\n"
            "For tenant switching, select or enter your approved tenant GUID first.\n"
            "Use Refresh context if you already signed in with Azure CLI.\n"
            "Select an accessible subscription, term, and lookback, then Analyze.\n\n"
            "The app reads Azure Advisor Cost recommendations and Azure Cost Management "
            "Savings Plan hourly commitment recommendations for existing usage.\n"
            "It never purchases a Savings Plan or changes Azure resources.\n\n"
            "For optional offline analysis, choose what-if or comparison and supply a CSV."
        )
        root.report_callback_exception = self.callback_error
        self.root.after(100, self.poll_events)

    def invalidate_result(self, *_args: Any) -> None:
        self.result = None
        if hasattr(self, "save_button"):
            self.save_button.configure(state="disabled")
            self.set_output("Inputs changed. Run analysis again for the selected context.")

    def invalidate_context(self, *_args: Any) -> None:
        self.azure.clear()
        self.subscription_ids = {}
        self.values["subscription"].set("")
        self.subscription_combo.configure(values=())
        self.invalidate_result()

    def change_mode(self, _event: Any = None) -> None:
        self.invalidate_result()
        if self.values["mode"].get() == "connected":
            self.offline_frame.grid_remove()
            self.azure_frame.grid()
        else:
            self.azure_frame.grid_remove()
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
        self.subscription_combo.configure(values=list(self.subscription_ids))
        self.set_output(
            f"Context refreshed: {len(self.subscription_ids)} enabled subscriptions available. "
            "Select a subscription explicitly, then Analyze."
            if self.subscription_ids else
            "No enabled subscriptions are accessible in this tenant. Check account membership and RBAC."
        )

    def show_result(self, result: dict[str, Any]) -> None:
        self.result = result
        self.set_output(format_result(result))
        self.save_button.configure(state="normal")

    def callback_error(self, exception_type: type[BaseException], exception: BaseException, traceback: Any) -> None:
        logging.error("Desktop callback failed", extra={"error_type": exception_type.__name__})
        self.result = None
        self.save_button.configure(state="disabled")
        self.set_output("An unexpected application error occurred. No result is available.")
        messagebox.showerror(APP_TITLE, "An unexpected application error occurred. Restart the app and retry.", parent=self.root)

    def set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def browse(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Select hourly costs CSV", filetypes=[("CSV files", "*.csv")])
        if path:
            self.values["csvFile"].set(path)

    def analyze(self) -> None:
        if self.busy:
            return
        if self.values["mode"].get() == "connected":
            tenant = self.values["tenantId"].get().strip()
            subscription = self.subscription_ids.get(self.values["subscription"].get())
            if not subscription:
                self.invalidate_result()
                messagebox.showerror("Azure context required", "Refresh context and select an accessible subscription.", parent=self.root)
                return
            term = self.values["azureTerm"].get()
            lookback = self.values["lookback"].get()
            self.run_task(
                lambda: self.azure.analyze(tenant, subscription, term, lookback),
                self.show_result, "Reading Azure Advisor and Savings Plan recommendations...",
            )
            return
        self.result = None
        self.save_button.configure(state="disabled")
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
            display = format_result(result)
        except (OSError, ValueError) as exc:
            self.set_output("Analysis failed. Check the selected file and assumptions.")
            messagebox.showerror("Analysis failed", str(exc), parent=self.root)
            return
        self.result = result
        self.set_output(display)
        self.save_button.configure(state="normal")

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
                Path(path).write_text(json.dumps(self.result, indent=2, allow_nan=False), encoding="utf-8")
            except (OSError, ValueError) as exc:
                messagebox.showerror("Export failed", str(exc), parent=self.root)


def main() -> None:
    root = tk.Tk()
    AdvisorWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
