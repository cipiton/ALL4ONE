from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RECAP_STAGE_DIRS = ("02_recap_production", "01_recap_production")
CP_PRODUCTION_FILES = (
    "02_beat_sheet.json",
    "03_asset_registry.json",
    "04_anchor_prompts.json",
    "05_video_prompts.json",
)
CP_PRODUCTION_OPTIONAL_FILES = ("01_narration_script.txt", "05_video_prompts.json")
ASSET_STAGE_DIRS = ("generated_assets", "05_assets_t2i", "04_assets_t2i")
ASSET_GROUPS = ("characters", "props", "scenes")
STYLE_TARGETS = ("realism", "3d-anime", "2d-anime-cartoon")


@dataclass(frozen=True, slots=True)
class RecapAsset:
    asset_type: str
    asset_id: str
    name: str
    description: str
    core_feature: str
    subject_content: str
    style_lighting: str
    prompt: str
    prompt_fields: dict[str, str]
    order: int
    source_payload: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, slots=True)
class RecapBeat:
    beat_id: str
    episode_number: int
    summary: str
    visual_prompt: str
    shot_type: str
    camera_motion: str
    mood: str
    anchor_text: str
    priority: str
    beat_role: str
    pace_weight: str
    asset_focus: str
    source_payload: dict[str, Any] = field(repr=False)

    @property
    def combined_text(self) -> str:
        parts = [
            self.summary,
            self.visual_prompt,
            self.anchor_text,
            self.mood,
            self.asset_focus,
        ]
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class GeneratedAsset:
    asset_type: str
    asset_id: str
    asset_name: str
    path: Path

    @property
    def search_tokens(self) -> tuple[str, ...]:
        variants = {
            normalize_match_text(self.asset_id),
            normalize_match_text(self.asset_name),
            normalize_match_text(self.path.stem),
        }
        variants.discard("")
        return tuple(sorted(variants))


@dataclass(slots=True)
class GeneratedAssetIndex:
    root_dir: Path
    items_by_group: dict[str, list[GeneratedAsset]]
    searched_paths: list[Path]

    def has_any_assets(self) -> bool:
        return any(self.items_by_group.get(group) for group in ASSET_GROUPS)

    def available_counts(self) -> dict[str, int]:
        return {group: len(self.items_by_group.get(group, [])) for group in ASSET_GROUPS}

    def select_for_beat(self, group_name: str, beat: RecapBeat) -> tuple[GeneratedAsset | None, str, str]:
        items = list(self.items_by_group.get(group_name, []))
        if not items:
            return None, "missing", f"No generated {group_name} assets were found."

        beat_text = normalize_match_text(beat.combined_text)
        exact_matches: list[GeneratedAsset] = []
        partial_matches: list[GeneratedAsset] = []

        for item in items:
            for token in item.search_tokens:
                if not token:
                    continue
                if token in beat_text:
                    exact_matches.append(item)
                    break
            else:
                if any(shared_token(token, beat_text) for token in item.search_tokens):
                    partial_matches.append(item)

        if exact_matches:
            chosen = sorted(exact_matches, key=lambda item: item.path.name.casefold())[0]
            return chosen, "exact_name_match", f"Matched {group_name[:-1]} asset by exact name in beat text."

        if partial_matches:
            chosen = sorted(partial_matches, key=lambda item: item.path.name.casefold())[0]
            return chosen, "token_overlap_fallback", f"Matched {group_name[:-1]} asset by token overlap fallback."

        if len(items) == 1:
            return items[0], "single_asset_fallback", f"Only one {group_name[:-1]} asset was available; using it as fallback."

        chosen = sorted(items, key=lambda item: item.path.name.casefold())[0]
        return chosen, "first_available_fallback", f"No reliable {group_name[:-1]} asset match was found; using the first available generated asset as fallback."


