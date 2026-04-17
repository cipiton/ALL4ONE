from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.app_paths import get_app_root, get_bundle_root, get_runtime_context
from engine.config_loader import get_config_value, load_repo_config
from engine.models import SkillRegistryEntry, resolve_localized_text
from engine.skill_loader import discover_skills

from .adapters import SkillAdapterError, create_adapter
from .protocol import SkillAdapter, SkillMenuSummary


class SkillCatalogError(RuntimeError):
    """Raised when the skill catalog cannot be loaded."""


class SkillCatalog:
    def __init__(self, repo_root: Path, skills: list[SkillAdapter]) -> None:
        self.repo_root = repo_root
        self._skills = skills
        self._skills_by_id = {skill.skill_id: skill for skill in skills}
        self._alias_to_skill_id: dict[str, str] = {}
        for skill in skills:
            aliases = getattr(skill, "aliases", [])
            for alias in aliases:
                if alias and alias not in self._skills_by_id and alias not in self._alias_to_skill_id:
                    self._alias_to_skill_id[alias] = skill.skill_id

    @classmethod
    def load(cls, repo_root: Path) -> "SkillCatalog":
        resource_root = get_bundle_root(repo_root)
        skills_root = resource_root / "skills"
        if not skills_root.exists():
            context = get_runtime_context(repo_root)
            raise SkillCatalogError(
                "Skills directory not found: "
                f"{skills_root} "
                f"(frozen={context['frozen']}, bundle_root={context['bundle_root']}, app_root={context['app_root']})"
            )

        registry_path = skills_root / "registry.yaml"
        if registry_path.exists():
            entries = _load_registry_entries(resource_root, registry_path)
        else:
            entries = _build_legacy_entries(resource_root)
        entries = _apply_skill_visibility_filters(repo_root, entries)

        adapters: list[SkillAdapter] = []
        seen_ids: set[str] = set()
        for entry in entries:
            if not entry.enabled:
                continue
            if entry.id in seen_ids:
                raise SkillCatalogError(f"Duplicate skill id '{entry.id}' in catalog.")
            seen_ids.add(entry.id)
            try:
                adapters.append(create_adapter(repo_root, entry))
            except SkillAdapterError as exc:
                raise SkillCatalogError(str(exc)) from exc

        if not adapters:
            source = registry_path if registry_path.exists() else skills_root
            raise SkillCatalogError(f"No enabled skills available from {source}")

        return cls(get_app_root(repo_root), adapters)

    def list_skills(self) -> list[SkillAdapter]:
        return list(self._skills)

    def get_skill(self, skill_id: str) -> SkillAdapter:
        if skill_id not in self._skills_by_id and skill_id in self._alias_to_skill_id:
            skill_id = self._alias_to_skill_id[skill_id]
        try:
            return self._skills_by_id[skill_id]
        except KeyError as exc:
            raise SkillCatalogError(f"Unknown skill id '{skill_id}'.") from exc

    def menu_summaries(self) -> list[SkillMenuSummary]:
        return [skill.to_summary() for skill in self._skills]


def _load_registry_entries(repo_root: Path, registry_path: Path) -> list[SkillRegistryEntry]:
    try:
        raw_registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SkillCatalogError(f"Invalid YAML in registry file {registry_path}: {exc}") from exc

    if not isinstance(raw_registry, dict):
        raise SkillCatalogError(f"Registry file must contain a mapping at the top level: {registry_path}")

    version = raw_registry.get("version")
    if version != 1:
        raise SkillCatalogError(
            f"Unsupported registry version in {registry_path}: expected 1, got {version!r}"
        )

    raw_skills = raw_registry.get("skills")
    if not isinstance(raw_skills, list):
        raise SkillCatalogError(f"Registry file must define a 'skills' list: {registry_path}")

    return [
        _parse_registry_entry(repo_root, registry_path, raw_entry, index)
        for index, raw_entry in enumerate(raw_skills, start=1)
    ]


