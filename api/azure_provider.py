from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from urllib.parse import urlsplit

import requests
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, OnBehalfOfCredential

from .models import LOOKBACK_PERIODS, RECOMMENDATION_SCOPES, TERMS

API_VERSION = "2026-06-01"
MANAGEMENT_RESOURCE = "https://management.azure.com/.default"
_SCOPE_PATTERN = re.compile(
    r"/(?:subscriptions/[A-Za-z0-9-]{36}"
    r"|providers/Microsoft\.Billing/billingAccounts/[A-Za-z0-9._-]+"
    r"(?:/(?:billingProfiles|invoiceSections|billingSubscriptions)/[A-Za-z0-9._-]+)*"
    r"|providers/Microsoft\.Management/managementGroups/[A-Za-z0-9._-]+)"
)
_DETAIL_FIELDS = (
    "averageUtilizationPercentage",
    "benefitCost",
    "commitmentAmount",
    "coveragePercentage",
    "overageCost",
    "savingsAmount",
    "savingsPercentage",
    "totalCost",
    "wastageCost",
)
_PROPERTY_FIELDS = (
    "armSkuName",
    "commitmentGranularity",
    "costWithoutBenefit",
    "currencyCode",
    "firstConsumptionDate",
    "lastConsumptionDate",
    "lookBackPeriod",
    "scope",
    "term",
    "totalHours",
)


class ConnectedProviderError(Exception):
    """A sanitized error communicating with Azure Cost Management."""

    def __init__(self, message: str, status: str = "unavailable") -> None:
        super().__init__(message)
        self.status = status


def arm_list(
    url: str, token: str, params: dict[str, str], source: str,
) -> list[dict[str, Any]]:
    expected = urlsplit(url)
    items: list[dict[str, Any]] = []
    visited: set[str] = set()
    while url:
        target = urlsplit(url)
        if (
            target.scheme != "https"
            or target.netloc != "management.azure.com"
            or target.path.rstrip("/").lower() != expected.path.rstrip("/").lower()
            or target.fragment
            or url in visited
            or len(visited) >= 100
        ):
            raise ConnectedProviderError(f"{source} returned an unsafe or excessive continuation.")
        visited.add(url)
        try:
            response = requests.get(
                url, params=params, headers={"Authorization": "Bearer " + token},
                timeout=60, allow_redirects=False,
            )
            status = getattr(response, "status_code", 200)
            if status in (401, 403):
                raise ConnectedProviderError(
                    f"{source}: access denied (HTTP {status}). Sign in to the selected tenant "
                    "and request the required read permission at the selected scope.",
                    status="denied",
                )
            if status == 404:
                raise ConnectedProviderError(
                    f"{source}: unavailable at this scope (HTTP 404). Check API and billing eligibility.",
                    status="unsupported",
                )
            if status == 429:
                raise ConnectedProviderError(f"{source}: throttled (HTTP 429). Retry later.")
            if 300 <= status < 400:
                raise ConnectedProviderError(f"{source} returned an unsupported redirect.")
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ConnectedProviderError(f"{source} is unavailable. Retry or check your network and Azure service status.") from exc
        except ValueError as exc:
            raise ConnectedProviderError(f"{source} returned invalid JSON.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise ConnectedProviderError(f"{source} returned an unexpected response shape.")
        if any(not isinstance(item, dict) for item in payload["value"]):
            raise ConnectedProviderError(f"{source} returned malformed records.")
        items.extend(payload["value"])
        next_link = payload.get("nextLink")
        if next_link is not None and not isinstance(next_link, str):
            raise ConnectedProviderError(f"{source} returned an invalid continuation.")
        url = next_link or ""
        params = {}
    return items


def _safe_primitive(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, (str, int, bool))
        or isinstance(value, float)
        and isfinite(value)
    )


def _validate_scope(scope: str) -> str:
    if not isinstance(scope, str) or not _SCOPE_PATTERN.fullmatch(scope):
        raise ValueError(
            "scope must be a supported Azure subscription, billing, or "
            "management-group resource ID."
        )
    if any(segment in {".", ".."} for segment in scope.split("/")):
        raise ValueError("scope contains an invalid resource path.")
    return scope


