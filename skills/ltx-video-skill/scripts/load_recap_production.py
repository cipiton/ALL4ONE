from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


RECAP_STAGE_DIRS = ("02_recap_production", "01_recap_production")
CANONICAL_SCENE_SCRIPT = "04_episode_scene_script.json"
OPTIONAL_SCENE_SCRIPT_MD = "04_episode_scene_script.md"
CP_PRODUCTION_REQUIRED_FILES = ("02_beat_sheet.json", "05_video_prompts.json")
CP_PRODUCTION_OPTIONAL_FILES = ("01_narration_script.txt", "03_asset_registry.json", "04_anchor_prompts.json")
KEYSCENE_STAGE_DIRS = ("generated_keyscenes", "06_keyscene_i2i", "05_keyscene_i2i")


@dataclass(frozen=True, slots=True)
class RecapShot:
    shot_id: str
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
    video_prompt: str = ""
    anchor_prompt: str = ""
    linked_assets: tuple[str, ...] = ()
    source_contract: str = "recap-production"
    source_payload: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def episode_id(self) -> str:
        return f"ep{self.episode_number:02d}"

    @property
    def combined_text(self) -> str:
        return "\n".join(
            part
            for part in (
                self.summary,
                self.video_prompt,
                self.visual_prompt,
                self.anchor_prompt,
                self.anchor_text,
                self.mood,
                self.shot_type,
                self.camera_motion,
                " ".join(self.linked_assets),
            )
            if part
        )


@dataclass(frozen=True, slots=True)
class GeneratedKeyscene:
    beat_id: str
    path: Path


@dataclass(slots=True)
class GeneratedKeysceneIndex:
    root_dir: Path
    items_by_beat: dict[str, GeneratedKeyscene]
    searched_paths: list[Path]

    def has_any_images(self) -> bool:
        return bool(self.items_by_beat)

    def find_for_shot(self, shot: RecapShot) -> GeneratedKeyscene | None:
        for key in candidate_shot_image_keys(shot):
            match = self.items_by_beat.get(key)
            if match is not None:
                return match
        return None


@dataclass(frozen=True, slots=True)
class RecapBundle:
    recap_dir: Path
    run_root: Path | None
    scene_script_file: Path
    scene_script_markdown: Path | None
    assets_file: Path | None
    image_config_file: Path | None
    anchor_prompts_file: Path | None
    video_prompts_file: Path | None
    narration_script_file: Path | None
    input_contract: str
    series_title: str
    story_slug: str
    assets_lookup: dict[str, dict[str, str]]
    shots: list[RecapShot]
    selection_notes: tuple[str, ...]

    def discover_generated_keyscenes(self, preferred_dirs: list[Path] | None = None) -> GeneratedKeysceneIndex:
        searched_paths: list[Path] = []
        for candidate in generated_keyscene_candidates(self.recap_dir, self.run_root, preferred_dirs=preferred_dirs):
            searched_paths.append(candidate)
            search_dir = candidate / "keyscenes" if (candidate / "keyscenes").is_dir() else candidate
            if not search_dir.exists() or not search_dir.is_dir():
                continue

            items: dict[str, GeneratedKeyscene] = {}
            for image_path in sorted(search_dir.iterdir(), key=lambda path: path.name.casefold()):
                if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                beat_id = image_path.stem
                items[beat_id] = GeneratedKeyscene(beat_id=beat_id, path=image_path.resolve())
            if items:
                return GeneratedKeysceneIndex(
                    root_dir=search_dir.resolve(),
                    items_by_beat=items,
                    searched_paths=searched_paths,
                )

        root_dir = searched_paths[0].resolve() if searched_paths else self.recap_dir.resolve()
        return GeneratedKeysceneIndex(root_dir=root_dir, items_by_beat={}, searched_paths=searched_paths)