@dataclass(frozen=True, slots=True)
class RecapBundle:
    recap_dir: Path
    run_root: Path | None
    assets_file: Path | None
    image_config_file: Path | None
    scene_script_file: Path | None
    anchor_prompts_file: Path | None
    input_contract: str
    series_title: str
    story_slug: str
    style_target: str
    assets_by_group: dict[str, list[RecapAsset]]
    beats: list[RecapBeat]
    selection_notes: tuple[str, ...] = ()

    def discover_generated_assets(self, preferred_dirs: list[Path] | None = None) -> GeneratedAssetIndex:
        searched_paths: list[Path] = []
        for candidate in generated_asset_candidates(self.recap_dir, self.run_root, preferred_dirs=preferred_dirs):
            searched_paths.append(candidate)
            if not candidate.exists() or not candidate.is_dir():
                continue

            items_by_group: dict[str, list[GeneratedAsset]] = {group: [] for group in ASSET_GROUPS}
            for group_name in ASSET_GROUPS:
                group_dir = candidate / group_name
                if not group_dir.exists() or not group_dir.is_dir():
                    continue
                for image_path in sorted(group_dir.iterdir(), key=lambda path: path.name.casefold()):
                    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                        continue
                    asset_type = group_name[:-1]
                    asset_id = image_path.stem
                    asset_name = name_from_asset_id(asset_id, asset_type)
                    items_by_group[group_name].append(
                        GeneratedAsset(
                            asset_type=asset_type,
                            asset_id=asset_id,
                            asset_name=asset_name,
                            path=image_path.resolve(),
                        )
                    )

            if any(items_by_group[group] for group in ASSET_GROUPS):
                return GeneratedAssetIndex(
                    root_dir=candidate.resolve(),
                    items_by_group=items_by_group,
                    searched_paths=searched_paths,
                )

        return GeneratedAssetIndex(
            root_dir=(searched_paths[0] if searched_paths else self.recap_dir).resolve(),
            items_by_group={group: [] for group in ASSET_GROUPS},
            searched_paths=searched_paths,
        )


def load_recap_bundle(input_path: str | Path) -> RecapBundle:
    recap_dir, run_root = resolve_recap_dir(input_path)
    if is_cp_production_dir(recap_dir):
        return load_cp_production_bundle(recap_dir, run_root)

    assets_file = require_existing_file(recap_dir / "02_assets.json", "02_assets.json")
    scene_script_file = require_existing_file(recap_dir / "04_episode_scene_script.json", "04_episode_scene_script.json")
    image_config_file = recap_dir / "03_image_config.json"
    if not image_config_file.exists():
        image_config_file = None

    assets_payload = load_json_file(assets_file)
    scene_script_payload = load_json_file(scene_script_file)
    image_config_payload = load_json_file(image_config_file) if image_config_file else {}

    style_target = normalize_style_target(
        first_text(
            image_config_payload.get("global_style", {}).get("style_preset") if isinstance(image_config_payload.get("global_style"), dict) else "",
            assets_payload.get("style_preset"),
            image_config_payload.get("style_preset"),
        )
    )
    series_title = first_text(
        scene_script_payload.get("series_title"),
        assets_payload.get("series_title"),
        recap_dir.parent.name if recap_dir.parent.name not in RECAP_STAGE_DIRS else recap_dir.name,
    )
    story_slug = first_text(scene_script_payload.get("story_slug"), assets_payload.get("story_slug"), safe_slug(series_title))

    return RecapBundle(
        recap_dir=recap_dir,
        run_root=run_root,
        assets_file=assets_file,
        image_config_file=image_config_file,
        scene_script_file=scene_script_file,
        anchor_prompts_file=None,
        input_contract="recap-production",
        series_title=series_title,
        story_slug=story_slug,
        style_target=style_target,
        assets_by_group={
            "characters": load_assets_group(assets_payload, "characters"),
            "props": load_assets_group(assets_payload, "props"),
            "scenes": load_assets_group(assets_payload, "scenes"),
        },
        beats=load_beats(scene_script_payload),
        selection_notes=("Detected recap-production input contract.",),
    )


