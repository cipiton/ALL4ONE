from __future__ import annotations

from pathlib import Path

from engine.models import SkillRegistryEntry

from ..protocol import SkillAdapter
from .skill_md_adapter import SkillMdAdapter


class SkillAdapterError(RuntimeError):
    """Raised when an adapter cannot be resolved or created."""


def create_adapter(repo_root: Path, entry: SkillRegistryEntry) -> SkillAdapter:
    if entry.adapter == "skill_md":
        return SkillMdAdapter(repo_root, entry)
    raise SkillAdapterError(
        f"Unsupported adapter '{entry.adapter}' for skill '{entry.id}'."
    )