def load_recap_bundle(input_path: str | Path) -> RecapBundle:
    recap_dir, run_root = resolve_recap_dir(input_path)
    if is_cp_production_dir(recap_dir):
        return load_cp_production_bundle(recap_dir, run_root)

    scene_script_file, notes = select_scene_script_file(recap_dir)
    payload = load_json_file(scene_script_file)
    series_title = first_text(payload.get("series_title"), recap_dir.parent.name, recap_dir.name)
    story_slug = safe_slug(first_text(payload.get("story_slug"), series_title))
    scene_script_markdown = optional_file(recap_dir / OPTIONAL_SCENE_SCRIPT_MD)
    assets_file = optional_file(recap_dir / "02_assets.json")
    image_config_file = optional_file(recap_dir / "03_image_config.json")
    return RecapBundle(
        recap_dir=recap_dir,
        run_root=run_root,
        scene_script_file=scene_script_file,
        scene_script_markdown=scene_script_markdown,
        assets_file=assets_file,
        image_config_file=image_config_file,
        anchor_prompts_file=None,
        video_prompts_file=None,
        narration_script_file=None,
        input_contract="recap-production",
        series_title=series_title,
        story_slug=story_slug,
        assets_lookup={},
        shots=load_shots(payload),
        selection_notes=tuple(notes),
    )


def load_cp_production_bundle(cp_dir: Path, run_root: Path | None) -> RecapBundle:
    notes = ["Detected cp-production input contract."]
    beat_sheet_file = require_existing_file(cp_dir / "02_beat_sheet.json", "02_beat_sheet.json")
    video_prompts_file = require_existing_file(cp_dir / "05_video_prompts.json", "05_video_prompts.json")
    asset_registry_file = optional_file(cp_dir / "03_asset_registry.json")
    anchor_prompts_file = optional_file(cp_dir / "04_anchor_prompts.json")
    narration_script_file = optional_file(cp_dir / "01_narration_script.txt")

    beat_sheet_payload = load_json_file(beat_sheet_file)
    video_prompts_payload = load_json_file(video_prompts_file)
    asset_registry_payload = load_json_file(asset_registry_file) if asset_registry_file else {}
    anchor_prompts_payload = load_json_file(anchor_prompts_file) if anchor_prompts_file else {}

    if asset_registry_file is not None:
        notes.append(f"Using asset registry: {asset_registry_file.name}")
    else:
        notes.append("03_asset_registry.json was not present; asset context will stay empty.")
    if anchor_prompts_file is not None:
        notes.append(f"Using anchor prompts: {anchor_prompts_file.name}")
    else:
        notes.append("04_anchor_prompts.json was not present; still-image setup will be inferred from the beat sheet only.")
    notes.append(f"Using beat sheet: {beat_sheet_file.name}")
    notes.append(f"Using video prompts: {video_prompts_file.name}")

    series_title = first_text(
        beat_sheet_payload.get("project_title"),
        video_prompts_payload.get("project_title"),
        asset_registry_payload.get("project_title"),
        cp_dir.name,
    )
    story_slug = safe_slug(first_text(beat_sheet_payload.get("story_slug"), video_prompts_payload.get("story_slug"), series_title))

    anchor_prompt_index = build_cp_anchor_prompt_index(anchor_prompts_payload)
    video_prompt_index = build_cp_video_prompt_index(video_prompts_payload)
    assets_lookup = build_cp_asset_lookup(asset_registry_payload)

    return RecapBundle(
        recap_dir=cp_dir,
        run_root=run_root,
        scene_script_file=beat_sheet_file,
        scene_script_markdown=None,
        assets_file=asset_registry_file,
        image_config_file=None,
        anchor_prompts_file=anchor_prompts_file,
        video_prompts_file=video_prompts_file,
        narration_script_file=narration_script_file,
        input_contract="cp-production",
        series_title=series_title,
        story_slug=story_slug,
        assets_lookup=assets_lookup,
        shots=load_cp_shots(
            beat_sheet_payload,
            anchor_prompt_index=anchor_prompt_index,
            video_prompt_index=video_prompt_index,
            assets_lookup=assets_lookup,
        ),
        selection_notes=tuple(notes),
    )


