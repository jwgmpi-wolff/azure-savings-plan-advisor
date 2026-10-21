from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from math import isfinite


MAX_CSV_ROWS = 26304
MAX_CSV_BYTES = 2_000_000
REQUIRED_COLUMNS = {"timestamp", "eligible_payg_cost"}


def parse_hourly_cost_csv(csv_text: str) -> list[float]:
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError("CSV data is required and cannot be empty.")
    try:
        encoded_size = len(csv_text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("CSV data contains invalid Unicode.") from exc
    if encoded_size > MAX_CSV_BYTES:
        raise ValueError("CSV data exceeds the 2 MB upload limit.")

    reader = csv.DictReader(io.StringIO(csv_text, newline=""), strict=True)
    try:
        fieldnames = reader.fieldnames
    except csv.Error as exc:
        raise ValueError("CSV header syntax is malformed.") from exc
    if fieldnames is None:
        raise ValueError("CSV header row is required.")

    headers = [
        (header or "").strip().lower().replace(" ", "_") for header in fieldnames
    ]
    if len(headers) != len(set(headers)):
        raise ValueError("CSV column names must be unique.")
    missing = REQUIRED_COLUMNS.difference(headers)
    if missing:
        raise ValueError(
            "CSV is missing required columns: "
            + ", ".join(sorted(missing))
            + "."
        )

    timestamp_column = headers.index("timestamp")
    cost_column = headers.index("eligible_payg_cost")
    costs: list[float] = []
    previous_timestamp: datetime | None = None

    row_number = 1
    while True:
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise ValueError(
                f"CSV syntax is malformed near line {reader.line_num}."
            ) from exc
        row_number += 1
        if row_number > MAX_CSV_ROWS + 1:
            raise ValueError(
                f"CSV contains more than {MAX_CSV_ROWS} hourly rows."
            )
        if None in row:
            raise ValueError(f"CSV row {row_number} has more values than headers.")
        values = list(row.values())
        if any(value is None for value in values):
            raise ValueError(f"CSV row {row_number} has missing values.")
        if len(values) != len(headers):
            raise ValueError(f"CSV row {row_number} has missing values.")

        timestamp_text = (values[timestamp_column] or "").strip()
        cost_text = (values[cost_column] or "").strip()
        if not timestamp_text or not cost_text:
            raise ValueError(
                f"CSV row {row_number} must include timestamp and eligible_payg_cost."
            )

        try:
            timestamp = datetime.fromisoformat(
                timestamp_text.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(
                f"CSV row {row_number} has a malformed ISO 8601 timestamp."
            ) from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError(
                f"CSV row {row_number} timestamp must include a timezone."
            )
        if (
            timestamp.minute
            or timestamp.second
            or timestamp.microsecond
        ):
            raise ValueError(
                f"CSV row {row_number} timestamp must align to an hour."
            )
        timestamp_utc = timestamp.astimezone(timezone.utc)
        if previous_timestamp is not None:
            if timestamp_utc <= previous_timestamp:
                raise ValueError(
                    f"CSV timestamps must be strictly increasing (row {row_number})."
                )
            if timestamp_utc - previous_timestamp != timedelta(hours=1):
                raise ValueError(
                    f"CSV timestamps must be consecutive hourly observations "
                    f"(gap before row {row_number})."
                )
        previous_timestamp = timestamp_utc

        try:
            cost = float(cost_text)
        except ValueError as exc:
            raise ValueError(
                f"CSV row {row_number} eligible_payg_cost must be numeric."
            ) from exc
        if not isfinite(cost):
            raise ValueError(
                f"CSV row {row_number} eligible_payg_cost must be finite."
            )
        if cost < 0:
            raise ValueError(
                f"CSV row {row_number} eligible_payg_cost cannot be negative."
            )
        costs.append(cost)

    if not costs:
        raise ValueError("CSV must contain at least one hourly data row.")
    return costs