def load_cp_production_bundle(cp_dir: Path, run_root: Path | None) -> RecapBundle:
    beat_sheet_file = optional_file(cp_dir / "02_beat_sheet.json")
    asset_registry_file = optional_file(cp_dir / "03_asset_registry.json")
    anchor_prompts_file = optional_file(cp_dir / "04_anchor_prompts.json")

    if beat_sheet_file is None and asset_registry_file is None and anchor_prompts_file is None:
        raise FileNotFoundError(
            "cp-production input did not include any usable planning files. "
            "Expected at least one of `02_beat_sheet.json`, `03_asset_registry.json`, or `04_anchor_prompts.json`."
        )

    beat_sheet_payload = load_json_file(beat_sheet_file)
    asset_registry_payload = load_json_file(asset_registry_file)
    anchor_prompts_payload = load_json_file(anchor_prompts_file)
    notes: list[str] = ["Detected cp-production input contract."]
    if beat_sheet_file is not None:
        notes.append(f"Loaded beat source: {beat_sheet_file.name}")
    else:
        notes.append("02_beat_sheet.json was missing; beat fallbacks will be inferred from anchor prompts only.")
    if asset_registry_file is not None:
        notes.append(f"Loaded asset source: {asset_registry_file.name}")
    else:
        notes.append("03_asset_registry.json was missing; asset generation can only reuse existing generated assets.")
    if anchor_prompts_file is not None:
        notes.append(f"Loaded anchor prompt source: {anchor_prompts_file.name}")
    else:
        notes.append("04_anchor_prompts.json was missing; scene prompting will fall back to beat-sheet fields only.")

    style_target = infer_cp_style_target(asset_registry_payload, anchor_prompts_payload)
    series_title = first_text(
        beat_sheet_payload.get("project_title"),
        asset_registry_payload.get("project_title"),
        anchor_prompts_payload.get("project_title"),
        cp_dir.name,
    )
    story_slug = first_text(
        beat_sheet_payload.get("story_slug"),
        asset_registry_payload.get("story_slug"),
        safe_slug(series_title),
    )
    anchor_prompt_index = build_cp_anchor_prompt_index(anchor_prompts_payload)

    return RecapBundle(
        recap_dir=cp_dir,
        run_root=run_root,
        assets_file=asset_registry_file,
        image_config_file=None,
        scene_script_file=beat_sheet_file,
        anchor_prompts_file=anchor_prompts_file,
        input_contract="cp-production",
        series_title=series_title,
        story_slug=story_slug,
        style_target=style_target,
        assets_by_group=load_cp_assets_groups(asset_registry_payload, style_target=style_target) if asset_registry_file else empty_asset_groups(),
        beats=load_cp_beats(beat_sheet_payload, anchor_prompt_index=anchor_prompt_index)
        if beat_sheet_file
        else load_cp_beats_from_anchor_prompts(anchor_prompts_payload),
        selection_notes=tuple(notes),
    )


def resolve_recap_dir(input_path: str | Path) -> tuple[Path, Path | None]:
    candidate = Path(input_path).expanduser().resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Recap production path does not exist: {candidate}")

    if candidate.is_file():
        candidate = candidate.parent

    if candidate.name in RECAP_STAGE_DIRS:
        return candidate, candidate.parent

    if is_cp_production_dir(candidate):
        return candidate, candidate

    for stage_name in RECAP_STAGE_DIRS:
        stage_candidate = candidate / stage_name
        if stage_candidate.exists() and stage_candidate.is_dir():
            return stage_candidate.resolve(), candidate.resolve()

    raise ValueError(
        "Expected one of: the recap production output folder itself, the story run folder that contains "
        "`02_recap_production/` or `01_recap_production/`, or a `cp-production` output folder containing at least one of "
        "`02_beat_sheet.json`, `03_asset_registry.json`, or `04_anchor_prompts.json`."
    )


