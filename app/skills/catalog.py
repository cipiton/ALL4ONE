from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.models import SkillRegistryEntry
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

    @classmethod
    def load(cls, repo_root: Path) -> "SkillCatalog":
        skills_root = repo_root / "skills"
        if not skills_root.exists():
            raise SkillCatalogError(f"Skills directory not found: {skills_root}")

        registry_path = skills_root / "registry.yaml"
        if registry_path.exists():
            entries = _load_registry_entries(repo_root, registry_path)
        else:
            entries = _build_legacy_entries(repo_root)

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

        return cls(repo_root, adapters)

    def list_skills(self) -> list[SkillAdapter]:
        return list(self._skills)

    def get_skill(self, skill_id: str) -> SkillAdapter:
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
        spec_path=spec_path,
        enabled=bool(raw_entry.get("enabled", True)),
        display_name=str(raw_entry.get("display_name") or ""),
        description=str(raw_entry.get("description") or ""),
    )


def _build_legacy_entries(repo_root: Path) -> list[SkillRegistryEntry]:
    entries: list[SkillRegistryEntry] = []
    for summary in discover_skills(repo_root):
        entries.append(
            SkillRegistryEntry(
                id=summary.name,
                entry_type="skill",
                adapter="skill_md",
                spec_path=(summary.skill_dir / "SKILL.md").resolve(),
                enabled=True,
                display_name=summary.display_name,
                description=summary.description,
            )
        )
    return entries


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


def _resolve_repo_path(repo_root: Path, raw_path: str, *, description: str) -> Path:
    candidate = (repo_root / Path(raw_path)).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise SkillCatalogError(f"{description} escapes the repository root: {raw_path}") from exc
    return candidate
