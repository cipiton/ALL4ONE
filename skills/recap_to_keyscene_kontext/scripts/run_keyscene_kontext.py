from __future__ import annotations

import argparse
import copy
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
for import_root in (REPO_ROOT, SCRIPT_DIR):
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)

try:
    from .prompt_cleanup import (
        PromptCleanupResult,
        build_prompt_cleanup_input,
        cleanup_prompt_with_gemini,
        normalize_model_alias,
        normalize_prompt_cleanup_mode,
    )
except ImportError:
    from prompt_cleanup import (
        PromptCleanupResult,
        build_prompt_cleanup_input,
        cleanup_prompt_with_gemini,
        normalize_model_alias,
        normalize_prompt_cleanup_mode,
    )


DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_PORTRAIT_WIDTH = 576
DEFAULT_PORTRAIT_HEIGHT = 1024
HIGH_QUALITY_PORTRAIT_WIDTH = 768
HIGH_QUALITY_PORTRAIT_HEIGHT = 1344
DEFAULT_WIDTH = DEFAULT_PORTRAIT_WIDTH
DEFAULT_HEIGHT = DEFAULT_PORTRAIT_HEIGHT
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ASSET_GROUPS = ("characters", "scenes", "props")
GROUP_TO_KIND = {"characters": "character", "scenes": "scene", "props": "prop"}
ROLE_TO_GROUP = {"character": "characters", "scene": "scenes", "prop": "props"}
REFERENCE_ORDER_MODES = ("auto", "identity_first", "staging_first", "object_first")
REFERENCE_ORDER_PRIORITY = {
    "identity_first": ("character", "scene", "prop"),
    "staging_first": ("scene", "character", "prop"),
    "object_first": ("prop", "scene", "character"),
}
BRIDGE_STAGE_FOLDERS = ("04_recap_to_comfy_bridge", "03_recap_to_comfy_bridge")
ASSETS_STAGE_FOLDERS = ("05_assets_t2i", "04_assets_t2i")
STORYBOARD_FILENAME = "videoarc_storyboard.json"
PROMPT_CLEANUP_MODEL_ALIAS = "gemini"


@dataclass(frozen=True, slots=True)
class AssetFile:
    group: str
    kind: str
    asset_id: str
    asset_name: str
    path: Path
    relpath: str
    source: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SelectedAsset:
    asset: AssetFile | None
    strategy: str
    score: int
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StagePaths:
    run_root: Path
    bridge_dir: Path
    assets_dir: Path
    storyboard_path: Path


@dataclass(frozen=True, slots=True)
class BeatPlan:
    index: int
    beat: dict[str, Any]
    beat_id: str
    prompt: str
    prompt_cleanup: PromptCleanupResult
    seed: int
    output_file: Path
    payload_file: Path
    selected: dict[str, SelectedAsset]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    role: str
    asset: AssetFile
    image_value: str


@dataclass(frozen=True, slots=True)
class ReferenceOrderPlan:
    mode: str
    shot_priority: str
    reason: str
    manual_override: bool
    candidates: tuple[ReferenceCandidate, ...]


@dataclass(frozen=True, slots=True)
class WorkflowReferenceGraph:
    load_image_nodes: dict[str, str]
    first_stitch_node_id: str | None
    second_stitch_node_id: str | None
    scale_after_first_stitch_node_id: str | None
    final_scale_node_id: str | None
    vae_encode_node_id: str | None
    reference_latent_node_id: str | None