def generated_asset_candidates(
    recap_dir: Path,
    run_root: Path | None,
    *,
    preferred_dirs: list[Path] | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    for candidate in preferred_dirs or []:
        resolved = Path(candidate).expanduser().resolve()
        if resolved not in candidates:
            candidates.append(resolved)
    for base in [recap_dir, run_root] if run_root else [recap_dir]:
        if base is None:
            continue
        for stage_name in ASSET_STAGE_DIRS:
            candidate = (base / stage_name).resolve()
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def load_assets_group(payload: dict[str, Any], group_name: str) -> list[RecapAsset]:
    raw_items = payload.get(group_name) or []
    if not isinstance(raw_items, list):
        raise ValueError(f"`{group_name}` in 02_assets.json must be a JSON array.")
    assets: list[RecapAsset] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"{group_name}[{index}] must be a JSON object.")
        asset_type = str(raw_item.get("asset_type") or group_name[:-1]).strip() or group_name[:-1]
        prompt_fields = raw_item.get("prompt_fields") if isinstance(raw_item.get("prompt_fields"), dict) else {}
        assets.append(
            RecapAsset(
                asset_type=asset_type,
                asset_id=first_text(raw_item.get("asset_id"), f"{asset_type}_{index:03d}"),
                name=first_text(raw_item.get("name"), f"{asset_type}_{index:03d}"),
                description=first_text(raw_item.get("description")),
                core_feature=first_text(raw_item.get("core_feature"), prompt_fields.get("核心特征")),
                subject_content=first_text(raw_item.get("subject_content"), prompt_fields.get("主体内容")),
                style_lighting=first_text(raw_item.get("style_lighting"), prompt_fields.get("风格及光线")),
                prompt=first_text(raw_item.get("visual_prompt"), raw_item.get("prompt"), raw_item.get("prompt_text")),
                prompt_fields={str(key): str(value) for key, value in prompt_fields.items() if str(value).strip()},
                order=coerce_int(raw_item.get("order"), default=index),
                source_payload=raw_item,
            )
        )
    return sorted(assets, key=lambda item: (item.order, item.name.casefold()))


def load_cp_assets_groups(payload: dict[str, Any], *, style_target: str) -> dict[str, list[RecapAsset]]:
    raw_items = payload.get("assets") or []
    if not isinstance(raw_items, list):
        return empty_asset_groups()

    grouped: dict[str, list[RecapAsset]] = {group: [] for group in ASSET_GROUPS}
    style_lighting = cp_style_lighting(style_target)

    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"assets[{index}] in 03_asset_registry.json must be a JSON object.")
        asset_type = first_text(raw_item.get("asset_type"), "prop")
        group_name = cp_asset_group_name(asset_type)
        asset_name = first_text(raw_item.get("asset_name"), raw_item.get("name"), raw_item.get("asset_id"), f"{asset_type}_{index:03d}")
        description = first_text(raw_item.get("short_description"), raw_item.get("description"))
        consistency_notes = first_text(raw_item.get("consistency_notes"))
        subject_content = build_cp_asset_subject_content(raw_item)
        grouped[group_name].append(
            RecapAsset(
                asset_type=asset_type,
                asset_id=first_text(raw_item.get("asset_id"), f"{asset_type}_{index:03d}"),
                name=asset_name,
                description=description,
                core_feature=infer_cp_core_feature(asset_name, description),
                subject_content=subject_content,
                style_lighting=style_lighting,
                prompt=subject_content,
                prompt_fields={
                    "asset_type": asset_type,
                    "recurrence_importance": first_text(raw_item.get("recurrence_importance")),
                    "generation_priority": first_text(raw_item.get("generation_priority")),
                    "linked_beats": ", ".join(str(item) for item in raw_item.get("linked_beats", []) if str(item).strip()),
                    "consistency_notes": consistency_notes,
                },
                order=index,
                source_payload=raw_item,
            )
        )

    for group_name in grouped:
        grouped[group_name] = sorted(grouped[group_name], key=lambda item: (item.order, item.name.casefold()))
    return grouped


