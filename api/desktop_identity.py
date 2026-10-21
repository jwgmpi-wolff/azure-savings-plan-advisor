from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any
from uuid import UUID

from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import AzureCliCredential

from .azure_provider import MANAGEMENT_RESOURCE


def run_cli(arguments: list[str], timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    executable = shutil.which("az")
    if not executable:
        raise ClientAuthenticationError("Install Azure CLI, then restart the app.")
    options: dict[str, Any] = {
        "capture_output": True, "stdin": subprocess.DEVNULL,
        "timeout": timeout, "check": False,
    }
    if env is not None:
        options["env"] = env
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = startup
    try:
        return subprocess.run([executable, *arguments], **options)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClientAuthenticationError(
            "Azure CLI could not complete the operation. Retry sign-in or check your CLI installation."
        ) from exc


class SilentAzureCliCredential(AzureCliCredential):
    """Use the CLI user session without the SDK's visible Windows shell."""

    def __init__(self, *, tenant_id: str, process_timeout: int = 60) -> None:
        self.selected_tenant = str(UUID(tenant_id))
        self.timeout = process_timeout
        super().__init__(tenant_id=self.selected_tenant, process_timeout=process_timeout)

    def get_token(
        self, *scopes: str, claims: str | None = None, tenant_id: str | None = None,
        enable_cae: bool = False, **kwargs: Any,
    ) -> AccessToken:
        if scopes != (MANAGEMENT_RESOURCE,) or claims or enable_cae or kwargs:
            raise ClientAuthenticationError("Only standard Azure Resource Manager user tokens are supported.")
        if tenant_id is not None and str(UUID(tenant_id)) != self.selected_tenant:
            raise ClientAuthenticationError("Token tenant does not match the selected context.")
        response = run_cli([
            "account", "get-access-token", "--resource", "https://management.azure.com",
            "--tenant", self.selected_tenant, "--output", "json", "--only-show-errors",
        ], timeout=self.timeout)
        if response.returncode:
            raise ClientAuthenticationError(
                "Azure user authentication was denied or expired. Sign in again to the selected tenant."
            )
        try:
            payload = json.loads(response.stdout)
            token = payload["accessToken"]
            expiration = payload["expires_on"]
            if not isinstance(token, str) or not token or isinstance(expiration, bool):
                raise ValueError("Invalid token response")
            expiration = int(expiration)
            if expiration <= 0:
                raise ValueError("Invalid token expiration")
        except (ValueError, KeyError, TypeError) as exc:
            raise ClientAuthenticationError(
                "Azure CLI returned an unsupported token response. Update Azure CLI and sign in again."
            ) from exc
        return AccessToken(token, expiration)
