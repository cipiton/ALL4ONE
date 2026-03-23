from __future__ import annotations

from typing import Any

from .project_state import ROLLING_CONTEXT_LIMIT, clean_string_list


PROMPT_CAPS = {
    "world_rules": 10,
    "timeline_anchors": 12,
    "characters": 12,
    "locations": 10,
    "factions": 10,
    "important_objects": 10,
    "unresolved_threads": 12,
    "resolved_threads": 8,
    "continuity_warnings": 8,
    "adaptation_decisions": 10,
    "rewrite_substitutions": 10,
    "chapter_coverage_map": 12,
    "chunk_summaries": 4,
}


def build_state_snapshot(project_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_overview": {
            "source_metadata": project_state.get("source_metadata", {}),
            "chunk_count": len(project_state.get("chunk_sources", [])),
            "processed_chunks": len(project_state.get("chunk_summaries", [])),
        },
        "canonical_digest": build_canonical_digest(project_state),
        "rolling_recent_context": project_state.get("rolling_recent_context", [])[-ROLLING_CONTEXT_LIMIT:],
    }


def build_canonical_digest(project_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(project_state.get("title") or "").strip(),
        "genre": str(project_state.get("genre") or "").strip(),
        "tone": str(project_state.get("tone") or "").strip(),
        "setting": str(project_state.get("setting") or "").strip(),
        "world_rules": _cap_string_items(project_state.get("world_rules", []), PROMPT_CAPS["world_rules"]),
        "timeline_anchors": _cap_string_items(project_state.get("timeline_anchors", []), PROMPT_CAPS["timeline_anchors"]),
        "characters": _compact_named_records(
            project_state.get("character_registry", []),
            key="name",
            limit=PROMPT_CAPS["characters"],
            detail_fields=("aliases", "relationships", "traits", "voice", "status"),
        ),
        "locations": _compact_named_records(
            project_state.get("locations", []),
            key="name",
            limit=PROMPT_CAPS["locations"],
            detail_fields=("details",),
        ),
        "factions": _compact_named_records(
            project_state.get("factions", []),
            key="name",
            limit=PROMPT_CAPS["factions"],
            detail_fields=("details",),
        ),
        "important_objects": _compact_named_records(
            project_state.get("important_objects", []),
            key="name",
            limit=PROMPT_CAPS["important_objects"],
            detail_fields=("details",),
        ),
        "unresolved_threads": _cap_string_items(project_state.get("unresolved_threads", []), PROMPT_CAPS["unresolved_threads"]),
        "resolved_threads": _cap_string_items(project_state.get("resolved_threads", []), PROMPT_CAPS["resolved_threads"]),
        "continuity_warnings": _cap_string_items(project_state.get("continuity_warnings", []), PROMPT_CAPS["continuity_warnings"]),
        "adaptation_decisions": _cap_string_items(project_state.get("adaptation_decisions", []), PROMPT_CAPS["adaptation_decisions"]),
        "rewrite_substitutions": _compact_rewrite_substitutions(
            project_state.get("rewrite_substitutions", []),
            PROMPT_CAPS["rewrite_substitutions"],
        ),
        "chapter_coverage_map": _compact_coverage_entries(
            project_state.get("chapter_coverage_map", []),
            PROMPT_CAPS["chapter_coverage_map"],
        ),
        "recent_chunk_summaries": _compact_recent_chunk_summaries(
            project_state.get("chunk_summaries", []),
            PROMPT_CAPS["chunk_summaries"],
        ),
        "totals": {
            "characters": len(project_state.get("character_registry", [])),
            "locations": len(project_state.get("locations", [])),
            "factions": len(project_state.get("factions", [])),
            "important_objects": len(project_state.get("important_objects", [])),
            "chunk_summaries": len(project_state.get("chunk_summaries", [])),
            "unresolved_threads": len(project_state.get("unresolved_threads", [])),
        },
    }


def build_synthesis_snapshot(project_state: dict[str, Any]) -> dict[str, Any]:
    canonical_digest = build_canonical_digest(project_state)
    recent_chunk_summaries = canonical_digest.pop("recent_chunk_summaries", [])
    chunk_summaries = project_state.get("chunk_summaries", [])
    return {
        "project_overview": {
            "source_metadata": project_state.get("source_metadata", {}),
            "chunk_count": len(project_state.get("chunk_sources", [])),
            "processed_chunks": len(chunk_summaries),
            "covered_chunks": len(project_state.get("chapter_coverage_map", [])),
        },
        "canonical_digest": canonical_digest,
        "rolling_recent_context": project_state.get("rolling_recent_context", [])[-ROLLING_CONTEXT_LIMIT:],
        "coverage_digest": _compact_coverage_entries(
            project_state.get("chapter_coverage_map", []),
            limit=max(PROMPT_CAPS["chapter_coverage_map"], 16),
        ),
        "continuity_digest": {
            "warnings": _cap_string_items(
                project_state.get("continuity_warnings", []),
                max(PROMPT_CAPS["continuity_warnings"], 12),
            ),
            "unresolved_threads": _cap_string_items(
                project_state.get("unresolved_threads", []),
                max(PROMPT_CAPS["unresolved_threads"], 16),
            ),
            "resolved_threads": _cap_string_items(
                project_state.get("resolved_threads", []),
                max(PROMPT_CAPS["resolved_threads"], 10),
            ),
        },
        "selected_chunk_summaries": recent_chunk_summaries,
        "milestone_chunk_summaries": _compact_milestone_chunk_summaries(chunk_summaries, limit=6),
    }


