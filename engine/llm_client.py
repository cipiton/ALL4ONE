from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib import error, request

from .models import LLMConfig, LLMResponse, PromptMessage


class LLMClientError(RuntimeError):
    """Readable provider/configuration exception."""


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config_from_env(repo_root: Path) -> LLMConfig:
    load_env_file(repo_root / ".env")

    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if provider not in {"openai", "openrouter"}:
        provider = "openrouter" if openrouter_key else "openai"

    timeout = float(os.getenv("OPENAI_TIMEOUT", "90"))
    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))

    if provider == "openrouter":
        api_key = openrouter_key or openai_key
        model = os.getenv("OPENROUTER_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip()
        base_url = (
            os.getenv("OPENROUTER_BASE_URL", "").strip()
            or os.getenv("OPENAI_BASE_URL", "").strip()
            or "https://openrouter.ai/api/v1"
        )
        if not api_key:
            raise LLMClientError("Missing OPENROUTER_API_KEY.")
        if not model:
            raise LLMClientError("Missing OPENROUTER_MODEL.")
        headers: dict[str, str] = {}
        referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
        title = os.getenv("OPENROUTER_APP_TITLE", "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        return LLMConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            headers=headers,
        )

    api_key = openai_key
    model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4.1-mini"
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1"
    if not api_key:
        raise LLMClientError("Missing OPENAI_API_KEY.")
    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
        headers={},
    )


def call_chat_completion(
    config: LLMConfig,
    messages: list[PromptMessage],
    *,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> LLMResponse:
    endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, object] = {
        "model": config.model,
        "messages": [message.to_dict() for message in messages],
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        **config.headers,
    }

    last_error: Exception | None = None
    for attempt in range(1, config.max_retries + 1):
        http_request = request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=config.timeout) as response:
                response_text = response.read().decode("utf-8")
            response_json = json.loads(response_text)
            output_text = _extract_output_text(response_json)
            if not output_text.strip():
                raise LLMClientError("The model returned an empty response.")
            return LLMResponse(
                text=output_text,
                model=str(response_json.get("model", config.model)),
                raw_response=response_json,
            )
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = LLMClientError(f"Provider returned HTTP {exc.code}: {body}")
        except error.URLError as exc:
            last_error = LLMClientError(f"Could not reach provider: {exc.reason}")
        except json.JSONDecodeError:
            last_error = LLMClientError("Provider returned invalid JSON.")
        except Exception as exc:  # noqa: BLE001
            last_error = exc

        if attempt < config.max_retries:
            time.sleep(min(2**attempt, 8))

    raise LLMClientError(str(last_error)) from last_error


def parse_json_response(response: LLMResponse) -> dict[str, object]:
    cleaned = response.text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMClientError(f"Model returned invalid JSON: {response.text}") from exc
    if not isinstance(parsed, dict):
        raise LLMClientError("Model JSON response was not an object.")
    return parsed


def _extract_output_text(response_json: dict[str, object]) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        return ""
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
