from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ltx_skill_module_loader import load_local_module

_build_ltx_prompt_requests = load_local_module("build_ltx_prompt_requests")
_gemini_prompt_director = load_local_module("gemini_prompt_director")
_load_recap_production = load_local_module("load_recap_production")
_validate_ltx_prompts = load_local_module("validate_ltx_prompts")

build_ltx_prompt_request = _build_ltx_prompt_requests.build_ltx_prompt_request
direct_shot_prompt_with_gemini = _gemini_prompt_director.direct_shot_prompt_with_gemini
RecapShot = _load_recap_production.RecapShot
load_recap_bundle = _load_recap_production.load_recap_bundle
validate_generated_prompt_payload = _validate_ltx_prompts.validate_generated_prompt_payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read a recap-production or cp-production folder and generate structured LTX-ready shot prompts with Gemini."
    )
    parser.add_argument(
        "--recap-folder",
        help=(
            "Path to the recap production folder, story run folder, 04_episode_scene_script.json, "
            "or a cp-production folder containing 02_beat_sheet.json and 05_video_prompts.json"
        ),
    )
    parser.add_argument("--model-alias", default="gemini", help="Configured model alias from config.ini. Default: gemini.")
    parser.add_argument("--limit", type=int, help="Only process the first N shots.")
    parser.add_argument("--shot-id", help="Only process one specific shot id, for example ep01_s03.")
    parser.add_argument("--output-root", help="Optional output directory. Defaults to a generated_ltx_prompts folder beside the recap bundle.")
    parser.add_argument("--debug-output", action="store_true", help="Write per-shot debug JSON with request, raw response, and fallback details.")
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting for missing recap folder.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = parse_args(argv)
    manifest_path = execute_generation(args)
    safe_print(f"[ltx-skill] completed: {manifest_path}")
    return 0


def run(
    *,
    repo_root: Path,
    skill,
    document,
    output_dir: Path,
    step_number: int,
    runtime_values: dict[str, Any],
    state,
) -> dict[str, Any]:
    del step_number, state
    configure_utf8_console()
    default_recap_folder = normalize_recap_folder_input(runtime_values.get("recap_folder") or str(document.path))
    recap_folder = prompt_recap_folder_with_default(non_interactive=False, default_value=default_recap_folder)
    args = argparse.Namespace(
        recap_folder=recap_folder,
        model_alias=runtime_values.get("model_alias") or "gemini",
        limit=optional_int(runtime_values.get("limit")),
        shot_id=runtime_values.get("shot_id"),
        output_root=str((output_dir.resolve() / "generated_ltx_prompts")),
        debug_output=truthy(runtime_values.get("debug_output")),
        non_interactive=True,
    )
    manifest_path = execute_generation(args, repo_root=repo_root, skill=skill)
    return {
        "primary_output": manifest_path,
        "output_files": {
            "primary": manifest_path,
            "manifest": manifest_path,
        },
        "notes": [
            f"Recap source: {document.path}",
            f"Model alias: {args.model_alias}",
            f"Manifest: {manifest_path}",
        ],
        "status": "completed",
    }


