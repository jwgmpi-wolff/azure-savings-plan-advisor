import json
import os
import subprocess
import sys
import threading
import time
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


@pytest.mark.skipif(os.name != "nt", reason="Windows MSI process configuration")
def test_msi_runner_calls_python_directly_so_cancellation_cannot_orphan_a_shell_child(monkeypatch, tmp_path):
    launcher = tmp_path / "wbin" / "az.cmd"
    launcher.parent.mkdir()
    launcher.write_text("synthetic launcher")
    runtime = tmp_path / "python.exe"
    runtime.write_bytes(b"synthetic executable fixture")
    monkeypatch.setattr(desktop_identity.shutil, "which", lambda _: str(launcher))
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b"{}", b""))
    monkeypatch.setattr(desktop_identity.subprocess, "run", run)
    environment = {"SYNTHETIC_OPTION": "value"}
    run_cli(["account", "show"], timeout=60, env=environment)
    assert run.call_args.args[0] == [str(runtime), "-IBm", "azure.cli", "account", "show"]
    assert run.call_args.kwargs["env"] == {**environment, "AZ_INSTALLER": "MSI"}
    assert environment == {"SYNTHETIC_OPTION": "value"}


def test_cancelled_operation_does_not_start_a_cli_process(monkeypatch):
    event = threading.Event()
    event.set()
    popen = Mock()
    monkeypatch.setattr(desktop_identity.subprocess, "Popen", popen)
    with pytest.raises(ClientAuthenticationError, match="cancelled"):
        run_cli(["login"], timeout=300, cancel_event=event)
    popen.assert_not_called()


@pytest.mark.parametrize("reason", ["cancel", "timeout"])
def test_waiting_login_is_killed_and_reaped_on_cancel_or_timeout(monkeypatch, reason):
    event = threading.Event()
    monkeypatch.setattr(desktop_identity.shutil, "which", lambda _: sys.executable)
    process = Mock()
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    process.poll.return_value = None

    def communicate(**_kwargs):
        if process.kill.called:
            return b"", b"synthetic-private-diagnostic"
        event.set()
        raise subprocess.TimeoutExpired("synthetic-cli", 0.2)

    process.communicate.side_effect = communicate
    popen = Mock(return_value=process)
    monkeypatch.setattr(desktop_identity.subprocess, "Popen", popen)
    if reason == "timeout":
        monkeypatch.setattr(desktop_identity.time, "monotonic", Mock(side_effect=[0, 301]))
    with pytest.raises(ClientAuthenticationError, match="cancelled" if reason == "cancel" else "timed out") as error:
        run_cli(["login"], timeout=300, cancel_event=event)
    process.kill.assert_called_once()
    assert process.communicate.call_args.kwargs["timeout"] == 5
    assert "private" not in str(error.value)
    assert popen.call_args.kwargs["stdin"] == subprocess.DEVNULL
    assert popen.call_args.kwargs["stdout"] == subprocess.PIPE


def test_cancellable_cli_returns_output_without_killing_completed_process(monkeypatch):
    monkeypatch.setattr(desktop_identity.shutil, "which", lambda _: sys.executable)
    process = Mock()
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    process.returncode = 0
    process.poll.return_value = 0
    process.communicate.return_value = (b"{}", b"")
    monkeypatch.setattr(desktop_identity.subprocess, "Popen", Mock(return_value=process))
    result = run_cli(["account", "show"], timeout=60, cancel_event=threading.Event())
    assert result.returncode == 0
    assert result.stdout == b"{}"
    process.kill.assert_not_called()


def test_cancellation_reaps_a_real_waiting_cli_process(monkeypatch):
    event = threading.Event()
    created = []
    original_popen = subprocess.Popen

    def record_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(desktop_identity.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(desktop_identity.subprocess, "Popen", record_process)
    timer = threading.Timer(0.3, event.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ClientAuthenticationError, match="cancelled"):
            run_cli(["-c", "import time; time.sleep(30)"], timeout=10, cancel_event=event)
    finally:
        timer.join(timeout=2)
    assert time.monotonic() - started < 5
    assert len(created) == 1
    assert created[0].poll() is not None
