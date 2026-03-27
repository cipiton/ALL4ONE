from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.llm_client import LLMClientError, call_chat_completion, load_config_from_env
from engine.models import PromptMessage

from .settings_manager import AppSettings, SettingsManager


@dataclass(slots=True)
class AssistantRequest:
    repo_root: Path
    settings: AppSettings
    messages: list[PromptMessage]


def generate_assistant_reply(request: AssistantRequest) -> str:
    if not request.settings.model.strip():
        raise LLMClientError("Model is not configured. Open Settings and save a model first.")
    if not request.settings.api_key.strip():
        raise LLMClientError("API key is not configured. Open Settings and save an API key first.")

    settings_manager = SettingsManager(request.repo_root)
    settings_manager.apply(request.settings)
    config = load_config_from_env(request.repo_root)
    response = call_chat_completion(config, request.messages, temperature=0.2)
    return response.text.strip()
