from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .input_loader import InputLoadError, resolve_input_paths


def resolve_skill_input_request(
    repo_root: Path,
    skill,
    *,
    raw_path: str | None = None,
    direct_text: str | None = None,
) -> tuple[Path, list[Path]]:
    text_input = str(direct_text or "").strip()
    if bool(getattr(skill, "allow_inline_text_input", False)) and text_input:
        return _create_inline_input_paths(repo_root, skill, text_input)

    raw_value = str(raw_path or "").strip()
    if bool(getattr(skill, "allow_inline_text_input", False)) and _should_treat_as_inline_text(raw_value):
        return _create_inline_input_paths(repo_root, skill, raw_value)

    if not raw_value:
        raise InputLoadError("Input path is empty.")

    input_root_path = Path(raw_value.strip().strip('"')).expanduser().resolve()
    return input_root_path, resolve_input_paths(
        str(input_root_path),
        skill.input_extensions,
        folder_mode=skill.folder_mode,
    )


def _should_treat_as_inline_text(raw_value: str) -> bool:
    stripped = raw_value.strip().strip('"')
    if not stripped:
        return False
    if any(separator in stripped for separator in ("\\", "/")):
        return False
    if Path(stripped).suffix:
        return False
    return True


def _create_inline_input_paths(repo_root: Path, skill, brief_text: str) -> tuple[Path, list[Path]]:
    skill_id = str(getattr(skill, "skill_id", getattr(skill, "name", "skill"))).strip().replace(" ", "_") or "skill"
    inline_inputs_dir = repo_root / "outputs" / ".internal" / "inline_inputs"
    inline_inputs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    input_path = inline_inputs_dir / f"{skill_id}__{timestamp}.txt"
    input_path.write_text(brief_text.strip() + "\n", encoding="utf-8")
    synthetic_root = repo_root / f"{skill_id}_inline_brief.txt"
    return synthetic_root, [input_path]
