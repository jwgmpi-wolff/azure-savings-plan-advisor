import json
import logging

from azure.functions import HttpRequest

import function_app


def _request(method, url, headers, body=b""):
    return HttpRequest(
        method=method,
        url=url,
        headers=headers,
        params={},
        route_params={},
        body=body,
    )


def test_health_response_is_minimal():
    response = function_app.health(_request("GET", "http://localhost/api/health", {}))

    assert response.status_code == 200
    assert json.loads(response.get_body()) == {
        "status": "ok",
        "service": "Azure Savings Plan Advisor",
    }


def test_json_what_if_endpoint_returns_calculated_result(monkeypatch, caplog):
    monkeypatch.setenv("REQUIRE_AUTHENTICATION", "false")
    caplog.set_level(logging.INFO)
    request_body = {
        "mode": "what-if",
        "term": "P1Y",
        "currencyCode": "USD",
        "expectedChangePercent": 0,
        "scenario": "balanced",
        "discountPercent": 20,
        "baselineHourlyCosts": [10] * 24,
    }
    response = function_app.analyze(
        _request(
            "POST",
            "http://localhost/api/analyze-savings-plan",
            {"Content-Type": "application/json"},
            json.dumps(request_body).encode(),
        )
    )

    result = json.loads(response.get_body())
    assert response.status_code == 200
    assert result["mode"] == "what-if"
    assert result["currencyCode"] == "USD"
    assert result["baselineEligibleCostObserved"] == 240
    event = next(
        record.custom_dimensions
        for record in caplog.records
        if hasattr(record, "custom_dimensions")
    )
    assert event == {
        "event_name": "savings_plan_analysis_completed",
        "mode": "what-if",
    }


def test_csv_upload_endpoint_parses_multipart_and_calculates(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTHENTICATION", "false")
    boundary = "cost-upload-boundary"
    csv_data = (
        "timestamp,eligible_payg_cost\n"
        "2026-01-01T00:00:00Z,10\n"
        "2026-01-01T01:00:00Z,12\n"
    )
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="csvFile"; filename="costs.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
        f"{csv_data}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="term"\r\n\r\n'
        "P1Y\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="currencyCode"\r\n\r\n'
        "USD\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="expectedChangePercent"\r\n\r\n'
        "0\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="discountPercent"\r\n\r\n'
        "20\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="scenario"\r\n\r\n'
        "balanced\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    response = function_app.analyze_csv(
        _request(
            "POST",
            "http://localhost/api/analyze-savings-plan-csv",
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body,
        )
    )

    result = json.loads(response.get_body())
    assert response.status_code == 200
    assert result["dataHours"] == 2
    assert result["currencyCode"] == "USD"


def test_invalid_json_returns_a_client_error_without_echoing_body(caplog):
    response = function_app.analyze(
        _request(
            "POST",
            "http://localhost/api/analyze-savings-plan",
            {"Content-Type": "application/json"},
            b'{"baselineHourlyCosts":[99999],',
        )
    )

    assert response.status_code == 400
    assert b"99999" not in response.get_body()
    assert "99999" not in caplog.text


def test_production_authentication_requires_easy_auth_principal(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTHENTICATION", "true")
    response = function_app.analyze(
        _request(
            "POST",
            "http://localhost/api/analyze-savings-plan",
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "mode": "what-if",
                    "term": "P1Y",
                    "currencyCode": "USD",
                    "expectedChangePercent": 0,
                    "scenario": "balanced",
                    "discountPercent": 20,
                    "baselineHourlyCosts": [1],
                }
            ).encode(),
        )
    )

    assert response.status_code == 401
    assert json.loads(response.get_body())["error"] == "Authentication is required."
