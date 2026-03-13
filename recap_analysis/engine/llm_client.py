from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LLMConfigurationError(RuntimeError):
    """Raised when required LLM configuration is missing."""


class LLMRequestError(RuntimeError):
    """Raised when the LLM request fails after retries."""


@dataclass(slots=True)
class LLMSettings:
    provider: str
    api_key: str
    model: str
    base_url: str | None = None
    timeout: float = 90.0
    max_retries: int = 3
    default_headers: dict[str, str] | None = None


class LLMClient:
    """Small OpenAI-compatible wrapper isolated from the runtime."""

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or self._load_settings()
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMConfigurationError("缺少 openai 依赖，请安装后再运行。") from exc

        client_kwargs: dict[str, Any] = {
            "api_key": self.settings.api_key,
            "timeout": self.settings.timeout,
        }
        if self.settings.base_url:
            client_kwargs["base_url"] = self.settings.base_url
        if self.settings.default_headers:
            client_kwargs["default_headers"] = self.settings.default_headers
        self._client = OpenAI(**client_kwargs)

    def generate_json(
        self,
        stage_name: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Request a JSON object from the model with retry handling."""
        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.settings.model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or "{}"
                return _parse_json(content)
            except Exception as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                time.sleep(min(2**attempt, 8))

        raise LLMRequestError(f"{stage_name} 阶段调用模型失败: {last_error}") from last_error

    @staticmethod
    def _load_settings() -> LLMSettings:
        env_candidates = (
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        )
        seen_paths: set[Path] = set()
        for env_path in env_candidates:
            resolved = env_path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            _load_dotenv_file(resolved)

        provider = _resolve_provider()
        timeout = float(os.getenv("OPENAI_TIMEOUT", "90"))
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "3"))

        if provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
            if not api_key:
                raise LLMConfigurationError("缺少 OPENROUTER_API_KEY，无法执行 OpenRouter 分析。")

            model = (
                os.getenv("OPENROUTER_MODEL", "").strip()
                or os.getenv("OPENAI_MODEL", "").strip()
                or "openai/gpt-4.1-mini"
            )
            base_url = (
                os.getenv("OPENROUTER_BASE_URL", "").strip()
                or "https://openrouter.ai/api/v1"
            )
            default_headers = _build_openrouter_headers()
            return LLMSettings(
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
                default_headers=default_headers or None,
            )

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise LLMConfigurationError("缺少 OPENAI_API_KEY，无法执行 LLM 分析。")

        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
        return LLMSettings(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=None,
        )


def _parse_json(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if "\n" in cleaned:
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMRequestError(f"模型返回了无效 JSON: {raw_text}") from exc
    if not isinstance(data, dict):
        raise LLMRequestError("模型返回的 JSON 不是对象。")
    return data


def _load_dotenv_file(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _build_openrouter_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    app_title = os.getenv("OPENROUTER_APP_TITLE", "").strip()

    if referer:
        headers["HTTP-Referer"] = referer
    if app_title:
        headers["X-Title"] = app_title
    return headers


def _resolve_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if provider in {"openai", "openrouter"}:
        if provider == "openai" and not openai_key and openrouter_key:
            return "openrouter"
        return provider

    if openrouter_key:
        return "openrouter"
    return "openai"
