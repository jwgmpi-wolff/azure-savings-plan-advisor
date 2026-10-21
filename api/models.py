from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator


TERMS = ("P1Y", "P3Y")
LOOKBACK_PERIODS = ("Last7Days", "Last30Days", "Last60Days")
RECOMMENDATION_SCOPES = ("Single", "Shared")
SCENARIOS = ("conservative", "balanced", "maximumSavings", "custom")

_COSTS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 26304,
    "items": {"type": "number", "minimum": 0, "maximum": 1000000000000},
}
_CURRENCY = {"type": "string", "pattern": "^[A-Z]{3}$"}
_DATA_PROPERTIES = {
    "mode": {"type": "string", "enum": ["what-if", "comparison", "connected"]},
    "currencyCode": _CURRENCY,
    "baselineHourlyCosts": _COSTS,
    "csvData": {"type": "string", "minLength": 1, "maxLength": 2000000},
    "expectedChangePercent": {
        "type": "number",
        "minimum": -100,
        "maximum": 10000,
    },
    "hourlyCommitment": {
        "type": "number",
        "minimum": 0,
        "maximum": 1000000000,
    },
    "scenario": {"type": "string", "enum": list(SCENARIOS)},
}

_SCHEMAS: dict[str, dict[str, Any]] = {
    "what-if": {
        "type": "object",
        "properties": {
            **_DATA_PROPERTIES,
            "term": {"type": "string", "enum": list(TERMS)},
            "hourlyCommitment": {
                "type": "number",
                "minimum": 0,
                "maximum": 1000000000,
            },
            "scenario": {"type": "string", "enum": list(SCENARIOS)},
            "discountPercent": {
                "type": "number",
                "minimum": 0,
                "exclusiveMaximum": 100,
            },
        },
        "required": [
            "mode",
            "term",
            "currencyCode",
            "expectedChangePercent",
            "discountPercent",
            "scenario",
        ],
        "anyOf": [
            {"required": ["baselineHourlyCosts"]},
            {"required": ["csvData"]},
        ],
        "additionalProperties": False,
    },
    "comparison": {
        "type": "object",
        "properties": {
            **_DATA_PROPERTIES,
            "discountPercentP1Y": {
                "type": "number",
                "minimum": 0,
                "exclusiveMaximum": 100,
            },
            "discountPercentP3Y": {
                "type": "number",
                "minimum": 0,
                "exclusiveMaximum": 100,
            },
        },
        "required": [
            "mode",
            "currencyCode",
            "expectedChangePercent",
            "discountPercentP1Y",
            "discountPercentP3Y",
        ],
        "anyOf": [
            {"required": ["baselineHourlyCosts"]},
            {"required": ["csvData"]},
        ],
        "additionalProperties": False,
    },
    "connected": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["what-if", "comparison", "connected"],
            },
            "scope": {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
            },
            "term": {"type": "string", "enum": list(TERMS)},
            "lookbackPeriod": {
                "type": "string",
                "enum": list(LOOKBACK_PERIODS),
            },
            "recommendationScope": {
                "type": "string",
                "enum": list(RECOMMENDATION_SCOPES),
            },
        },
        "required": [
            "mode",
            "scope",
            "term",
            "lookbackPeriod",
            "recommendationScope",
        ],
        "additionalProperties": False,
    },
}


def validate_request(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("The request body must be a JSON object.")

    normalized = dict(data)
    mode = str(normalized.get("mode", "")).lower()
    if mode not in _SCHEMAS:
        raise ValueError("mode must be what-if, comparison, or connected.")
    normalized["mode"] = mode

    if mode != "connected":
        if "baselineHourlyCosts" in normalized and "csvData" in normalized:
            raise ValueError(
                "Provide baselineHourlyCosts or csvData, not both."
            )

    errors = sorted(
        Draft202012Validator(_SCHEMAS[mode]).iter_errors(normalized),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        field = ".".join(str(part) for part in error.absolute_path) or "request"
        raise ValueError(f"Invalid {field}: {error.message}")
    return normalized


@dataclass(frozen=True)
class ForecastRequest:
    mode: str
    term: str
    lookback_period: str
    hourly_commitment: float | None
    baseline_hourly_costs: list[float]
    expected_change_percent: float
    discount_percent: float | None
    scope: str | None
    scenario: str = "balanced"
    currency_code: str = "USD"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ForecastRequest":
        normalized = validate_request(data)
        costs = [
            float(value)
            for value in normalized.get("baselineHourlyCosts", [])
        ]
        commitment = normalized.get("hourlyCommitment")
        discount = normalized.get("discountPercent")
        return ForecastRequest(
            mode=normalized["mode"],
            term=normalized["term"],
            lookback_period="Last30Days",
            hourly_commitment=(
                float(commitment) if commitment is not None else None
            ),
            baseline_hourly_costs=costs,
            expected_change_percent=float(normalized["expectedChangePercent"]),
            discount_percent=float(discount) if discount is not None else None,
            scope=normalized.get("scope"),
            scenario=normalized["scenario"],
            currency_code=normalized["currencyCode"],
        )