def resolve_recap_dir(input_path: str | Path) -> tuple[Path, Path | None]:
    candidate = Path(input_path).expanduser().resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"LTX input path does not exist: {candidate}")
    if candidate.is_file():
        if candidate.name == CANONICAL_SCENE_SCRIPT:
            return candidate.parent.resolve(), candidate.parent.parent.resolve()
        if candidate.name in CP_PRODUCTION_REQUIRED_FILES or candidate.name in CP_PRODUCTION_OPTIONAL_FILES:
            return candidate.parent.resolve(), candidate.parent.resolve()
        candidate = candidate.parent
    if candidate.name in RECAP_STAGE_DIRS:
        return candidate.resolve(), candidate.parent.resolve()
    if is_cp_production_dir(candidate):
        return candidate.resolve(), candidate.resolve()
    for stage_name in RECAP_STAGE_DIRS:
        stage_candidate = candidate / stage_name
        if stage_candidate.exists() and stage_candidate.is_dir():
            return stage_candidate.resolve(), candidate.resolve()
    raise ValueError(
        "Unsupported LTX input. Expected one of: the recap production folder itself, the story run folder that contains "
        f"`02_recap_production/` or `01_recap_production/`, the legacy `{CANONICAL_SCENE_SCRIPT}` file, or a "
        "cp-production output folder containing `02_beat_sheet.json` and `05_video_prompts.json` "
        "(optionally `03_asset_registry.json` and `04_anchor_prompts.json`)."
    )


def select_scene_script_file(recap_dir: Path) -> tuple[Path, list[str]]:
    notes: list[str] = []
    canonical = recap_dir / CANONICAL_SCENE_SCRIPT
    if canonical.exists() and canonical.is_file():
        notes.append(f"Selected canonical scene script: {canonical.name}")
        return canonical.resolve(), notes

    candidates = sorted(recap_dir.glob("*episode*scene*script*.json"), key=lambda path: path.name.casefold())
    if candidates:
        chosen = candidates[0].resolve()
        notes.append(f"Canonical scene script was missing; selected fallback JSON: {chosen.name}")
        if len(candidates) > 1:
            notes.append(f"Multiple scene-script candidates were found; chose the first sorted JSON file: {chosen.name}")
        return chosen, notes

    raise FileNotFoundError(
        f"Could not find `{CANONICAL_SCENE_SCRIPT}` or another matching scene-script JSON file in {recap_dir}"
    )


def load_shots(payload: dict[str, Any]) -> list[RecapShot]:
    episodes = payload.get("episodes")
    if not isinstance(episodes, list):
        raise ValueError("`episodes` in the episode scene script must be a JSON array.")
    shots: list[RecapShot] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        episode_number = coerce_int(episode.get("episode_number"), default=0)
        scene_beats = episode.get("scene_beats")
        if not isinstance(scene_beats, list):
            continue
        for index, beat in enumerate(scene_beats, start=1):
            if not isinstance(beat, dict):
                continue
            shot_id = first_text(beat.get("scene_id"), beat.get("shot_id"), f"ep{episode_number:02d}_s{index:02d}")
            shots.append(
                RecapShot(
                    shot_id=shot_id,
                    episode_number=episode_number,
                    summary=first_text(beat.get("summary")),
                    visual_prompt=first_text(beat.get("visual_prompt"), beat.get("prompt")),
                    shot_type=first_text(beat.get("shot_type")),
                    camera_motion=first_text(beat.get("camera_motion")),
                    mood=first_text(beat.get("mood")),
                    anchor_text=first_text(beat.get("anchor_text")),
                    priority=first_text(beat.get("priority")),
                    beat_role=first_text(beat.get("beat_role")),
                    pace_weight=first_text(beat.get("pace_weight")),
                    asset_focus=first_text(beat.get("asset_focus")),
                    source_contract="recap-production",
                    source_payload=beat,
                )
            )
    if not shots:
        raise ValueError("No scene beats were found in the episode scene script.")
    return shots