def _cap_string_items(values: list[Any], limit: int) -> list[str]:
    cleaned = [str(item).strip() for item in values or [] if str(item).strip()]
    if len(cleaned) <= limit:
        return cleaned
    omitted = len(cleaned) - limit
    return cleaned[:limit] + [f"... ({omitted} more omitted)"]


def _compact_named_records(records: list[Any], *, key: str, limit: int, detail_fields: tuple[str, ...]) -> list[str]:
    entries: list[str] = []
    omitted = 0
    for raw_record in records or []:
        if not isinstance(raw_record, dict):
            continue
        name = str(raw_record.get(key) or "").strip()
        if not name:
            continue
        if len(entries) >= limit:
            omitted += 1
            continue
        parts = [name]
        for field_name in detail_fields:
            value = raw_record.get(field_name)
            if isinstance(value, list):
                items = [str(item).strip() for item in value if str(item).strip()][:3]
                if items:
                    parts.append(f"{field_name}={', '.join(items)}")
            else:
                text = str(value or "").strip()
                if text:
                    parts.append(f"{field_name}={text[:120]}")
        entries.append(" | ".join(parts))
    if omitted:
        entries.append(f"... ({omitted} more omitted)")
    return entries


def _compact_rewrite_substitutions(records: list[Any], limit: int) -> list[str]:
    entries: list[str] = []
    omitted = 0
    for raw_record in records or []:
        if not isinstance(raw_record, dict):
            continue
        original = str(raw_record.get("original") or "").strip()
        replacement = str(raw_record.get("replacement") or "").strip()
        reason = str(raw_record.get("reason") or "").strip()
        if not original:
            continue
        if len(entries) >= limit:
            omitted += 1
            continue
        entry = f"{original} -> {replacement}" if replacement else original
        if reason:
            entry = f"{entry} | reason={reason[:100]}"
        entries.append(entry)
    if omitted:
        entries.append(f"... ({omitted} more omitted)")
    return entries


def _compact_coverage_entries(records: list[Any], limit: int) -> list[str]:
    entries: list[str] = []
    omitted = 0
    for raw_record in records or []:
        if not isinstance(raw_record, dict):
            continue
        chunk_id = str(raw_record.get("chunk_id") or "").strip()
        coverage = str(raw_record.get("coverage") or "").strip()
        if not chunk_id and not coverage:
            continue
        if len(entries) >= limit:
            omitted += 1
            continue
        entries.append(f"{chunk_id}: {coverage}".strip(": "))
    if omitted:
        entries.append(f"... ({omitted} more omitted)")
    return entries


def _compact_recent_chunk_summaries(records: list[Any], limit: int) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for raw_record in (records or [])[-limit:]:
        if not isinstance(raw_record, dict):
            continue
        compacted.append(
            {
                "chunk_id": str(raw_record.get("chunk_id") or "").strip(),
                "summary": str(raw_record.get("summary") or "").strip()[:300],
                "continuity_notes": clean_string_list(raw_record.get("continuity_notes", []))[:3],
            }
        )
    return compacted


def _compact_milestone_chunk_summaries(records: list[Any], limit: int) -> list[dict[str, Any]]:
    valid_records = [record for record in records or [] if isinstance(record, dict)]
    if len(valid_records) <= limit:
        return _compact_recent_chunk_summaries(valid_records, limit)

    if limit <= 1:
        sampled = [valid_records[-1]]
    else:
        sampled = []
        max_index = len(valid_records) - 1
        for position in range(limit):
            source_index = round((max_index * position) / (limit - 1))
            sampled.append(valid_records[source_index])

    compacted: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_record in sampled:
        chunk_id = str(raw_record.get("chunk_id") or "").strip()
        if chunk_id and chunk_id in seen_ids:
            continue
        if chunk_id:
            seen_ids.add(chunk_id)
        compacted.append(
            {
                "chunk_id": chunk_id,
                "summary": str(raw_record.get("summary") or "").strip()[:260],
                "coverage": str(raw_record.get("coverage") or "").strip()[:180],
                "continuity_notes": clean_string_list(raw_record.get("continuity_notes", []))[:2],
            }
        )
    return compacted
