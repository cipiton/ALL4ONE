from __future__ import annotations

import os
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

from engine.config_loader import (
    clear_repo_config_cache,
    get_config_value,
    load_repo_config,
    save_repo_config,
)
from .workspace_manager import default_workspace_root


@dataclass(slots=True)
class AppSettings:
    provider: str
    model: str
    api_key: str
    base_url: str
    default_output_path: str
    default_skill_id: str
    workspace_root: str
    last_project_name: str


class SettingsManager:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.config_path = self.repo_root / "config.ini"
        self.env_path = self.repo_root / ".env"

    def load(self) -> AppSettings:
        parser = load_repo_config(self.repo_root)
        env_values = self._read_env_values()
        provider = (
            env_values.get("LLM_PROVIDER")
            or get_config_value(parser, "llm", "provider", "")
            or "openrouter"
        ).strip().lower()
        provider = provider if provider in {"openai", "openrouter"} else "openrouter"
        api_key = env_values.get(self._provider_key_name(provider), "").strip()
        if not api_key:
            fallback_key = "OPENROUTER_API_KEY" if provider == "openai" else "OPENAI_API_KEY"
            api_key = env_values.get(fallback_key, "").strip()
        model = get_config_value(parser, "llm", "model", "")
        base_url = get_config_value(parser, "llm", "base_url", "")
        default_output_path = get_config_value(
            parser,
            "gui",
            "default_output_path",
            str((self.repo_root / "outputs").resolve()),
        )
        default_skill_id = get_config_value(parser, "gui", "default_skill_id", "")
        workspace_root = get_config_value(
            parser,
            "gui",
            "workspace_root",
            str(default_workspace_root()),
        )
        last_project_name = get_config_value(parser, "gui", "last_project_name", "")
        return AppSettings(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            default_output_path=default_output_path,
            default_skill_id=default_skill_id,
            workspace_root=workspace_root,
            last_project_name=last_project_name,
        )

    def save(self, settings: AppSettings) -> None:
        parser = ConfigParser()
        if self.config_path.exists():
            parser.read(self.config_path, encoding="utf-8-sig")

        for section in ("llm", "gui"):
            if not parser.has_section(section):
                parser.add_section(section)

        parser.set("llm", "provider", settings.provider.strip().lower())
        parser.set("llm", "model", settings.model.strip())
        parser.set("llm", "base_url", settings.base_url.strip())
        parser.set("gui", "default_output_path", settings.default_output_path.strip())
        parser.set("gui", "default_skill_id", settings.default_skill_id.strip())
        parser.set("gui", "workspace_root", settings.workspace_root.strip())
        parser.set("gui", "last_project_name", settings.last_project_name.strip())
        save_repo_config(self.repo_root, parser)

        env_updates = {
            "LLM_PROVIDER": settings.provider.strip().lower(),
            self._provider_key_name(settings.provider): settings.api_key.strip(),
        }
        self._write_env_values(env_updates)
        self.apply(settings)

    def save_gui_state(
        self,
        *,
        workspace_root: str,
        last_project_name: str,
        default_skill_id: str,
        default_output_path: str,
    ) -> None:
        parser = ConfigParser()
        if self.config_path.exists():
            parser.read(self.config_path, encoding="utf-8-sig")
        if not parser.has_section("gui"):
            parser.add_section("gui")
        parser.set("gui", "workspace_root", workspace_root.strip())
        parser.set("gui", "last_project_name", last_project_name.strip())
        parser.set("gui", "default_skill_id", default_skill_id.strip())
        parser.set("gui", "default_output_path", default_output_path.strip())
        save_repo_config(self.repo_root, parser)

    def apply(self, settings: AppSettings) -> None:
        provider = settings.provider.strip().lower() or "openrouter"
        api_key_name = self._provider_key_name(provider)
        os.environ["LLM_PROVIDER"] = provider
        os.environ[api_key_name] = settings.api_key.strip()
        if provider == "openrouter":
            os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            os.environ["OPENROUTER_BASE_URL"] = settings.base_url.strip()
            os.environ["OPENROUTER_MODEL"] = settings.model.strip()
            os.environ["OPENAI_MODEL"] = ""
            os.environ["OPENAI_BASE_URL"] = ""
        else:
            os.environ.setdefault("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
            os.environ["OPENAI_BASE_URL"] = settings.base_url.strip()
            os.environ["OPENAI_MODEL"] = settings.model.strip()
            os.environ["OPENROUTER_MODEL"] = ""
            os.environ["OPENROUTER_BASE_URL"] = ""
        clear_repo_config_cache()

    def _provider_key_name(self, provider: str) -> str:
        return "OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY"

    def _read_env_values(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in self.env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cleaned = value.strip().strip('"').strip("'")
            values[key.strip()] = cleaned
        return values

    def _write_env_values(self, updates: dict[str, str]) -> None:
        lines = self.env_path.read_text(encoding="utf-8").splitlines() if self.env_path.exists() else []
        remaining = {key: value for key, value in updates.items()}
        updated_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                updated_lines.append(line)
                continue
            key, _ = line.split("=", 1)
            clean_key = key.strip()
            if clean_key in remaining:
                updated_lines.append(f"{clean_key}={remaining.pop(clean_key)}")
            else:
                updated_lines.append(line)

        for key, value in remaining.items():
            updated_lines.append(f"{key}={value}")

        self.env_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