def load_cp_shots(
    payload: dict[str, Any],
    *,
    anchor_prompt_index: dict[str, dict[str, Any]],
    video_prompt_index: dict[str, dict[str, Any]],
    assets_lookup: dict[str, dict[str, str]],
) -> list[RecapShot]:
    raw_beats = payload.get("beats")
    if not isinstance(raw_beats, list):
        raise ValueError("`beats` in 02_beat_sheet.json must be a JSON array.")
    shots: list[RecapShot] = []
    for index, raw_beat in enumerate(raw_beats, start=1):
        if not isinstance(raw_beat, dict):
            continue
        beat_id = first_text(raw_beat.get("beat_id"), f"beat_{index:03d}")
        anchor_prompt = anchor_prompt_index.get(beat_id, {})
        video_prompt = video_prompt_index.get(beat_id, {})
        linked_assets = tuple(normalize_string_list(video_prompt.get("linked_assets") or anchor_prompt.get("linked_assets")))
        linked_asset_context = [assets_lookup[asset_id] for asset_id in linked_assets if asset_id in assets_lookup]
        shots.append(
            RecapShot(
                shot_id=beat_id,
                episode_number=infer_cp_episode_number(raw_beat, beat_id=beat_id, index=index),
                summary=first_text(raw_beat.get("summary")),
                visual_prompt=first_text(
                    anchor_prompt.get("anchor_image_prompt"),
                    build_cp_visual_prompt(raw_beat, anchor_prompt),
                ),
                shot_type=first_text(anchor_prompt.get("shot_size"), raw_beat.get("shot_type_suggestion")),
                camera_motion=first_text(video_prompt.get("camera_movement"), raw_beat.get("camera_movement_suggestion")),
                mood=first_text(video_prompt.get("pacing"), raw_beat.get("mood")),
                anchor_text=first_text(raw_beat.get("narration_anchor_line"), raw_beat.get("anchor_text")),
                priority=first_text(raw_beat.get("priority")),
                beat_role=first_text(raw_beat.get("story_function"), raw_beat.get("beat_role")),
                pace_weight=first_text(raw_beat.get("duration_class"), raw_beat.get("pace_weight")),
                asset_focus=infer_cp_asset_focus(raw_beat, anchor_prompt, video_prompt),
                video_prompt=first_text(video_prompt.get("video_prompt"), build_cp_motion_prompt(raw_beat, video_prompt)),
                anchor_prompt=first_text(anchor_prompt.get("anchor_image_prompt")),
                linked_assets=linked_assets,
                source_contract="cp-production",
                source_payload={
                    **raw_beat,
                    "cp_anchor_prompt": anchor_prompt,
                    "cp_video_prompt": video_prompt,
                    "cp_linked_asset_context": linked_asset_context,
                },
            )
        )
    if not shots:
        raise ValueError("No beats were found in 02_beat_sheet.json.")
    return shots


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a top-level JSON object in {path}")
    return payload


def require_existing_file(path: Path, label: str) -> Path:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Required LTX input file was not found: {label} at {path}")
    return path.resolve()


def optional_file(path: Path) -> Path | None:
    return path.resolve() if path.exists() and path.is_file() else None


def build_cp_anchor_prompt_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_prompts = payload.get("anchor_prompts")
    if raw_prompts is None:
        return {}
    if not isinstance(raw_prompts, list):
        raise ValueError("`anchor_prompts` in 04_anchor_prompts.json must be a JSON array.")
    index: dict[str, dict[str, Any]] = {}
    for raw_prompt in raw_prompts:
        if not isinstance(raw_prompt, dict):
            continue
        beat_id = first_text(raw_prompt.get("beat_id"))
        if beat_id:
            index[beat_id] = raw_prompt
    return index


def build_cp_video_prompt_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_prompts = payload.get("video_prompts")
    if not isinstance(raw_prompts, list):
        raise ValueError("`video_prompts` in 05_video_prompts.json must be a JSON array.")
    index: dict[str, dict[str, Any]] = {}
    for raw_prompt in raw_prompts:
        if not isinstance(raw_prompt, dict):
            continue
        beat_id = first_text(raw_prompt.get("beat_id"))
        if beat_id:
            index[beat_id] = raw_prompt
    return index


