from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from azure.core.exceptions import ClientAuthenticationError
from .desktop_identity import SilentAzureCliCredential, run_cli

from .azure_provider import (
    MANAGEMENT_RESOURCE,
    ConnectedProviderError,
    arm_list,
    get_benefit_recommendations,
)
from .models import LOOKBACK_PERIODS, TERMS

COMPUTE_SOURCES = (
    ("virtualMachines", "Microsoft.Compute/virtualMachines", "2024-07-01", "Virtual machine"),
    ("virtualMachineScaleSets", "Microsoft.Compute/virtualMachineScaleSets", "2024-07-01", "Virtual machine scale set"),
    ("appServicePlans", "Microsoft.Web/serverfarms", "2024-11-01", "App Service plan"),
)


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
        try:
            result = run_cli(
                ["account", "show", "--query", "{tenantId:tenantId,userType:user.type}",
                 "--output", "json", "--only-show-errors"],
                timeout=60,
            )
            if result.returncode:
                raise ConnectedProviderError("Sign in with Azure CLI as a user, then refresh context.")
            account = json.loads(result.stdout)
        except (ClientAuthenticationError, ValueError) as exc:
            raise ConnectedProviderError("Unable to read Azure CLI user context. Sign in again.") from exc
        if not isinstance(account, dict) or account.get("userType") != "user":
            raise ConnectedProviderError("The desktop app requires an interactive user account, not a service principal or managed identity.")
        return context_id(account.get("tenantId"))

    def sign_in(self, tenant_id: str) -> str:
        tenant_id = context_id(tenant_id) if tenant_id else ""
        self.clear()
        try:
            result = run_cli(
                ["login", *(["--tenant", tenant_id] if tenant_id else []),
                 "--allow-no-subscriptions", "--output", "none", "--only-show-errors"],
                timeout=300,
                env={
                    **os.environ,
                    "AZURE_CORE_LOGIN_EXPERIENCE_V2": "off",
                    "AZURE_CORE_ENABLE_BROKER_ON_WINDOWS": "false",
                },
            )
        except ClientAuthenticationError as exc:
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
            with SilentAzureCliCredential(tenant_id=tenant_id, process_timeout=60) as credential:
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
            "advisorRecommendations": [], "recommendations": [], "computeInventory": [],
            "notice": (
                "Read-only Azure recommendations for existing workloads; no CSV is required. "
                "Advisor returns cached Cost recommendations, typically with a 30-day Savings Plan lookback. "
                "Hourly commitment amounts come from Azure Cost Management Benefit Recommendations. "
                "Sources are not added together; Advisor cost actions are not all Savings Plans. "
                "No workload estimates or discounts are fabricated when Azure returns no recommendation."
            ),
        }
        try:
            with SilentAzureCliCredential(tenant_id=tenant_id, process_timeout=60) as credential:
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
                for key, resource_type, version, label in COMPUTE_SOURCES:
                    coverage: dict[str, Any] = {
                        "source": f"Azure Resource Manager {resource_type} List",
                        "apiVersion": version,
                    }
                    result["coverage"][key] = coverage
                    try:
                        items = arm_list(
                            f"https://management.azure.com{scope}/providers/{resource_type}",
                            token, {"api-version": version}, f"Azure {label} inventory",
                        )
                        inventory = [
                            _compute_record(item, subscription_id, resource_type, label, coverage["source"])
                            for item in items
                        ]
                        result["computeInventory"].extend(sorted(inventory, key=lambda item: item["resourceId"].lower()))
                        coverage.update({"status": "ok" if inventory else "empty", "count": len(inventory)})
                    except ConnectedProviderError as exc:
                        coverage.update({"status": exc.status, "message": str(exc)})
        except ClientAuthenticationError as exc:
            raise ConnectedProviderError("Azure authentication expired or was denied. Sign in again to the selected tenant.") from exc
        result["completeness"] = (
            "partial" if any(item["status"] not in ("ok", "empty") for item in result["coverage"].values()) else "complete"
        )
        return result

    def analyze_many(
        self, tenant_id: str, subscription_ids: list[str], term: str, lookback: str,
    ) -> dict[str, Any]:
        tenant_id = context_id(tenant_id)
        selected = sorted({context_id(value) for value in subscription_ids})
        if not selected:
            raise ValueError("Select at least one subscription.")
        if term not in TERMS or lookback not in LOOKBACK_PERIODS:
            raise ValueError("Select a valid Savings Plan term and lookback period.")
        self.refresh(tenant_id)
        names = {item["subscriptionId"]: item["name"] for item in self.subscriptions}
        if any(value not in names for value in selected):
            raise ValueError("A selected subscription is not enabled or accessible in the selected tenant. Refresh context.")
        result: dict[str, Any] = {
            "mode": "connected", "source": "Azure Advisor and Azure Cost Management",
            "collectedAt": datetime.now(timezone.utc).isoformat(),
            "context": {"tenantId": tenant_id, "subscriptionIds": selected},
            "filters": {"term": term, "lookbackPeriod": lookback, "recommendationScope": "Single"},
            "coverage": {}, "recommendations": [], "advisorRecommendations": [], "computeInventory": [],
            "notice": (
                "Each subscription is assessed independently at Single scope using existing Azure recommendations. "
                "No CSV is required. Commitments and savings are not added across subscriptions or alternatives. "
                "Advisor Cost actions are not all Savings Plans; hourly commitments come from Cost Management. "
                "Advisor uses cached recommendations; its Savings Plan lookback is typically 30 days. "
                "No estimate is substituted for denied, unavailable or empty data."
            ),
        }
        for subscription_id in selected:
            metadata = {"subscriptionId": subscription_id, "subscriptionName": names[subscription_id]}
            try:
                collected = self.analyze(tenant_id, subscription_id, term, lookback)
            except (ConnectedProviderError, ValueError) as exc:
                status = exc.status if isinstance(exc, ConnectedProviderError) else "unavailable"
                sources = (
                    ("advisor", "Azure Advisor", "2025-01-01"),
                    ("savingsPlan", "Azure Cost Management", "2026-06-01"),
                    *((key, f"Azure Resource Manager {resource_type} List", version)
                      for key, resource_type, version, _label in COMPUTE_SOURCES),
                )
                for source, name, version in sources:
                    result["coverage"][f"{subscription_id}/{source}"] = {
                        **metadata, "status": status, "message": str(exc),
                        "source": name, "apiVersion": version,
                    }
                continue
            for key in ("recommendations", "advisorRecommendations", "computeInventory"):
                result[key].extend({**item, **metadata} for item in collected.get(key, []))
            for source, coverage in collected["coverage"].items():
                result["coverage"][f"{subscription_id}/{source}"] = {
                    **coverage, **metadata, "collectedAt": collected["collectedAt"],
                }
        result["completeness"] = (
            "partial" if any(item["status"] not in ("ok", "empty") for item in result["coverage"].values()) else "complete"
        )
        return result


