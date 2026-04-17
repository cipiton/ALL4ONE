from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from load_recap_production import ASSET_GROUPS, RecapBundle


@dataclass(frozen=True, slots=True)
class FluxWorkflowPlan:
    requested_mode: str | None
    resolved_mode: str | None
    should_generate_assets: bool
    should_generate_keyscenes: bool
    asset_types: tuple[str, ...]
    style_target: str
    input_contract: str
    source_files: dict[str, str | None]
    available_counts: dict[str, int]
    has_existing_assets: bool
    selected_assets_root: str | None
    continuity_strategy: str
    fallback_strategy: str
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    stop_reason: str | None = None
    planner_source: str = "deterministic_policy"

    def as_manifest_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_generation_workflow(
    *,
    bundle: RecapBundle,
    requested_mode: str | None,
    explicit_assets_folder: str | None,
    asset_types: list[str] | None,
    style_target: str | None,
) -> FluxWorkflowPlan:
    asset_index = bundle.discover_generated_assets(
        [Path(explicit_assets_folder).expanduser().resolve()] if explicit_assets_folder else None
    )
    has_existing_assets = asset_index.has_any_assets()
    has_asset_source = any(bundle.assets_by_group.get(group) for group in ASSET_GROUPS)
    has_beats = bool(bundle.beats)
    has_anchor_planning = bundle.anchor_prompts_file is not None

    requested = (requested_mode or "").strip() or None
    warnings: list[str] = []
    notes = list(bundle.selection_notes)
    resolved_mode = requested

    if requested is None:
        if has_beats and has_existing_assets:
            resolved_mode = "keyscene"
            notes.append("Auto-selected keyscene generation because beat planning and reusable generated assets are both available.")
        elif has_beats and has_asset_source:
            resolved_mode = "asset_then_keyscene"
            notes.append("Auto-selected assets then keyscenes because beat planning exists but reusable generated assets were not found.")
        elif has_asset_source:
            resolved_mode = "asset"
            notes.append("Auto-selected asset generation because structured asset planning exists.")
        elif has_beats or has_anchor_planning:
            resolved_mode = "keyscene"
            notes.append("Auto-selected keyscene generation because beat or anchor planning exists, but the run still depends on reusable generated assets.")

    if resolved_mode == "asset":
        if not has_asset_source:
            return build_stopped_plan(
                bundle=bundle,
                requested_mode=requested,
                style_target=style_target,
                asset_types=asset_types,
                available_counts=asset_index.available_counts(),
                has_existing_assets=has_existing_assets,
                selected_assets_root=str(asset_index.root_dir) if has_existing_assets else None,
                reason="Asset generation needs structured asset planning. This source bundle does not include a usable asset registry.",
                warnings=warnings,
                notes=notes,
            )

    if resolved_mode == "keyscene":
        if not has_beats and not has_anchor_planning:
            return build_stopped_plan(
                bundle=bundle,
                requested_mode=requested,
                style_target=style_target,
                asset_types=asset_types,
                available_counts=asset_index.available_counts(),
                has_existing_assets=has_existing_assets,
                selected_assets_root=str(asset_index.root_dir) if has_existing_assets else None,
                reason="Keyscene generation needs beat planning or anchor prompt planning. This source bundle does not contain either.",
                warnings=warnings,
                notes=notes,
            )
        if not has_existing_assets:
            if has_asset_source:
                resolved_mode = "asset_then_keyscene"
                warnings.append("Reusable generated assets were missing, so the plan was upgraded from keyscenes-only to assets then keyscenes.")
            else:
                return build_stopped_plan(
                    bundle=bundle,
                    requested_mode=requested,
                    style_target=style_target,
                    asset_types=asset_types,
                    available_counts=asset_index.available_counts(),
                    has_existing_assets=False,
                    selected_assets_root=None,
                    reason="Keyscene generation prefers real generated assets for image conditioning, but no generated assets were found and no asset source is available for regeneration.",
                    warnings=warnings,
                    notes=notes,
                )

    if resolved_mode == "asset_then_keyscene":
        if not has_asset_source:
            if has_existing_assets and (has_beats or has_anchor_planning):
                resolved_mode = "keyscene"
                warnings.append("Structured asset planning was missing, so the plan fell back to keyscenes-only using existing generated assets.")
            else:
                return build_stopped_plan(
                    bundle=bundle,
                    requested_mode=requested,
                    style_target=style_target,
                    asset_types=asset_types,
                    available_counts=asset_index.available_counts(),
                    has_existing_assets=has_existing_assets,
                    selected_assets_root=str(asset_index.root_dir) if has_existing_assets else None,
                    reason="Assets then keyscenes requires structured asset planning before still-image references can be generated.",
                    warnings=warnings,
                    notes=notes,
                )
        if resolved_mode == "asset_then_keyscene" and not (has_beats or has_anchor_planning):
            resolved_mode = "asset"
            warnings.append("Beat planning was missing, so the plan was reduced to assets-only.")

    if resolved_mode is None:
        return build_stopped_plan(
            bundle=bundle,
            requested_mode=requested,
            style_target=style_target,
            asset_types=asset_types,
            available_counts=asset_index.available_counts(),
            has_existing_assets=has_existing_assets,
            selected_assets_root=str(asset_index.root_dir) if has_existing_assets else None,
            reason="The skill could not determine whether to run assets, keyscenes, or both from the current source bundle.",
            warnings=warnings,
            notes=notes,
        )

    resolved_asset_types = tuple(asset_types or list(ASSET_GROUPS)) if resolved_mode in {"asset", "asset_then_keyscene"} else ()
    continuity_strategy = describe_continuity_strategy(resolved_mode)
    fallback_strategy = describe_fallback_strategy(resolved_mode, has_existing_assets=has_existing_assets)
    if has_anchor_planning and not has_beats:
        warnings.append("Beat planning was inferred from anchor prompts only, so scene progression may be more skeletal than a full recap bundle.")
    if bundle.input_contract == "cp-production" and bundle.assets_file is None:
        warnings.append("cp-production asset registry was missing, so the skill can only reuse previously generated assets.")

    return FluxWorkflowPlan(
        requested_mode=requested,
        resolved_mode=resolved_mode,
        should_generate_assets=resolved_mode in {"asset", "asset_then_keyscene"},
        should_generate_keyscenes=resolved_mode in {"keyscene", "asset_then_keyscene"},
        asset_types=resolved_asset_types,
        style_target=style_target or bundle.style_target,
        input_contract=bundle.input_contract,
        source_files={
            "assets_file": str(bundle.assets_file) if bundle.assets_file else None,
            "image_config_file": str(bundle.image_config_file) if bundle.image_config_file else None,
            "scene_script_file": str(bundle.scene_script_file) if bundle.scene_script_file else None,
            "anchor_prompts_file": str(bundle.anchor_prompts_file) if bundle.anchor_prompts_file else None,
        },
        available_counts=asset_index.available_counts(),
        has_existing_assets=has_existing_assets,
        selected_assets_root=str(asset_index.root_dir) if has_existing_assets else None,
        continuity_strategy=continuity_strategy,
        fallback_strategy=fallback_strategy,
        warnings=tuple(warnings),
        notes=tuple(notes),
    )


