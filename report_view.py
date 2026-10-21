from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from api.reporting import BLUE, NAVY, PALE, TEAL, SavingsReport, chart_label, display, record_lines, report_charts


def apply_theme(root: tk.Tk) -> None:
    root.configure(background=PALE)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background="white", foreground=NAVY)
    style.configure("App.TFrame", background=PALE)
    style.configure("TFrame", background="white")
    style.configure("TLabel", background="white", foreground=NAVY)
    style.configure("TLabelFrame", background="white", bordercolor="#d2dce5", relief="solid", borderwidth=1)
    style.configure("TLabelFrame.Label", font=("Segoe UI", 11, "bold"), background="white", foreground=NAVY)
    style.configure("TButton", background=TEAL, foreground="white", padding=(12, 7), borderwidth=0)
    style.map("TButton", background=[("disabled", "#d3e0e5"), ("active", "#096764")],
              foreground=[("disabled", "#687c8e")])
    style.configure("TCombobox", fieldbackground="white", padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", "white")])
    style.configure("TEntry", fieldbackground="white", padding=5)
    style.configure("Treeview", background="white", fieldbackground="white", rowheight=30, borderwidth=0)
    style.configure("Treeview.Heading", background="#e9f7f6", foreground=TEAL, font=("Segoe UI", 9, "bold"), padding=6)
    style.map("Treeview", background=[("selected", "#d8eeef")], foreground=[("selected", NAVY)])
    style.configure("TNotebook", background=PALE, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 7))