def _authorization_token(authorization_header: str | None) -> str:
    auth_mode = os.getenv("AZURE_AUTH_MODE", "obo").lower()
    if auth_mode == "developer":
        credential = DefaultAzureCredential()
        try:
            return credential.get_token(MANAGEMENT_RESOURCE).token
        finally:
            credential.close()
    if auth_mode != "obo":
        raise ValueError("AZURE_AUTH_MODE must be 'obo' or 'developer'.")

    if not authorization_header:
        raise ValueError("An authenticated bearer token is required.")
    scheme, separator, assertion = authorization_header.partition(" ")
    if not separator or scheme.lower() != "bearer" or not assertion.strip():
        raise ValueError("A valid bearer token is required.")

    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    if not tenant_id or not client_id or not client_secret:
        raise RuntimeError(
            "On-behalf-of authentication is not configured."
        )
    credential = OnBehalfOfCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        user_assertion=assertion.strip(),
    )
    try:
        return credential.get_token(MANAGEMENT_RESOURCE).token
    finally:
        credential.close()


def _safe_details(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("value"), list):
        candidates = [
            item for item in value["value"] if isinstance(item, dict)
        ]
    elif isinstance(value, dict):
        candidates = [value]
    elif isinstance(value, list):
        candidates = [item for item in value if isinstance(item, dict)]
    else:
        return []

    return [
        {
            key: item[key]
            for key in _DETAIL_FIELDS
            if key in item
            and _safe_primitive(item[key])
        }
        for item in candidates
    ]


def _normalize_recommendation(item: dict[str, Any]) -> dict[str, Any]:
    properties = item.get("properties")
    if not isinstance(properties, dict):
        properties = {}

    normalized: dict[str, Any] = {
        key: properties[key]
        for key in _PROPERTY_FIELDS
        if key in properties
        and _safe_primitive(properties[key])
    }
    if isinstance(item.get("kind"), str):
        normalized["kind"] = item["kind"]
    if isinstance(item.get("id"), str):
        normalized["recommendationReference"] = hashlib.sha256(
            item["id"].encode("utf-8")
        ).hexdigest()[:16]

    recommendation_details = _safe_details(
        properties.get("recommendationDetails")
    )
    if recommendation_details:
        normalized["recommendationDetails"] = recommendation_details[0]
    alternatives = _safe_details(properties.get("allRecommendationDetails"))
    if alternatives:
        normalized["alternatives"] = alternatives
    return normalized


def get_benefit_recommendations(
    scope: str,
    term: str,
    lookback: str,
    recommendation_scope: str,
    authorization_header: str | None = None,
    *,
    credential: TokenCredential | None = None,
) -> dict[str, Any]:
    scope = _validate_scope(scope)
    if term not in TERMS:
        raise ValueError(f"term must be one of: {', '.join(TERMS)}.")
    if lookback not in LOOKBACK_PERIODS:
        raise ValueError(
            f"lookbackPeriod must be one of: {', '.join(LOOKBACK_PERIODS)}."
        )
    if recommendation_scope not in RECOMMENDATION_SCOPES:
        raise ValueError(
            "recommendationScope must be Single or Shared."
        )

    token = (
        credential.get_token(MANAGEMENT_RESOURCE).token
        if credential is not None else _authorization_token(authorization_header)
    )
    url = (
        f"https://management.azure.com{scope}"
        "/providers/Microsoft.CostManagement/benefitRecommendations"
    )
    params = {
        "api-version": API_VERSION,
        "$filter": (
            f"properties/scope eq '{recommendation_scope}' AND "
            f"properties/lookBackPeriod eq '{lookback}' AND "
            f"properties/term eq '{term}'"
        ),
        "$expand": "properties/allRecommendationDetails",
    }
    items = arm_list(url, token, params, "Azure Cost Management")
    recommendations = [
        _normalize_recommendation(item)
        for item in items
        if isinstance(item, dict) and item.get("kind") == "SavingsPlan"
    ]
    return {
        "source": "Azure Cost Management Benefit Recommendations API",
        "apiVersion": API_VERSION,
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "filters": {
            "term": term,
            "lookbackPeriod": lookback,
            "recommendationScope": recommendation_scope,
        },
        "recommendationCount": len(recommendations),
        "recommendations": recommendations,
        "notice": (
            "Recommendations below were returned by Azure Cost Management. "
            "Review the recommendation and its assumptions before purchase."
            if recommendations
            else "Azure Cost Management returned no Savings Plan recommendations "
            "for these filters; no estimate was substituted."
        ),
    }
