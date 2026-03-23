from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Any

from .project_snapshots import PROMPT_CAPS, build_canonical_digest
from .project_state import ROLLING_CONTEXT_LIMIT
from .writer import write_json_file, write_text_file


FINAL_OUTPUT_MAX_PARTS = 4
FINAL_OUTPUT_PART_THRESHOLD = 36_000


def persist_project_artifacts(intermediate_dir: Path, project_state: dict[str, Any], continuity_log: list[dict[str, Any]]) -> None:
    project_state["prompt_digest"] = build_canonical_digest(project_state)
    project_state["state_compaction"] = {
        "rolling_recent_context_limit": ROLLING_CONTEXT_LIMIT,
        "caps": dict(PROMPT_CAPS),
    }
    write_json_file(intermediate_dir, "project_state.json", project_state)
    write_json_file(intermediate_dir, "continuity_log.json", continuity_log)
    write_json_file(intermediate_dir, "chunk_summaries.json", {"chunks": project_state.get("chunk_summaries", [])})


def split_large_final_output(final_dir: Path, primary_output_path: str | None) -> list[Path]:
    if not primary_output_path:
        return []
    primary_path = Path(primary_output_path)
    if not primary_path.exists():
        return []
    text = primary_path.read_text(encoding="utf-8")
    if len(text) <= FINAL_OUTPUT_PART_THRESHOLD:
        return []

    part_count = min(FINAL_OUTPUT_MAX_PARTS, max(2, ceil(len(text) / FINAL_OUTPUT_PART_THRESHOLD)))
    parts: list[Path] = []
    cursor = 0
    remaining_parts = part_count
    index = 1
    while cursor < len(text) and remaining_parts > 0:
        end = _choose_part_end(text, cursor, remaining_parts)
        if end <= cursor:
            end = len(text)
        part_text = text[cursor:end]
        if part_text:
            parts.append(write_text_file(final_dir, f"final_output_part_{index:02d}.txt", part_text))
            index += 1
        cursor = end
        remaining_parts -= 1
    return parts


def build_ingestion_report(metadata: dict[str, Any], chunk_infos: list[dict[str, Any]]) -> str:
    lines = [
        "Project ingestion report",
        f"Mode: {metadata.get('mode', 'unknown')}",
        f"Source path: {metadata.get('source_path', '')}",
        f"Chunk count: {len(chunk_infos)}",
        f"Overlap chars: {metadata.get('overlap_chars', 0)}",
        "",
        "Chunks:",
    ]
    for chunk in chunk_infos:
        lines.append(
            f"- {chunk['index']:03d}/{chunk['total']:03d} {chunk['name']} | chars={chunk['character_count']} | est_tokens={chunk['estimated_tokens']}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _choose_part_end(text: str, cursor: int, remaining_parts: int) -> int:
    if remaining_parts <= 1:
        return len(text)

    remaining_chars = len(text) - cursor
    target_span = ceil(remaining_chars / remaining_parts)
    ideal_end = min(len(text), cursor + target_span)
    search_floor = min(len(text), cursor + max(1, int(target_span * 0.6)))

    backward_boundary = text.rfind("\n", search_floor, ideal_end + 1)
    if backward_boundary >= search_floor:
        return backward_boundary + 1

    forward_limit = min(len(text), ideal_end + max(2_000, target_span // 3))
    forward_boundary = text.find("\n", ideal_end, forward_limit)
    if forward_boundary != -1:
        return forward_boundary + 1

    return ideal_end
