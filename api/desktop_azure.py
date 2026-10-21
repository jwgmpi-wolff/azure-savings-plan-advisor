from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import AzureCliCredential

from .azure_provider import (
    MANAGEMENT_RESOURCE,
    ConnectedProviderError,
    arm_list,
    get_benefit_recommendations,
)
from .models import LOOKBACK_PERIODS, TERMS


def context_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Enter a valid tenant or subscription GUID.") from exc


class DesktopAzure:
    """Delegated CLI user identity only; never falls back to a hosting identity."""

    def __init__(self) -> None:
        self.tenant_id: str | None = None
        self.subscriptions: list[dict[str, str]] = []

    def clear(self) -> None:
        self.tenant_id = None
        self.subscriptions = []

    def current_tenant(self) -> str:
        executable = shutil.which("az")
        if not executable:
            raise ValueError("Install Azure CLI from the README, then restart the app.")
        try:
            result = subprocess.run(
                [executable, "account", "show", "--query", "{tenantId:tenantId,userType:user.type}",
                 "--output", "json", "--only-show-errors"],
                capture_output=True, timeout=60, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise ConnectedProviderError("Sign in with Azure CLI as a user, then refresh context.")
            account = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise ConnectedProviderError("Unable to read Azure CLI user context. Sign in again.") from exc
        if not isinstance(account, dict) or account.get("userType") != "user":
            raise ConnectedProviderError("The desktop app requires an interactive user account, not a service principal or managed identity.")
        return context_id(account.get("tenantId"))

    def sign_in(self, tenant_id: str) -> str:
        tenant_id = context_id(tenant_id) if tenant_id else ""
        self.clear()
        executable = shutil.which("az")
        if not executable:
            raise ValueError("Install Azure CLI from the README, then restart the app to sign in.")
        try:
            result = subprocess.run(
                [executable, "login", * (["--tenant", tenant_id] if tenant_id else []),
                 "--allow-no-subscriptions", "--output", "none", "--only-show-errors"],
                capture_output=True, timeout=300, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env={
                    **os.environ,
                    "AZURE_CORE_LOGIN_EXPERIENCE_V2": "off",
                    "AZURE_CORE_ENABLE_BROKER_ON_WINDOWS": "false",
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ConnectedProviderError("Azure sign-in could not complete. Retry sign-in in the selected tenant.") from exc
        if result.returncode:
            raise ConnectedProviderError(
                "Azure sign-in was cancelled or denied. Check tenant membership and Conditional Access. "
                "If necessary, run az login --tenant <tenant> in PowerShell, then use Refresh context."
            )
        current_tenant = self.current_tenant()
        self.tenant_id = tenant_id or current_tenant
        return self.tenant_id

    def refresh(self, tenant_id: str) -> dict[str, Any]:
        self.clear()
        current_tenant = self.current_tenant()
        tenant_id = context_id(tenant_id) if tenant_id else current_tenant
        try:
            with AzureCliCredential(tenant_id=tenant_id, process_timeout=60) as credential:
                token = credential.get_token(MANAGEMENT_RESOURCE).token
                tenants = arm_list(
                    "https://management.azure.com/tenants", token,
                    {"api-version": "2022-12-01"}, "Azure tenant discovery",
                )
                if not any(item.get("tenantId", "").lower() == tenant_id for item in tenants):
                    raise ConnectedProviderError("The selected tenant is not available to the signed-in identity.")
                subscriptions = arm_list(
                    "https://management.azure.com/subscriptions", token,
                    {"api-version": "2022-12-01"}, "Azure subscription discovery",
                )
        except ClientAuthenticationError as exc:
            raise ConnectedProviderError("Sign in to the selected tenant with Azure CLI, then refresh context.") from exc
        available = []
        for item in subscriptions:
            if item.get("tenantId", "").lower() != tenant_id or item.get("state") != "Enabled":
                continue
            subscription_id = context_id(item.get("subscriptionId"))
            available.append({
                "subscriptionId": subscription_id,
                "name": str(item.get("displayName") or "Unnamed subscription"),
            })
        self.tenant_id = tenant_id
        self.subscriptions = sorted(available, key=lambda item: (item["name"], item["subscriptionId"]))
        return {
            "tenantId": tenant_id,
            "tenants": sorted(
                [context_id(item["tenantId"]) for item in tenants if isinstance(item.get("tenantId"), str)]
            ),
            "subscriptions": self.subscriptions,
        }

    def analyze(self, tenant_id: str, subscription_id: str, term: str, lookback: str) -> dict[str, Any]:
        tenant_id = context_id(tenant_id)
        subscription_id = context_id(subscription_id)
        if term not in TERMS or lookback not in LOOKBACK_PERIODS:
            raise ValueError("Select a valid Savings Plan term and lookback period.")
        # Re-enumerate membership on every collection, not just when the UI signed in.
        self.refresh(tenant_id)
        if not any(item["subscriptionId"] == subscription_id for item in self.subscriptions):
            raise ValueError("The selected subscription is not enabled or accessible in the selected tenant.")
        scope = f"/subscriptions/{subscription_id}"
        result: dict[str, Any] = {
            "mode": "connected", "source": "Azure Advisor and Azure Cost Management",
            "collectedAt": datetime.now(timezone.utc).isoformat(),
            "context": {"tenantId": tenant_id, "subscriptionId": subscription_id},
            "filters": {"term": term, "lookbackPeriod": lookback, "recommendationScope": "Single"},
            "coverage": {
                "advisor": {"source": "Azure Advisor Recommendations API", "apiVersion": "2025-01-01"},
                "savingsPlan": {"source": "Azure Cost Management Benefit Recommendations API", "apiVersion": "2026-06-01"},
            },
            "advisorRecommendations": [], "recommendations": [],
            "notice": (
                "Read-only Azure recommendations for existing workloads; no CSV is required. "
                "Advisor returns cached Cost recommendations, typically with a 30-day Savings Plan lookback. "
                "Hourly commitment amounts come from Azure Cost Management Benefit Recommendations. "
                "Sources are not added together; Advisor cost actions are not all Savings Plans. "
                "No workload estimates or discounts are fabricated when Azure returns no recommendation."
            ),
        }
        try:
            with AzureCliCredential(tenant_id=tenant_id, process_timeout=60) as credential:
                token = credential.get_token(MANAGEMENT_RESOURCE).token
                try:
                    items = arm_list(
                        f"https://management.azure.com{scope}/providers/Microsoft.Advisor/recommendations",
                        token, {"api-version": "2025-01-01", "$filter": "Category eq 'Cost'"},
                        "Azure Advisor",
                    )
                    result["advisorRecommendations"] = [_advisor_record(item) for item in items]
                    result["coverage"]["advisor"].update({
                        "status": "ok" if items else "empty", "count": len(items),
                        "source": "Azure Advisor Recommendations API", "apiVersion": "2025-01-01",
                    })
                except ConnectedProviderError as exc:
                    result["coverage"]["advisor"].update({"status": exc.status, "message": str(exc)})
                try:
                    benefit = get_benefit_recommendations(
                        scope, term, lookback, "Single", credential=credential,
                    )
                    result["recommendations"] = benefit["recommendations"]
                    result["coverage"]["savingsPlan"].update({
                        "status": "ok" if benefit["recommendations"] else "empty",
                        "count": benefit["recommendationCount"], "source": benefit["source"],
                        "apiVersion": benefit["apiVersion"], "message": benefit["notice"],
                    })
                except ConnectedProviderError as exc:
                    result["coverage"]["savingsPlan"].update({"status": exc.status, "message": str(exc)})
        except ClientAuthenticationError as exc:
            raise ConnectedProviderError("Azure authentication expired or was denied. Sign in again to the selected tenant.") from exc
        result["completeness"] = (
            "partial" if any(item["status"] not in ("ok", "empty") for item in result["coverage"].values()) else "complete"
        )
        return result


def _advisor_record(item: dict[str, Any]) -> dict[str, Any]:
    properties = item.get("properties")
    if not isinstance(properties, dict):
        raise ConnectedProviderError("Azure Advisor returned malformed recommendation properties.")
    description = properties.get("shortDescription") or {}
    if not isinstance(description, dict):
        raise ConnectedProviderError("Azure Advisor returned a malformed description.")
    return {
        "recommendationReference": hashlib.sha256(str(item.get("id", "")).encode()).hexdigest()[:16],
        "category": properties.get("category"),
        "impact": properties.get("impact"),
        "lastUpdated": properties.get("lastUpdated"),
        "problem": description.get("problem"),
        "solution": description.get("solution"),
    }