def _compute_record(
    item: dict[str, Any], subscription_id: str, resource_type: str, label: str, source: str,
) -> dict[str, Any]:
    resource_id = item.get("id")
    properties = item.get("properties")
    if (
        not isinstance(resource_id, str)
        or not resource_id.lower().startswith(f"/subscriptions/{subscription_id}/resourcegroups/".lower())
        or str(item.get("type", "")).lower() != resource_type.lower()
        or not isinstance(properties, dict)
    ):
        raise ConnectedProviderError(f"Azure {label} inventory returned malformed or out-of-scope resource metadata.")
    profile = properties.get("hardwareProfile") if resource_type == "Microsoft.Compute/virtualMachines" else item.get("sku")
    sku = profile.get("vmSize" if resource_type == "Microsoft.Compute/virtualMachines" else "name") if isinstance(profile, dict) else None
    vm_profile = properties.get("virtualMachineProfile") if resource_type == "Microsoft.Compute/virtualMachineScaleSets" else properties
    license_type = vm_profile.get("licenseType") if isinstance(vm_profile, dict) else None
    return {
        "resourceId": resource_id,
        "recommendationReference": hashlib.sha256(resource_id.lower().encode()).hexdigest()[:16],
        "name": item.get("name") if isinstance(item.get("name"), str) else None,
        "computeType": label, "computeSku": sku if isinstance(sku, str) else None,
        "licenseType": license_type if isinstance(license_type, str) else None,
        "source": source,
    }


def _advisor_record(item: dict[str, Any]) -> dict[str, Any]:
    properties = item.get("properties")
    if not isinstance(properties, dict):
        raise ConnectedProviderError("Azure Advisor returned malformed recommendation properties.")
    description = properties.get("shortDescription") or {}
    if not isinstance(description, dict):
        raise ConnectedProviderError("Azure Advisor returned a malformed description.")
    resource_metadata = properties.get("resourceMetadata")
    resource_id = resource_metadata.get("resourceId") if isinstance(resource_metadata, dict) else None
    return {
        "recommendationReference": hashlib.sha256(str(item.get("id", "")).encode()).hexdigest()[:16],
        "category": properties.get("category"),
        "impact": properties.get("impact"),
        "lastUpdated": properties.get("lastUpdated"),
        "problem": description.get("problem"),
        "solution": description.get("solution"),
        "resourceId": resource_id if isinstance(resource_id, str) else None,
    }
