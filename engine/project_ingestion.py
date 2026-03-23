from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .input_loader import load_input_document
from .llm_client import call_chat_completion, parse_json_response
from .models import DocumentResult, InputDocument, PromptMessage, SkillDefinition
from .project_chunks import prepare_project_chunks
from .project_detection import should_use_project_ingestion as _should_use_project_ingestion
from .project_outputs import persist_project_artifacts, split_large_final_output
from .project_snapshots import build_state_snapshot, build_synthesis_snapshot
from .project_state import initial_project_state, merge_project_state
from .writer import write_json_file, write_text_file


def should_use_project_ingestion(
    skill: SkillDefinition,
    input_paths: list[Path],
    *,
    input_root_path: Path | None,
) -> bool:
    return _should_use_project_ingestion(skill, input_paths, input_root_path=input_root_path)


def execute_project_ingestion(
    repo_root: Path,
    skill: SkillDefinition,
    input_paths: list[Path],
    *,
    input_root_path: Path | None,
    session_dir: Path,
    forced_step_number: int | None,
    runtime_config,
    config,
    execute_document_fn,
    verbose: bool = True,
) -> tuple[Path, list[DocumentResult]]:
    intermediate_dir = session_dir / "intermediate"
    final_dir = session_dir / "final"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    chunks, source_metadata = prepare_project_chunks(
        input_paths,
        input_root_path=input_root_path,
        intermediate_dir=intermediate_dir,
    )

    if verbose:
        print(
            f"[...] input too large for single-pass processing; switching to project ingestion mode "
            f"({len(chunks)} chunk(s), overlap-aware continuity state)."
        )

    project_state = initial_project_state(skill, source_metadata, chunks)
    continuity_log: list[dict[str, Any]] = []
    persist_project_artifacts(intermediate_dir, project_state, continuity_log)

    for index, chunk in enumerate(chunks, start=1):
        if verbose:
            print(f"[project {index}/{len(chunks)}] ingesting {chunk.path.name}")
        chunk_update = _ingest_chunk(skill, chunk, project_state, config)
        merge_project_state(project_state, chunk_update, chunk)
        continuity_log.extend(
            {
                "chunk_id": chunk_update.get("chunk_id") or chunk.path.stem,
                "warning": warning,
            }
            for warning in chunk_update.get("continuity_warnings", [])
            if str(warning).strip()
        )
        persist_project_artifacts(intermediate_dir, project_state, continuity_log)

    if verbose:
        print("[...] synthesizing consolidated project outline from shared state")

    master_outline_text = _synthesize_master_outline(skill, project_state, config)
    master_outline_path = write_text_file(intermediate_dir, "master_outline.txt", master_outline_text)
    project_state["master_outline_path"] = str(master_outline_path)
    persist_project_artifacts(intermediate_dir, project_state, continuity_log)

    if verbose:
        print("[...] generating final deliverables from consolidated state")

    master_document = load_input_document(master_outline_path)
    state = execute_document_fn(
        repo_root,
        skill,
        master_document,
        final_dir,
        forced_step_number=forced_step_number,
        runtime_config=runtime_config,
        verbose=verbose,
    )

    final_parts = split_large_final_output(final_dir, state.primary_output_path)
    if final_parts:
        state.output_files["final_parts_manifest"] = str(
            write_json_file(final_dir, "final_output_parts.json", {"parts": [str(path) for path in final_parts]})
        )

    primary_output = Path(state.primary_output_path) if state.primary_output_path else None
    result = DocumentResult(
        document_path=input_root_path or input_paths[0],
        output_directory=session_dir,
        status=state.status,
        primary_output=primary_output,
    )
    return session_dir, [result]


