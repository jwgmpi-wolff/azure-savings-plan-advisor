import copy
import csv
from pathlib import Path

import pytest
from pptx import Presentation
from pypdf import PdfReader

from api.reporting import (
    build_report, chart_records, clean_text, export_csv, export_pdf,
    export_powerpoint, redacted_result, write_report,
)
from desktop_app import analyze_csv_file


@pytest.fixture
def connected_result():
    return {
        "mode": "connected", "collectedAt": "2026-01-01T00:00:00Z",
        "completeness": "partial", "context": {"tenantId": "synthetic-tenant", "subscriptionId": "synthetic-subscription"},
        "filters": {"term": "P1Y", "lookbackPeriod": "Last30Days", "recommendationScope": "Single"},
        "coverage": {
            "advisor": {"status": "denied", "source": "Azure Advisor", "apiVersion": "2025-01-01", "message": "Request Reader access."},
            "savingsPlan": {"status": "ok", "source": "Azure Cost Management", "apiVersion": "2026-06-01"},
        },
        "notice": "Synthetic fixture only. Alternatives are not additive.",
        "recommendations": [{
            "recommendationReference": "evidence-001", "term": "P1Y",
            "currencyCode": "USD", "commitmentGranularity": "Hourly",
            "costWithoutBenefit": 1000, "totalHours": 720,
            "recommendationDetails": {
                "commitmentAmount": 4.25, "savingsAmount": 123.45,
                "savingsPercentage": 12.345, "coveragePercentage": 80,
                "averageUtilizationPercentage": 95, "totalCost": 876.55,
            },
            "alternatives": [{"commitmentAmount": 2.75, "savingsAmount": 100, "savingsPercentage": 10}],
        }],
        "advisorRecommendations": [],
    }


def text_from_pdf(path):
    return "\n".join(page.extract_text() for page in PdfReader(path).pages)


def text_from_powerpoint(path):
    return "\n".join(
        shape.text for slide in Presentation(path).slides
        for shape in slide.shapes if shape.has_text_frame
    )


def test_report_preserves_azure_values_and_missing_is_not_zero(connected_result):
    report = build_report(connected_result)
    assert report.collected_at == connected_result["collectedAt"]
    assert report.records[0]["hourlyCommitment"] == 4.25
    assert report.records[0]["savingsAmount"] == 123.45
    assert report.records[1]["recordType"] == "alternative"
    assert report.records[1]["modeledCost"] is None
    assert report.metrics[0][1] == "1"
    assert report.metrics[2][1] == "partial"
    assert len(chart_records(report)) == 1
    assert any("denied" in line for line in report.coverage)


@pytest.mark.parametrize("kind,exporter,reader", [
    ("pdf", export_pdf, text_from_pdf), ("pptx", export_powerpoint, text_from_powerpoint),
])
def test_executive_exports_include_values_sources_evidence_and_partial_coverage(tmp_path, connected_result, kind, exporter, reader):
    report = build_report(connected_result)
    path = tmp_path / f"report.{kind}"
    exporter(report, path)
    text = reader(path)
    for expected in ["Savings plans", "4.25", "123.45", "evidence-001", "partial", "denied",
                     "2026-01-01", "synthetic-subscription", "2026-06-01", "not additive", "alternative"]:
        assert expected in text
    assert path.stat().st_size > 1000


def test_csv_schema_is_explicit_and_contains_all_records_with_provenance(tmp_path, connected_result):
    report = build_report(connected_result)
    path = tmp_path / "report.csv"
    export_csv(report, path)
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    assert len(rows) == 2
    assert rows[0]["hourlyCommitment"] == "4.25"
    assert rows[0]["savingsAmount"] == "123.45"
    assert rows[1]["modeledCost"] == ""
    assert all("denied" in row["sourceCoverage"] for row in rows)
    assert all(row["collectedAt"] == report.collected_at for row in rows)


def test_mixed_currencies_are_not_aggregated(connected_result):
    second = copy.deepcopy(connected_result["recommendations"][0])
    second["currencyCode"] = "EUR"
    connected_result["recommendations"].append(second)
    report = build_report(connected_result)
    assert report.metrics[-1] == ("Currencies (not summed)", "EUR, USD")
    assert {row["currency"] for row in report.records} == {"EUR", "USD"}
    assert not any("total savings" in label.lower() for label, _ in report.metrics)


