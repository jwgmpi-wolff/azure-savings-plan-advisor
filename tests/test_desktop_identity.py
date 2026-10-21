import json
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.core.exceptions import ClientAuthenticationError

from api import desktop_identity
from api.azure_provider import MANAGEMENT_RESOURCE
from api.desktop_identity import SilentAzureCliCredential, run_cli


TENANT = "00000000-0000-0000-0000-000000000001"


@pytest.mark.skipif(os.name != "nt", reason="Windows process configuration")
def test_every_cli_operation_hides_console_and_disconnects_stdin(monkeypatch):
    monkeypatch.setattr(desktop_identity.shutil, "which", lambda _: "az.cmd")
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=b"{}"))
    monkeypatch.setattr(desktop_identity.subprocess, "run", run)
    run_cli(["account", "show"], timeout=60)
    arguments, options = run.call_args
    assert arguments[0] == ["az.cmd", "account", "show"]
    assert options["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert options["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert options["startupinfo"].wShowWindow == subprocess.SW_HIDE
    assert options["stdin"] == subprocess.DEVNULL
    assert options["capture_output"] is True
    assert not options.get("shell", False)


def test_token_uses_hidden_runner_and_explicit_tenant(monkeypatch):
    run = Mock(return_value=SimpleNamespace(
        returncode=0, stdout=json.dumps({"accessToken": "synthetic-token", "expires_on": 2000000000}).encode(),
    ))
    monkeypatch.setattr(desktop_identity, "run_cli", run)
    with SilentAzureCliCredential(tenant_id=TENANT) as credential:
        token = credential.get_token(MANAGEMENT_RESOURCE)
    assert token.token == "synthetic-token"
    assert token.expires_on == 2000000000
    arguments = run.call_args.args[0]
    assert arguments[:2] == ["account", "get-access-token"]
    assert arguments[arguments.index("--tenant") + 1] == TENANT


@pytest.mark.parametrize("output,code", [
    ({"accessToken": "synthetic-secret"}, 0),
    ({"accessToken": "synthetic-secret", "expires_on": False}, 0),
    ({"accessToken": "", "expires_on": 2000000000}, 0),
    ([], 0),
    ({"accessToken": "synthetic-secret"}, 1),
])
def test_token_errors_never_expose_cli_output(monkeypatch, output, code):
    monkeypatch.setattr(desktop_identity, "run_cli", lambda *args, **kwargs: SimpleNamespace(
        returncode=code, stdout=json.dumps(output).encode(),
    ))
    with pytest.raises(ClientAuthenticationError) as failure:
        SilentAzureCliCredential(tenant_id=TENANT).get_token(MANAGEMENT_RESOURCE)
    assert "synthetic-secret" not in str(failure.value)


def test_tenant_and_scope_cannot_be_overridden(monkeypatch):
    run = Mock()
    monkeypatch.setattr(desktop_identity, "run_cli", run)
    credential = SilentAzureCliCredential(tenant_id=TENANT)
    with pytest.raises(ClientAuthenticationError):
        credential.get_token(MANAGEMENT_RESOURCE, tenant_id="00000000-0000-0000-0000-000000000002")
    with pytest.raises(ClientAuthenticationError):
        credential.get_token("https://unexpected.invalid/.default")
    run.assert_not_called()