def load_beats(payload: dict[str, Any]) -> list[RecapBeat]:
    episodes = payload.get("episodes") or []
    if not isinstance(episodes, list):
        raise ValueError("`episodes` in 04_episode_scene_script.json must be a JSON array.")
    beats: list[RecapBeat] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        episode_number = coerce_int(episode.get("episode_number"), default=0)
        scene_beats = episode.get("scene_beats") or []
        if not isinstance(scene_beats, list):
            continue
        for index, raw_beat in enumerate(scene_beats, start=1):
            if not isinstance(raw_beat, dict):
                continue
            beat_id = first_text(raw_beat.get("scene_id"), raw_beat.get("beat_id"), f"ep{episode_number:02d}_s{index:02d}")
            beats.append(
                RecapBeat(
                    beat_id=beat_id,
                    episode_number=episode_number,
                    summary=first_text(raw_beat.get("summary")),
                    visual_prompt=first_text(raw_beat.get("visual_prompt"), raw_beat.get("prompt")),
                    shot_type=first_text(raw_beat.get("shot_type")),
                    camera_motion=first_text(raw_beat.get("camera_motion")),
                    mood=first_text(raw_beat.get("mood")),
                    anchor_text=first_text(raw_beat.get("anchor_text")),
                    priority=first_text(raw_beat.get("priority")),
                    beat_role=first_text(raw_beat.get("beat_role")),
                    pace_weight=first_text(raw_beat.get("pace_weight")),
                    asset_focus=first_text(raw_beat.get("asset_focus")),
                    source_payload=raw_beat,
                )
            )
    return beats


def load_cp_beats(payload: dict[str, Any], *, anchor_prompt_index: dict[str, dict[str, Any]]) -> list[RecapBeat]:
    raw_beats = payload.get("beats") or []
    if not isinstance(raw_beats, list):
        raise ValueError("`beats` in 02_beat_sheet.json must be a JSON array.")

    beats: list[RecapBeat] = []
    for index, raw_beat in enumerate(raw_beats, start=1):
        if not isinstance(raw_beat, dict):
            continue
        beat_id = first_text(raw_beat.get("beat_id"), f"beat_{index:03d}")
        anchor_prompt = anchor_prompt_index.get(beat_id, {})
        beats.append(
            RecapBeat(
                beat_id=beat_id,
                episode_number=infer_cp_episode_number(raw_beat, beat_id=beat_id, index=index),
                summary=first_text(raw_beat.get("summary")),
                visual_prompt=first_text(
                    anchor_prompt.get("anchor_image_prompt"),
                    build_cp_visual_prompt(raw_beat, anchor_prompt),
                    raw_beat.get("summary"),
                ),
                shot_type=first_text(anchor_prompt.get("shot_size"), raw_beat.get("shot_type_suggestion")),
                camera_motion=first_text(raw_beat.get("camera_movement_suggestion")),
                mood=first_text(raw_beat.get("mood")),
                anchor_text=first_text(raw_beat.get("narration_anchor_line"), raw_beat.get("anchor_text")),
                priority=first_text(raw_beat.get("priority")),
                beat_role=first_text(raw_beat.get("story_function"), raw_beat.get("beat_role")),
                pace_weight=first_text(raw_beat.get("duration_class"), raw_beat.get("pace_weight")),
                asset_focus=infer_cp_asset_focus(raw_beat, anchor_prompt),
                source_payload={
                    **raw_beat,
                    "cp_anchor_prompt": anchor_prompt,
                },
            )
        )
    return beats