def build_cp_asset_lookup(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        return {}
    lookup: dict[str, dict[str, str]] = {}
    for raw_asset in raw_assets:
        if not isinstance(raw_asset, dict):
            continue
        asset_id = first_text(raw_asset.get("asset_id"))
        if not asset_id:
            continue
        lookup[asset_id] = {
            "asset_id": asset_id,
            "asset_type": first_text(raw_asset.get("asset_type")),
            "asset_name": first_text(raw_asset.get("asset_name"), raw_asset.get("name"), asset_id),
            "short_description": first_text(raw_asset.get("short_description"), raw_asset.get("description")),
            "consistency_notes": first_text(raw_asset.get("consistency_notes")),
        }
    return lookup


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


def build_cp_motion_prompt(raw_beat: dict[str, Any], video_prompt: dict[str, Any]) -> str:
    parts = [
        first_text(video_prompt.get("character_action")),
        first_text(video_prompt.get("environment_motion")),
        first_text(video_prompt.get("camera_movement")),
        first_text(raw_beat.get("summary")),
    ]
    return "。".join(part for part in parts if part).strip("。 ")


def infer_cp_episode_number(raw_beat: dict[str, Any], *, beat_id: str, index: int) -> int:
    for candidate in (raw_beat.get("chapter_id"), beat_id):
        match = re.search(r"(\d+)", str(candidate or ""))
        if match:
            return coerce_int(match.group(1), default=index)
    return index


def infer_cp_asset_focus(raw_beat: dict[str, Any], anchor_prompt: dict[str, Any], video_prompt: dict[str, Any]) -> str:
    shot_text = " ".join(
        first_text(value)
        for value in (
            anchor_prompt.get("shot_size"),
            raw_beat.get("shot_type_suggestion"),
            video_prompt.get("motion_focus"),
        )
    ).casefold()
    if "insert" in shot_text:
        return "object"
    if first_text(raw_beat.get("prop_focus")) and not first_text(raw_beat.get("subject_focus")):
        return "object"
    if first_text(raw_beat.get("scene_focus")) and not first_text(raw_beat.get("subject_focus")):
        return "environment"
    if any(token in shot_text for token in ("close-up", "close up", "reaction", "emotion")):
        return "character"
    return "interaction"


def is_cp_production_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and all((path / name).is_file() for name in CP_PRODUCTION_REQUIRED_FILES)


def generated_keyscene_candidates(
    recap_dir: Path,
    run_root: Path | None,
    *,
    preferred_dirs: list[Path] | None = None,
) -> list[Path]:
    candidates: list[Path] = []

    def add_candidate(path: Path | None) -> None:
        if path is None:
            return
        resolved = path.expanduser().resolve()
        if resolved not in candidates:
            candidates.append(resolved)

    for candidate in preferred_dirs or []:
        add_candidate(Path(candidate))
    add_candidate(recap_dir / "generated_keyscenes")
    add_candidate(recap_dir.parent / "generated_keyscenes")
    add_candidate(recap_dir / "06_keyscene_i2i")
    add_candidate(recap_dir.parent / "06_keyscene_i2i")
    for base in (recap_dir, run_root):
        if base is None:
            continue
        for folder_name in KEYSCENE_STAGE_DIRS:
            add_candidate(base / folder_name)
    return candidates


def candidate_shot_image_keys(shot: RecapShot) -> tuple[str, ...]:
    keys = {shot.shot_id}
    source_payload = shot.source_payload if isinstance(shot.source_payload, dict) else {}
    for key in ("scene_id", "beat_id", "shot_id"):
        value = first_text(source_payload.get(key))
        if value:
            keys.add(value)
    return tuple(sorted(keys))


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_slug(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in str(value or ""))
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return cleaned or "story"