@pytest.mark.parametrize("kind,exporter,reader", [
    ("pdf", export_pdf, text_from_pdf), ("pptx", export_powerpoint, text_from_powerpoint),
    ("csv", export_csv, lambda path: path.read_text(encoding="utf-8-sig")),
])
def test_empty_denied_result_still_exports_coverage_not_success(tmp_path, connected_result, kind, exporter, reader):
    connected_result["recommendations"] = []
    report = build_report(connected_result)
    path = tmp_path / f"empty.{kind}"
    exporter(report, path)
    text = reader(path)
    assert "No recommendation records" in text
    assert "denied" in text
    assert "Request Reader access" in text
    assert "4.25" not in text


def test_csv_formula_neutralization_and_shared_secret_redaction(tmp_path, connected_result):
    connected_result["advisorRecommendations"] = [{
        "recommendationReference": "advisor-001", "problem": "=HYPERLINK(\"bad\")",
        "solution": "Authorization: Bearer synthetic-private-token password=private-password",
        "impact": "High",
    }]
    report = build_report(connected_result)
    advisor = report.records[-1]
    assert "synthetic-private-token" not in advisor["notes"]
    assert "private-password" not in advisor["notes"]
    assert "[REDACTED]" in advisor["notes"]
    path = tmp_path / "safe.csv"
    export_csv(report, path)
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert rows[-1]["label"].startswith("'=")
    assert redacted_result({"access_token": "private", "nested": ["Bearer private"]}) == {
        "access_token": "[REDACTED]", "nested": ["[REDACTED]"],
    }


@pytest.mark.parametrize("kind,reader", [
    ("pdf", text_from_pdf), ("pptx", text_from_powerpoint),
    ("csv", lambda path: path.read_text(encoding="utf-8-sig")),
])
def test_secrets_are_redacted_in_every_report_format(tmp_path, connected_result, kind, reader):
    connected_result["advisorRecommendations"] = [{
        "problem": "Review workload", "solution": "Bearer secret-test-assertion client_secret=secret-test-value",
        "recommendationReference": "advisor-redacted", "impact": "High",
    }]
    path = tmp_path / f"safe.{kind}"
    write_report(build_report(connected_result), path, kind)
    text = reader(path)
    assert "secret-test-assertion" not in text
    assert "secret-test-value" not in text
    assert "[REDACTED]" in text


def test_failed_export_preserves_existing_file_and_removes_temporary_file(tmp_path, connected_result, monkeypatch):
    from api import reporting

    path = tmp_path / "existing.pdf"
    path.write_bytes(b"previous report")
    def fail(_report, destination):
        destination.write_bytes(b"incomplete new report")
        raise OSError("Disk write failed")
    monkeypatch.setattr(reporting, "export_pdf", fail)
    with pytest.raises(OSError, match="Disk write failed"):
        write_report(build_report(connected_result), path, "pdf")
    assert path.read_bytes() == b"previous report"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("kind,exporter,reader", [
    ("pdf", export_pdf, text_from_pdf), ("pptx", export_powerpoint, text_from_powerpoint),
])
def test_long_reports_paginate_without_losing_last_record_or_assumptions(tmp_path, connected_result, kind, exporter, reader):
    connected_result["advisorRecommendations"] = [{
        "recommendationReference": f"advisor-{index}", "problem": "Cost optimization & <review>",
        "solution": "Long recommendation text " * 100 + f"FINAL-{index}",
        "impact": "High", "lastUpdated": "2026-01-01",
    } for index in range(12)]
    path = tmp_path / f"long.{kind}"
    exporter(build_report(connected_result), path)
    text = reader(path)
    assert "FINAL-11" in text
    assert "advisor-11" in text
    if kind == "pdf":
        assert len(PdfReader(path).pages) > 2
    else:
        presentation = Presentation(path)
        assert len(presentation.slides) > 12
        for slide in presentation.slides:
            for shape in slide.shapes:
                assert shape.top + shape.height <= presentation.slide_height


@pytest.mark.parametrize("mode", ["what-if", "comparison"])
def test_offline_report_labels_estimates_and_preserves_option_values(mode):
    sample = Path(__file__).parents[1] / "samples" / "hourly-costs.csv"
    assumptions = {
        "mode": mode, "currencyCode": "USD", "expectedChangePercent": 0,
        **({"term": "P1Y", "discountPercent": 20, "scenario": "balanced"} if mode == "what-if"
           else {"discountPercentP1Y": 15, "discountPercentP3Y": 25}),
    }
    result = analyze_csv_file(sample, assumptions)
    report = build_report(result)
    assert len(report.records) == (1 if mode == "what-if" else 3)
    assert all(row["recordType"] == "model" for row in report.records)
    assert any("Offline planning estimate" in notice for notice in report.notices)
    assert "no Azure" in report.coverage[0]
    assert report.records[0]["savingsAmount"] == (
        result["netSavingsObserved"] if mode == "what-if" else result["options"][0]["netSavingsObserved"]
    )