def load_cp_beats_from_anchor_prompts(payload: dict[str, Any]) -> list[RecapBeat]:
    raw_prompts = payload.get("anchor_prompts") or []
    if not isinstance(raw_prompts, list):
        return []
    beats: list[RecapBeat] = []
    for index, raw_prompt in enumerate(raw_prompts, start=1):
        if not isinstance(raw_prompt, dict):
            continue
        beat_id = first_text(raw_prompt.get("beat_id"), raw_prompt.get("prompt_id"), f"beat_{index:03d}")
        summary = ". ".join(
            part
            for part in (
                first_text(raw_prompt.get("subject")),
                first_text(raw_prompt.get("environment")),
                first_text(raw_prompt.get("main_object")),
                first_text(raw_prompt.get("visible_state")),
            )
            if part
        )
        beats.append(
            RecapBeat(
                beat_id=beat_id,
                episode_number=infer_cp_episode_number(raw_prompt, beat_id=beat_id, index=index),
                summary=summary,
                visual_prompt=first_text(raw_prompt.get("anchor_image_prompt"), summary),
                shot_type=first_text(raw_prompt.get("shot_size")),
                camera_motion="",
                mood=first_text(raw_prompt.get("style")),
                anchor_text=first_text(raw_prompt.get("subject")),
                priority="medium",
                beat_role="development",
                pace_weight="medium",
                asset_focus=infer_cp_asset_focus({}, raw_prompt),
                source_payload={**raw_prompt, "fallback_source": "anchor_prompts_only"},
            )
        )
    return beats


def load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a top-level JSON object in {path}")
    return payload