class KeysceneValidationError(FileNotFoundError):
    def __init__(self, message: str, *, missing_paths: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_paths = list(missing_paths or [])


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
    skill_dir = Path(getattr(skill, "skill_dir", Path(__file__).resolve().parents[1]))
    endpoint = _runtime_value(runtime_values, "comfyui_url") or os.environ.get("ONE4ALL_COMFYUI_URL") or DEFAULT_COMFYUI_URL
    dry_run = _truthy(_runtime_value(runtime_values, "dry_run") or os.environ.get("ONE4ALL_KONTEXT_DRY_RUN"))
    width = _optional_int(_runtime_value(runtime_values, "width") or os.environ.get("ONE4ALL_KONTEXT_WIDTH")) or DEFAULT_WIDTH
    height = _optional_int(_runtime_value(runtime_values, "height") or os.environ.get("ONE4ALL_KONTEXT_HEIGHT")) or DEFAULT_HEIGHT
    seed_override = _optional_int(_runtime_value(runtime_values, "seed") or os.environ.get("ONE4ALL_KONTEXT_SEED"))
    limit = _optional_int(_runtime_value(runtime_values, "limit") or os.environ.get("ONE4ALL_KONTEXT_LIMIT"))
    reference_order_mode = _normalize_reference_order_mode(
        _runtime_value(runtime_values, "reference_order_mode") or os.environ.get("ONE4ALL_KONTEXT_REFERENCE_ORDER_MODE")
    )
    debug_reference_order = _truthy(
        _runtime_value(runtime_values, "debug_reference_order") or os.environ.get("ONE4ALL_KONTEXT_DEBUG_REFERENCE_ORDER")
    )
    prompt_cleanup_mode = normalize_prompt_cleanup_mode(
        _runtime_value(runtime_values, "prompt_cleanup_mode") or os.environ.get("ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODE")
    )
    prompt_cleanup_model = normalize_model_alias(
        _runtime_value(runtime_values, "prompt_cleanup_model") or os.environ.get("ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODEL") or PROMPT_CLEANUP_MODEL_ALIAS
    )
    debug_prompt_cleanup = _truthy(
        _runtime_value(runtime_values, "debug_prompt_cleanup") or os.environ.get("ONE4ALL_KONTEXT_DEBUG_PROMPT_CLEANUP")
    )
    template_path = Path(
        _runtime_value(runtime_values, "workflow_template")
        or os.environ.get("ONE4ALL_KONTEXT_WORKFLOW_TEMPLATE")
        or skill_dir / "assets" / "i2iscenes.json"
    ).expanduser().resolve()
    upload_assets = not _falsy(os.environ.get("ONE4ALL_COMFY_UPLOAD_IMAGES"))

    result = run_keyscene_stage(
        input_path=document.path,
        output_dir=output_dir,
        skill_dir=skill_dir,
        template_path=template_path,
        endpoint=endpoint,
        dry_run=dry_run,
        width=width,
        height=height,
        seed_override=seed_override,
        limit=limit,
        upload_assets=upload_assets,
        reference_order_mode=reference_order_mode,
        debug_reference_order=debug_reference_order,
        repo_root=repo_root,
        skill=skill,
        prompt_cleanup_mode=prompt_cleanup_mode,
        prompt_cleanup_model=prompt_cleanup_model,
        debug_prompt_cleanup=debug_prompt_cleanup,
    )
    notes = [
        f"Loaded {result['beat_count']} storyboard beat(s).",
        f"Prepared {result['processed_count']} ComfyUI payload(s).",
        f"Dry run: {result['dry_run']}.",
        f"Wrote manifest to {result['manifest_path']}.",
    ]
    if result["failure_count"]:
        notes.append(f"Beat failures: {result['failure_count']}.")
    return {
        "primary_output": Path(result["manifest_path"]),
        "output_files": {
            "primary": Path(result["manifest_path"]),
            "manifest": Path(result["manifest_path"]),
            "payloads_dir": output_dir / "payloads",
        },
        "notes": notes,
        "status": "completed",
    }


def run_keyscene_stage(
    *,
    input_path: Path,
    output_dir: Path | None,
    skill_dir: Path,
    repo_root: Path,
    skill,
    template_path: Path,
    endpoint: str,
    dry_run: bool,
    width: int,
    height: int,
    seed_override: int | None,
    limit: int | None,
    upload_assets: bool,
    reference_order_mode: str,
    debug_reference_order: bool,
    prompt_cleanup_mode: str,
    prompt_cleanup_model: str,
    debug_prompt_cleanup: bool,
) -> dict[str, Any]:
    del skill_dir
    stage_paths = resolve_stage_paths(input_path)
    if output_dir is None:
        output_dir = stage_paths.run_root / "06_keyscene_i2i"
    output_dir = output_dir.resolve()
    payloads_dir = output_dir / "payloads"
    prompt_cleanup_debug_dir = output_dir / "prompt_cleanup_debug"
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads_dir.mkdir(parents=True, exist_ok=True)
    if debug_prompt_cleanup:
        prompt_cleanup_debug_dir.mkdir(parents=True, exist_ok=True)

    template = _load_json(template_path)
    storyboard = _load_json(stage_paths.storyboard_path)
    beats = _extract_beats(storyboard)
    if limit is not None and limit > 0:
        beats = beats[:limit]
    if not beats:
        raise ValueError(f"No storyboard beats found in {stage_paths.storyboard_path}")
    assets = load_asset_catalog(stage_paths.assets_dir)
    manifest_items: list[dict[str, Any] | None] = [None] * len(beats)
    beat_plans: list[BeatPlan] = []
    success_count = 0
    failure_count = 0
    dry_run_count = 0

    for index, beat in enumerate(beats, start=1):
        beat_id = _beat_id(beat, index)
        output_file = output_dir / f"{_safe_stem(beat_id)}.png"
        payload_file = payloads_dir / f"{_safe_stem(beat_id)}.json"
        seed = seed_override if seed_override is not None else _stable_seed(beat_id, _beat_text(beat))
        selected = {
            "scene": select_asset("scenes", beat, assets.get("scenes", [])),
            "character": select_asset("characters", beat, assets.get("characters", [])),
            "prop": select_asset("props", beat, assets.get("props", [])),
        }
        notes: list[str] = []
        for selected_asset in selected.values():
            notes.extend(selected_asset.notes)

        try:
            _validate_selected_assets(beat_id=beat_id, selected=selected, assets_dir=stage_paths.assets_dir)
        except Exception as exc:  # noqa: BLE001
            failure_count += 1
            manifest_items[index - 1] = _build_error_manifest_item(
                beat=beat,
                beat_id=beat_id,
                prompt=prompt,
                seed=seed,
                width=width,
                height=height,
                selected=selected,
                assets_dir=stage_paths.assets_dir,
                output_dir=output_dir,
                payload_file=payload_file,
                output_file=output_file,
                notes=notes,
                exc=exc,
            )
            continue

        prompt_cleanup = _prepare_keyscene_prompt(
            repo_root=repo_root,
            skill=skill,
            beat=beat,
            beat_id=beat_id,
            selected=selected,
            prompt_cleanup_mode=prompt_cleanup_mode,
            prompt_cleanup_model=prompt_cleanup_model,
            debug_prompt_cleanup=debug_prompt_cleanup,
            prompt_cleanup_debug_dir=prompt_cleanup_debug_dir,
        )
        prompt = prompt_cleanup.final_prompt

        beat_plans.append(
            BeatPlan(
                index=index,
                beat=beat,
                beat_id=beat_id,
                prompt=prompt,
                prompt_cleanup=prompt_cleanup,
                seed=seed,
                output_file=output_file,
                payload_file=payload_file,
                selected=selected,
                notes=tuple(_dedupe_preserve_order(notes)),
            )
        )

    if beat_plans and not dry_run:
        _assert_comfyui_reachable(endpoint)

    for plan in beat_plans:
        try:
            workflow = copy.deepcopy(template)
            workflow_asset_inputs = _resolve_workflow_image_values(
                endpoint=endpoint,
                selected=plan.selected,
                dry_run=dry_run,
                upload_assets=upload_assets,
            )
            reference_plan = _build_reference_order_plan(
                beat=plan.beat,
                selected=plan.selected,
                workflow_asset_inputs=workflow_asset_inputs,
                requested_mode=reference_order_mode,
                prompt_cleanup=plan.prompt_cleanup,
            )
            substitution_summary = substitute_workflow(
                workflow,
                reference_plan=reference_plan,
                prompt=plan.prompt,
                filename_prefix=f"one4all_keyscene/{_safe_stem(plan.beat_id)}",
                width=width,
                height=height,
                seed=plan.seed,
            )
            if debug_reference_order:
                _log_reference_order_debug(plan.beat_id, reference_plan, substitution_summary)
            plan.payload_file.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
            item: dict[str, Any] = {
                "beat_id": plan.beat_id,
                "episode_number": plan.beat.get("episode_number"),
                "prompt": plan.prompt,
                "seed": plan.seed,
                "width": width,
                "height": height,
                "chosen_scene_asset": _selected_asset_manifest(plan.selected["scene"], stage_paths.assets_dir),
                "chosen_character_asset": _selected_asset_manifest(plan.selected["character"], stage_paths.assets_dir),
                "chosen_prop_asset": _selected_asset_manifest(plan.selected["prop"], stage_paths.assets_dir),
                "workflow_inputs": workflow_asset_inputs,
                "prompt_cleanup": _prompt_cleanup_manifest(plan.prompt_cleanup, output_dir=output_dir),
                "reference_order": _reference_plan_manifest(reference_plan),
                "workflow_substitutions": substitution_summary,
                "payload_file": str(plan.payload_file.relative_to(output_dir)),
                "output_file": str(plan.output_file.relative_to(output_dir)),
                "fallback_notes": list(plan.notes),
            }
            if dry_run:
                dry_run_count += 1
                item["status"] = "dry_run"
            else:
                item["comfyui"] = submit_and_collect(endpoint=endpoint, workflow=workflow, output_path=plan.output_file)
                item["status"] = "success"
                success_count += 1
            manifest_items[plan.index - 1] = item
        except Exception as exc:  # noqa: BLE001
            failure_count += 1
            manifest_items[plan.index - 1] = _build_error_manifest_item(
                beat=plan.beat,
                beat_id=plan.beat_id,
                prompt=plan.prompt,
                seed=plan.seed,
                width=width,
                height=height,
                selected=plan.selected,
                assets_dir=stage_paths.assets_dir,
                output_dir=output_dir,
                payload_file=plan.payload_file,
                output_file=plan.output_file,
                notes=plan.notes,
                prompt_cleanup=plan.prompt_cleanup,
                exc=exc,
            )

    manifest_path = output_dir / "manifest.json"
    manifest_items = [item for item in manifest_items if item is not None]
    manifest = {
        "schema": "one4all_keyscene_i2i_manifest_v1",
        "skill": "recap_to_keyscene_kontext",
        "backend": {
            "type": "comfyui-flux-kontext-api",
            "endpoint": endpoint,
            "workflow_template": str(template_path),
            "upload_assets": upload_assets,
        },
        "prompt_cleanup": {
            "mode": prompt_cleanup_mode,
            "model_alias": prompt_cleanup_model,
            "debug_enabled": debug_prompt_cleanup,
        },
        "dry_run": dry_run,
        "story_title": storyboard.get("series_title") or stage_paths.run_root.parent.name,
        "run_root": str(stage_paths.run_root),
        "source_storyboard_file": str(stage_paths.storyboard_path),
        "source_assets_dir": str(stage_paths.assets_dir),
        "output_dir": str(output_dir),
        "beat_count": len(beats),
        "processed_count": len(manifest_items),
        "success_count": success_count,
        "dry_run_count": dry_run_count,
        "failure_count": failure_count,
        "items": manifest_items,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "manifest_path": str(manifest_path),
        "beat_count": len(beats),
        "processed_count": len(manifest_items),
        "success_count": success_count,
        "dry_run_count": dry_run_count,
        "failure_count": failure_count,
        "dry_run": dry_run,
    }


def resolve_stage_paths(input_path: Path) -> StagePaths:
    candidate = input_path.expanduser().resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Input path does not exist: {candidate}")
    run_root = _infer_run_root(candidate)
    if run_root is None:
        raise ValueError(
            "Recap To Keyscene Kontext expects the story run folder, "
            "`04_recap_to_comfy_bridge/`, `05_assets_t2i/`, an asset-group subfolder, "
            "or a file inside either stage folder."
        )
    bridge_dir = _resolve_stage_dir(run_root, BRIDGE_STAGE_FOLDERS) or run_root / BRIDGE_STAGE_FOLDERS[0]
    assets_dir = _resolve_stage_dir(run_root, ASSETS_STAGE_FOLDERS) or run_root / ASSETS_STAGE_FOLDERS[0]
    return _validated_stage_paths(run_root, bridge_dir, assets_dir, bridge_dir / STORYBOARD_FILENAME)


def _infer_run_root(candidate: Path) -> Path | None:
    anchor = candidate if candidate.is_dir() else candidate.parent
    if anchor.name in ASSET_GROUPS and anchor.parent.name in ASSETS_STAGE_FOLDERS:
        return anchor.parent.parent.resolve()
    if anchor.name in BRIDGE_STAGE_FOLDERS or anchor.name in ASSETS_STAGE_FOLDERS:
        return anchor.parent.resolve()
    if candidate.is_dir():
        return candidate.resolve()
    return None


def _resolve_stage_dir(run_root: Path, stage_folders: tuple[str, ...]) -> Path | None:
    for stage_folder in stage_folders:
        candidate = run_root / stage_folder
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _validated_stage_paths(run_root: Path, bridge_dir: Path, assets_dir: Path, storyboard_path: Path) -> StagePaths:
    problems: list[str] = []
    missing_paths: list[str] = []
    if not bridge_dir.exists() or not bridge_dir.is_dir():
        problems.append(f"bridge stage folder: {bridge_dir}")
        missing_paths.append(str(bridge_dir))
    if not assets_dir.exists() or not assets_dir.is_dir():
        problems.append(f"asset stage folder: {assets_dir}")
        missing_paths.append(str(assets_dir))
    if not storyboard_path.exists() or not storyboard_path.is_file():
        problems.append(f"storyboard file: {storyboard_path}")
        missing_paths.append(str(storyboard_path))
    for group in ASSET_GROUPS:
        group_dir = assets_dir / group
        if not group_dir.exists() or not group_dir.is_dir():
            problems.append(f"{group} assets folder: {group_dir}")
            missing_paths.append(str(group_dir))
    if problems:
        raise KeysceneValidationError(
            "Recap To Keyscene Kontext requires a story run with bridge outputs and T2I assets. "
            f"Missing required input(s): {'; '.join(problems)}",
            missing_paths=missing_paths,
        )
    return StagePaths(run_root.resolve(), bridge_dir.resolve(), assets_dir.resolve(), storyboard_path.resolve())


def _validate_selected_assets(*, beat_id: str, selected: dict[str, SelectedAsset], assets_dir: Path) -> None:
    problems: list[str] = []
    missing_paths: list[str] = []
    available_count = 0
    for role in ("character", "scene", "prop"):
        selected_asset = selected.get(role)
        asset = selected_asset.asset if selected_asset is not None else None
        if asset is None:
            continue
        available_count += 1
        if not asset.path.exists() or not asset.path.is_file():
            problems.append(f"{role} reference for beat '{beat_id}' is missing: {asset.path}")
            missing_paths.append(str(asset.path))
    if available_count == 0:
        problems.append(
            f"beat '{beat_id}' does not have any usable reference images in {assets_dir}"
        )
        missing_paths.append(str(assets_dir))
    if problems:
        raise KeysceneValidationError(
            "Missing required reference image(s) before ComfyUI submission: " + "; ".join(problems),
            missing_paths=missing_paths,
        )


def load_asset_catalog(assets_dir: Path) -> dict[str, list[AssetFile]]:
    manifest_path = assets_dir / "manifest.json"
    manifest = _load_json(manifest_path) if manifest_path.exists() else {}
    catalog: dict[str, list[AssetFile]] = {group: [] for group in ASSET_GROUPS}
    for item in manifest.get("items", []) if isinstance(manifest, dict) else []:
        if not isinstance(item, dict):
            continue
        group = str(item.get("group") or "").replace("\\", "/").strip()
        if group not in catalog:
            continue
        output_file = str(item.get("output_file") or "").strip()
        if not output_file:
            continue
        path = (assets_dir / Path(output_file)).resolve()
        if not path.exists():
            continue
        catalog[group].append(
            AssetFile(
                group=group,
                kind=str(item.get("asset_type") or GROUP_TO_KIND[group]),
                asset_id=str(item.get("asset_id") or path.stem).strip(),
                asset_name=str(item.get("asset_name") or _name_from_stem(path.stem, GROUP_TO_KIND[group])).strip(),
                path=path,
                relpath=str(path.relative_to(assets_dir)),
                source=item,
            )
        )
    for group in ASSET_GROUPS:
        known_paths = {asset.path for asset in catalog[group]}
        for path in sorted((assets_dir / group).iterdir(), key=lambda item: item.name.casefold()):
            if path.suffix.lower() not in IMAGE_EXTENSIONS or path.resolve() in known_paths:
                continue
            kind = GROUP_TO_KIND[group]
            catalog[group].append(
                AssetFile(
                    group=group,
                    kind=kind,
                    asset_id=path.stem,
                    asset_name=_name_from_stem(path.stem, kind),
                    path=path.resolve(),
                    relpath=str(path.resolve().relative_to(assets_dir.resolve())),
                    source={"source": "directory_scan"},
                )
            )
    return catalog


def select_asset(group: str, beat: dict[str, Any], assets: list[AssetFile]) -> SelectedAsset:
    if not assets:
        return SelectedAsset(None, "missing", 0, (f"No {group} assets are available.",))
    kind = GROUP_TO_KIND[group]
    hints = _hint_values(group, beat)
    beat_text = _beat_text(beat)
    notes: list[str] = []
    if len(hints) > 1:
        notes.append(f"{group}: multiple hints found ({', '.join(hints)}); v1 uses one primary {kind}.")
    scored: list[tuple[int, str, AssetFile]] = []
    for asset in assets:
        score, strategy = _score_asset(asset, hints, beat_text)
        scored.append((score, strategy, asset))
    scored.sort(key=lambda item: (-item[0], item[2].asset_name.casefold(), item[2].relpath.casefold()))
    best_score, strategy, asset = scored[0]
    if best_score <= 0:
        strategy = "fallback_first_asset"
        notes.append(f"{group}: no name match; fell back to first available {kind} asset '{asset.asset_name}'.")
    elif strategy == "beat_text_substring":
        notes.append(f"{group}: matched '{asset.asset_name}' from beat text rather than explicit hints.")
    return SelectedAsset(asset, strategy, best_score, tuple(notes))


def build_legacy_prompt(beat: dict[str, Any]) -> str:
    parts = [
        "Create one cinematic recap keyscene from the supplied scene, character, and prop reference images.",
        "Preserve identity and key object features from the references while composing a natural single frame.",
    ]
    summary = _first_text(beat.get("description"), beat.get("summary"))
    visual = _first_text(beat.get("prompt"), beat.get("visual_prompt"))
    anchor = _first_text(beat.get("anchor_text"))
    mood = _first_text(beat.get("mood"))
    camera = beat.get("camera") if isinstance(beat.get("camera"), dict) else {}
    shot_type = _first_text(camera.get("shot_type"), beat.get("shot_type"))
    camera_motion = _first_text(camera.get("camera_motion"), beat.get("camera_motion"))
    if summary:
        parts.append(f"Beat summary: {summary}")
    if visual:
        parts.append(f"Visual prompt: {visual}")
    if anchor:
        parts.append(f"Anchor text context, do not render as text: {anchor}")
    if shot_type:
        parts.append(f"Shot type: {shot_type}")
    if camera_motion:
        parts.append(f"Camera motion cue: {camera_motion}")
    if mood:
        parts.append(f"Mood: {mood}")
    parts.append("Do not add subtitles, captions, logos, watermarks, contact-sheet panels, or extra reference-layout borders.")
    return "\n".join(parts)


def _prepare_keyscene_prompt(
    *,
    repo_root: Path,
    skill,
    beat: dict[str, Any],
    beat_id: str,
    selected: dict[str, SelectedAsset],
    prompt_cleanup_mode: str,
    prompt_cleanup_model: str,
    debug_prompt_cleanup: bool,
    prompt_cleanup_debug_dir: Path,
) -> PromptCleanupResult:
    legacy_prompt = build_legacy_prompt(beat)
    selected_assets = {
        role: {
            "asset_name": selected_asset.asset.asset_name,
            "kind": selected_asset.asset.kind,
            "group": selected_asset.asset.group,
        }
        for role, selected_asset in selected.items()
        if selected_asset is not None and selected_asset.asset is not None
    }
    compact_input = build_prompt_cleanup_input(
        beat=beat,
        selected_assets=selected_assets,
    )

    if prompt_cleanup_mode == "off":
        result = PromptCleanupResult(
            mode="off",
            source="legacy",
            final_prompt=legacy_prompt,
            structured_input=compact_input,
            validated_payload=None,
            model_alias=prompt_cleanup_model,
            cleanup_status="disabled",
        )
    else:
        result = cleanup_prompt_with_gemini(
            repo_root=repo_root,
            skill=skill,
            compact_input=compact_input,
            legacy_prompt=legacy_prompt,
            model_alias=prompt_cleanup_model,
        )
        if result.warning:
            print(f"[prompt-cleanup] beat={beat_id} {result.warning}")

    if debug_prompt_cleanup:
        artifact_path = prompt_cleanup_debug_dir / f"{_safe_stem(beat_id)}.json"
        artifact_payload = {
            "beat_id": beat_id,
            "mode": result.mode,
            "cleanup_status": result.cleanup_status,
            "source": result.source,
            "model_alias": result.model_alias,
            "model": result.model,
            "route": result.route,
            "warning": result.warning,
            "structured_input": result.structured_input,
            "raw_response_text": result.raw_response_text,
            "raw_response_json": result.raw_response_json,
            "validated_payload": result.validated_payload,
            "final_prompt": result.final_prompt,
            "legacy_prompt": legacy_prompt,
        }
        artifact_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return PromptCleanupResult(
            mode=result.mode,
            source=result.source,
            final_prompt=result.final_prompt,
            structured_input=result.structured_input,
            validated_payload=result.validated_payload,
            raw_response_text=result.raw_response_text,
            raw_response_json=result.raw_response_json,
            warning=result.warning,
            model=result.model,
            route=result.route,
            model_alias=result.model_alias,
            shot_priority=result.shot_priority,
            cleanup_status=result.cleanup_status,
            artifact_path=str(artifact_path),
        )
    return result


def substitute_workflow(
    workflow: dict[str, Any],
    *,
    reference_plan: ReferenceOrderPlan,
    prompt: str,
    filename_prefix: str,
    width: int,
    height: int,
    seed: int,
) -> dict[str, Any]:
    substitutions: dict[str, Any] = {
        "load_image_nodes": {},
        "reference_graph": {},
        "reference_injection": {},
        "prompt_nodes": [],
        "save_image_nodes": [],
        "size_nodes": [],
        "seed_nodes": [],
    }
    role_nodes = _classify_load_image_nodes(_class_nodes(workflow, "LoadImage"))
    graph = _classify_reference_graph(workflow, role_nodes)
    substitutions["reference_graph"] = {
        "character_load_image_node": graph.load_image_nodes.get("character"),
        "scene_load_image_node": graph.load_image_nodes.get("scene"),
        "prop_load_image_node": graph.load_image_nodes.get("prop"),
        "first_stitch_node": graph.first_stitch_node_id,
        "scale_after_first_stitch_node": graph.scale_after_first_stitch_node_id,
        "second_stitch_node": graph.second_stitch_node_id,
        "final_scale_node": graph.final_scale_node_id,
        "vae_encode_node": graph.vae_encode_node_id,
        "reference_latent_node": graph.reference_latent_node_id,
    }
    for candidate in reference_plan.candidates:
        node = role_nodes.get(candidate.role)
        if node is None or not candidate.image_value:
            continue
        node_id, payload = node
        payload.setdefault("inputs", {})["image"] = candidate.image_value
        substitutions["load_image_nodes"][candidate.role] = node_id
    substitutions["reference_injection"] = _inject_reference_order_into_workflow(workflow, graph, reference_plan)
    for node_id, node in _text_encode_nodes(workflow):
        node.setdefault("inputs", {})["text"] = prompt
        substitutions["prompt_nodes"].append(node_id)
        break
    for node_id, node in _class_nodes(workflow, "SaveImage"):
        inputs = node.setdefault("inputs", {})
        if "filename_prefix" in inputs:
            inputs["filename_prefix"] = filename_prefix
            substitutions["save_image_nodes"].append(node_id)
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        touched_size = False
        if "width" in inputs and _is_number_like(inputs.get("width")):
            inputs["width"] = width
            touched_size = True
        if "height" in inputs and _is_number_like(inputs.get("height")):
            inputs["height"] = height
            touched_size = True
        if touched_size:
            substitutions["size_nodes"].append(str(node_id))
        if "seed" in inputs and _is_number_like(inputs.get("seed")):
            inputs["seed"] = seed
            substitutions["seed_nodes"].append(str(node_id))
    return substitutions


def _build_reference_order_plan(
    *,
    beat: dict[str, Any],
    selected: dict[str, SelectedAsset],
    workflow_asset_inputs: dict[str, str],
    requested_mode: str,
    prompt_cleanup: PromptCleanupResult,
) -> ReferenceOrderPlan:
    mode_override, override_source = _reference_order_override(beat, requested_mode)
    cleanup_override = _reference_order_from_prompt_cleanup(prompt_cleanup)
    shot_priority, default_mode, reason = _shot_aware_reference_policy(beat)
    mode = mode_override or cleanup_override or default_mode
    candidates = _build_reference_candidates(selected, workflow_asset_inputs, mode)
    if mode_override:
        reason = f"{override_source} forced {mode_override}."
    elif cleanup_override:
        reason = f"Prompt cleanup shot_priority '{prompt_cleanup.shot_priority}' mapped to {cleanup_override}."
    return ReferenceOrderPlan(
        mode=mode,
        shot_priority=(
            "manual_override"
            if mode_override
            else f"prompt_cleanup:{prompt_cleanup.shot_priority}"
            if cleanup_override
            else shot_priority
        ),
        reason=reason,
        manual_override=bool(mode_override),
        candidates=tuple(candidates),
    )


def _reference_order_override(beat: dict[str, Any], requested_mode: str) -> tuple[str | None, str | None]:
    if requested_mode != "auto":
        return requested_mode, "runtime/env override"
    hints = beat.get("asset_hints") if isinstance(beat.get("asset_hints"), dict) else {}
    for source_name, raw_value in (
        ("beat.reference_order_mode", beat.get("reference_order_mode")),
        ("beat.reference_priority", beat.get("reference_priority")),
        ("beat.asset_hints.reference_order_mode", hints.get("reference_order_mode")),
        ("beat.asset_hints.reference_priority", hints.get("reference_priority")),
    ):
        try:
            normalized = _normalize_reference_order_mode(raw_value)
        except ValueError:
            continue
        if normalized != "auto":
            return normalized, source_name
    return None, None


def _reference_order_from_prompt_cleanup(prompt_cleanup: PromptCleanupResult) -> str | None:
    priority = str(prompt_cleanup.shot_priority or "").strip().casefold()
    mapping = {
        "identity": "identity_first",
        "staging": "staging_first",
        "object": "object_first",
    }
    return mapping.get(priority)


def _shot_aware_reference_policy(beat: dict[str, Any]) -> tuple[str, str, str]:
    shot_type = _normalize_descriptor(_first_text(_camera_shot_type(beat), beat.get("shot_type")))
    asset_focus = _normalize_descriptor(beat.get("asset_focus"))
    beat_text = _normalize_descriptor(_beat_text(beat))

    object_tokens = ("insert", "detail", "close detail", "object", "prop", "product", "cutaway")
    staging_tokens = ("wide", "establishing", "master", "long shot", "full shot", "two shot", "group shot")
    identity_tokens = ("close-up", "close up", "medium close-up", "medium close up", "portrait", "reaction")

    if (
        asset_focus in {"object", "prop"}
        or any(token in shot_type for token in object_tokens)
        or any(token in beat_text for token in ("object-centric", "prop reveal", "engine detail", "道具特写", "物体特写"))
    ):
        object_label = shot_type if any(token in shot_type for token in object_tokens) else asset_focus or "object"
        return "object_centric", "object_first", f"Shot focus '{object_label}' is object-centric."
    if (
        asset_focus == "character"
        or any(token in shot_type for token in identity_tokens)
        or any(token in beat_text for token in ("emotion", "dialogue", "reaction", "close on face", "情绪", "对话"))
    ):
        identity_label = shot_type if any(token in shot_type for token in identity_tokens) else asset_focus or "identity"
        return "identity_critical", "identity_first", f"Shot focus '{identity_label}' is identity-critical."
    if (
        asset_focus in {"environment", "interaction"}
        or any(token in shot_type for token in staging_tokens)
        or any(token in beat_text for token in ("establishing", "staging-heavy", "blocking", "群体调度", "场面调度"))
    ):
        staging_label = shot_type if any(token in shot_type for token in staging_tokens) else asset_focus or "staging"
        return "staging_heavy", "staging_first", f"Shot focus '{staging_label}' is staging-heavy."
    return "default_story_beat", "identity_first", "No explicit shot-type override; defaulting to identity_first with prop last."


def _build_reference_candidates(
    selected: dict[str, SelectedAsset],
    workflow_asset_inputs: dict[str, str],
    mode: str,
) -> list[ReferenceCandidate]:
    role_order = REFERENCE_ORDER_PRIORITY[mode]
    ordered: list[ReferenceCandidate] = []
    for role in role_order:
        selected_asset = selected.get(role)
        asset = selected_asset.asset if selected_asset is not None else None
        image_value = str(workflow_asset_inputs.get(role) or "").strip()
        if asset is None or not image_value:
            continue
        ordered.append(ReferenceCandidate(role=role, asset=asset, image_value=image_value))
    return ordered[:3]


def _classify_reference_graph(
    workflow: dict[str, Any],
    role_nodes: dict[str, tuple[str, dict[str, Any]]],
) -> WorkflowReferenceGraph:
    # Current bundled template chain:
    # character LoadImage (190), scene LoadImage (191), prop LoadImage (194)
    # -> first ImageStitch (146) -> FluxKontextImageScale (42)
    # -> second ImageStitch (192) -> final FluxKontextImageScale (195)
    # -> VAEEncode (124) -> ReferenceLatent (177)
    # This classifier keeps the same downstream node IDs but allows the stitch inputs to be rewired by mode.
    load_image_nodes = {role: node_id for role, (node_id, _node) in role_nodes.items()}
    role_node_ids = set(load_image_nodes.values())
    stitch_nodes = _class_nodes(workflow, "ImageStitch")
    scale_nodes = _class_nodes(workflow, "FluxKontextImageScale")
    first_stitch_node_id: str | None = None
    for node_id, node in stitch_nodes:
        left = _node_link_target(node, "image1")
        right = _node_link_target(node, "image2")
        if left in role_node_ids and right in role_node_ids and first_stitch_node_id is None:
            first_stitch_node_id = node_id
            continue
    scale_after_first_stitch_node_id: str | None = None
    final_scale_node_id: str | None = None
    for node_id, node in scale_nodes:
        image_source = _node_link_target(node, "image")
        if first_stitch_node_id and image_source == first_stitch_node_id and scale_after_first_stitch_node_id is None:
            scale_after_first_stitch_node_id = node_id
    second_stitch_node_id: str | None = None
    for node_id, node in stitch_nodes:
        if node_id == first_stitch_node_id:
            continue
        left = _node_link_target(node, "image1")
        right = _node_link_target(node, "image2")
        if first_stitch_node_id and (left == first_stitch_node_id or right == first_stitch_node_id):
            second_stitch_node_id = node_id
            break
        if scale_after_first_stitch_node_id and (left == scale_after_first_stitch_node_id or right == scale_after_first_stitch_node_id):
            second_stitch_node_id = node_id
            break
    for node_id, node in scale_nodes:
        image_source = _node_link_target(node, "image")
        if second_stitch_node_id and image_source == second_stitch_node_id and final_scale_node_id is None:
            final_scale_node_id = node_id
    if first_stitch_node_id is None and stitch_nodes:
        first_stitch_node_id = stitch_nodes[0][0]
    if second_stitch_node_id is None and len(stitch_nodes) > 1:
        second_stitch_node_id = stitch_nodes[1][0]
    if scale_after_first_stitch_node_id is None and scale_nodes:
        scale_after_first_stitch_node_id = scale_nodes[0][0]
    if final_scale_node_id is None and len(scale_nodes) > 1:
        final_scale_node_id = scale_nodes[-1][0]
    vae_encode_nodes = _class_nodes(workflow, "VAEEncode")
    reference_latent_nodes = _class_nodes(workflow, "ReferenceLatent")
    return WorkflowReferenceGraph(
        load_image_nodes=load_image_nodes,
        first_stitch_node_id=first_stitch_node_id,
        second_stitch_node_id=second_stitch_node_id,
        scale_after_first_stitch_node_id=scale_after_first_stitch_node_id,
        final_scale_node_id=final_scale_node_id,
        vae_encode_node_id=vae_encode_nodes[0][0] if vae_encode_nodes else None,
        reference_latent_node_id=reference_latent_nodes[0][0] if reference_latent_nodes else None,
    )


def _inject_reference_order_into_workflow(
    workflow: dict[str, Any],
    graph: WorkflowReferenceGraph,
    plan: ReferenceOrderPlan,
) -> dict[str, Any]:
    ordered_roles = [candidate.role for candidate in plan.candidates]
    injection_summary: dict[str, Any] = {
        "mode": plan.mode,
        "shot_priority": plan.shot_priority,
        "manual_override": plan.manual_override,
        "ordered_roles": ordered_roles,
        "ordered_reference_node_ids": [graph.load_image_nodes.get(role) for role in ordered_roles],
        "reference_count": len(plan.candidates),
        "stitch_mapping": {},
    }
    if graph.final_scale_node_id is None:
        raise RuntimeError("Could not find the final FluxKontextImageScale node for keyscene reference injection.")
    if not plan.candidates:
        raise RuntimeError("No workflow reference candidates were available for keyscene injection.")

    final_scale_node = workflow.get(graph.final_scale_node_id)
    if not isinstance(final_scale_node, dict):
        raise RuntimeError(f"Final scale node is missing or invalid: {graph.final_scale_node_id}")

    if len(plan.candidates) == 1:
        role = plan.candidates[0].role
        _set_node_link(final_scale_node, "image", graph.load_image_nodes[role])
        injection_summary["stitch_mapping"]["single_reference"] = {
            "role": role,
            "target_node": graph.final_scale_node_id,
            "input_name": "image",
        }
        return injection_summary

    if graph.first_stitch_node_id is None:
        raise RuntimeError("Could not find the first ImageStitch node for keyscene reference injection.")
    first_stitch_node = workflow.get(graph.first_stitch_node_id)
    if not isinstance(first_stitch_node, dict):
        raise RuntimeError(f"First stitch node is missing or invalid: {graph.first_stitch_node_id}")
    _set_node_link(first_stitch_node, "image1", graph.load_image_nodes[plan.candidates[0].role])
    _set_node_link(first_stitch_node, "image2", graph.load_image_nodes[plan.candidates[1].role])
    injection_summary["stitch_mapping"]["stitch1"] = {
        "node_id": graph.first_stitch_node_id,
        "image1_role": plan.candidates[0].role,
        "image1_node_id": graph.load_image_nodes[plan.candidates[0].role],
        "image2_role": plan.candidates[1].role,
        "image2_node_id": graph.load_image_nodes[plan.candidates[1].role],
    }

    if len(plan.candidates) == 2:
        _set_node_link(final_scale_node, "image", graph.first_stitch_node_id)
        injection_summary["stitch_mapping"]["final_scale"] = {
            "node_id": graph.final_scale_node_id,
            "image_source_node_id": graph.first_stitch_node_id,
            "image_source_type": "first_stitch",
        }
        return injection_summary

    if graph.scale_after_first_stitch_node_id is None or graph.second_stitch_node_id is None:
        raise RuntimeError("Could not find the full stitch chain needed for three-reference keyscene injection.")
    scale_after_first_node = workflow.get(graph.scale_after_first_stitch_node_id)
    second_stitch_node = workflow.get(graph.second_stitch_node_id)
    if not isinstance(scale_after_first_node, dict) or not isinstance(second_stitch_node, dict):
        raise RuntimeError("Reference stitch chain nodes are missing or invalid.")
    _set_node_link(scale_after_first_node, "image", graph.first_stitch_node_id)
    _set_node_link(second_stitch_node, "image1", graph.scale_after_first_stitch_node_id)
    _set_node_link(second_stitch_node, "image2", graph.load_image_nodes[plan.candidates[2].role])
    _set_node_link(final_scale_node, "image", graph.second_stitch_node_id)
    injection_summary["stitch_mapping"]["stitch2"] = {
        "node_id": graph.second_stitch_node_id,
        "image1_role": "stitched_pair",
        "image1_node_id": graph.scale_after_first_stitch_node_id,
        "image2_role": plan.candidates[2].role,
        "image2_node_id": graph.load_image_nodes[plan.candidates[2].role],
    }
    injection_summary["stitch_mapping"]["final_scale"] = {
        "node_id": graph.final_scale_node_id,
        "image_source_node_id": graph.second_stitch_node_id,
        "image_source_type": "second_stitch",
    }
    return injection_summary


def _node_link_target(node: dict[str, Any], input_name: str) -> str | None:
    inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
    value = inputs.get(input_name)
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _set_node_link(node: dict[str, Any], input_name: str, source_node_id: str) -> None:
    node.setdefault("inputs", {})[input_name] = [str(source_node_id), 0]


def _reference_plan_manifest(plan: ReferenceOrderPlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "shot_priority": plan.shot_priority,
        "manual_override": plan.manual_override,
        "reason": plan.reason,
        "chosen_references": [
            {
                "role": candidate.role,
                "asset_id": candidate.asset.asset_id,
                "asset_name": candidate.asset.asset_name,
                "path": str(candidate.asset.path),
            }
            for candidate in plan.candidates
        ],
    }


def _prompt_cleanup_manifest(result: PromptCleanupResult, *, output_dir: Path) -> dict[str, Any]:
    payload = {
        "mode": result.mode,
        "cleanup_status": result.cleanup_status,
        "source": result.source,
        "model_alias": result.model_alias,
        "model": result.model,
        "route": result.route,
        "warning": result.warning,
        "shot_priority": result.shot_priority,
    }
    if result.validated_payload is not None:
        payload["validated_payload"] = result.validated_payload
    if result.artifact_path:
        artifact_path = Path(result.artifact_path)
        try:
            payload["artifact_file"] = str(artifact_path.relative_to(output_dir))
        except ValueError:
            payload["artifact_file"] = str(artifact_path)
    return payload


def _log_reference_order_debug(beat_id: str, plan: ReferenceOrderPlan, substitutions: dict[str, Any]) -> None:
    ordered_roles = " -> ".join(candidate.role for candidate in plan.candidates) or "(none)"
    target_nodes = substitutions.get("reference_injection", {}).get("stitch_mapping", {})
    print(
        "[reference-order] "
        f"beat={beat_id} "
        f"shot_priority={plan.shot_priority} "
        f"mode={plan.mode} "
        f"ordered={ordered_roles} "
        f"targets={json.dumps(target_nodes, ensure_ascii=False)}"
    )


def submit_and_collect(*, endpoint: str, workflow: dict[str, Any], output_path: Path) -> dict[str, Any]:
    client_id = str(uuid.uuid4())
    response = _json_request(f"{_normalize_endpoint(endpoint)}/prompt", {"prompt": workflow, "client_id": client_id})
    prompt_id = str(response.get("prompt_id") or "").strip()
    if not prompt_id:
        raise RuntimeError(f"ComfyUI did not return a prompt_id: {response}")
    history = _poll_history(endpoint, prompt_id)
    image_info = _first_history_image(history)
    if image_info is None:
        raise RuntimeError(f"ComfyUI completed prompt {prompt_id} but no SaveImage output was found.")
    _download_comfy_image(endpoint, image_info, output_path)
    return {"prompt_id": prompt_id, "client_id": client_id, "history_image": image_info}


def upload_image(endpoint: str, path: Path) -> str:
    boundary = f"----one4all-{uuid.uuid4().hex}"
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        ('Content-Disposition: form-data; name="image"; filename="' + path.name + f'"\r\nContent-Type: {mime_type}\r\n\r\n').encode("utf-8"),
        path.read_bytes(),
        b"\r\n",
        f"--{boundary}\r\n".encode("utf-8"),
        b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    request = Request(
        f"{_normalize_endpoint(endpoint)}/upload/image",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    name = str(payload.get("name") or "").strip()
    subfolder = str(payload.get("subfolder") or "").strip().strip("/")
    if not name:
        raise RuntimeError(f"ComfyUI upload response did not include a name: {payload}")
    return f"{subfolder}/{name}" if subfolder else name


def _resolve_workflow_image_values(
    *,
    endpoint: str,
    selected: dict[str, SelectedAsset],
    dry_run: bool,
    upload_assets: bool,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for role, selected_asset in selected.items():
        asset = selected_asset.asset
        if asset is None:
            values[role] = ""
        elif dry_run or not upload_assets:
            values[role] = str(asset.path)
        else:
            values[role] = upload_image(endpoint, asset.path)
    return values


def _assert_comfyui_reachable(endpoint: str) -> None:
    try:
        with urlopen(f"{_normalize_endpoint(endpoint)}/system_stats", timeout=10) as response:  # noqa: S310
            response.read(256)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"ComfyUI is not reachable at {_normalize_endpoint(endpoint)}. "
            "Start ComfyUI first or set ONE4ALL_COMFYUI_URL."
        ) from exc


def _json_request(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        detail = f" | {body}" if body else ""
        raise RuntimeError(f"ComfyUI API request failed: {url} | HTTP {exc.code}: {exc.reason}{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"ComfyUI API request failed: {url} | {exc}") from exc


def _poll_history(endpoint: str, prompt_id: str) -> dict[str, Any]:
    deadline = time.time() + DEFAULT_TIMEOUT_SECONDS
    history_url = f"{_normalize_endpoint(endpoint)}/history/{prompt_id}"
    while time.time() < deadline:
        with urlopen(history_url, timeout=60) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if prompt_id in payload:
            return payload[prompt_id]
        time.sleep(DEFAULT_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}.")


def _first_history_image(history: dict[str, Any]) -> dict[str, str] | None:
    outputs = history.get("outputs")
    if not isinstance(outputs, dict):
        return None
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        images = output.get("images")
        if not isinstance(images, list) or not images:
            continue
        first = images[0]
        if isinstance(first, dict) and first.get("filename"):
            return {
                "filename": str(first.get("filename") or ""),
                "subfolder": str(first.get("subfolder") or ""),
                "type": str(first.get("type") or "output"),
            }
    return None


def _download_comfy_image(endpoint: str, image_info: dict[str, str], output_path: Path) -> None:
    query = urlencode(
        {
            "filename": image_info.get("filename", ""),
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
    )
    with urlopen(f"{_normalize_endpoint(endpoint)}/view?{query}", timeout=120) as response:  # noqa: S310
        image_bytes = response.read()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)


def _extract_beats(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    flat = storyboard.get("storyboard_shots")
    if isinstance(flat, list) and flat:
        return [item for item in flat if isinstance(item, dict)]
    beats: list[dict[str, Any]] = []
    for episode in storyboard.get("episodes", []) if isinstance(storyboard.get("episodes"), list) else []:
        if not isinstance(episode, dict):
            continue
        for shot in episode.get("shots", []) if isinstance(episode.get("shots"), list) else []:
            if isinstance(shot, dict):
                merged = dict(shot)
                merged.setdefault("episode_number", episode.get("episode_number"))
                beats.append(merged)
    return beats


def _hint_values(group: str, beat: dict[str, Any]) -> list[str]:
    hints_payload = beat.get("asset_hints")
    if not isinstance(hints_payload, dict):
        return []
    values = hints_payload.get(group)
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _score_asset(asset: AssetFile, hints: list[str], beat_text: str) -> tuple[int, str]:
    asset_values = [asset.asset_name, asset.asset_id, asset.path.stem]
    normalized_asset_values = [_normalize_match_text(value) for value in asset_values if value]
    normalized_hints = [_normalize_match_text(value) for value in hints if value]
    normalized_beat = _normalize_match_text(beat_text)
    for hint in normalized_hints:
        if hint and hint in normalized_asset_values:
            return 100, "hint_exact"
    for hint in normalized_hints:
        for asset_value in normalized_asset_values:
            if hint and asset_value and (hint in asset_value or asset_value in hint):
                return 85, "hint_substring"
    for asset_value in normalized_asset_values:
        if asset_value and asset_value in normalized_beat:
            return 60, "beat_text_substring"
    for hint in normalized_hints:
        hint_tokens = _match_tokens(hint)
        for asset_value in normalized_asset_values:
            if hint_tokens and hint_tokens.intersection(_match_tokens(asset_value)):
                return 35, "hint_token_overlap"
    return 0, "no_match"


def _class_nodes(workflow: dict[str, Any], class_type: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (str(node_id), node)
        for node_id, node in sorted(workflow.items(), key=lambda item: _node_sort_key(item[0]))
        if isinstance(node, dict) and str(node.get("class_type") or "") == class_type
    ]


def _text_encode_nodes(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    nodes: list[tuple[str, dict[str, Any]]] = []
    for node_id, node in sorted(workflow.items(), key=lambda item: _node_sort_key(item[0])):
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type") or "")
        inputs = node.get("inputs")
        if "TextEncode" not in class_type or not isinstance(inputs, dict) or "text" not in inputs:
            continue
        label = _node_label(str(node_id), node)
        if "negative" in label or "反向" in label:
            continue
        nodes.append((str(node_id), node))
    return nodes


def _classify_load_image_nodes(image_nodes: list[tuple[str, dict[str, Any]]]) -> dict[str, tuple[str, dict[str, Any]]]:
    classified: dict[str, tuple[str, dict[str, Any]]] = {}
    role_terms = {
        "character": ("character", "char", "person", "角色", "人物"),
        "scene": ("scene", "environment", "background", "场景", "环境"),
        "prop": ("prop", "object", "item", "道具", "物体"),
    }
    for node_id, node in image_nodes:
        label = _node_label(node_id, node)
        for role, terms in role_terms.items():
            if role not in classified and any(term in label for term in terms):
                classified[role] = (node_id, node)
    used_ids = {node_id for node_id, _node in classified.values()}
    fallback_roles = [role for role in ("character", "scene", "prop") if role not in classified]
    fallback_nodes = [(node_id, node) for node_id, node in image_nodes if node_id not in used_ids]
    for role, node in zip(fallback_roles, fallback_nodes):
        classified[role] = node
    return classified


def _node_label(node_id: str, node: dict[str, Any]) -> str:
    inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
    meta = node.get("_meta") if isinstance(node.get("_meta"), dict) else {}
    parts = [node_id, str(meta.get("title") or ""), str(inputs.get("image") or "")]
    return " ".join(parts).casefold()


def _node_sort_key(value: Any) -> tuple[int, str]:
    text = str(value)
    return (int(text), text) if text.isdigit() else (999999, text)


def _selected_asset_manifest(selected: SelectedAsset, assets_dir: Path) -> dict[str, Any] | None:
    asset = selected.asset
    if asset is None:
        return None
    return {
        "asset_id": asset.asset_id,
        "asset_name": asset.asset_name,
        "group": asset.group,
        "kind": asset.kind,
        "path": str(asset.path),
        "relative_path": str(asset.path.relative_to(assets_dir)),
        "match_strategy": selected.strategy,
        "match_score": selected.score,
    }


def _build_error_manifest_item(
    *,
    beat: dict[str, Any],
    beat_id: str,
    prompt: str,
    seed: int,
    width: int,
    height: int,
    selected: dict[str, SelectedAsset],
    assets_dir: Path,
    output_dir: Path,
    payload_file: Path,
    output_file: Path,
    notes: list[str] | tuple[str, ...],
    prompt_cleanup: PromptCleanupResult | None = None,
    exc: Exception,
) -> dict[str, Any]:
    error_detail = "".join(traceback.format_exception_only(type(exc), exc)).strip() or str(exc)
    item: dict[str, Any] = {
        "beat_id": beat_id,
        "episode_number": beat.get("episode_number"),
        "prompt": prompt,
        "seed": seed,
        "width": width,
        "height": height,
        "chosen_scene_asset": _selected_asset_manifest(selected["scene"], assets_dir),
        "chosen_character_asset": _selected_asset_manifest(selected["character"], assets_dir),
        "chosen_prop_asset": _selected_asset_manifest(selected["prop"], assets_dir),
        "payload_file": str(payload_file.relative_to(output_dir)),
        "output_file": str(output_file.relative_to(output_dir)),
        "fallback_notes": _dedupe_preserve_order(list(notes)),
        "status": "error",
        "error": error_detail,
        "error_stage": "validation" if isinstance(exc, KeysceneValidationError) else "execution",
    }
    if prompt_cleanup is not None:
        item["prompt_cleanup"] = _prompt_cleanup_manifest(prompt_cleanup, output_dir=output_dir)
    if isinstance(exc, KeysceneValidationError) and exc.missing_paths:
        item["missing_paths"] = list(exc.missing_paths)
    return item


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected top-level JSON object: {path}")
    return payload


def _beat_id(beat: dict[str, Any], index: int) -> str:
    return str(beat.get("shot_id") or beat.get("scene_id") or beat.get("source_scene_id") or f"beat_{index:03d}").strip()


def _beat_text(beat: dict[str, Any]) -> str:
    parts = [
        beat.get("asset_focus"),
        beat.get("description"),
        beat.get("summary"),
        beat.get("prompt"),
        beat.get("visual_prompt"),
        beat.get("anchor_text"),
        beat.get("beat_role"),
        beat.get("priority"),
    ]
    hints = beat.get("asset_hints")
    if isinstance(hints, dict):
        parts.append(json.dumps(hints, ensure_ascii=False))
    return "\n".join(str(part) for part in parts if part not in (None, ""))


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _stable_seed(beat_id: str, prompt: str) -> int:
    digest = hashlib.sha256(f"{beat_id}\n{prompt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", str(value).strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:96] or "keyscene"


def _name_from_stem(stem: str, kind: str) -> str:
    return re.sub(rf"^{re.escape(kind)}[_-]", "", stem).strip() or stem


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value).casefold())


def _match_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", value.casefold()) if token}


def _runtime_value(runtime_values: dict[str, Any], key: str) -> Any:
    value = runtime_values.get(key)
    return value if value not in (None, "") else None


def _normalize_reference_order_mode(value: Any) -> str:
    text = str(value or "auto").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "auto": "auto",
        "identity_first": "identity_first",
        "character_first": "identity_first",
        "staging_first": "staging_first",
        "scene_first": "staging_first",
        "object_first": "object_first",
        "prop_first": "object_first",
    }
    normalized = aliases.get(text)
    if normalized is None:
        raise ValueError(
            "Unsupported reference order mode. Choose one of: auto, identity_first, staging_first, object_first."
        )
    return normalized


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "on"}


def _falsy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"0", "false", "no", "n", "off"}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _is_number_like(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _normalize_endpoint(endpoint: str) -> str:
    return str(endpoint or DEFAULT_COMFYUI_URL).strip().rstrip("/")


def _camera_shot_type(beat: dict[str, Any]) -> Any:
    camera = beat.get("camera")
    if isinstance(camera, dict):
        return camera.get("shot_type")
    return None


def _normalize_descriptor(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate stage-06 recap keyscenes from a story run through ComfyUI Flux Kontext.")
    parser.add_argument(
        "input",
        nargs="?",
        help="Preferred: story run folder. Convenience fallbacks: 04_recap_to_comfy_bridge/, 05_assets_t2i/, an asset-group subfolder, or a file inside either stage.",
    )
    parser.add_argument("--bridge-dir", help="Advanced override: explicit 04_recap_to_comfy_bridge folder.")
    parser.add_argument("--assets-dir", help="Advanced override: explicit 05_assets_t2i folder.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to <run_root>/06_keyscene_i2i.")
    parser.add_argument("--template", default=str(Path(__file__).resolve().parents[1] / "assets" / "i2iscenes.json"))
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("ONE4ALL_COMFYUI_URL") or DEFAULT_COMFYUI_URL,
        help="Advanced override for the ComfyUI API endpoint. Defaults to ONE4ALL_COMFYUI_URL or http://127.0.0.1:8188.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Advanced mode: write payloads and manifest without submitting to ComfyUI.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N beats.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--prompt-cleanup-mode",
        choices=("off", "gemini"),
        default=os.environ.get("ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODE") or "gemini",
        help="Optional prompt-normalization stage before image generation. Default: gemini.",
    )
    parser.add_argument(
        "--prompt-cleanup-model",
        default=os.environ.get("ONE4ALL_KONTEXT_PROMPT_CLEANUP_MODEL") or PROMPT_CLEANUP_MODEL_ALIAS,
        help="Model alias for prompt cleanup. Defaults to the config alias 'gemini'.",
    )
    parser.add_argument(
        "--debug-prompt-cleanup",
        action="store_true",
        help="Write prompt-cleanup debug artifacts and warnings without stopping the run.",
    )
    parser.add_argument(
        "--reference-order-mode",
        choices=REFERENCE_ORDER_MODES,
        default=os.environ.get("ONE4ALL_KONTEXT_REFERENCE_ORDER_MODE") or "auto",
        help="Reference order policy. auto uses shot-aware routing; manual modes are identity_first, staging_first, object_first.",
    )
    parser.add_argument(
        "--debug-reference-order",
        action="store_true",
        help="Print per-beat reference-order selection and stitch target mapping.",
    )
    parser.add_argument("--no-upload", action="store_true", help="Do not upload images to ComfyUI before prompt submission.")
    args = parser.parse_args(argv)

    if args.bridge_dir and args.assets_dir:
        bridge_dir = Path(args.bridge_dir).expanduser().resolve()
        assets_dir = Path(args.assets_dir).expanduser().resolve()
        stage_paths = _validated_stage_paths(bridge_dir.parent, bridge_dir, assets_dir, bridge_dir / "videoarc_storyboard.json")
        input_path = stage_paths.storyboard_path
    elif args.input:
        input_path = Path(args.input).expanduser().resolve()
    else:
        parser.error("Provide an input path or both --bridge-dir and --assets-dir.")

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    result = run_keyscene_stage(
        input_path=input_path,
        output_dir=output_dir,
        skill_dir=Path(__file__).resolve().parents[1],
        repo_root=REPO_ROOT,
        skill=None,
        template_path=Path(args.template).expanduser().resolve(),
        endpoint=args.endpoint,
        dry_run=bool(args.dry_run),
        width=args.width,
        height=args.height,
        seed_override=args.seed,
        limit=args.limit,
        upload_assets=not args.no_upload,
        prompt_cleanup_mode=normalize_prompt_cleanup_mode(args.prompt_cleanup_mode),
        prompt_cleanup_model=normalize_model_alias(args.prompt_cleanup_model),
        debug_prompt_cleanup=bool(args.debug_prompt_cleanup or _truthy(os.environ.get("ONE4ALL_KONTEXT_DEBUG_PROMPT_CLEANUP"))),
        reference_order_mode=_normalize_reference_order_mode(args.reference_order_mode),
        debug_reference_order=bool(args.debug_reference_order or _truthy(os.environ.get("ONE4ALL_KONTEXT_DEBUG_REFERENCE_ORDER"))),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