def _ingest_chunk(skill: SkillDefinition, chunk: InputDocument, project_state: dict[str, Any], config) -> dict[str, Any]:
    schema = {
        "title": "string",
        "genre": "string",
        "tone": "string",
        "setting": "string",
        "world_rules": ["string"],
        "timeline_anchors": ["string"],
        "chapter_coverage_entry": {"chunk_id": "string", "coverage": "string"},
        "character_updates": [
            {
                "name": "string",
                "aliases": ["string"],
                "relationships": ["string"],
                "traits": ["string"],
                "voice": "string",
                "status": "string",
            }
        ],
        "locations": [{"name": "string", "details": "string"}],
        "factions": [{"name": "string", "details": "string"}],
        "important_objects": [{"name": "string", "details": "string"}],
        "unresolved_threads": ["string"],
        "resolved_threads": ["string"],
        "continuity_warnings": ["string"],
        "adaptation_decisions": ["string"],
        "rewrite_substitutions": [{"original": "string", "replacement": "string", "reason": "string"}],
        "chunk_summary": {
            "chunk_id": "string",
            "summary": "string",
            "coverage": "string",
            "key_events": ["string"],
            "continuity_notes": ["string"],
        },
        "scene_events": ["string"],
    }
    messages = [
        PromptMessage(
            role="system",
            content="You are updating a persistent long-text project state. Return only one JSON object.",
        ),
        PromptMessage(
            role="user",
            content=(
                f"Skill: {skill.display_name}\n"
                f"Description: {skill.description}\n"
                "Task: read the current text chunk, preserve durable facts in canonical state, and preserve immediate local continuity in rolling context.\n\n"
                f"Current canonical/rolling state snapshot:\n{json.dumps(build_state_snapshot(project_state), ensure_ascii=False, indent=2)}\n\n"
                f"Current chunk: {chunk.path.name}\n"
                f"Estimated tokens: {chunk.estimated_tokens}\n\n"
                f"Chunk text:\n{chunk.text}\n\n"
                f"Return JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
            ),
        ),
    ]
    response = call_chat_completion(config, messages, json_mode=True)
    payload = parse_json_response(response)
    payload["chunk_id"] = str(payload.get("chunk_id") or chunk.path.stem)
    return payload


def _synthesize_master_outline(skill: SkillDefinition, project_state: dict[str, Any], config) -> str:
    synthesis_snapshot = build_synthesis_snapshot(project_state)
    messages = [
        PromptMessage(
            role="system",
            content="You are synthesizing a consolidated large-text project context for a downstream skill. Return only the final text.",
        ),
        PromptMessage(
            role="user",
            content=(
                f"Target skill: {skill.display_name}\n"
                f"Skill description: {skill.description}\n"
                f"Synthesis guidance: {_build_skill_synthesis_guidance(skill)}\n\n"
                "Use the project state below to produce one consolidated master outline / source dossier that preserves continuity across all chunks.\n"
                "This text will become the single logical input for the downstream skill workflow.\n\n"
                f"Project state:\n{json.dumps(synthesis_snapshot, ensure_ascii=False, indent=2)}"
            ),
        ),
    ]
    response = call_chat_completion(config, messages, json_mode=False)
    return response.text


def _build_skill_synthesis_guidance(skill: SkillDefinition) -> str:
    if skill.name == "rewriting":
        return (
            "Produce a rewrite-ready consolidated source dossier: preserve chronology, scene/event order, character voice, and any rewrite substitutions or platform-safe wording decisions."
        )
    if skill.name == "novel_adaptation_plan":
        return (
            "Produce an adaptation-planning master outline emphasizing premise, characters, pacing phases, set pieces, and chapter/event coverage."
        )
    if skill.name == "novel_to_drama_script":
        return (
            "Produce a script-generation dossier emphasizing episode structure, major beats, continuity anchors, scene flow, and actionable adaptation detail."
        )
    if skill.execution_strategy == "structured_report":
        return "Produce a structured-analysis master outline optimized for the downstream report workflow."
    return "Produce a compact but continuity-safe master outline optimized for the downstream workflow."