def require_existing_file(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Required recap production file was not found: {label} at {path}")
    return path.resolve()


def optional_file(path: Path) -> Path | None:
    return path.resolve() if path.exists() and path.is_file() else None


def normalize_style_target(value: str) -> str:
    text = str(value or "").strip().casefold().replace("_", "-")
    if not text:
        return "2d-anime-cartoon"
    aliases = {
        "2d": "2d-anime-cartoon",
        "2d-anime": "2d-anime-cartoon",
        "2d-anime-cartoon": "2d-anime-cartoon",
        "anime": "2d-anime-cartoon",
        "cartoon": "2d-anime-cartoon",
        "动漫": "2d-anime-cartoon",
        "3d": "3d-anime",
        "3d-anime": "3d-anime",
        "cg": "3d-anime",
        "realism": "realism",
        "realistic": "realism",
        "写实": "realism",
    }
    return aliases.get(text, "2d-anime-cartoon")


def infer_cp_style_target(asset_registry_payload: dict[str, Any], anchor_prompts_payload: dict[str, Any]) -> str:
    candidates: list[str] = []
    for payload in (asset_registry_payload, anchor_prompts_payload):
        if not isinstance(payload, dict):
            continue
        candidates.extend(
            str(value)
            for value in (
                payload.get("style_target"),
                payload.get("style"),
                payload.get("visual_style"),
            )
            if str(value or "").strip()
        )
    for prompt in anchor_prompts_payload.get("anchor_prompts", []) if isinstance(anchor_prompts_payload.get("anchor_prompts"), list) else []:
        if not isinstance(prompt, dict):
            continue
        candidates.extend(
            str(value)
            for value in (
                prompt.get("style"),
                prompt.get("anchor_image_prompt"),
            )
            if str(value or "").strip()
        )
    for candidate in candidates:
        normalized = infer_style_target_from_text(candidate)
        if normalized:
            return normalized
    return "realism"


def infer_style_target_from_text(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    if not text:
        return None
    if any(token in text for token in ("3d", "cg", "cgi")):
        return "3d-anime"
    if any(token in text for token in ("2d", "anime", "cartoon", "动漫", "漫")):
        return "2d-anime-cartoon"
    if any(token in text for token in ("realism", "realistic", "cinematic realism", "写实", "grounded")):
        return "realism"
    return None


def normalize_match_text(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "").casefold())


def is_cp_production_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and any((path / filename).is_file() for filename in CP_PRODUCTION_FILES)


def empty_asset_groups() -> dict[str, list[RecapAsset]]:
    return {group: [] for group in ASSET_GROUPS}


def cp_asset_group_name(asset_type: str) -> str:
    normalized = str(asset_type or "").strip().casefold()
    if normalized == "character":
        return "characters"
    if normalized == "environment":
        return "scenes"
    return "props"


def cp_style_lighting(style_target: str) -> str:
    if style_target == "3d-anime":
        return "high-precision 3D CG style, realistic layered light"
    if style_target == "2d-anime-cartoon":
        return "2D anime style, layered stylized light"
    return "grounded cinematic realism, controlled natural light"


def build_cp_asset_subject_content(raw_item: dict[str, Any]) -> str:
    parts = [
        first_text(raw_item.get("short_description"), raw_item.get("description")),
        first_text(raw_item.get("consistency_notes")),
    ]
    return " ".join(part for part in parts if part).strip()


def infer_cp_core_feature(asset_name: str, description: str) -> str:
    candidate = first_text(asset_name, description)
    return candidate[:48].strip()


def build_cp_anchor_prompt_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    raw_prompts = payload.get("anchor_prompts") or []
    if not isinstance(raw_prompts, list):
        raise ValueError("`anchor_prompts` in 04_anchor_prompts.json must be a JSON array.")
    for raw_prompt in raw_prompts:
        if not isinstance(raw_prompt, dict):
            continue
        beat_id = first_text(raw_prompt.get("beat_id"))
        if beat_id:
            index[beat_id] = raw_prompt
    return index


def build_cp_visual_prompt(raw_beat: dict[str, Any], anchor_prompt: dict[str, Any]) -> str:
    parts = [
        first_text(anchor_prompt.get("subject")),
        first_text(anchor_prompt.get("environment")),
        first_text(anchor_prompt.get("main_object")),
        first_text(anchor_prompt.get("composition")),
        first_text(anchor_prompt.get("lighting")),
        first_text(anchor_prompt.get("visible_state")),
        first_text(raw_beat.get("scene_focus")),
        first_text(raw_beat.get("subject_focus")),
        first_text(raw_beat.get("prop_focus")),
    ]
    return ". ".join(part for part in parts if part).strip()


def infer_cp_episode_number(raw_beat: dict[str, Any], *, beat_id: str, index: int) -> int:
    for candidate in (raw_beat.get("chapter_id"), beat_id):
        text = str(candidate or "")
        match = re.search(r"(\d+)", text)
        if match:
            return coerce_int(match.group(1), default=index)
    return index


def infer_cp_asset_focus(raw_beat: dict[str, Any], anchor_prompt: dict[str, Any]) -> str:
    shot_text = first_text(anchor_prompt.get("shot_size"), raw_beat.get("shot_type_suggestion")).casefold()
    summary_text = " ".join(
        first_text(raw_beat.get(key))
        for key in ("summary", "subject_focus", "scene_focus", "prop_focus")
    ).casefold()
    if "insert" in shot_text or (first_text(raw_beat.get("prop_focus")) and not first_text(raw_beat.get("subject_focus"))):
        return "object"
    if any(token in summary_text for token in ("motorcycle", "bike", "vehicle", "car", "摩托", "赛车", "车")):
        return "interaction"
    if first_text(raw_beat.get("scene_focus")) and not first_text(raw_beat.get("subject_focus")):
        return "environment"
    if any(token in shot_text for token in ("close-up", "close up", "medium close")):
        return "character"
    return "interaction"


def name_from_asset_id(asset_id: str, asset_type: str) -> str:
    prefix = f"{asset_type}_"
    if asset_id.startswith(prefix):
        return asset_id[len(prefix):]
    return asset_id


def shared_token(value: str, beat_text: str) -> bool:
    tokens = [token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", value) if token]
    return any(token in beat_text for token in tokens)


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", str(value).strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:96] or "story"


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def coerce_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed
