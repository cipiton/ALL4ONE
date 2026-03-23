from __future__ import annotations

import re
from typing import Any

from .models import InputDocument, SkillDefinition


ROLLING_CONTEXT_LIMIT = 4


def initial_project_state(
    skill: SkillDefinition,
    source_metadata: dict[str, Any],
    chunks: list[InputDocument],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "skill_name": skill.name,
        "skill_display_name": skill.display_name,
        "source_metadata": source_metadata,
        "title": "",
        "genre": "",
        "tone": "",
        "setting": "",
        "world_rules": [],
        "timeline_anchors": [],
        "chapter_coverage_map": [],
        "character_registry": [],
        "locations": [],
        "factions": [],
        "important_objects": [],
        "unresolved_threads": [],
        "resolved_threads": [],
        "continuity_warnings": [],
        "adaptation_decisions": [],
        "rewrite_substitutions": [],
        "chunk_summaries": [],
        "scene_event_index": [],
        "rolling_recent_context": [],
        "chunk_sources": [str(chunk.path) for chunk in chunks],
    }


def merge_project_state(project_state: dict[str, Any], update: dict[str, Any], chunk: InputDocument) -> None:
    for field in ("title", "genre", "tone", "setting"):
        value = str(update.get(field, "")).strip()
        if value and not str(project_state.get(field, "")).strip():
            project_state[field] = value

    for field in (
        "world_rules",
        "timeline_anchors",
        "unresolved_threads",
        "resolved_threads",
        "continuity_warnings",
        "adaptation_decisions",
    ):
        project_state[field] = merge_string_lists(project_state.get(field, []), update.get(field, []))

    project_state["rewrite_substitutions"] = merge_named_records(
        project_state.get("rewrite_substitutions", []),
        update.get("rewrite_substitutions", []),
        key="original",
        merge_list_fields=[],
        keep_text_fields=["replacement", "reason"],
    )
    project_state["character_registry"] = merge_named_records(
        project_state.get("character_registry", []),
        update.get("character_updates", []),
        key="name",
        merge_list_fields=["aliases", "relationships", "traits"],
        keep_text_fields=["voice", "status"],
    )
    project_state["locations"] = merge_named_records(
        project_state.get("locations", []),
        update.get("locations", []),
        key="name",
        merge_list_fields=[],
        keep_text_fields=["details"],
    )
    project_state["factions"] = merge_named_records(
        project_state.get("factions", []),
        update.get("factions", []),
        key="name",
        merge_list_fields=[],
        keep_text_fields=["details"],
    )
    project_state["important_objects"] = merge_named_records(
        project_state.get("important_objects", []),
        update.get("important_objects", []),
        key="name",
        merge_list_fields=[],
        keep_text_fields=["details"],
    )
    project_state["scene_event_index"] = merge_string_lists(
        project_state.get("scene_event_index", []),
        update.get("scene_events", []),
    )

    coverage_entry = update.get("chapter_coverage_entry")
    if isinstance(coverage_entry, dict):
        normalized_entry = {
            "chunk_id": str(coverage_entry.get("chunk_id") or chunk.path.stem),
            "coverage": str(coverage_entry.get("coverage") or "").strip(),
        }
        project_state["chapter_coverage_map"] = merge_named_records(
            project_state.get("chapter_coverage_map", []),
            [normalized_entry],
            key="chunk_id",
            merge_list_fields=[],
            keep_text_fields=["coverage"],
        )

    chunk_summary = update.get("chunk_summary")
    if not isinstance(chunk_summary, dict):
        chunk_summary = {}
    normalized_summary = {
        "chunk_id": str(chunk_summary.get("chunk_id") or chunk.path.stem),
        "source_file": chunk.path.name,
        "summary": str(chunk_summary.get("summary") or "").strip(),
        "coverage": str(chunk_summary.get("coverage") or "").strip(),
        "key_events": clean_string_list(chunk_summary.get("key_events", [])),
        "continuity_notes": clean_string_list(chunk_summary.get("continuity_notes", [])),
    }
    project_state["chunk_summaries"] = merge_named_records(
        project_state.get("chunk_summaries", []),
        [normalized_summary],
        key="chunk_id",
        merge_list_fields=["key_events", "continuity_notes"],
        keep_text_fields=["source_file", "summary", "coverage"],
    )
    project_state["rolling_recent_context"] = [
        {
            "chunk_id": item.get("chunk_id"),
            "summary": item.get("summary"),
            "continuity_notes": item.get("continuity_notes", []),
        }
        for item in project_state["chunk_summaries"][-ROLLING_CONTEXT_LIMIT:]
    ]


def merge_string_lists(existing: list[Any], updates: list[Any]) -> list[str]:
    merged = [str(item).strip() for item in existing if str(item).strip()]
    seen = {normalize_string_list_value(item) for item in merged}
    for item in updates or []:
        candidate = str(item).strip()
        normalized_candidate = normalize_string_list_value(candidate)
        if candidate and normalized_candidate not in seen:
            merged.append(candidate)
            seen.add(normalized_candidate)
    return merged


def clean_string_list(values: list[Any]) -> list[str]:
    return [str(item).strip() for item in values or [] if str(item).strip()]


def merge_named_records(
    existing: list[Any],
    updates: list[Any],
    *,
    key: str,
    merge_list_fields: list[str],
    keep_text_fields: list[str],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    def normalize_name(value: Any) -> str:
        return str(value or "").strip()

    for record in existing or []:
        if not isinstance(record, dict):
            continue
        record_key = normalize_name(record.get(key))
        if record_key:
            merged[normalize_merge_key(record_key)] = dict(record)

    for record in updates or []:
        if not isinstance(record, dict):
            continue
        record_key = normalize_name(record.get(key))
        if not record_key:
            continue
        normalized_key = normalize_merge_key(record_key)
        target = merged.setdefault(normalized_key, {key: record_key})
        if not str(target.get(key) or "").strip():
            target[key] = record_key
        for field_name in merge_list_fields:
            target[field_name] = merge_string_lists(target.get(field_name, []), record.get(field_name, []))
        for field_name in keep_text_fields:
            value = str(record.get(field_name) or "").strip()
            if value:
                target[field_name] = value

    return list(merged.values())


def normalize_merge_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def normalize_string_list_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()
