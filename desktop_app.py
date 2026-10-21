from __future__ import annotations

import json
import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from api.calculator import calculate_comparison, calculate_forecast
from api.csv_parser import MAX_CSV_BYTES, parse_hourly_cost_csv
from api.models import ForecastRequest, validate_request


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
        root.title(APP_TITLE)
        root.geometry("1000x780")
        root.minsize(760, 600)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(13, weight=1)
        ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            frame,
            text="Offline what-if and comparison estimates. No Azure login or network access required.",
            wraplength=700,
        ).grid(row=1, column=0, columnspan=3, sticky="w")
        self.values: dict[str, tk.StringVar] = {}
        fields = [
            ("csvFile", "Hourly costs CSV", None),
            ("mode", "Analysis mode", ("what-if", "comparison")),
            ("currencyCode", "Currency code (e.g. USD)", None),
            ("expectedChangePercent", "Expected usage change (%)", None),
            ("term", "What-if term", ("P1Y", "P3Y")),
            ("discountPercent", "What-if discount (%)", None),
            ("scenario", "What-if scenario", ("conservative", "balanced", "maximumSavings", "custom")),
            ("hourlyCommitment", "Custom hourly commitment", None),
            ("discountPercentP1Y", "Comparison P1Y discount (%)", None),
            ("discountPercentP3Y", "Comparison P3Y discount (%)", None),
        ]
        for row, (key, label, choices) in enumerate(fields, start=2):
            variable = tk.StringVar()
            self.values[key] = variable
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            if choices:
                widget = ttk.Combobox(frame, textvariable=variable, values=choices, state="readonly")
            else:
                widget = ttk.Entry(frame, textvariable=variable)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Button(frame, text="Browse...", command=self.browse).grid(row=2, column=2, padx=(8, 0))
        actions = ttk.Frame(frame)
        actions.grid(row=12, column=0, columnspan=3, sticky="w", pady=10)
        ttk.Button(actions, text="Analyze", command=self.analyze).pack(side="left")
        self.save_button = ttk.Button(actions, text="Save result as JSON...", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=8)
        self.output = ScrolledText(frame, wrap="word", font=("Consolas", 10), state="disabled")
        self.output.grid(row=13, column=0, columnspan=3, sticky="nsew")
        self.set_output(
            "Choose a UTF-8 CSV with timestamp and eligible_payg_cost columns.\n"
            "Timestamps must include a timezone and be consecutive hourly observations.\n\n"
            "Select a mode and explicitly enter all applicable assumptions.\n"
            "Use 0 for expected usage change only when that is your intended assumption.\n"
            "Comparison uses balanced scenario commitments for each term.\n"
            "Custom what-if requires an hourly commitment; leave it empty otherwise.\n\n"
            "Results are local estimates, not live Azure recommendations or price quotes.\n"
            "Connected recommendations require the separately deployed, authenticated API."
        )
        root.report_callback_exception = self.callback_error

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
