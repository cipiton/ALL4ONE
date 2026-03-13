"""OpenRouter chat completions client."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

from engine.models import ChatMessage, LLMConfig, LLMResult


class LLMClientError(RuntimeError):
    """Readable exception for provider and configuration failures."""


def load_env_file(env_path: Path) -> None:
    """Load a local .env file into the environment if present."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_config_from_env() -> LLMConfig:
    """Read and validate OpenRouter settings."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENROUTER_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip()
    base_url = (
        os.getenv("OPENROUTER_BASE_URL", "").strip()
        or os.getenv("OPENAI_BASE_URL", "").strip()
        or "https://openrouter.ai/api/v1"
    )

    missing = [name for name, value in {"OPENROUTER_API_KEY": api_key, "OPENROUTER_MODEL": model}.items() if not value]
    if missing:
        raise LLMClientError(f"Missing required environment variables: {', '.join(missing)}.")

    return LLMConfig(api_key=api_key, base_url=base_url, model=model)


def call_chat_completion(config: LLMConfig, messages: list[ChatMessage]) -> LLMResult:
    """Call OpenRouter's chat completions endpoint."""
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": config.model,
        "messages": [message.to_dict() for message in messages],
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title

    http_request = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=120) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise LLMClientError("Authentication failed. Check OPENROUTER_API_KEY.") from exc
        raise LLMClientError(f"OpenRouter returned HTTP {exc.code}: {response_body}") from exc
    except error.URLError as exc:
        raise LLMClientError(f"Could not reach OpenRouter: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMClientError(f"Unexpected OpenRouter client error: {exc}") from exc

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise LLMClientError("OpenRouter returned invalid JSON.") from exc

    output_text = _extract_output_text(response_json)
    if not output_text.strip():
        raise LLMClientError("The model returned an empty response.")

    return LLMResult(
        text=output_text,
        model=str(response_json.get("model", config.model)),
        raw_response=response_json,
    )


def _extract_output_text(response_json: dict) -> str:
    """Extract assistant text from an OpenRouter response payload."""
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""