def execute_generation(
    args: argparse.Namespace,
    *,
    repo_root: Path | None = None,
    skill: Any = None,
) -> Path:
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    recap_folder = (
        args.recap_folder
        if args.non_interactive and args.recap_folder
        else prompt_recap_folder_with_default(non_interactive=args.non_interactive, default_value=args.recap_folder)
    )
    safe_print(f"[ltx-skill] reading LTX source folder: {recap_folder}")
    bundle = load_recap_bundle(recap_folder)
    safe_print(f"[ltx-skill] input contract: {bundle.input_contract}")
    safe_print(f"[ltx-skill] locating beat source: {bundle.scene_script_file}")
    for note in bundle.selection_notes:
        safe_print(f"[ltx-skill] {note}")
    keyscene_index = bundle.discover_generated_keyscenes()
    if keyscene_index.has_any_images():
        safe_print(f"[ltx-skill] discovered image-conditioning candidates: {len(keyscene_index.items_by_beat)} in {keyscene_index.root_dir}")
    else:
        safe_print("[ltx-skill] no generated keyscene images were found; prompt-pack generation will continue in text-only mode.")

    shots = select_shots(bundle.shots, limit=args.limit, shot_id=args.shot_id)
    safe_print(f"[ltx-skill] extracting shot beats: {len(shots)}")

    output_root = resolve_output_dir(args.output_root, bundle.recap_dir, "generated_ltx_prompts")
    output_root.mkdir(parents=True, exist_ok=True)
    debug_dir = output_root / "debug"
    if args.debug_output:
        debug_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    by_episode: dict[str, list[dict[str, Any]]] = {}
    fallback_count = 0
    success_count = 0
    validation_issue_count = 0
    resolved_route = ""
    resolved_model = ""

    total = len(shots)
    for index, shot in enumerate(shots, start=1):
        image_conditioning = keyscene_index.find_for_shot(shot)
        request = build_ltx_prompt_request(shot, total_shots=total, shot_index=index)
        safe_print(f"[ltx-skill] sending shot {index}/{total} to Gemini: {shot.shot_id}")
        result = direct_shot_prompt_with_gemini(
            repo_root=repo_root,
            skill=skill,
            request_payload=request,
            model_alias=args.model_alias,
        )
        resolved_route = result.route or resolved_route
        resolved_model = result.model or resolved_model
        validation = validate_generated_prompt_payload(result.payload)
        status = "valid" if validation.is_valid else "invalid"
        safe_print(f"[ltx-skill] validating generated prompt: {shot.shot_id} -> {status}")
        if result.status != "success":
            fallback_count += 1
        else:
            success_count += 1
        if not validation.is_valid:
            validation_issue_count += len(validation.issues)

        item = build_prompt_item(
            shot=shot,
            payload=result.payload,
            result=result,
            validation_issues=list(validation.issues),
            image_conditioning_path=image_conditioning.path if image_conditioning is not None else None,
        )
        items.append(item)
        by_episode.setdefault(shot.episode_id, []).append(item)

        if args.debug_output:
            write_debug_artifact(
                debug_dir / f"{safe_slug(shot.shot_id)}.json",
                shot=shot,
                request=request.structured_input,
                result=result,
                validation_issues=list(validation.issues),
                image_conditioning_path=image_conditioning.path if image_conditioning is not None else None,
            )

    prompts_path = output_root / "prompts.json"
    prompts_payload = {
        "schema": "ltx_prompt_pack_v2",
        "input_contract": bundle.input_contract,
        "series_title": bundle.series_title,
        "story_slug": bundle.story_slug,
        "model_alias": args.model_alias,
        "resolved_model_route": resolved_route,
        "resolved_model": resolved_model,
        "item_count": len(items),
        "items": items,
    }
    prompts_path.write_text(json.dumps(prompts_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    prompts_by_episode_path = output_root / "prompts_by_episode.json"
    prompts_by_episode_payload = {
        "schema": "ltx_prompt_pack_by_episode_v2",
        "series_title": bundle.series_title,
        "episodes": [
            {
                "episode_id": episode_id,
                "shot_count": len(episode_items),
                "items": episode_items,
            }
            for episode_id, episode_items in sorted(by_episode.items())
        ],
    }
    prompts_by_episode_path.write_text(
        json.dumps(prompts_by_episode_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest_path = output_root / "manifest.json"
    manifest = {
        "schema": "ltx_prompt_generation_manifest_v2",
        "timestamp": timestamp_now(),
        "input_folder": str(bundle.recap_dir),
        "input_contract": bundle.input_contract,
        "selected_scene_script": str(bundle.scene_script_file),
        "selection_notes": list(bundle.selection_notes),
        "input_files": {
            "scene_script_or_beat_sheet": str(bundle.scene_script_file),
            "scene_script_markdown": str(bundle.scene_script_markdown) if bundle.scene_script_markdown else None,
            "assets_file": str(bundle.assets_file) if bundle.assets_file else None,
            "image_config_file": str(bundle.image_config_file) if bundle.image_config_file else None,
            "anchor_prompts_file": str(bundle.anchor_prompts_file) if bundle.anchor_prompts_file else None,
            "video_prompts_file": str(bundle.video_prompts_file) if bundle.video_prompts_file else None,
            "narration_script_file": str(bundle.narration_script_file) if bundle.narration_script_file else None,
        },
        "asset_context_count": len(bundle.assets_lookup),
        "series_title": bundle.series_title,
        "story_slug": bundle.story_slug,
        "model_alias_used": args.model_alias,
        "resolved_model_route": resolved_route,
        "resolved_model": resolved_model,
        "shot_count": len(items),
        "success_count": success_count,
        "fallback_count": fallback_count,
        "validation_issue_count": validation_issue_count,
        "validation_status": "valid" if validation_issue_count == 0 else "warnings",
        "image_conditioning_summary": {
            "found": keyscene_index.has_any_images(),
            "count": len(keyscene_index.items_by_beat),
            "root_dir": str(keyscene_index.root_dir),
            "searched_paths": [str(path) for path in keyscene_index.searched_paths],
        },
        "output_root": str(output_root),
        "output_paths": {
            "prompts": str(prompts_path),
            "prompts_by_episode": str(prompts_by_episode_path),
            "debug": str(debug_dir) if args.debug_output else None,
            "manifest": str(manifest_path),
        },
    }
    safe_print("[ltx-skill] saving structured prompt outputs")
    safe_print("[ltx-skill] writing manifest")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def build_prompt_item(
    *,
    shot: RecapShot,
    payload: dict[str, str],
    result,
    validation_issues: list[str],
    image_conditioning_path: Path | None,
) -> dict[str, Any]:
    return {
        "episode_id": payload.get("episode_id") or shot.episode_id,
        "shot_id": payload.get("shot_id") or shot.shot_id,
        "source_contract": shot.source_contract,
        "shot_type": payload.get("shot_type") or shot.shot_type,
        "shot_mode": payload.get("shot_mode", ""),
        "scene_setup": payload.get("scene_setup", ""),
        "character_definition": payload.get("character_definition", ""),
        "action_sequence": payload.get("action_sequence", ""),
        "environment_motion": payload.get("environment_motion", ""),
        "camera_motion": payload.get("camera_motion", ""),
        "audio_description": payload.get("audio_description", ""),
        "acting_cues": payload.get("acting_cues", ""),
        "duration_hint": payload.get("duration_hint", ""),
        "final_prompt": payload.get("final_prompt", ""),
        "prompt_language": payload.get("prompt_language", "zh"),
        "raw_gemini_final_prompt": payload.get("raw_gemini_final_prompt", ""),
        "source_summary": shot.summary,
        "source_video_prompt": shot.video_prompt,
        "source_visual_prompt": shot.visual_prompt,
        "source_anchor_prompt": shot.anchor_prompt,
        "source_anchor_text": shot.anchor_text,
        "source_mood": shot.mood,
        "source_camera_motion": shot.camera_motion,
        "source_shot_type": shot.shot_type,
        "source_linked_assets": list(shot.linked_assets),
        "source_linked_asset_context": shot.source_payload.get("cp_linked_asset_context", []) if isinstance(shot.source_payload, dict) else [],
        "source_beat_text": shot.combined_text,
        "image_conditioning_path": str(image_conditioning_path) if image_conditioning_path else None,
        "image_conditioning_found": image_conditioning_path is not None,
        "prompt_source": result.source,
        "generation_status": result.status,
        "warning": result.warning,
        "fallback_reason": result.fallback_reason,
        "is_valid": not validation_issues,
        "validation_issues": validation_issues,
        "model_alias": result.model_alias,
        "resolved_model": result.model,
        "resolved_route": result.route,
    }


def write_debug_artifact(
    path: Path,
    *,
    shot: RecapShot,
    request: dict[str, Any],
    result,
    validation_issues: list[str],
    image_conditioning_path: Path | None,
) -> None:
    payload = {
        "shot_id": shot.shot_id,
        "episode_id": shot.episode_id,
        "source_beat_text": {
            "source_contract": shot.source_contract,
            "summary": shot.summary,
            "video_prompt": shot.video_prompt,
            "visual_prompt": shot.visual_prompt,
            "anchor_prompt": shot.anchor_prompt,
            "anchor_text": shot.anchor_text,
            "mood": shot.mood,
            "shot_type": shot.shot_type,
            "camera_motion": shot.camera_motion,
            "pace_weight": shot.pace_weight,
            "asset_focus": shot.asset_focus,
            "linked_assets": list(shot.linked_assets),
            "linked_asset_context": shot.source_payload.get("cp_linked_asset_context", []) if isinstance(shot.source_payload, dict) else [],
            "combined_text": shot.combined_text,
        },
        "image_conditioning_path": str(image_conditioning_path) if image_conditioning_path else None,
        "request": request,
        "structured_intermediate_fields": result.payload,
        "result_status": result.status,
        "result_source": result.source,
        "warning": result.warning,
        "fallback_reason": result.fallback_reason,
        "validation_result": {
            "is_valid": not validation_issues,
            "issues": validation_issues,
        },
        "final_prompt": result.payload.get("final_prompt", ""),
        "raw_response_text": result.raw_response_text,
        "raw_response_json": result.raw_response_json,
        "resolved_model": result.model,
        "resolved_route": result.route,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def select_shots(shots: list[RecapShot], *, limit: int | None, shot_id: str | None) -> list[RecapShot]:
    selected = shots
    if shot_id:
        selected = [shot for shot in shots if shot.shot_id == shot_id]
        if not selected:
            raise ValueError(f"Shot id not found in recap bundle: {shot_id}")
    if limit is not None:
        selected = selected[: max(limit, 0)]
    if not selected:
        raise ValueError("No shots were selected for prompt generation.")
    return selected


def resolve_output_dir(output_root: str | None, recap_dir: Path, folder_name: str) -> Path:
    if output_root:
        return Path(output_root).expanduser().resolve()
    if recap_dir.name in {"02_recap_production", "01_recap_production"}:
        return (recap_dir.parent / folder_name).resolve()
    return (recap_dir / folder_name).resolve()


def normalize_recap_folder_input(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    if candidate.is_file() and candidate.name in {
        "04_episode_scene_script.json",
        "02_beat_sheet.json",
        "03_asset_registry.json",
        "04_anchor_prompts.json",
        "05_video_prompts.json",
    }:
        return str(candidate.parent)
    return str(candidate)


def prompt_recap_folder_with_default(*, non_interactive: bool, default_value: str | None) -> str:
    if non_interactive:
        if not default_value:
            raise ValueError("Missing required --recap-folder for non-interactive execution.")
        return default_value
    prompt = "What is the recap production or cp-production output folder path?"
    if default_value:
        prompt += f" Press Enter to use [{default_value}]: "
    else:
        prompt += " "
    response = input(prompt).strip()
    if not response:
        response = default_value or ""
    if not response:
        raise ValueError("A recap production or cp-production output folder path is required.")
    return response


def optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def timestamp_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in str(value or ""))
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned or "item"


def safe_print(message: str) -> None:
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                continue


if __name__ == "__main__":
    raise SystemExit(main())