class ReportView(ttk.Frame):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, padding=12)
        self.report: SavingsReport | None = None
        self.details_window: tk.Toplevel | None = None
        self.heading = ttk.Label(self, text="Savings plans", font=("Segoe UI", 22, "bold"))
        self.heading.pack(anchor="w")
        self.subtitle = ttk.Label(self, text="Run a live report to view the executive dashboard.", wraplength=1050)
        self.subtitle.pack(anchor="w", pady=(2, 10))
        cards = ttk.Frame(self)
        cards.pack(fill="x", pady=(0, 10))
        self.cards: list[tuple[ttk.Label, ttk.Label]] = []
        for index in range(4):
            card = tk.Frame(cards, background="#f1fafb", highlightbackground="#d2dce5", highlightthickness=1, padx=12, pady=8)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 5))
            cards.columnconfigure(index, weight=1, uniform="cards")
            title = ttk.Label(card, text="Awaiting report", background="#f1fafb", font=("Segoe UI", 9))
            title.pack(anchor="w")
            value = ttk.Label(card, text="--", background="#f1fafb", foreground=TEAL, font=("Segoe UI", 18, "bold"), wraplength=220)
            value.pack(anchor="w")
            self.cards.append((title, value))
        self.coverage = ttk.Label(self, text="", wraplength=1050, foreground=TEAL)
        self.model_guidance = ttk.Label(self, text="", wraplength=1050, foreground=NAVY)
        self.model_guidance.pack(anchor="w", pady=(0, 8))
        self.chart = tk.Canvas(self, height=200, background="white", highlightthickness=0)
        self.chart.bind("<Configure>", lambda _event: self.draw_chart())
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, pady=(8, 0))
        columns = ("type", "subscriptionName", "subscription", "label", "term", "currency", "commitment", "baseline",
                   "cost", "savings", "percent", "coverage", "utilization", "runtime", "period", "breakeven", "unused",
                   "computeType", "computeSku")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=7)
        self.table.bind("<ButtonRelease-1>", self.open_clicked_row)
        self.table.bind("<Return>", self.open_focused_row)
        ttk.Label(table_frame, text="Click a row for compute, benefit and discount details. Keyboard: Enter.").grid(
            row=2, column=0, sticky="w", pady=(5, 0),
        )
        headings = ("Record", "Subscription name", "Subscription ID", "Recommendation / option", "Term", "Currency",
                    "Hourly commitment", "PAYG baseline", "Modeled cost", "Savings amount", "Savings %", "Coverage %",
                    "Utilization %", "Running hours", "Period hours", "Break-even hours", "Unused commitment",
                    "Compute type", "Compute SKU")
        for column, heading in zip(columns, headings):
            self.table.heading(column, text=heading)
            self.table.column(column, width=125 if column != "label" else 250, minwidth=90, stretch=True)
        vertical = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.chart.pack(fill="x", pady=(12, 0))
        self.coverage.pack(anchor="w", pady=(8, 0))
        self.footnote = ttk.Label(
            self, text="No values are added across plans, alternatives, or currencies. Full evidence and assumptions are in Details and exports.",
            wraplength=1050, font=("Segoe UI", 9),
        )
        self.footnote.pack(anchor="w", pady=(8, 0))
        self.bind("<Configure>", self.resize)

    def resize(self, event: tk.Event) -> None:
        width = max(300, event.width - 24)
        for label in (self.subtitle, self.coverage, self.footnote, self.model_guidance):
            label.configure(wraplength=width)
        for title, value in self.cards:
            title.configure(wraplength=max(100, width // 4 - 30))
            value.configure(wraplength=max(100, width // 4 - 30))

    def clear(self) -> None:
        self.close_details()
        self.report = None
        self.subtitle.configure(text="Report cleared. Run analysis for the current context.")
        self.coverage.configure(text="")
        self.coverage.pack_forget()
        self.model_guidance.configure(text="")
        for title, value in self.cards:
            title.configure(text="Awaiting report")
            value.configure(text="--")
        self.table.delete(*self.table.get_children())
        self.chart.delete("all")

    def show(self, report: SavingsReport) -> None:
        self.clear()
        self.report = report
        label = "LIVE AZURE REPORT" if report.mode == "connected" else "OFFLINE PLANNING ESTIMATE"
        self.subtitle.configure(text=f"{label} | Collected {report.collected_at}\nScope: {report.scope}")
        for (title, value), (label, text) in zip(self.cards, report.metrics):
            title.configure(text=label)
            value.configure(text=text)
        self.coverage.configure(text="\n".join(report.coverage))
        if report.coverage:
            self.coverage.pack(before=self.footnote, anchor="w", pady=(8, 0))
        self.table.configure(displaycolumns=(
            ("label", "runtime", "baseline", "cost", "savings", "breakeven", "currency", "commitment",
             "period", "unused", "percent", "coverage", "utilization", "term", "type")
            if report.mode == "modeler" else
            ("type", "subscriptionName", "subscription", "label", "term", "currency", "commitment",
             "computeType", "computeSku", "baseline", "cost", "savings", "percent", "coverage", "utilization")
        ))
        if report.mode == "modeler":
            model = report.records[0]
            self.model_guidance.configure(text=(
                "Calculation-based guidance (not Copilot-generated): commitment is paid for every elapsed hour, including idle hours. "
                f"Period commitment: {display(model['commitmentCost'])} {model['currency']}; "
                f"break-even runtime: {display(model['breakEvenHours'])} hours. "
                "The threshold is not an elapsed-time payback promise. "
                "Review full guidance and repeated-duty-cycle term projections in Evidence & details. "
                "Copy for Copilot prepares a prompt only; it does not send data."
            ))
        for index, record in enumerate(report.records):
            self.table.insert("", "end", iid=str(index), values=[
                display(record.get(key)) for key in (
                    "recordType", "subscriptionName", "subscriptionId", "label", "term", "currency", "hourlyCommitment",
                    "baselineCost", "modeledCost", "savingsAmount", "savingsPercent", "coveragePercent", "utilizationPercent",
                    "computeHours", "periodHours", "breakEvenHours", "unusedCommitment", "computeType", "computeSku",
                )
            ])
        self.draw_chart()

    def close_details(self) -> None:
        if self.details_window is not None:
            self.details_window.destroy()
            self.details_window = None

    def open_clicked_row(self, event: tk.Event) -> None:
        if self.table.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        row = self.table.identify_row(event.y)
        if row:
            self.table.selection_set(row)
            self.table.focus(row)
            self.show_row_details(row)

    def open_focused_row(self, _event: tk.Event) -> str:
        row = self.table.focus()
        if row:
            self.show_row_details(row)
        return "break"

    def show_row_details(self, row: str) -> None:
        if self.report is None or not self.table.exists(row):
            return
        record = self.report.records[int(row)]
        self.close_details()
        popup = tk.Toplevel(self)
        self.details_window = popup
        popup.title("Recommendation details")
        popup.geometry("820x650")
        popup.minsize(500, 350)
        popup.transient(self.winfo_toplevel())
        popup.protocol("WM_DELETE_WINDOW", self.close_details)
        popup.bind("<Escape>", lambda _event: self.close_details())
        content = ttk.Frame(popup, padding=12)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text=display(record.get("label")), font=("Segoe UI", 14, "bold"),
                  wraplength=740).pack(anchor="w", pady=(0, 8))
        text = ScrolledText(content, wrap="word", font=("Segoe UI", 10), foreground=NAVY)
        text.pack(fill="both", expand=True)
        lines = [
            f"Collected: {self.report.collected_at}", f"Scope: {self.report.scope}", "",
            "COMPUTE, BENEFITS AND DISCOUNTS",
            f"Compute type: {display(record.get('computeType'))}",
            f"Compute SKU: {display(record.get('computeSku'))}",
            f"Benefit type: {display(record.get('benefitType'))}",
            f"Benefit / plan SKU (not workload SKU): {display(record.get('benefitSku'))}",
            f"Assumed discount (%): {display(record.get('discountPercent'))}",
            f"Savings (%): {display(record.get('savingsPercent'))}",
            "",
            "Connected compute inventory covers current VMs, VM scale sets and App Service plans, subject to read access. "
            "Subscription-level plans do not identify an individual workload SKU; their related inventory is shown below "
            "as context only, not attributed benefit coverage. Advisor details are linked only by exact resource ID. "
            "Offline inputs do not identify compute type/SKU. A benefit/plan SKU does not identify a workload SKU. "
            "Savings percentage is the overall estimated saving, not a per-SKU discount. "
            "Offline discounts are user assumptions, not verified Azure pricing; CSV model assumptions are listed below.",
            "", "FULL ROW DETAILS", *record_lines(record),
            *(["", "COLLECTION NOTES", *self.report.coverage] if self.report.coverage else []),
            "", "LIMITATIONS AND ASSUMPTIONS", *self.report.notices,
        ]
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        ttk.Button(content, text="Close", command=self.close_details).pack(anchor="e", pady=(8, 0))
        text.focus_set()

    def draw_chart(self) -> None:
        self.chart.delete("all")
        if self.report is None:
            return
        width = max(self.chart.winfo_width(), 650)
        charts = report_charts(self.report)
        self.chart.configure(height=max(85, len(charts) * 215))
        if not charts:
            self.chart.create_text(8, 55, anchor="w", text="No returned savings percentages to chart. See source coverage and details.", fill=NAVY)
            return
        for chart_index, (title, field, unit, rows) in enumerate(charts):
            offset = chart_index * 215
            self.chart.create_text(8, offset + 12, anchor="w", text=title, fill=NAVY, font=("Segoe UI", 11, "bold"))
            maximum = max(max(abs(record[field]) for record in rows), .01)
            shown = rows[:5]
            for index, record in enumerate(shown):
                y = offset + 45 + index * 27
                self.chart.create_text(8, y, anchor="w", text=chart_label(record)[:45], fill=NAVY, font=("Segoe UI", 9))
                start = 315
                end = width - 120
                length = (end - start) * abs(record[field]) / maximum
                self.chart.create_rectangle(start, y - 7, end, y + 7, fill="#e4eaf2", outline="")
                self.chart.create_rectangle(start, y - 7, start + length, y + 7, fill=BLUE if record[field] >= 0 else "#b54343", outline="")
                self.chart.create_text(width - 8, y, anchor="e", text=f"{record[field]:.2f}{unit}", fill=NAVY)
            self.chart.create_text(8, offset + 189, anchor="w", text=f"Showing {len(shown)} of {len(rows)} values; alternatives excluded. Length = magnitude; red = negative. Independent scales.", fill=NAVY, font=("Segoe UI", 8))
