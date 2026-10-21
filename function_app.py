from __future__ import annotations

import json
import logging
import os
from email import policy
from email.parser import BytesParser
from typing import Any

import azure.functions as func

from api.azure_provider import (
    ConnectedProviderError,
    get_benefit_recommendations,
)
from api.calculator import calculate_comparison, calculate_forecast
from api.csv_parser import MAX_CSV_BYTES, parse_hourly_cost_csv
from api.models import ForecastRequest, validate_request

MAX_REQUEST_BYTES = MAX_CSV_BYTES + 65536
NUMERIC_FORM_FIELDS = {
    "discountPercent",
    "discountPercentP1Y",
    "discountPercentP3Y",
    "expectedChangePercent",
    "hourlyCommitment",
}

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _json_response(payload: dict[str, Any], status_code: int = 200):
    return func.HttpResponse(
        json.dumps(payload, allow_nan=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _log_event(
    level: int,
    event_name: str,
    message: str,
    **dimensions: str,
) -> None:
    logging.log(
        level,
        message,
        extra={
            "custom_dimensions": {
                "event_name": event_name,
                **dimensions,
            }
        },
    )


def _reject_json_constant(value: str):
    raise ValueError(f"JSON number {value} is not permitted.")


def _read_json_request(req: func.HttpRequest) -> dict[str, Any]:
    body = req.get_body()
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds the 2 MB upload limit.")
    try:
        result = json.loads(body, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Request body must contain valid JSON.") from exc
    if not isinstance(result, dict):
        raise ValueError("The request body must be a JSON object.")
    return result


def _read_multipart_request(req: func.HttpRequest) -> dict[str, Any]:
    body = req.get_body()
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("Request exceeds the 2 MB upload limit.")
    content_type = req.headers.get("Content-Type", "")
    if (
        not content_type.lower().startswith("multipart/form-data;")
        or "\r" in content_type
        or "\n" in content_type
    ):
        raise ValueError("Request must use multipart/form-data.")
    message_bytes = (
        f"Content-Type: {content_type}\r\n"
        "MIME-Version: 1.0\r\n\r\n"
    ).encode("ascii", errors="strict") + body
    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    if not message.is_multipart():
        raise ValueError("Request must use multipart/form-data.")

    fields: dict[str, Any] = {}
    csv_uploads = 0
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str):
            continue
        raw_value = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            value = raw_value.decode(charset)
        except (LookupError, UnicodeDecodeError) as exc:
            raise ValueError(f"Multipart field {name} is not valid text.") from exc

        if name == "csvFile":
            csv_uploads += 1
            if csv_uploads > 1:
                raise ValueError("Upload exactly one CSV file.")
            fields["csvData"] = value
        elif name not in fields:
            if name in NUMERIC_FORM_FIELDS:
                try:
                    fields[name] = json.loads(
                        value, parse_constant=_reject_json_constant
                    )
                except (ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"Multipart field {name} must be a JSON number."
                    ) from exc
            else:
                fields[name] = value
        else:
            raise ValueError(f"Multipart field {name} must not be repeated.")

    if csv_uploads != 1:
        raise ValueError("A CSV file is required in the csvFile field.")
    fields.setdefault("mode", "what-if")
    return fields


def _prepare_request_data(data: dict[str, Any]) -> dict[str, Any]:
    validated = validate_request(data)
    if validated["mode"] != "connected" and "csvData" in validated:
        validated["baselineHourlyCosts"] = parse_hourly_cost_csv(
            validated.pop("csvData")
        )
        validated = validate_request(validated)
    return validated


def _require_authenticated_user(req: func.HttpRequest):
    if (
        os.getenv("REQUIRE_AUTHENTICATION", "false").lower() == "true"
        and not req.headers.get("X-MS-CLIENT-PRINCIPAL-ID")
    ):
        _log_event(
            logging.WARNING,
            "savings_plan_authentication_required",
            "Unauthenticated request rejected",
        )
        return _json_response({"error": "Authentication is required."}, 401)
    return None


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(_: func.HttpRequest) -> func.HttpResponse:
    return _json_response({"status": "ok", "service": "Azure Savings Plan Advisor"})


def _analyze_data(
    req: func.HttpRequest, data: dict[str, Any]
) -> func.HttpResponse:
    authenticated = _require_authenticated_user(req)
    if authenticated is not None:
        return authenticated

    try:
        request = _prepare_request_data(data)
        mode = request["mode"]
        if mode == "connected":
            if (
                os.getenv("AZURE_AUTH_MODE", "obo").lower() != "developer"
                and not req.headers.get("Authorization")
            ):
                return _json_response(
                    {"error": "An authenticated Azure user session is required."},
                    401,
                )
            result = get_benefit_recommendations(
                scope=request["scope"],
                term=request["term"],
                lookback=request["lookbackPeriod"],
                recommendation_scope=request["recommendationScope"],
                authorization_header=req.headers.get("Authorization"),
            )
            _log_event(
                logging.INFO,
                "savings_plan_analysis_completed",
                "Savings plan analysis completed",
                mode=mode,
            )
            return _json_response(
                {"mode": "connected", "result": result}
            )

        if mode == "comparison":
            result = calculate_comparison(request)
            _log_event(
                logging.INFO,
                "savings_plan_analysis_completed",
                "Savings plan analysis completed",
                mode=mode,
            )
            return _json_response(result)

        result = calculate_forecast(ForecastRequest.from_dict(request))
        _log_event(
            logging.INFO,
            "savings_plan_analysis_completed",
            "Savings plan analysis completed",
            mode=mode,
        )
        return _json_response(result)
    except ValueError as exc:
        _log_event(
            logging.INFO,
            "savings_plan_request_rejected",
            "Savings plan request rejected",
            error_type=type(exc).__name__,
        )
        return _json_response({"error": str(exc)}, 400)
    except ConnectedProviderError as exc:
        _log_event(
            logging.ERROR,
            "azure_cost_management_request_failed",
            "Azure Cost Management request failed",
            error_type=type(exc).__name__,
        )
        return _json_response(
            {
                "error": (
                    "Azure Cost Management could not complete the request. "
                    "Check the sign-in, billing scope permissions, and service status."
                )
            },
            502,
        )
    except Exception as exc:
        _log_event(
            logging.ERROR,
            "savings_plan_analysis_failed",
            "Savings plan analysis failed",
            error_type=type(exc).__name__,
        )
        return _json_response(
            {"error": "Analysis failed. See application diagnostics."}, 500
        )


@app.route(
    route="analyze-savings-plan",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def analyze(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _analyze_data(req, _read_json_request(req))
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 400)


@app.route(
    route="analyze-savings-plan-csv",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def analyze_csv(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = _read_multipart_request(req)
        return _analyze_data(req, data)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 400)