def _parse_registry_entry(
    repo_root: Path,
    registry_path: Path,
    raw_entry: Any,
    index: int,
) -> SkillRegistryEntry:
    if not isinstance(raw_entry, dict):
        raise SkillCatalogError(f"Registry entry #{index} in {registry_path} must be a mapping.")

    entry_id = _require_string(raw_entry, "id", registry_path, index)
    entry_type = _require_string(raw_entry, "type", registry_path, index)
    adapter = _require_string(raw_entry, "adapter", registry_path, index)
    raw_spec_path = _require_string(raw_entry, "spec_path", registry_path, index)

    if entry_type != "skill":
        raise SkillCatalogError(
            f"Unsupported registry type '{entry_type}' for skill '{entry_id}' in {registry_path}; "
            "Phase 2 only supports type: skill."
        )

    spec_path = _resolve_repo_path(repo_root, raw_spec_path, description=f"registry entry '{entry_id}' spec_path")
    if spec_path.name != "SKILL.md":
        raise SkillCatalogError(
            f"Registry entry '{entry_id}' in {registry_path} must point to a SKILL.md file: {raw_spec_path}"
        )
    if not spec_path.exists():
        raise SkillCatalogError(
            f"Registry entry '{entry_id}' points to a missing SKILL.md: {raw_spec_path}"
        )

    return SkillRegistryEntry(
        id=entry_id,
        entry_type=entry_type,
        adapter=adapter,
        aliases=[str(item) for item in raw_entry.get("aliases", []) or []],
        spec_path=spec_path,
        enabled=bool(raw_entry.get("enabled", True)),
        display_name=resolve_localized_text(_load_localized_text_map(raw_entry.get("display_name")), "en"),
        description=resolve_localized_text(_load_localized_text_map(raw_entry.get("description")), "en"),
        display_name_i18n=_load_localized_text_map(raw_entry.get("display_name")),
        description_i18n=_load_localized_text_map(raw_entry.get("description")),
    )


def _build_legacy_entries(repo_root: Path) -> list[SkillRegistryEntry]:
    entries: list[SkillRegistryEntry] = []
    for summary in discover_skills(repo_root):
        entries.append(
            SkillRegistryEntry(
                id=summary.name,
                entry_type="skill",
                adapter="skill_md",
                aliases=[],
                spec_path=(summary.skill_dir / "SKILL.md").resolve(),
                enabled=True,
                display_name=summary.display_name,
                description=summary.description,
                display_name_i18n={"en": summary.display_name} if summary.display_name else {},
                description_i18n={"en": summary.description} if summary.description else {},
            )
        )
    return entries


def _apply_skill_visibility_filters(repo_root: Path, entries: list[SkillRegistryEntry]) -> list[SkillRegistryEntry]:
    parser = load_repo_config(get_app_root(repo_root))
    visible_ids = _parse_skill_id_list(get_config_value(parser, "skills", "visible_skill_ids", ""))
    hidden_ids = _parse_skill_id_list(get_config_value(parser, "skills", "hidden_skill_ids", ""))

    if not visible_ids and not hidden_ids:
        return entries

    visible_lookup = {item.casefold() for item in visible_ids}
    hidden_lookup = {item.casefold() for item in hidden_ids}
    filtered: list[SkillRegistryEntry] = []

    for entry in entries:
        names = {entry.id.casefold(), *(alias.casefold() for alias in entry.aliases)}
        if visible_lookup and not names.intersection(visible_lookup):
            continue
        if hidden_lookup and names.intersection(hidden_lookup):
            continue
        filtered.append(entry)
    return filtered


def _require_string(
    raw_entry: dict[str, Any],
    field_name: str,
    registry_path: Path,
    index: int,
) -> str:
    value = raw_entry.get(field_name)
    if value in (None, ""):
        raise SkillCatalogError(
            f"Registry entry #{index} in {registry_path} is missing required field '{field_name}'."
        )
    return str(value)


def _parse_skill_id_list(raw_value: str) -> list[str]:
    cleaned = str(raw_value or "").replace("\r", "\n")
    values: list[str] = []
    seen: set[str] = set()
    for chunk in cleaned.split("\n"):
        for item in chunk.split(","):
            token = str(item).strip()
            lowered = token.casefold()
            if not token or lowered in seen:
                continue
            seen.add(lowered)
            values.append(token)
    return values


def _resolve_repo_path(repo_root: Path, raw_path: str, *, description: str) -> Path:
    candidate = (repo_root / Path(raw_path)).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise SkillCatalogError(f"{description} escapes the repository root: {raw_path}") from exc
    return candidate


def _normalize_language_key(language: str) -> str:
    lowered = str(language).strip().lower().replace("-", "_")
    if lowered in {"zh", "zh_cn", "zh_hans", "zh_hans_cn"}:
        return "zh_cn"
    if lowered.startswith("en"):
        return "en"
    return lowered


def _load_localized_text_map(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        localized: dict[str, str] = {}
        for language, text in value.items():
            cleaned = str(text).strip()
            if cleaned:
                localized[_normalize_language_key(str(language))] = cleaned
        return localized
    cleaned = str(value).strip()
    return {"en": cleaned} if cleaned else {}