def build_stopped_plan(
    *,
    bundle: RecapBundle,
    requested_mode: str | None,
    style_target: str | None,
    asset_types: list[str] | None,
    available_counts: dict[str, int],
    has_existing_assets: bool,
    selected_assets_root: str | None,
    reason: str,
    warnings: list[str],
    notes: list[str],
) -> FluxWorkflowPlan:
    return FluxWorkflowPlan(
        requested_mode=requested_mode,
        resolved_mode=None,
        should_generate_assets=False,
        should_generate_keyscenes=False,
        asset_types=tuple(asset_types or ()),
        style_target=style_target or bundle.style_target,
        input_contract=bundle.input_contract,
        source_files={
            "assets_file": str(bundle.assets_file) if bundle.assets_file else None,
            "image_config_file": str(bundle.image_config_file) if bundle.image_config_file else None,
            "scene_script_file": str(bundle.scene_script_file) if bundle.scene_script_file else None,
            "anchor_prompts_file": str(bundle.anchor_prompts_file) if bundle.anchor_prompts_file else None,
        },
        available_counts=available_counts,
        has_existing_assets=has_existing_assets,
        selected_assets_root=selected_assets_root,
        continuity_strategy=describe_continuity_strategy(None),
        fallback_strategy=describe_fallback_strategy(None, has_existing_assets=has_existing_assets),
        warnings=tuple(warnings),
        notes=tuple(notes),
        stop_reason=reason,
    )


def describe_continuity_strategy(resolved_mode: str | None) -> str:
    if resolved_mode == "asset":
        return (
            "Generate reusable identity anchors for characters, props, and environments first. "
            "Keep naming stable so later keyscene matching can reuse them deterministically."
        )
    if resolved_mode == "keyscene":
        return (
            "Prefer existing scene and character references for continuity. "
            "Add prop references only when story-critical or when the beat is insert-like."
        )
    if resolved_mode == "asset_then_keyscene":
        return (
            "Establish reusable assets first, then carry those exact outputs into keyscenes so identity, wardrobe, vehicles, "
            "and environment layout stay stable across beats."
        )
    return "Stop rather than hallucinating continuity when the source contract is incomplete."


def describe_fallback_strategy(resolved_mode: str | None, *, has_existing_assets: bool) -> str:
    if resolved_mode == "asset":
        return "If structured assets are incomplete, stop clearly instead of generating generic placeholders."
    if resolved_mode == "keyscene":
        return (
            "If beat or anchor planning is weak, derive the scene unit from the strongest available planning fields. "
            "If reusable assets disappear mid-run, stop and name the searched asset folders."
        )
    if resolved_mode == "asset_then_keyscene":
        if has_existing_assets:
            return "Reuse existing assets where possible, regenerate only the missing groups, then continue into keyscenes."
        return "Generate assets first, then continue into keyscenes. If beat planning is absent, reduce the run to assets-only."
    return "No fallback. Stop and explain the missing source materials."
