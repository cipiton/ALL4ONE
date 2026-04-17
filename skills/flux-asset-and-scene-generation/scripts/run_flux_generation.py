from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def discover_repo_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / "config.ini").exists():
            return candidate
    return start_dir.parents[3]


REPO_ROOT = discover_repo_root(SCRIPT_DIR)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from build_flux_prompts import (
    DEFAULT_FINAL_PROMPT_LANGUAGE,
    SHOT_MODE_IDENTITY,
    SHOT_MODE_INSERT,
    SHOT_MODE_STAGING,
    SHOT_MODE_VEHICLE,
    VEHICLE_PRESET_DETAIL,
    VEHICLE_PRESET_RIDING,
    VEHICLE_PRESET_STANDING,
    VEHICLE_PRESET_TRACK,
    VEHICLE_PRESET_WORKSHOP,
    build_asset_prompt,
    build_keyscene_prompt,
    classify_keyscene_shot_mode,
    classify_vehicle_shot_preset,
    is_vehicle_shot,
    normalize_final_prompt_language,
)
from engine.config_loader import get_config_value, load_repo_config
from flux_generate import BatchGenerationJob, DEFAULT_MODEL_IDS, DEFAULT_SIZES, FluxImageGenerator, build_generation_config
from llm_prompt_author import author_asset_prompt, author_keyscene_prompt
from load_recap_production import ASSET_GROUPS, GeneratedAsset, RecapAsset, RecapBeat, load_recap_bundle, safe_slug
from workflow_planner import FluxWorkflowPlan, plan_generation_workflow


@dataclass(frozen=True, slots=True)
class AssetMatch:
    asset: GeneratedAsset | None
    strategy: str
    note: str
    score: int
    matched_terms: tuple[str, ...]
    candidate_scores: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class KeysceneSelectionPlan:
    beat: RecapBeat
    shot_mode: str
    prompt_template: str
    vehicle_preset: str | None
    scene: AssetMatch
    character: AssetMatch
    prop: AssetMatch
    selected_assets: dict[str, GeneratedAsset | None]
    reference_paths: tuple[Path, ...]
    reference_policy: str
    validation_warnings: tuple[str, ...]
    dropped_prop_reason: str | None


@dataclass(frozen=True, slots=True)
class ResumeSource:
    root_dir: Path
    keyscene_dir: Path
    manifest_path: Path | None


@dataclass(frozen=True, slots=True)
class FluxResolutionConfig:
    sizes: dict[str, tuple[int | None, int | None]]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FluxAssetPromptConfig:
    character_plain_white_background: bool = False
    prop_plain_white_background: bool = False
    warnings: tuple[str, ...] = ()


