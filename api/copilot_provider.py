from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import requests

from .compute_modeler import copilot_prompt
from .reporting import clean_text


AI_SOURCE = "Ollama (local)"
DEFAULT_MODEL = "llama3.1:8b"
_BASE_URL = "http://127.0.0.1:11434"


class CopilotError(RuntimeError):
    """A safe, user-facing AI connection or inference failure."""


def _post(client: requests.Session, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    response = client.post(
        _BASE_URL + path, json=payload, timeout=(3, timeout), allow_redirects=False,
    )
    if path == "/api/show" and response.status_code == 404:
        raise CopilotError(
            "The selected local model is not installed. Run 'ollama list' and enter an installed "
            "chat model name, or install a model through your organization's approved process."
        )
    if response.status_code != 200:
        raise CopilotError(
            f"The local AI service returned HTTP {response.status_code}. Check Ollama and retry Ask AI. "
            "No AI explanation is available; calculated reference figures are unchanged."
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise CopilotError("The local AI service returned invalid JSON. Check Ollama and retry Ask AI.") from exc
    if not isinstance(data, dict) or data.get("error"):
        raise CopilotError("The local AI service returned an invalid or failed response. Check Ollama and retry Ask AI.")
    return data


def explain_model(result: dict[str, Any], *, model: str = DEFAULT_MODEL) -> dict[str, str]:
    model = model.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model):
        raise CopilotError("Enter an installed local Ollama chat model name, such as llama3.1:8b.")
    if ":cloud" in model.casefold():
        raise CopilotError("Cloud models are not allowed by this local-only connection. Select an installed local model.")
    prompt = copilot_prompt(result)
    try:
        with requests.Session() as client:
            # Do not let proxy or netrc settings redirect local figures or add credentials.
            client.trust_env = False
            metadata = _post(client, "/api/show", {"model": model}, 10)
            model_info = metadata.get("model_info")
            if (
                metadata.get("remote_host") or metadata.get("remote_model")
                or not isinstance(model_info, dict) or not model_info
            ):
                raise CopilotError(
                    "The selected model could not be verified as local. Cloud or remote models are not "
                    "allowed; no financial figures were sent. Select an installed local chat model."
                )
            capabilities = metadata.get("capabilities")
            if not isinstance(capabilities, list) or "completion" not in capabilities:
                raise CopilotError("The selected model does not support chat completion. Select a local chat model.")
            response = _post(client, "/api/chat", {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": (
                        "Explain only the supplied Azure Savings Plan financial model. Preserve every "
                        "calculated figure exactly. Do not invent prices, perform new calculations, use "
                        "tools, access files or retrieve external information. Keep the answer concise."
                    )},
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": 0, "num_predict": 1024},
            }, 150)
    except requests.Timeout as exc:
        raise CopilotError(
            "Local AI timed out. Check that the selected model fits this PC's memory, then retry Ask AI. "
            "Calculated reference figures remain available."
        ) from exc
    except requests.ConnectionError as exc:
        raise CopilotError(
            "Cannot connect to local Ollama. Start Ollama on this PC (or run 'ollama serve'), "
            "then retry Ask AI. No Azure or GitHub sign-in is required."
        ) from exc
    except requests.RequestException as exc:
        logging.error("Local AI request failed", extra={"error_type": type(exc).__name__})
        raise CopilotError("The local AI request failed. Check Ollama and retry Ask AI.") from exc

    message = response.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if (
        response.get("done") is not True or response.get("done_reason") != "stop"
        or not isinstance(message, dict) or message.get("role") != "assistant"
        or message.get("tool_calls") or not isinstance(content, str) or not content.strip()
        or len(content) > 20000 or response.get("model") != model
    ):
        raise CopilotError(
            "Local AI returned no complete, verifiable explanation (it may have been truncated). "
            "Retry Ask AI or select another installed local chat model. Calculations are unchanged."
        )
    return {
        "status": "complete", "source": AI_SOURCE, "model": model,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "modelCollectedAt": result["collectedAt"],
        "explanation": clean_text(content.strip()),
    }
