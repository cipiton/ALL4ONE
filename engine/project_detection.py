from __future__ import annotations

import re
from math import ceil
from pathlib import Path

from .input_loader import load_input_document
from .models import SkillDefinition


SAFE_SINGLE_PASS_TOKENS = 9_000
CHUNK_NAME_PATTERNS = (
    re.compile(r"^\d{3}[_-]"),
    re.compile(r"^chapter[_-]?\d+", re.IGNORECASE),
    re.compile(r"^chapters?[_-]?\d+(?:[_-]\d+)?", re.IGNORECASE),
    re.compile(r"^chunk[_-]?\d+", re.IGNORECASE),
    re.compile(r"^part[_-]?\d+", re.IGNORECASE),
    re.compile(r"^第[零一二三四五六七八九十百千\d]+[章节卷集部篇回][_-]?", re.IGNORECASE),
)
PROJECT_MARKER_FILES = {
    "index.txt",
    "ingestion_report.txt",
    "project_state.json",
    "continuity_log.json",
    "chunk_summaries.json",
    "chunk_manifest.json",
    "manifest.json",
}


def should_use_project_ingestion(
    skill: SkillDefinition,
    input_paths: list[Path],
    *,
    input_root_path: Path | None,
) -> bool:
    if skill.execution_strategy not in {"step_prompt", "structured_report"}:
        return False
    if ".txt" not in {suffix.lower() for suffix in skill.input_extensions}:
        return False
    if not input_paths:
        return False

    if len(input_paths) > 1:
        return looks_like_chunk_project(input_paths, input_root_path=input_root_path)

    document = load_input_document(input_paths[0])
    return document.estimated_tokens > SAFE_SINGLE_PASS_TOKENS


def looks_like_chunk_project(input_paths: list[Path], *, input_root_path: Path | None) -> bool:
    if input_root_path is not None and input_root_path.is_dir():
        if has_explicit_project_markers(input_root_path):
            return True
        lowered_name = input_root_path.name.casefold()
        if any(token in lowered_name for token in ("chunk", "chapter", "split", "parts")):
            return True

    filtered = [path for path in input_paths if path.name.casefold() != "index.txt"]
    if len(filtered) < 2:
        return False
    sample = filtered[: min(len(filtered), 12)]
    match_count = sum(1 for path in sample if filename_looks_like_chunk(path.name))
    return match_count >= max(2, ceil(len(sample) * 0.6))


def has_explicit_project_markers(root: Path) -> bool:
    if any((root / marker).exists() for marker in PROJECT_MARKER_FILES):
        return True
    if (root / "chapters").is_dir() or (root / "chunks").is_dir():
        return True
    return False


def filename_looks_like_chunk(filename: str) -> bool:
    if filename.casefold() == "index.txt":
        return True
    return any(pattern.match(filename) for pattern in CHUNK_NAME_PATTERNS)