class AssetQueueProgress:
    def __init__(self, queued_assets: list[tuple[str, RecapAsset, Path]]) -> None:
        self.queued_assets = queued_assets
        self.total = len(queued_assets)
        inline_setting = os.environ.get("ONE4ALL_INLINE_PROGRESS", "").strip().lower()
        disabled = inline_setting in {"0", "false", "no", "off"}
        forced = inline_setting in {"1", "true", "yes", "on", "force"}
        self.dynamic = bool(
            self.total
            and not disabled
            and (forced or sys.stdout.isatty())
            and os.environ.get("TERM", "").lower() != "dumb"
        )
        self.started = False

    def render_initial(self) -> None:
        if not self.total:
            return
        self.started = True
        safe_print("[flux-skill] asset queue:")
        for index, (group_name, asset, output_path) in enumerate(self.queued_assets, start=1):
            safe_print(self._queue_line("[ ]", index, group_name, asset, output_path))
        if self.dynamic:
            self._write_line("[flux-skill] current: waiting")

    def set_current(self, index: int, group_name: str, asset: RecapAsset, output_path: Path) -> None:
        pass

    def mark_done(self, index: int, group_name: str, asset: RecapAsset, output_path: Path) -> None:
        if self.dynamic:
            self._replace_queue_line(index, self._queue_line("[x]", index, group_name, asset, output_path))
            self._replace_current_line(
                f"[flux-skill] completed {index}/{self.total}: {self._asset_kind(group_name)} -> {output_path.name}"
            )
            return
        safe_print(f"[flux-skill] [x] completed {index}/{self.total}: {self._asset_kind(group_name)} -> {output_path.name}")

    def mark_failed(self, index: int, group_name: str, asset: RecapAsset, output_path: Path) -> None:
        if self.dynamic:
            self._replace_queue_line(index, self._queue_line("[!]", index, group_name, asset, output_path))
            self._replace_current_line(
                f"[flux-skill] failed {index}/{self.total}: {self._asset_kind(group_name)} -> {output_path.name}"
            )
            return
        safe_print(f"[flux-skill] [!] failed {index}/{self.total}: {self._asset_kind(group_name)} -> {output_path.name}")

    def finish(self) -> None:
        if self.dynamic and self.started:
            self._replace_current_line(f"[flux-skill] current: complete {self.total}/{self.total}")

    def should_log_generator_output(self) -> bool:
        return not self.dynamic

    def _queue_line(self, marker: str, index: int, group_name: str, asset: RecapAsset, output_path: Path) -> str:
        return f"[flux-skill] {marker} {index}/{self.total} {self._asset_kind(group_name)} -> {output_path.name} ({asset.name})"

    @staticmethod
    def _asset_kind(group_name: str) -> str:
        return group_name[:-1] if group_name.endswith("s") else group_name

    def _replace_queue_line(self, index: int, text: str) -> None:
        if not self.dynamic:
            return
        up = self.total - index + 2
        down = self.total - index + 2
        self._write(f"\033[{up}A\r\033[2K{text}\033[{down}B\r")

    def _replace_current_line(self, text: str) -> None:
        if not self.dynamic:
            return
        self._write(f"\033[1A\r\033[2K{text}\n")

    def _write_line(self, text: str) -> None:
        self._write(f"{text}\n")

    @staticmethod
    def _write(text: str) -> None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except UnicodeEncodeError:
            sys.stdout.write(text.encode("ascii", "backslashreplace").decode("ascii"))
            sys.stdout.flush()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read a recap production folder and generate FLUX.2 klein assets or keyscenes locally."
    )
    parser.add_argument("--mode", choices=("asset", "keyscene", "asset_then_keyscene"), help="Generation mode.")
    parser.add_argument("--recap-folder", help="Path to the recap production folder or story run folder.")
    parser.add_argument(
        "--assets-folder",
        help="Optional explicit generated assets folder. If omitted, the planner searches sibling generated-assets folders and may switch to assets -> keyscenes when reuse is impossible.",
    )
    parser.add_argument("--episode-script", help="For keyscene mode: path to the episode scene script JSON file.")
    parser.add_argument(
        "--goal",
        help="Optional freeform goal for this run, such as 'assets only', 'continue through keyscenes', or 'reuse existing assets when possible'.",
    )
    parser.add_argument(
        "--asset-types",
        help="For asset mode: comma-separated subset of characters,props,scenes. Default: all.",
    )
    parser.add_argument(
        "--style-target",
        choices=("realism", "3d-anime", "2d-anime-cartoon"),
        help="Optional explicit style target override.",
    )
    parser.add_argument("--model", help="Optional explicit FLUX.2 klein model override.")
    parser.add_argument(
        "--backend",
        choices=("klein_cli", "diffusers", "mock"),
        default=os.environ.get("ONE4ALL_FLUX_BACKEND") or "klein_cli",
    )
    parser.add_argument("--steps", type=int, help="Inference steps override.")
    parser.add_argument("--guidance", type=float, help="Guidance scale override.")
    parser.add_argument("--width", type=int, help="Width override.")
    parser.add_argument("--height", type=int, help="Height override.")
    parser.add_argument("--seed", type=int, help="Global seed override.")
    parser.add_argument("--limit", type=int, help="Only process the first N assets or beats.")
    parser.add_argument("--output-root", help="Optional parent output directory. Defaults inside the recap folder.")
    parser.add_argument(
        "--resume-from",
        help="Optional previous keyscene output root, session folder, or keyscenes folder to reuse completed images from.",
    )
    parser.add_argument(
        "--no-resume-keyscenes",
        action="store_false",
        dest="resume_keyscenes",
        help="Disable automatic keyscene resume/reuse of completed PNG outputs.",
    )
    parser.add_argument(
        "--scene-validation",
        choices=("off", "warn", "fail"),
        default=os.environ.get("ONE4ALL_FLUX_SCENE_VALIDATION") or "warn",
        help="How to handle semantic scene mismatches during keyscene generation.",
    )
    parser.add_argument(
        "--debug-keyscene-output",
        action="store_true",
        help="Write per-beat debug JSON with prompt compression, selected references, and validation notes.",
    )
    parser.add_argument("--non-interactive", action="store_true", help="Fail instead of prompting for missing mode or folder.")
    parser.set_defaults(resume_keyscenes=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = parse_args(argv)
    manifest_path = execute_generation(args)
    safe_print(f"[flux-skill] completed: {manifest_path}")
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
    output_dir = output_dir.resolve()
    mode = normalize_mode(runtime_values.get("mode"))
    default_recap_folder = normalize_recap_folder_input(runtime_values.get("recap_folder") or str(document.path))
    args = argparse.Namespace(
        mode=mode,
        recap_folder=default_recap_folder,
        assets_folder=runtime_values.get("assets_folder"),
        episode_script=runtime_values.get("episode_script"),
        goal=runtime_values.get("goal"),
        asset_types=runtime_values.get("asset_types"),
        style_target=runtime_values.get("style_target"),
        model=runtime_values.get("model"),
        backend=runtime_values.get("backend") or (os.environ.get("ONE4ALL_FLUX_BACKEND") or "klein_cli"),
        steps=optional_int(runtime_values.get("steps")),
        guidance=optional_float(runtime_values.get("guidance")),
        width=optional_int(runtime_values.get("width")),
        height=optional_int(runtime_values.get("height")),
        seed=optional_int(runtime_values.get("seed")),
        limit=optional_int(runtime_values.get("limit")),
        resume_from=runtime_values.get("resume_from"),
        resume_keyscenes=not truthy(runtime_values.get("no_resume_keyscenes")),
        scene_validation=runtime_values.get("scene_validation") or (os.environ.get("ONE4ALL_FLUX_SCENE_VALIDATION") or "warn"),
        debug_keyscene_output=truthy(runtime_values.get("debug_keyscene_output")),
        output_root=str(
            output_dir
            / (
                "generated_assets"
                if mode == "asset"
                else ("generated_keyscenes" if mode == "keyscene" else "generated_assets")
            )
        ),
        non_interactive=False,
    )
    if mode == "keyscene" and args.resume_keyscenes and not args.resume_from:
        auto_resume_root = detect_previous_keyscene_output_root(Path(args.output_root))
        if auto_resume_root is not None:
            args.resume_from = str(auto_resume_root)
    manifest_path = execute_generation(args, utility_session_root=output_dir, skill_definition=skill, repo_root=repo_root)
    plan_summary = load_plan_summary(manifest_path)
    return {
        "primary_output": manifest_path,
        "output_files": {
            "primary": manifest_path,
            "manifest": manifest_path,
        },
        "notes": [
            f"Requested mode: {mode or 'auto/prompted'}",
            f"Resolved mode: {plan_summary.get('resolved_mode', 'unknown')}",
            f"Recap source: {document.path}",
            f"Manifest: {manifest_path}",
        ],
        "status": "completed",
    }


def resolve_final_prompt_language_from_config(repo_root: Path) -> tuple[str, str | None]:
    parser = load_repo_config(repo_root)
    configured = get_config_value(parser, "generation", "final_prompt_language", DEFAULT_FINAL_PROMPT_LANGUAGE)
    return normalize_final_prompt_language(configured)


def resolve_flux_resolution_config(repo_root: Path) -> FluxResolutionConfig:
    parser = load_repo_config(repo_root)
    sizes: dict[str, tuple[int | None, int | None]] = {}
    warnings: list[str] = []
    keys = ("asset", "keyscene", "character", "prop", "scene", "environment", "vehicle", "wardrobe", "state_variant")
    for key in keys:
        width = read_positive_config_int(
            parser,
            "flux_generation",
            f"{key}_width",
            warnings=warnings,
        )
        height = read_positive_config_int(
            parser,
            "flux_generation",
            f"{key}_height",
            warnings=warnings,
        )
        if width is not None or height is not None:
            sizes[key] = (width, height)
    return FluxResolutionConfig(sizes=sizes, warnings=tuple(warnings))


def resolve_flux_asset_prompt_config(repo_root: Path) -> FluxAssetPromptConfig:
    parser = load_repo_config(repo_root)
    warnings: list[str] = []
    character_plain_white_background = read_bool_config(
        parser,
        "flux_generation",
        "character_plain_white_background",
        default=False,
        warnings=warnings,
    )
    prop_plain_white_background = read_bool_config(
        parser,
        "flux_generation",
        "prop_plain_white_background",
        default=False,
        warnings=warnings,
    )
    return FluxAssetPromptConfig(
        character_plain_white_background=character_plain_white_background,
        prop_plain_white_background=prop_plain_white_background,
        warnings=tuple(warnings),
    )


def read_positive_config_int(parser, section: str, option: str, *, warnings: list[str]) -> int | None:
    raw_value = get_config_value(parser, section, option, "")
    if not raw_value:
        return None
    try:
        value = int(raw_value)
    except ValueError:
        warnings.append(f"Ignoring invalid config value [{section}] {option}={raw_value!r}; expected a positive integer.")
        return None
    if value <= 0:
        warnings.append(f"Ignoring invalid config value [{section}] {option}={raw_value!r}; expected a positive integer.")
        return None
    return value


def read_bool_config(parser, section: str, option: str, *, default: bool, warnings: list[str]) -> bool:
    raw_value = get_config_value(parser, section, option, "")
    if not raw_value:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    warnings.append(f"Ignoring invalid config value [{section}] {option}={raw_value!r}; expected true/false.")
    return default


def resolve_generation_dimensions(
    *,
    args: argparse.Namespace,
    resolution_config: FluxResolutionConfig,
    mode: str,
    asset_type: str | None = None,
) -> tuple[int | None, int | None]:
    if args.width is not None or args.height is not None:
        return args.width, args.height

    if mode == "keyscene":
        return resolution_config.sizes.get("keyscene", (None, None))

    asset_width, asset_height = resolution_config.sizes.get("asset", (None, None))
    type_width, type_height = resolution_config.sizes.get(asset_type or "scene", (None, None))
    return type_width or asset_width, type_height or asset_height


def apply_asset_prompt_config(
    prompt_result,
    *,
    group_name: str,
    final_prompt_language: str,
    asset_prompt_config: FluxAssetPromptConfig,
):
    if group_name == "characters":
        enabled = asset_prompt_config.character_plain_white_background
    elif group_name == "props":
        enabled = asset_prompt_config.prop_plain_white_background
    else:
        enabled = False
    if not enabled:
        return prompt_result

    prompt = append_plain_white_background_clause(prompt_result.prompt, final_prompt_language=final_prompt_language)
    if prompt == prompt_result.prompt:
        return prompt_result

    metadata = dict(prompt_result.metadata)
    metadata["plain_white_background_enforced"] = True
    notes = (*prompt_result.notes, "Applied configured plain white background requirement for reusable asset generation.")
    return replace(prompt_result, prompt=prompt, notes=notes, metadata=metadata)


def append_plain_white_background_clause(prompt: str, *, final_prompt_language: str) -> str:
    lowered = prompt.casefold()
    if final_prompt_language == "zh":
        if "纯白背景" in prompt or "纯白色背景" in prompt:
            return prompt
        clause = "主体必须孤立呈现在纯白背景上，不要出现房间、地面纹理、环境细节、文字或额外场景信息。"
    else:
        if "plain white background" in lowered or "pure white background" in lowered:
            return prompt
        clause = (
            "The subject must be isolated on a plain pure white background, with no room, floor texture, "
            "environmental detail, text, or extra scene context."
        )
    return f"{prompt.rstrip()} {clause}".strip()


def execute_generation(
    args: argparse.Namespace,
    *,
    utility_session_root: Path | None = None,
    skill_definition=None,
    repo_root: Path = REPO_ROOT,
) -> Path:
    final_prompt_language, language_warning = resolve_final_prompt_language_from_config(REPO_ROOT)
    if language_warning:
        safe_print(f"[flux-skill] warning: {language_warning}")
    safe_print(f"[flux-skill] final prompt language: {final_prompt_language}")
    resolution_config = resolve_flux_resolution_config(repo_root)
    for warning in resolution_config.warnings:
        safe_print(f"[flux-skill] warning: {warning}")
    asset_prompt_config = resolve_flux_asset_prompt_config(repo_root)
    for warning in asset_prompt_config.warnings:
        safe_print(f"[flux-skill] warning: {warning}")
    requested_mode = args.mode or prompt_mode(non_interactive=args.non_interactive)
    recap_folder = resolve_recap_folder_for_request(args, requested_mode=requested_mode)
    bundle = load_recap_bundle(recap_folder)
    explicit_asset_types = parse_asset_types(args.asset_types) if args.asset_types else []
    if requested_mode in {"asset", "asset_then_keyscene"} and not explicit_asset_types and not args.non_interactive:
        requested_mode, explicit_asset_types = prompt_output_targets(requested_mode)

    style_target = args.style_target or (
        prompt_style_target(default_value=bundle.style_target)
        if not args.non_interactive
        else bundle.style_target
    )
    explicit_assets_folder = args.assets_folder or derive_default_assets_folder(recap_folder)
    workflow_plan = plan_generation_workflow(
        bundle=bundle,
        requested_mode=requested_mode,
        explicit_assets_folder=explicit_assets_folder,
        asset_types=explicit_asset_types,
        style_target=style_target,
    )
    print_workflow_plan(workflow_plan)
    if workflow_plan.stop_reason:
        raise ValueError(workflow_plan.stop_reason)

    resolved_mode = workflow_plan.resolved_mode or requested_mode
    asset_types = list(workflow_plan.asset_types)
    default_session_root = (
        utility_session_root
        or (Path(args.output_root).expanduser().resolve() if args.output_root else build_default_session_root(bundle.recap_dir))
    )
    asset_output_override = default_session_root / "generated_assets"
    keyscene_output_override = default_session_root / "generated_keyscenes"
    generator = FluxImageGenerator(args.backend)

    if resolved_mode == "asset":
        return run_asset_generation(
            bundle=bundle,
            generator=generator,
            asset_types=asset_types or list(ASSET_GROUPS),
            style_target=workflow_plan.style_target,
            final_prompt_language=final_prompt_language,
            args=args,
            workflow_plan=workflow_plan,
            resolution_config=resolution_config,
            asset_prompt_config=asset_prompt_config,
            output_dir_override=asset_output_override,
            skill_definition=skill_definition,
            repo_root=repo_root,
        )[0]
    if resolved_mode == "keyscene":
        return run_keyscene_generation(
            bundle=bundle,
            generator=generator,
            style_target=workflow_plan.style_target,
            final_prompt_language=final_prompt_language,
            args=args,
            preferred_generated_assets_dir=Path(explicit_assets_folder).expanduser().resolve() if explicit_assets_folder else None,
            workflow_plan=workflow_plan,
            resolution_config=resolution_config,
            output_dir_override=keyscene_output_override,
            skill_definition=skill_definition,
            repo_root=repo_root,
        )

    asset_manifest_path, asset_output_dir = run_asset_generation(
        bundle=bundle,
        generator=generator,
        asset_types=asset_types or list(ASSET_GROUPS),
        style_target=workflow_plan.style_target,
        final_prompt_language=final_prompt_language,
            args=args,
            workflow_plan=workflow_plan,
            resolution_config=resolution_config,
            asset_prompt_config=asset_prompt_config,
            output_dir_override=asset_output_override,
            skill_definition=skill_definition,
            repo_root=repo_root,
    )
    keyscene_output_root = keyscene_output_override
    keyscene_args = argparse.Namespace(**vars(args))
    keyscene_args.output_root = str(keyscene_output_root)
    keyscene_manifest_path = run_keyscene_generation(
        bundle=bundle,
        generator=generator,
        style_target=workflow_plan.style_target,
        final_prompt_language=final_prompt_language,
        args=keyscene_args,
        preferred_generated_assets_dir=asset_output_dir,
        workflow_plan=workflow_plan,
        resolution_config=resolution_config,
        output_dir_override=keyscene_output_override,
        skill_definition=skill_definition,
        repo_root=repo_root,
    )
    combined_manifest_path = keyscene_output_root / "combined_manifest.json"
    combined_manifest = {
        "schema": "flux_asset_then_keyscene_manifest_v1",
        "timestamp": timestamp_now(),
        "input_folder": str(bundle.recap_dir),
        "mode": "asset_then_keyscene",
        "style_target": workflow_plan.style_target,
        "final_prompt_language": final_prompt_language,
        "input_contract": bundle.input_contract,
        "selection_notes": list(bundle.selection_notes),
        "workflow_plan": workflow_plan.as_manifest_dict(),
        "asset_manifest": str(asset_manifest_path),
        "keyscene_manifest": str(keyscene_manifest_path),
        "asset_output_root": str(asset_output_dir),
        "keyscene_output_root": str(keyscene_output_root),
    }
    combined_manifest_path.write_text(json.dumps(combined_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_print(f"[flux-skill] combined run manifest: {combined_manifest_path}")
    return combined_manifest_path


def run_asset_generation(
    *,
    bundle,
    generator: FluxImageGenerator,
    asset_types: list[str],
    style_target: str,
    final_prompt_language: str,
    args: argparse.Namespace,
    workflow_plan: FluxWorkflowPlan,
    resolution_config: FluxResolutionConfig,
    asset_prompt_config: FluxAssetPromptConfig,
    output_dir_override: Path | None = None,
    skill_definition=None,
    repo_root: Path = REPO_ROOT,
) -> tuple[Path, Path]:
    output_dir = output_dir_override or resolve_output_dir(args.output_root, bundle.recap_dir, "generated_assets")
    output_dir.mkdir(parents=True, exist_ok=True)
    for group_name in ASSET_GROUPS:
        (output_dir / group_name).mkdir(parents=True, exist_ok=True)

    selected_groups = [group for group in ASSET_GROUPS if group in asset_types]
    queued_assets: list[tuple[str, RecapAsset, Path]] = []
    for group_name in selected_groups:
        assets = list(bundle.assets_by_group.get(group_name, []))
        if args.limit is not None:
            assets = assets[: max(args.limit, 0)]
        for asset in assets:
            queued_assets.append(
                (
                    group_name,
                    asset,
                    output_dir / group_name / f"{safe_slug(asset.asset_id)}.png",
                )
            )
    items: list[dict[str, Any]] = []
    safe_print(f"[flux-skill] loading model for asset generation: {args.model or DEFAULT_MODEL_IDS['asset']}")
    safe_print(f"[flux-skill] reading recap folder: {bundle.recap_dir}")
    progress = AssetQueueProgress(queued_assets)
    progress.render_initial()

    for index, (group_name, asset, output_path) in enumerate(queued_assets, start=1):
        prompt_result = build_asset_prompt(
            asset,
            style_target=style_target,
            final_prompt_language=final_prompt_language,
        )
        prompt_result = author_asset_prompt(
            repo_root=repo_root,
            fallback_result=prompt_result,
            style_target=style_target,
            final_prompt_language=final_prompt_language,
            skill_definition=skill_definition,
        )
        prompt_result = apply_asset_prompt_config(
            prompt_result,
            group_name=group_name,
            final_prompt_language=final_prompt_language,
            asset_prompt_config=asset_prompt_config,
        )
        seed = args.seed if args.seed is not None else stable_seed(asset.asset_id, bundle.story_slug, group_name)
        width, height = resolve_generation_dimensions(
            args=args,
            resolution_config=resolution_config,
            mode="asset",
            asset_type=asset.asset_type,
        )
        config = build_generation_config(
            backend=args.backend,
            mode="asset",
            model_id=args.model,
            steps=args.steps,
            guidance_scale=args.guidance,
            width=width,
            height=height,
            seed=seed,
            asset_type=asset.asset_type,
        )
        progress.set_current(index, group_name, asset, output_path)
        try:
            generator.generate(
                prompt=prompt_result.prompt,
                output_path=output_path,
                config=config,
                references=None,
                log_output=progress.should_log_generator_output(),
            )
        except Exception:
            progress.mark_failed(index, group_name, asset, output_path)
            raise
        prompt_text_path = write_resolved_prompt_text(output_path, prompt_result)
        progress.mark_done(index, group_name, asset, output_path)
        items.append(
            manifest_item_for_asset(
                asset=asset,
                output_path=output_path,
                prompt_result=prompt_result,
                config=config,
                style_target=style_target,
                resolved_prompt_path=prompt_text_path,
            )
        )

    progress.finish()
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema": "flux_asset_generation_manifest_v1",
        "timestamp": timestamp_now(),
        "input_folder": str(bundle.recap_dir),
        "mode": "asset",
        "input_contract": bundle.input_contract,
        "selection_notes": list(bundle.selection_notes),
        "style_target": style_target,
        "final_prompt_language": final_prompt_language,
        "workflow_plan": workflow_plan.as_manifest_dict(),
        "chosen_model": args.model or DEFAULT_MODEL_IDS["asset"],
        "backend": args.backend,
        "output_root": str(output_dir),
        "selected_asset_types": selected_groups,
        "item_count": len(items),
        "items": items,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_print("[flux-skill] saving outputs")
    return manifest_path, output_dir


def run_keyscene_generation(
    *,
    bundle,
    generator: FluxImageGenerator,
    style_target: str,
    final_prompt_language: str,
    args: argparse.Namespace,
    preferred_generated_assets_dir: Path | None = None,
    workflow_plan: FluxWorkflowPlan,
    resolution_config: FluxResolutionConfig,
    output_dir_override: Path | None = None,
    skill_definition=None,
    repo_root: Path = REPO_ROOT,
) -> Path:
    preferred_dirs = [preferred_generated_assets_dir] if preferred_generated_assets_dir is not None else None
    asset_index = bundle.discover_generated_assets(preferred_dirs)
    if not asset_index.has_any_assets():
        searched = "\n".join(f"- {path}" for path in asset_index.searched_paths)
        raise FileNotFoundError(
            "Keyscene generation requires generated assets, but none were found.\n"
            "Searched these locations:\n"
            f"{searched}"
        )

    output_dir = output_dir_override or resolve_output_dir(args.output_root, bundle.recap_dir, "generated_keyscenes")
    keyscene_dir = output_dir / "keyscenes"
    keyscene_dir.mkdir(parents=True, exist_ok=True)
    resume_source = resolve_resume_source(
        args.resume_from,
        current_output_root=output_dir,
        enable_resume=bool(getattr(args, "resume_keyscenes", True)),
    )
    previous_manifest_items = load_previous_keyscene_items(resume_source)
    debug_dir = output_dir / "debug"
    if args.debug_keyscene_output:
        debug_dir.mkdir(parents=True, exist_ok=True)

    safe_print(f"[flux-skill] loading model for keyscene generation: {args.model or DEFAULT_MODEL_IDS['keyscene']}")
    safe_print(f"[flux-skill] reading recap folder: {bundle.recap_dir}")
    safe_print(f"[flux-skill] using generated assets from: {asset_index.root_dir}")
    if resume_source is not None:
        safe_print(f"[flux-skill] resume source detected: {resume_source.root_dir}")

    beats = list(bundle.beats)
    if args.limit is not None:
        beats = beats[: max(args.limit, 0)]

    plans = [
        plan_keyscene_selection(
            bundle=bundle,
            asset_index=asset_index,
            beat=beat,
            scene_validation_mode=args.scene_validation,
        )
        for beat in beats
    ]

    items: list[dict[str, Any]] = []
    jobs: list[BatchGenerationJob] = []
    if plans:
        safe_print("[flux-skill] keyscene queue:")
    for index, plan in enumerate(plans, start=1):
        beat = plan.beat
        prompt_result = build_keyscene_prompt(
            beat,
            style_target=style_target,
            final_prompt_language=final_prompt_language,
            shot_mode=plan.shot_mode,
            vehicle_preset=plan.vehicle_preset,
            scene_asset=plan.selected_assets["scene"],
            character_asset=plan.selected_assets["character"],
            prop_asset=plan.selected_assets["prop"],
            scene_strategy=plan.scene.strategy,
            character_strategy=plan.character.strategy,
            prop_strategy=plan.prop.strategy,
        )
        prompt_result = author_keyscene_prompt(
            repo_root=repo_root,
            fallback_result=prompt_result,
            style_target=style_target,
            final_prompt_language=final_prompt_language,
            reference_roles=reference_role_summary(plan),
            skill_definition=skill_definition,
        )
        seed = args.seed if args.seed is not None else stable_seed(beat.beat_id, bundle.story_slug, "keyscene")
        width, height = resolve_generation_dimensions(
            args=args,
            resolution_config=resolution_config,
            mode="keyscene",
        )
        config = build_generation_config(
            backend=args.backend,
            mode="keyscene",
            model_id=args.model,
            steps=args.steps,
            guidance_scale=args.guidance,
            width=width,
            height=height,
            seed=seed,
        )
        output_path = keyscene_dir / f"{safe_slug(beat.beat_id)}.png"
        debug_artifact = None
        if args.debug_keyscene_output:
            debug_artifact = debug_dir / f"{safe_slug(beat.beat_id)}.json"
            write_keyscene_debug_artifact(
                debug_artifact,
                plan=plan,
                prompt_result=prompt_result,
            )
        prompt_text_path = keyscene_dir / f"{safe_slug(beat.beat_id)}.resolved_prompt.txt"
        prompt_text_path.write_text(prompt_result.prompt + "\n", encoding="utf-8")
        resume_status, resume_source_path = maybe_resume_existing_keyscene_output(
            beat_id=beat.beat_id,
            output_path=output_path,
            resume_source=resume_source,
        )
        if resume_status == "queued":
            safe_print(
                f"[flux-skill] [ ] {index}/{len(plans)} {output_path.name} "
                f"({plan.shot_mode}, {len(plan.reference_paths)} refs)"
            )
            safe_print(
                f"[flux-skill] queueing keyscene {index}/{len(plans)} -> {output_path.name} "
                f"({plan.shot_mode}, {len(plan.reference_paths)} refs)"
            )
            jobs.append(
                BatchGenerationJob(
                    prompt=prompt_result.prompt,
                    output_path=output_path,
                    config=config,
                    references=tuple(plan.reference_paths),
                    job_id=beat.beat_id,
                )
            )
        else:
            safe_print(
                f"[flux-skill] resuming keyscene {index}/{len(plans)} -> {output_path.name} "
                f"from existing output"
            )
            safe_print(f"[flux-skill] [x] completed {index}/{len(plans)}: {output_path.name} (reused)")
        items.append(
            manifest_item_for_keyscene(
                beat=beat,
                output_path=output_path,
                prompt_result=prompt_result,
                config=config,
                style_target=style_target,
                selected_assets=plan.selected_assets,
                matching_notes=[plan.scene.note, plan.character.note, plan.prop.note],
                shot_mode=plan.shot_mode,
                prompt_template=plan.prompt_template,
                vehicle_preset=plan.vehicle_preset,
                reference_policy=plan.reference_policy,
                reference_count=len(plan.reference_paths),
                validation_warnings=list(plan.validation_warnings),
                debug_artifact=debug_artifact,
                candidate_scores={
                    "scene": list(plan.scene.candidate_scores),
                    "character": list(plan.character.candidate_scores),
                    "prop": list(plan.prop.candidate_scores),
                },
                resolved_prompt_path=prompt_text_path,
                resume_status=resume_status,
                resumed_from=resume_source_path,
                previous_item=previous_manifest_items.get(beat.beat_id),
                dropped_prop_reason=plan.dropped_prop_reason,
            )
        )

    if len(jobs) > 1 and generator.backend != "mock":
        safe_print(f"[flux-skill] generating keyscenes in one batch to reuse {args.model or DEFAULT_MODEL_IDS['keyscene']}")
    if jobs:
        generator.generate_batch(jobs)
        queued_lookup = {job.job_id or job.output_path.stem: job.output_path for job in jobs}
        for index, plan in enumerate(plans, start=1):
            output_path = queued_lookup.get(plan.beat.beat_id)
            if output_path is not None:
                safe_print(f"[flux-skill] [x] completed {index}/{len(plans)}: {output_path.name}")
    else:
        safe_print("[flux-skill] all requested keyscenes were already available; no new generation was needed.")

    manifest_path = output_dir / "manifest.json"
    manifest = {
        "schema": "flux_keyscene_generation_manifest_v1",
        "timestamp": timestamp_now(),
        "input_folder": str(bundle.recap_dir),
        "mode": "keyscene",
        "input_contract": bundle.input_contract,
        "selection_notes": list(bundle.selection_notes),
        "style_target": style_target,
        "final_prompt_language": final_prompt_language,
        "workflow_plan": workflow_plan.as_manifest_dict(),
        "chosen_model": args.model or DEFAULT_MODEL_IDS["keyscene"],
        "backend": args.backend,
        "generated_assets_root": str(asset_index.root_dir),
        "available_asset_counts": asset_index.available_counts(),
        "resume_enabled": bool(getattr(args, "resume_keyscenes", True)),
        "resume_source": str(resume_source.root_dir) if resume_source is not None else None,
        "scene_validation": args.scene_validation,
        "debug_keyscene_output": bool(args.debug_keyscene_output),
        "batch_generation": {
            "job_count": len(jobs),
            "requested_model_reuse": len(jobs) > 1,
        },
        "output_root": str(output_dir),
        "item_count": len(items),
        "items": items,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_print("[flux-skill] saving outputs")
    return manifest_path


def plan_keyscene_selection(
    *,
    bundle,
    asset_index,
    beat: RecapBeat,
    scene_validation_mode: str,
) -> KeysceneSelectionPlan:
    scene_match = select_best_asset_match(
        bundle=bundle,
        asset_index=asset_index,
        beat=beat,
        group_name="scenes",
        allow_fallback=True,
    )
    provisional_character = select_best_asset_match(
        bundle=bundle,
        asset_index=asset_index,
        beat=beat,
        group_name="characters",
        allow_fallback=False,
    )
    provisional_prop = select_best_asset_match(
        bundle=bundle,
        asset_index=asset_index,
        beat=beat,
        group_name="props",
        allow_fallback=False,
    )
    shot_mode = classify_keyscene_shot_mode(
        beat,
        has_character=provisional_character.asset is not None,
        has_prop=provisional_prop.asset is not None,
    )
    vehicle_preset = classify_vehicle_shot_preset(beat) if shot_mode == SHOT_MODE_VEHICLE else None

    character_match = provisional_character
    prop_match = provisional_prop
    warnings: list[str] = []
    dropped_prop_reason: str | None = None

    if shot_mode == SHOT_MODE_VEHICLE:
        character_match, prop_match, vehicle_warnings, dropped_prop_reason = resolve_vehicle_reference_policy(
            beat=beat,
            vehicle_preset=vehicle_preset,
            character_match=provisional_character,
            prop_match=provisional_prop,
        )
        warnings.extend(vehicle_warnings)
    elif shot_mode == SHOT_MODE_INSERT:
        character_match = missing_asset_match("characters", "Insert/object keyscenes default to scene + prop.")
        if prop_match.asset is None:
            warnings.append(f"{beat.beat_id}: insert/object beat did not find a confident prop match; generating with scene-only context.")
        elif not matches_primary_object_context(beat, prop_match):
            warnings.append(
                f"{beat.beat_id}: omitted prop `{prop_match.asset.asset_name}` because it only matched secondary visual text, not the primary object beat."
            )
            prop_match = missing_asset_match("props", "Prop omitted because it did not match the primary object beat.")
            dropped_prop_reason = "primary_object_mismatch"
    else:
        if character_match.asset is None:
            warnings.append(f"{beat.beat_id}: no confident character match was found; keyscene will rely on scene context only.")
        if not should_include_prop(beat, shot_mode=shot_mode, prop_match=prop_match):
            if prop_match.asset is not None:
                warnings.append(f"{beat.beat_id}: prop reference omitted to keep the prompt/edit set compact.")
            prop_match = missing_asset_match("props", "Prop omitted by reference policy.")
            dropped_prop_reason = "compact_reference_policy"

    scene_warnings = validate_scene_selection(
        beat=beat,
        selected_match=scene_match,
        candidate_scores=scene_match.candidate_scores,
        mode=scene_validation_mode,
    )
    warnings.extend(scene_warnings)

    selected_assets = {
        "scene": scene_match.asset,
        "character": character_match.asset,
        "prop": prop_match.asset,
    }
    reference_paths = tuple(asset.path for asset in selected_assets.values() if asset is not None)
    reference_policy = describe_reference_policy(
        shot_mode=shot_mode,
        scene_present=scene_match.asset is not None,
        character_present=character_match.asset is not None,
        prop_present=prop_match.asset is not None,
    )
    return KeysceneSelectionPlan(
        beat=beat,
        shot_mode=shot_mode,
        prompt_template="vehicle_keyscene" if shot_mode == SHOT_MODE_VEHICLE else shot_mode,
        vehicle_preset=vehicle_preset,
        scene=scene_match,
        character=character_match,
        prop=prop_match,
        selected_assets=selected_assets,
        reference_paths=reference_paths,
        reference_policy=reference_policy,
        validation_warnings=tuple(warnings),
        dropped_prop_reason=dropped_prop_reason,
    )


def select_best_asset_match(
    *,
    bundle,
    asset_index,
    beat: RecapBeat,
    group_name: str,
    allow_fallback: bool,
) -> AssetMatch:
    generated_items = list(asset_index.items_by_group.get(group_name, []))
    if not generated_items:
        return missing_asset_match(group_name, f"No generated {group_name} assets were found.")

    recap_lookup = {asset.asset_id: asset for asset in bundle.assets_by_group.get(group_name, [])}
    scored_candidates = []
    for item in generated_items:
        scored_candidates.append(score_generated_asset_match(item, recap_lookup.get(item.asset_id), beat))
    scored_candidates.sort(key=lambda entry: (-entry["score"], entry["asset"].path.name.casefold()))
    best = scored_candidates[0]

    if best["score"] > 0:
        matched_terms = tuple(best["matched_terms"])
        if best["strategy"] == "exact_name_match":
            note = f"Matched {group_name[:-1]} asset by explicit beat phrase: {', '.join(matched_terms)}."
        else:
            note = f"Matched {group_name[:-1]} asset by keyword overlap: {', '.join(matched_terms)}."
        return AssetMatch(
            asset=best["asset"],
            strategy=best["strategy"],
            note=note,
            score=int(best["score"]),
            matched_terms=matched_terms,
            candidate_scores=tuple(format_candidate_scores(scored_candidates)),
        )

    if allow_fallback and len(generated_items) == 1:
        only_item = generated_items[0]
        return AssetMatch(
            asset=only_item,
            strategy="single_asset_fallback",
            note=f"Only one generated {group_name[:-1]} asset was available; using it as fallback.",
            score=0,
            matched_terms=(),
            candidate_scores=tuple(format_candidate_scores(scored_candidates)),
        )

    if allow_fallback:
        first_item = sorted(generated_items, key=lambda item: item.path.name.casefold())[0]
        return AssetMatch(
            asset=first_item,
            strategy="first_available_fallback",
            note=f"No reliable {group_name[:-1]} asset match was found; using the first available generated asset as fallback.",
            score=0,
            matched_terms=(),
            candidate_scores=tuple(format_candidate_scores(scored_candidates)),
        )

    return missing_asset_match(
        group_name,
        f"No confident {group_name[:-1]} asset match was found, so this reference was omitted.",
        candidate_scores=tuple(format_candidate_scores(scored_candidates)),
    )


def score_generated_asset_match(
    generated_asset: GeneratedAsset,
    recap_asset: RecapAsset | None,
    beat: RecapBeat,
) -> dict[str, Any]:
    phrases = build_asset_match_phrases(generated_asset, recap_asset)
    score = 0
    matched_terms: list[str] = []
    strategy = "no_match"
    weighted_segments = build_weighted_beat_segments(beat)

    for phrase in phrases:
        normalized_phrase = normalize_match_text_local(phrase)
        if len(normalized_phrase) < 2:
            continue
        for segment_text, weight in weighted_segments:
            if normalized_phrase in segment_text:
                if phrase == generated_asset.asset_name:
                    score += 80 * weight
                    strategy = "exact_name_match"
                else:
                    score += weight * min(40, max(12, len(normalized_phrase) * 2))
                    if strategy != "exact_name_match":
                        strategy = "keyword_overlap"
                if phrase not in matched_terms:
                    matched_terms.append(phrase)
                break

    for keyword in build_asset_keywords(generated_asset, recap_asset):
        if len(keyword) < 2:
            continue
        normalized_keyword = normalize_match_text_local(keyword)
        for segment_text, weight in weighted_segments:
            if normalized_keyword and normalized_keyword in segment_text:
                score += 6 * weight
                if keyword not in matched_terms:
                    matched_terms.append(keyword)
                if strategy == "no_match":
                    strategy = "keyword_overlap"
                break

    score += contextual_asset_match_bonus(generated_asset, beat)

    return {
        "asset": generated_asset,
        "score": max(score, 0),
        "strategy": strategy,
        "matched_terms": matched_terms[:6],
    }


def build_asset_match_text(beat: RecapBeat) -> str:
    return "\n".join(
        part
        for part in (
            beat.summary,
            beat.visual_prompt,
            beat.anchor_text,
            beat.asset_focus,
            beat.mood,
        )
        if part
    )


def build_weighted_beat_segments(beat: RecapBeat) -> list[tuple[str, int]]:
    segments = [
        (normalize_match_text_local(beat.summary), 4),
        (normalize_match_text_local(beat.anchor_text), 3),
        (normalize_match_text_local(beat.asset_focus), 2),
        (normalize_match_text_local(beat.visual_prompt), 1),
        (normalize_match_text_local(beat.mood), 1),
    ]
    return [(text, weight) for text, weight in segments if text]


def build_asset_match_phrases(generated_asset: GeneratedAsset, recap_asset: RecapAsset | None) -> list[str]:
    phrases = [generated_asset.asset_name, generated_asset.asset_id.replace(f"{generated_asset.asset_type}_", "")]
    if recap_asset is not None:
        phrases.extend(
            [
                recap_asset.name,
                recap_asset.core_feature,
            ]
        )
    return [phrase.strip() for phrase in phrases if str(phrase).strip()]


def build_asset_keywords(generated_asset: GeneratedAsset, recap_asset: RecapAsset | None) -> list[str]:
    text_parts = [generated_asset.asset_name]
    if recap_asset is not None:
        text_parts.extend([recap_asset.description, recap_asset.subject_content])
    keywords: list[str] = []
    seen: set[str] = set()
    for text in text_parts:
        for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", str(text or "")):
            token = token.strip()
            if len(token) < 2 or token.casefold() in {"scene", "character", "prop", "2d", "3d", "ai漫剧风格"}:
                continue
            if token in {"风格", "内容", "主体", "环境", "细节", "丰富", "高清4k", "光影质感", "层次丰富"}:
                continue
            normalized = normalize_match_text_local(token)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(token)
    return keywords


def normalize_match_text_local(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "").casefold())


def contextual_asset_match_bonus(generated_asset: GeneratedAsset, beat: RecapBeat) -> int:
    beat_text = f"{beat.summary}\n{beat.anchor_text}\n{beat.visual_prompt}\n{beat.asset_focus}".casefold()
    if not is_vehicle_shot(beat):
        return scene_context_bonus(generated_asset, beat_text)

    bonus = scene_context_bonus(generated_asset, beat_text)
    if generated_asset.asset_type == "prop":
        if is_vehicle_named_asset(generated_asset.asset_name):
            if any(token in beat_text for token in ("摩托", "赛车", "bike", "motorcycle", "车", "engine", "发动机", "排气")):
                bonus += 140
            if "发动机" in beat_text and any(token in generated_asset.asset_name.casefold() for token in ("发动机", "engine", "排气")):
                bonus += 120
            if any(token in beat_text for token in ("赛道", "track", "拉力赛", "达喀尔", "波尔蒂芒")) and any(
                token in generated_asset.asset_name.casefold() for token in ("kove", "摩托", "赛车")
            ):
                bonus += 80
        else:
            if any(token in beat_text for token in ("摩托", "赛车", "engine", "发动机", "赛道", "车")):
                bonus -= 80
    return bonus


def scene_context_bonus(generated_asset: GeneratedAsset, beat_text: str) -> int:
    if generated_asset.asset_type != "scene":
        return 0
    name = generated_asset.asset_name.casefold()
    if any(token in name for token in ("山路", "公路", "road")) and any(token in beat_text for token in ("暴雨", "乡路", "公路", "道路", "泥浆", "追赶")):
        return 140
    if any(token in name for token in ("沙漠", "赛地")) and any(token in beat_text for token in ("沙漠", "达喀尔", "拉力赛", "风沙", "烈日")):
        return 160
    if "波尔蒂芒" in name and any(token in beat_text for token in ("波尔蒂芒", "终点线", "看台", "世界赛场")):
        return 180
    if "赛道" in name and any(token in beat_text for token in ("赛道", "终点线", "发车", "维修区", "护栏", "看台", "赛车")):
        return 150
    if "加油站" in name and any(token in beat_text for token in ("加油站", "油站", "采访车", "返程")):
        return 140
    if any(token in name for token in ("工坊", "工棚", "测功房")) and any(token in beat_text for token in ("工坊", "工棚", "测功房", "台架", "工作间")):
        return 150
    if "霓虹街" in name and any(token in beat_text for token in ("霓虹", "街头", "街道", "夜晚")):
        return 150
    return 0


def is_vehicle_named_asset(name: str) -> bool:
    text = str(name or "").casefold()
    return any(token in text for token in ("摩托", "赛车", "发动机", "engine", "kove", "zxmoto", "排气", "前叉", "轮胎", "车架"))


def should_include_prop(beat: RecapBeat, *, shot_mode: str, prop_match: AssetMatch) -> bool:
    if prop_match.asset is None:
        return False
    if shot_mode == SHOT_MODE_VEHICLE:
        return False
    if shot_mode == SHOT_MODE_INSERT:
        return prop_match.score >= 60
    if prop_match.score < 120:
        return False
    focus = str(beat.asset_focus or "").strip().casefold()
    return focus in {"object", "interaction", "montage"}


def matches_primary_object_context(beat: RecapBeat, prop_match: AssetMatch) -> bool:
    if prop_match.asset is None:
        return False
    primary_text = normalize_match_text_local("\n".join(part for part in (beat.summary, beat.anchor_text) if part))
    if not primary_text:
        return False
    candidate_terms = [prop_match.asset.asset_name, *prop_match.matched_terms]
    return any(normalize_match_text_local(term) in primary_text for term in candidate_terms if term)


def resolve_vehicle_reference_policy(
    *,
    beat: RecapBeat,
    vehicle_preset: str | None,
    character_match: AssetMatch,
    prop_match: AssetMatch,
) -> tuple[AssetMatch, AssetMatch, list[str], str | None]:
    warnings: list[str] = []
    dropped_prop_reason: str | None = None
    design_critical = vehicle_design_is_critical(beat, prop_match)
    scene_character_preferred = vehicle_preset in {VEHICLE_PRESET_RIDING, VEHICLE_PRESET_STANDING, VEHICLE_PRESET_TRACK}

    if vehicle_preset in {VEHICLE_PRESET_DETAIL, VEHICLE_PRESET_WORKSHOP}:
        if prop_match.asset is None:
            warnings.append(f"{beat.beat_id}: vehicle-dominant beat did not find a confident vehicle prop; prompt will rely on scene context.")
        if vehicle_preset == VEHICLE_PRESET_DETAIL:
            character_match = missing_asset_match("characters", "Vehicle detail keyscenes default to scene + prop.")
        elif character_match.asset is not None and prop_match.asset is not None and prop_match.score >= 180:
            warnings.append(f"{beat.beat_id}: character reference omitted so the vehicle build stays physically dominant.")
            character_match = missing_asset_match("characters", "Vehicle build prompt prioritizes scene + prop over scene + character.")
        return character_match, prop_match, warnings, None

    if character_match.asset is None and prop_match.asset is not None:
        warnings.append(f"{beat.beat_id}: vehicle shot will use scene + prop because no confident rider/character match was found.")
        return character_match, prop_match, warnings, None

    if scene_character_preferred and prop_match.asset is not None:
        if not design_critical:
            warnings.append(
                f"{beat.beat_id}: dropped vehicle prop `{prop_match.asset.asset_name}` to keep scene + character and reduce oversized-bike risk."
            )
            dropped_prop_reason = "scene_character_preferred"
            prop_match = missing_asset_match("props", "Vehicle shot prefers scene + character to keep scale stable.")
        elif vehicle_preset == VEHICLE_PRESET_TRACK:
            warnings.append(
                f"{beat.beat_id}: dropped prop `{prop_match.asset.asset_name}` on track shot to avoid poster-scale vehicle behavior; exact design stays in prompt context."
            )
            dropped_prop_reason = "track_scale_guardrail"
            prop_match = missing_asset_match("props", "Track vehicle shot prefers scene + character for scale stability.")
        elif prop_match.score < 180:
            warnings.append(
                f"{beat.beat_id}: dropped vehicle prop `{prop_match.asset.asset_name}` because the match was not strong enough for a 3-reference vehicle shot."
            )
            dropped_prop_reason = "weak_vehicle_prop_match"
            prop_match = missing_asset_match("props", "Vehicle prop omitted because the match was not strong enough.")
    elif prop_match.asset is None and character_match.asset is None:
        warnings.append(f"{beat.beat_id}: vehicle shot is missing both rider and vehicle prop references; generation will rely on scene context only.")

    return character_match, prop_match, warnings, dropped_prop_reason


def vehicle_design_is_critical(beat: RecapBeat, prop_match: AssetMatch) -> bool:
    beat_text = f"{beat.summary}\n{beat.anchor_text}\n{beat.visual_prompt}".casefold()
    named_vehicle_tokens = (
        "旧款125",
        "kove",
        "zxmoto",
        "820rr-rs",
        "自制摩托",
        "三缸发动机",
        "车架号",
        "编号",
        "涂装",
        "logo",
        "贴花",
        "定制外壳",
        "同一辆",
        "exact bike",
        "exact vehicle",
    )
    if any(token in beat_text for token in named_vehicle_tokens):
        return True
    if prop_match.asset is None:
        return False
    asset_name = prop_match.asset.asset_name.casefold()
    if any(token in asset_name for token in ("kove", "zxmoto", "820", "rr-rs")):
        return True
    if any(char.isdigit() for char in asset_name):
        return True
    return False


def validate_scene_selection(
    *,
    beat: RecapBeat,
    selected_match: AssetMatch,
    candidate_scores: tuple[dict[str, Any], ...],
    mode: str,
) -> list[str]:
    warnings: list[str] = []
    if mode == "off" or selected_match.asset is None:
        return warnings

    best_candidate = candidate_scores[0] if candidate_scores else None
    if best_candidate is None:
        return warnings

    severe = False
    if selected_match.score <= 0 and len(candidate_scores) > 1:
        severe = True
        warnings.append(
            f"{beat.beat_id}: scene selection has no semantic overlap with the beat; chosen scene `{selected_match.asset.asset_name}` is low confidence."
        )
    elif selected_match.score < 60:
        warnings.append(
            f"{beat.beat_id}: scene selection for `{selected_match.asset.asset_name}` is only weakly matched to the beat intent."
        )

    if best_candidate.get("asset_id") and selected_match.asset.asset_id != best_candidate["asset_id"]:
        severe = True
        warnings.append(
            f"{beat.beat_id}: selected scene `{selected_match.asset.asset_name}` conflicts with a stronger semantic match `{best_candidate['asset_name']}`."
        )

    if severe and mode == "fail":
        candidate_summary = "; ".join(
            f"{entry['asset_name']}:{entry['score']}" for entry in candidate_scores[:5]
        )
        raise ValueError(
            f"Semantic scene validation failed for {beat.beat_id}. "
            f"Selected scene: {selected_match.asset.asset_name}. "
            f"Candidates: {candidate_summary}"
        )
    return warnings


def describe_reference_policy(*, shot_mode: str, scene_present: bool, character_present: bool, prop_present: bool) -> str:
    parts = []
    if scene_present:
        parts.append("scene")
    if character_present:
        parts.append("character")
    if prop_present:
        parts.append("prop")
    joined = " + ".join(parts) if parts else "no references"
    return f"{shot_mode}: {joined}"


def missing_asset_match(group_name: str, note: str, candidate_scores: tuple[dict[str, Any], ...] = ()) -> AssetMatch:
    return AssetMatch(
        asset=None,
        strategy="missing",
        note=note,
        score=0,
        matched_terms=(),
        candidate_scores=candidate_scores,
    )


def format_candidate_scores(scored_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    for entry in scored_candidates[:5]:
        asset = entry["asset"]
        formatted.append(
            {
                "asset_id": asset.asset_id,
                "asset_name": asset.asset_name,
                "score": int(entry["score"]),
                "strategy": entry["strategy"],
                "matched_terms": list(entry["matched_terms"]),
            }
        )
    return formatted


def write_keyscene_debug_artifact(
    path: Path,
    *,
    plan: KeysceneSelectionPlan,
    prompt_result,
) -> None:
    payload = {
        "beat_id": plan.beat.beat_id,
        "shot_mode": plan.shot_mode,
        "vehicle_shot": plan.shot_mode == SHOT_MODE_VEHICLE,
        "prompt_template": plan.prompt_template,
        "vehicle_preset": plan.vehicle_preset,
        "reference_policy": plan.reference_policy,
        "dropped_prop_reason": plan.dropped_prop_reason,
        "chosen_references": {
            role: (
                {
                    "asset_id": asset.asset_id,
                    "asset_name": asset.asset_name,
                    "path": str(asset.path),
                }
                if asset is not None
                else None
            )
            for role, asset in plan.selected_assets.items()
        },
        "selected_scene_asset": plan.scene.candidate_scores[0] if plan.scene.candidate_scores else None,
        "selected_character_asset": plan.character.candidate_scores[0] if plan.character.candidate_scores else None,
        "selected_prop_asset": plan.prop.candidate_scores[0] if plan.prop.candidate_scores else None,
        "final_prompt_language": prompt_result.final_prompt_language,
        "prompt_author": prompt_result.metadata.get("prompt_author"),
        "authoring_model": prompt_result.metadata.get("authoring_model"),
        "fallback_reason": prompt_result.metadata.get("fallback_reason"),
        "source_structured_input": prompt_result.source_structured_input,
        "raw_long_form_source_description": prompt_result.metadata.get("raw_source_description"),
        "compressed_final_prompt": prompt_result.prompt,
        "final_rendered_prompt": prompt_result.prompt,
        "deterministic_fallback_prompt": prompt_result.metadata.get("deterministic_fallback_prompt"),
        "prompt_length": prompt_result.metadata.get("prompt_length"),
        "legacy_prompt": prompt_result.metadata.get("legacy_prompt"),
        "legacy_prompt_length": prompt_result.metadata.get("legacy_prompt_length"),
        "camera_motion_removed": prompt_result.metadata.get("camera_motion_removed"),
        "anti_oversize_rules": prompt_result.metadata.get("anti_oversize_rules"),
        "framing_clause": prompt_result.metadata.get("framing_clause"),
        "validation_warnings": list(plan.validation_warnings),
        "candidate_scores": {
            "scene": list(plan.scene.candidate_scores),
            "character": list(plan.character.candidate_scores),
            "prop": list(plan.prop.candidate_scores),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_resume_source(resume_from: str | None, *, current_output_root: Path, enable_resume: bool) -> ResumeSource | None:
    if not enable_resume:
        return None
    candidate_path = Path(resume_from).expanduser().resolve() if resume_from else None
    if candidate_path is None:
        candidate_path = detect_previous_keyscene_output_root(current_output_root)
        if candidate_path is None:
            return None
    resolved = normalize_resume_root(candidate_path)
    if resolved is None:
        return None
    if resolved.root_dir == current_output_root.resolve():
        return None
    return resolved


def detect_previous_keyscene_output_root(current_output_root: Path) -> Path | None:
    current_output_root = current_output_root.resolve()
    session_dir = current_output_root.parent
    skill_output_root = session_dir.parent
    prefix = session_dir.name.split("__", 1)[0]
    candidates: list[Path] = []
    for sibling in skill_output_root.iterdir():
        if sibling == session_dir or not sibling.is_dir():
            continue
        if not sibling.name.startswith(f"{prefix}__"):
            continue
        normalized = normalize_resume_root(sibling)
        if normalized is None:
            continue
        if any(is_valid_existing_output(path) for path in normalized.keyscene_dir.glob("*.png")):
            candidates.append(normalized.root_dir)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def normalize_resume_root(path: Path) -> ResumeSource | None:
    candidate = path.resolve()
    if candidate.is_file():
        candidate = candidate.parent
    if candidate.name == "keyscenes" and candidate.is_dir():
        root_dir = candidate.parent
        manifest_path = root_dir / "manifest.json"
        return ResumeSource(root_dir=root_dir, keyscene_dir=candidate, manifest_path=manifest_path if manifest_path.exists() else None)
    if (candidate / "keyscenes").is_dir():
        manifest_path = candidate / "manifest.json"
        return ResumeSource(
            root_dir=candidate,
            keyscene_dir=(candidate / "keyscenes").resolve(),
            manifest_path=manifest_path if manifest_path.exists() else None,
        )
    if (candidate / "generated_keyscenes" / "keyscenes").is_dir():
        root_dir = (candidate / "generated_keyscenes").resolve()
        manifest_path = root_dir / "manifest.json"
        return ResumeSource(
            root_dir=root_dir,
            keyscene_dir=(root_dir / "keyscenes").resolve(),
            manifest_path=manifest_path if manifest_path.exists() else None,
        )
    return None


def maybe_resume_existing_keyscene_output(
    *,
    beat_id: str,
    output_path: Path,
    resume_source: ResumeSource | None,
) -> tuple[str, str | None]:
    if is_valid_existing_output(output_path):
        return "existing_output_reused", str(output_path)
    if resume_source is None:
        return "queued", None
    source_path = resume_source.keyscene_dir / f"{safe_slug(beat_id)}.png"
    if not is_valid_existing_output(source_path):
        return "queued", None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, output_path)
    return "copied_from_resume_source", str(source_path)


def is_valid_existing_output(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def load_previous_keyscene_items(resume_source: ResumeSource | None) -> dict[str, dict[str, Any]]:
    if resume_source is None or resume_source.manifest_path is None:
        return {}
    try:
        payload = json.loads(resume_source.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = payload.get("items")
    if not isinstance(items, list):
        return {}
    resolved: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        beat_id = str(item.get("beat_id") or "").strip()
        if beat_id:
            resolved[beat_id] = item
    return resolved


def manifest_item_for_asset(
    *,
    asset: RecapAsset,
    output_path: Path,
    prompt_result,
    config,
    style_target: str,
    resolved_prompt_path: Path,
) -> dict[str, Any]:
    return {
        "timestamp": timestamp_now(),
        "asset_type": asset.asset_type,
        "asset_id": asset.asset_id,
        "asset_name": asset.name,
        "mode": "asset",
        "style_target": style_target,
        "chosen_model": config.model_id,
        "backend": config.backend,
        "steps": config.steps,
        "guidance_scale": config.guidance_scale,
        "seed": config.seed,
        "width": config.width,
        "height": config.height,
        "prompt": prompt_result.prompt,
        "final_rendered_prompt": prompt_result.prompt,
        "final_prompt_language": prompt_result.final_prompt_language,
        "source_structured_input": prompt_result.source_structured_input,
        "prompt_source": prompt_result.prompt_source,
        "prompt_confidence": prompt_result.confidence,
        "prompt_notes": list(prompt_result.notes),
        "prompt_author": prompt_result.metadata.get("prompt_author"),
        "authoring_model": prompt_result.metadata.get("authoring_model"),
        "fallback_reason": prompt_result.metadata.get("fallback_reason"),
        "deterministic_fallback_prompt": prompt_result.metadata.get("deterministic_fallback_prompt"),
        "resolved_prompt_path": str(resolved_prompt_path),
        "output_path": str(output_path),
    }


def manifest_item_for_keyscene(
    *,
    beat: RecapBeat,
    output_path: Path,
    prompt_result,
    config,
    style_target: str,
    selected_assets: dict[str, Any],
    matching_notes: list[str],
    shot_mode: str,
    prompt_template: str,
    vehicle_preset: str | None,
    reference_policy: str,
    reference_count: int,
    validation_warnings: list[str],
    debug_artifact: Path | None,
    candidate_scores: dict[str, list[dict[str, Any]]],
    resolved_prompt_path: Path,
    resume_status: str,
    resumed_from: str | None,
    previous_item: dict[str, Any] | None,
    dropped_prop_reason: str | None,
) -> dict[str, Any]:
    limitations = [
        note
        for note in matching_notes + validation_warnings
        if "fallback" in note or note.startswith("No reliable") or note.startswith("No generated") or "low confidence" in note
    ]
    prompt_metadata = prompt_result.metadata
    return {
        "timestamp": timestamp_now(),
        "beat_id": beat.beat_id,
        "episode_number": beat.episode_number,
        "mode": "keyscene",
        "style_target": style_target,
        "chosen_model": config.model_id,
        "backend": config.backend,
        "steps": config.steps,
        "guidance_scale": config.guidance_scale,
        "seed": config.seed,
        "width": config.width,
        "height": config.height,
        "prompt": prompt_result.prompt,
        "final_rendered_prompt": prompt_result.prompt,
        "final_prompt_language": prompt_result.final_prompt_language,
        "source_structured_input": prompt_result.source_structured_input,
        "prompt_source": prompt_result.prompt_source,
        "prompt_confidence": prompt_result.confidence,
        "prompt_notes": list(prompt_result.notes),
        "prompt_author": prompt_result.metadata.get("prompt_author"),
        "authoring_model": prompt_result.metadata.get("authoring_model"),
        "fallback_reason": prompt_result.metadata.get("fallback_reason"),
        "deterministic_fallback_prompt": prompt_result.metadata.get("deterministic_fallback_prompt"),
        "shot_mode": shot_mode,
        "prompt_template": prompt_template,
        "vehicle_shot": shot_mode == SHOT_MODE_VEHICLE,
        "vehicle_preset": vehicle_preset,
        "reference_policy": reference_policy,
        "reference_count": reference_count,
        "prompt_length": prompt_metadata.get("prompt_length"),
        "legacy_prompt_length": prompt_metadata.get("legacy_prompt_length"),
        "raw_source_description": prompt_metadata.get("raw_source_description"),
        "anti_oversize_rules": prompt_metadata.get("anti_oversize_rules"),
        "framing_clause": prompt_metadata.get("framing_clause"),
        "summary": beat.summary,
        "anchor_text": beat.anchor_text,
        "selected_assets": {
            role: (
                {
                    "asset_id": asset.asset_id,
                    "asset_name": asset.asset_name,
                    "path": str(asset.path),
                }
                if asset is not None
                else None
            )
            for role, asset in selected_assets.items()
        },
        "matching_notes": matching_notes,
        "validation_warnings": validation_warnings,
        "candidate_scores": candidate_scores,
        "limitations": limitations,
        "debug_artifact": str(debug_artifact) if debug_artifact is not None else None,
        "resolved_prompt_path": str(resolved_prompt_path),
        "resume_status": resume_status,
        "resumed_from": resumed_from,
        "previous_output_path": previous_item.get("output_path") if isinstance(previous_item, dict) else None,
        "dropped_prop_reason": dropped_prop_reason,
        "output_path": str(output_path),
    }


def load_plan_summary(manifest_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    plan = payload.get("workflow_plan")
    return plan if isinstance(plan, dict) else {}


def print_workflow_plan(plan: FluxWorkflowPlan) -> None:
    safe_print(f"[flux-skill] input contract: {plan.input_contract}")
    safe_print(
        "[flux-skill] workflow plan: "
        f"requested={plan.requested_mode or 'auto'} -> resolved={plan.resolved_mode or 'stop'}"
    )
    if plan.asset_types:
        safe_print(f"[flux-skill] asset scope: {', '.join(plan.asset_types)}")
    if plan.selected_assets_root:
        safe_print(f"[flux-skill] reusable assets: {plan.selected_assets_root}")
    for note in plan.notes:
        safe_print(f"[flux-skill] note: {note}")
    for warning in plan.warnings:
        safe_print(f"[flux-skill] warning: {warning}")
    if plan.stop_reason:
        safe_print(f"[flux-skill] stop: {plan.stop_reason}")


def reference_role_summary(plan: KeysceneSelectionPlan) -> list[dict[str, str]]:
    roles: list[dict[str, str]] = []
    ordered_roles = (
        ("scene", "image 1", "scene/layout/background"),
        ("character", "image 2", "character identity / wardrobe / pose basis"),
        ("prop", "image 3", "prop / vehicle / design cue"),
    )
    for role_name, label, purpose in ordered_roles:
        asset = plan.selected_assets.get(role_name)
        if asset is None:
            continue
        roles.append(
            {
                "role": label,
                "purpose": purpose,
                "asset_name": asset.asset_name,
                "asset_type": asset.asset_type,
                "path": str(asset.path),
            }
        )
    return roles


def write_resolved_prompt_text(output_path: Path, prompt_result) -> Path:
    prompt_path = output_path.with_suffix(".resolved_prompt.txt")
    prompt_path.write_text(prompt_result.prompt + "\n", encoding="utf-8")
    return prompt_path


def prompt_mode(*, non_interactive: bool) -> str:
    if non_interactive:
        raise ValueError("Missing required --mode for non-interactive execution.")
    print("Choose generation mode:")
    print("1. assets")
    print("2. keyscenes")
    print("3. assets and keyscenes")
    response = input("Enter choice: ").strip().casefold()
    normalized = normalize_mode(response)
    if normalized is not None:
        return normalized
    if response.startswith("asset"):
        return "asset"
    if response.startswith("keyscene"):
        return "keyscene"
    raise ValueError("Please answer 1, 2, or 3, or type `asset generation`, `keyscene generation`, or `assets then keyscenes`.")


def prompt_recap_folder(*, non_interactive: bool) -> str:
    return prompt_recap_folder_with_default(non_interactive=non_interactive, default_value=None)


def prompt_recap_folder_with_default(*, non_interactive: bool, default_value: str | None) -> str:
    if non_interactive:
        raise ValueError("Missing required --recap-folder for non-interactive execution.")
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


def resolve_recap_folder_for_request(args: argparse.Namespace, *, requested_mode: str) -> str:
    if requested_mode == "keyscene":
        return resolve_keyscene_recap_folder(args)
    return (
        args.recap_folder
        if args.non_interactive and args.recap_folder
        else prompt_recap_folder_with_default(
            non_interactive=args.non_interactive,
            default_value=args.recap_folder,
        )
    )


def resolve_keyscene_recap_folder(args: argparse.Namespace) -> str:
    default_recap_folder = normalize_recap_folder_input(args.recap_folder or args.episode_script)
    if args.non_interactive:
        if not default_recap_folder:
            raise ValueError("Keyscene mode requires --recap-folder or --episode-script for non-interactive execution.")
        return default_recap_folder
    return prompt_recap_folder_with_default(non_interactive=False, default_value=default_recap_folder)


def derive_default_assets_folder(path_value: str) -> str:
    if not path_value:
        return ""
    candidate = Path(path_value).expanduser().resolve()
    if candidate.is_dir():
        recap_dir = candidate
    else:
        recap_dir = candidate.parent
    run_root = recap_dir.parent if recap_dir.name in {"02_recap_production", "01_recap_production"} else recap_dir
    for folder_name in ("generated_assets", "05_assets_t2i", "04_assets_t2i"):
        assets_dir = run_root / folder_name
        if assets_dir.exists() and assets_dir.is_dir():
            return str(assets_dir)
    return ""


def normalize_recap_folder_input(path_value: str | None) -> str | None:
    if not path_value:
        return None
    candidate = Path(path_value).expanduser().resolve()
    if candidate.is_file():
        if candidate.name in {
            "04_episode_scene_script.json",
            "02_beat_sheet.json",
            "03_asset_registry.json",
            "04_anchor_prompts.json",
            "05_video_prompts.json",
        }:
            return str(candidate.parent)
        return str(candidate.parent)
    return str(candidate)


def prompt_asset_types() -> list[str]:
    _, asset_types = prompt_output_targets("asset")
    return asset_types


def prompt_style_target(*, default_value: str) -> str:
    default_choice = style_choice_number(default_value)
    print("Choose style target:")
    print(f"1. 2d{format_default_suffix(default_choice, '1')}")
    print(f"2. 3d{format_default_suffix(default_choice, '2')}")
    print(f"3. realism{format_default_suffix(default_choice, '3')}")
    response = input("Enter choice (blank for default): ").strip().casefold()
    if not response:
        return default_value
    aliases = {
        "1": "2d-anime-cartoon",
        "2d": "2d-anime-cartoon",
        "2": "3d-anime",
        "3d": "3d-anime",
        "3": "realism",
        "realism": "realism",
        "realistic": "realism",
    }
    resolved = aliases.get(response)
    if not resolved:
        raise ValueError("Choose 1, 2, or 3 for style target.")
    return resolved


def prompt_output_targets(initial_mode: str) -> tuple[str, list[str]]:
    include_keyscenes = initial_mode == "asset_then_keyscene"
    print("Choose outputs to generate:")
    print("1. characters")
    print("2. scenes")
    print("3. props")
    if include_keyscenes:
        print("4. keyscenes")
    response = input("Enter numbers separated by commas, or press Enter for all: ").strip()
    if not response:
        return (
            ("asset_then_keyscene" if include_keyscenes else "asset"),
            list(ASSET_GROUPS),
        )

    selected_numbers = [item.strip() for item in response.split(",") if item.strip()]
    asset_types: list[str] = []
    wants_keyscenes = False
    for item in selected_numbers:
        if item == "1" and "characters" not in asset_types:
            asset_types.append("characters")
        elif item == "2" and "scenes" not in asset_types:
            asset_types.append("scenes")
        elif item == "3" and "props" not in asset_types:
            asset_types.append("props")
        elif include_keyscenes and item == "4":
            wants_keyscenes = True

    if not asset_types and not wants_keyscenes:
        raise ValueError("Choose at least one listed output number, or press Enter for all.")
    if include_keyscenes:
        if wants_keyscenes and asset_types:
            return "asset_then_keyscene", asset_types
        if wants_keyscenes:
            return "keyscene", []
        return "asset", asset_types
    return "asset", asset_types


def parse_asset_types(value: str | None) -> list[str]:
    if value in (None, "", "all"):
        return list(ASSET_GROUPS)
    resolved: list[str] = []
    aliases = {
        "character": "characters",
        "characters": "characters",
        "prop": "props",
        "props": "props",
        "scene": "scenes",
        "scenes": "scenes",
    }
    for raw_item in str(value).split(","):
        item = aliases.get(raw_item.strip().casefold())
        if item and item not in resolved:
            resolved.append(item)
    if not resolved:
        raise ValueError("Asset subsets must use characters, props, and/or scenes.")
    return resolved


def normalize_mode(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if text == "1":
        return "asset"
    if text == "2":
        return "keyscene"
    if text == "3":
        return "asset_then_keyscene"
    if text.startswith("asset"):
        if "then" in text or "both" in text:
            return "asset_then_keyscene"
        return "asset"
    if text.startswith("keyscene"):
        return "keyscene"
    if "asset" in text and "keyscene" in text:
        return "asset_then_keyscene"
    return None


def stable_seed(identifier: str, story_slug: str, salt: str) -> int:
    digest = hashlib.sha256(f"{story_slug}\n{salt}\n{identifier}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def resolve_output_dir(output_root: str | None, recap_dir: Path, folder_name: str) -> Path:
    if output_root:
        return Path(output_root).expanduser().resolve()
    return (build_default_session_root(recap_dir) / folder_name).resolve()


def build_default_session_root(recap_dir: Path) -> Path:
    source_name = recap_dir.parent.name if recap_dir.name in {"02_recap_production", "01_recap_production"} else recap_dir.name
    session_name = f"{safe_slug(source_name)}__{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return (REPO_ROOT / "outputs" / "flux-asset-and-scene-generation" / session_name).resolve()


def style_choice_number(style_target: str) -> str:
    if style_target == "2d-anime-cartoon":
        return "1"
    if style_target == "3d-anime":
        return "2"
    return "3"


def format_default_suffix(default_choice: str, choice: str) -> str:
    return " (default)" if default_choice == choice else ""


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().casefold()
    return text in {"1", "true", "yes", "y", "on"}


def timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                continue


def safe_print(message: str) -> None:
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    raise SystemExit(main())
