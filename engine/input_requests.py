from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .input_loader import InputLoadError, resolve_input_paths

RECAP_PRODUCTION_STAGE_FOLDERS = ("02_recap_production", "01_recap_production")
RECAP_BRIDGE_STAGE_FOLDERS = ("04_recap_to_comfy_bridge", "03_recap_to_comfy_bridge")
RECAP_ASSETS_STAGE_FOLDERS = ("05_assets_t2i", "04_assets_t2i")
RECAP_SCRIPT_FILENAME = "01_recap_script.txt"
RECAP_SCENE_SCRIPT_FILENAME = "04_episode_scene_script.json"
RECAP_ASSETS_FILENAME = "assets.json"
CP_BEAT_SHEET_FILENAME = "02_beat_sheet.json"
CP_ASSET_REGISTRY_FILENAME = "03_asset_registry.json"
CP_ANCHOR_PROMPTS_FILENAME = "04_anchor_prompts.json"
CP_VIDEO_PROMPTS_FILENAME = "05_video_prompts.json"


def resolve_skill_input_request(
    repo_root: Path,
    skill,
    *,
    raw_path: str | None = None,
    direct_text: str | None = None,
) -> tuple[Path, list[Path]]:
    text_input = str(direct_text or "").strip()
    if bool(getattr(skill, "allow_inline_text_input", False)) and text_input:
        return _create_inline_input_paths(repo_root, skill, text_input)

    raw_value = str(raw_path or "").strip()
    if bool(getattr(skill, "allow_inline_text_input", False)) and _should_treat_as_inline_text(raw_value):
        return _create_inline_input_paths(repo_root, skill, raw_value)

    if not raw_value:
        raise InputLoadError("Input path is empty.")

    input_root_path = Path(raw_value.strip().strip('"')).expanduser().resolve()
    special_case = _resolve_skill_specific_input_request(skill, input_root_path)
    if special_case is not None:
        return special_case
    preferred_single_input = _resolve_preferred_single_file(skill, input_root_path)
    if preferred_single_input is not None:
        return input_root_path, [preferred_single_input]
    return input_root_path, resolve_input_paths(
        str(input_root_path),
        skill.input_extensions,
        folder_mode=skill.folder_mode,
    )


def _should_treat_as_inline_text(raw_value: str) -> bool:
    stripped = raw_value.strip().strip('"')
    if not stripped:
        return False
    if any(separator in stripped for separator in ("\\", "/")):
        return False
    if Path(stripped).suffix:
        return False
    return True


def _create_inline_input_paths(repo_root: Path, skill, brief_text: str) -> tuple[Path, list[Path]]:
    skill_id = str(getattr(skill, "skill_id", getattr(skill, "name", "skill"))).strip().replace(" ", "_") or "skill"
    inline_inputs_dir = repo_root / "outputs" / ".internal" / "inline_inputs"
    inline_inputs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    input_path = inline_inputs_dir / f"{skill_id}__{timestamp}.txt"
    input_path.write_text(brief_text.strip() + "\n", encoding="utf-8")
    synthetic_root = repo_root / f"{skill_id}_inline_brief.txt"
    return synthetic_root, [input_path]


def _resolve_skill_specific_input_request(skill, input_root_path: Path) -> tuple[Path, list[Path]] | None:
    skill_id = _skill_id(skill)
    if skill_id == "recap_to_tts":
        return _resolve_recap_to_tts_input_request(input_root_path)
    if skill_id == "recap_to_comfy_bridge":
        return _resolve_recap_to_comfy_bridge_input_request(input_root_path)
    if skill_id == "recap_to_assets_zimage":
        return _resolve_recap_to_assets_zimage_input_request(input_root_path)
    if skill_id == "recap_to_keyscene_kontext":
        return _resolve_recap_to_keyscene_kontext_input_request(input_root_path)
    if skill_id == "flux-asset-and-scene-generation":
        return _resolve_flux_asset_and_scene_generation_input_request(input_root_path)
    if skill_id == "ltx-video-skill":
        return _resolve_ltx_video_skill_input_request(input_root_path)
    return None


def _resolve_recap_to_tts_input_request(input_root_path: Path) -> tuple[Path, list[Path]] | None:
    if not input_root_path.exists():
        raise InputLoadError(f"Input path does not exist: {input_root_path}")

    if input_root_path.is_file():
        if input_root_path.suffix.lower() == ".txt":
            return input_root_path, [input_root_path]
        raise InputLoadError(
            "Recap To TTS expects the `02_recap_production` folder or its "
            f"`{RECAP_SCRIPT_FILENAME}` file. "
            f"Received unsupported file: {input_root_path.name}"
        )

    if not input_root_path.is_dir():
        raise InputLoadError(f"Input path is neither a file nor a directory: {input_root_path}")

    stage_dir = _resolve_recap_stage_dir(input_root_path)
    if stage_dir is None:
        return None

    recap_script_path = stage_dir / RECAP_SCRIPT_FILENAME
    if not recap_script_path.exists() or not recap_script_path.is_file():
        raise InputLoadError(
            "Recap To TTS found the recap-production folder but it is missing "
            f"`{RECAP_SCRIPT_FILENAME}`: {recap_script_path}"
        )
    return input_root_path, [recap_script_path.resolve()]


def _resolve_recap_to_comfy_bridge_input_request(input_root_path: Path) -> tuple[Path, list[Path]] | None:
    if not input_root_path.exists():
        raise InputLoadError(f"Input path does not exist: {input_root_path}")

    if input_root_path.is_file():
        if input_root_path.name == RECAP_SCENE_SCRIPT_FILENAME:
            return input_root_path, [input_root_path]
        raise InputLoadError(
            "Recap To Comfy Bridge expects the `02_recap_production` folder or its "
            f"`{RECAP_SCENE_SCRIPT_FILENAME}` file. "
            f"Received unsupported file: {input_root_path.name}"
        )

    if not input_root_path.is_dir():
        raise InputLoadError(f"Input path is neither a file nor a directory: {input_root_path}")

    stage_dir = _resolve_recap_stage_dir(input_root_path)
    if stage_dir is None:
        raise InputLoadError(
            "Recap To Comfy Bridge expects either:\n"
            "- the `02_recap_production` stage folder\n"
            f"- or the file `02_recap_production/{RECAP_SCENE_SCRIPT_FILENAME}`\n"
            "- legacy `01_recap_production` folders are still accepted\n\n"
            f"Received unsupported directory: {input_root_path}"
        )

    scene_script_path = stage_dir / RECAP_SCENE_SCRIPT_FILENAME
    if not scene_script_path.exists() or not scene_script_path.is_file():
        raise InputLoadError(
            "The recap bundle is missing the required file "
            f"`{RECAP_SCENE_SCRIPT_FILENAME}`: {scene_script_path}"
        )
    return input_root_path, [scene_script_path.resolve()]


def _resolve_recap_stage_dir(input_root_path: Path) -> Path | None:
    if input_root_path.name in RECAP_PRODUCTION_STAGE_FOLDERS:
        return input_root_path

    for stage_folder in RECAP_PRODUCTION_STAGE_FOLDERS:
        child_stage_dir = input_root_path / stage_folder
        if child_stage_dir.exists() and child_stage_dir.is_dir():
            return child_stage_dir
    return None


def _resolve_flux_asset_and_scene_generation_input_request(input_root_path: Path) -> tuple[Path, list[Path]] | None:
    if not input_root_path.exists():
        raise InputLoadError(f"Input path does not exist: {input_root_path}")

    if input_root_path.is_file():
        if input_root_path.name in {
            RECAP_SCENE_SCRIPT_FILENAME,
            CP_BEAT_SHEET_FILENAME,
            CP_ASSET_REGISTRY_FILENAME,
            CP_ANCHOR_PROMPTS_FILENAME,
            CP_VIDEO_PROMPTS_FILENAME,
        }:
            return input_root_path, [input_root_path.resolve()]
        raise InputLoadError(
            "FLUX Asset and Scene Generation expects the recap production folder, the story run folder that contains it, "
            f"the file `{RECAP_SCENE_SCRIPT_FILENAME}`, or a cp-production JSON file such as `{CP_BEAT_SHEET_FILENAME}`. "
            f"Received unsupported file: {input_root_path.name}"
        )

    if not input_root_path.is_dir():
        raise InputLoadError(f"Input path is neither a file nor a directory: {input_root_path}")

    stage_dir = _resolve_recap_stage_dir(input_root_path)
    if stage_dir is None and _is_cp_production_dir(input_root_path):
        return input_root_path, [_preferred_cp_flux_input_file(input_root_path)]
    if stage_dir is None:
        raise InputLoadError(
            "FLUX Asset and Scene Generation expects either:\n"
            "- the `02_recap_production` stage folder\n"
            "- the legacy `01_recap_production` stage folder\n"
            f"- or the file `02_recap_production/{RECAP_SCENE_SCRIPT_FILENAME}`\n"
            f"- or a `cp-production` output folder containing `{CP_BEAT_SHEET_FILENAME}` plus `{CP_ANCHOR_PROMPTS_FILENAME}` "
            f"or `{CP_ASSET_REGISTRY_FILENAME}`\n\n"
            f"Received unsupported directory: {input_root_path}"
        )

    scene_script_path = stage_dir / RECAP_SCENE_SCRIPT_FILENAME
    if not scene_script_path.exists() or not scene_script_path.is_file():
        raise InputLoadError(
            "The recap bundle is missing the required file "
            f"`{RECAP_SCENE_SCRIPT_FILENAME}`: {scene_script_path}"
        )
    return input_root_path, [scene_script_path.resolve()]


def _resolve_ltx_video_skill_input_request(input_root_path: Path) -> tuple[Path, list[Path]] | None:
    if not input_root_path.exists():
        raise InputLoadError(f"Input path does not exist: {input_root_path}")

    if input_root_path.is_file():
        if input_root_path.name in {
            RECAP_SCENE_SCRIPT_FILENAME,
            CP_BEAT_SHEET_FILENAME,
            CP_ASSET_REGISTRY_FILENAME,
            CP_ANCHOR_PROMPTS_FILENAME,
            CP_VIDEO_PROMPTS_FILENAME,
        }:
            return input_root_path, [input_root_path.resolve()]
        raise InputLoadError(
            "LTX Video Skill expects the recap production folder, the story run folder that contains it, "
            f"the file `{RECAP_SCENE_SCRIPT_FILENAME}`, or a cp-production JSON file such as `{CP_BEAT_SHEET_FILENAME}`. "
            f"Received unsupported file: {input_root_path.name}"
        )

    if not input_root_path.is_dir():
        raise InputLoadError(f"Input path is neither a file nor a directory: {input_root_path}")

    stage_dir = _resolve_recap_stage_dir(input_root_path)
    if stage_dir is None and _is_cp_production_dir(input_root_path):
        return input_root_path, [_preferred_cp_ltx_input_file(input_root_path)]
    if stage_dir is None:
        raise InputLoadError(
            "LTX Video Skill expects either:\n"
            "- the `02_recap_production` stage folder\n"
            "- the legacy `01_recap_production` stage folder\n"
            f"- or the file `02_recap_production/{RECAP_SCENE_SCRIPT_FILENAME}`\n"
            f"- or a `cp-production` output folder containing `{CP_BEAT_SHEET_FILENAME}` and `{CP_VIDEO_PROMPTS_FILENAME}`\n\n"
            f"Received unsupported directory: {input_root_path}"
        )

    scene_script_path = stage_dir / RECAP_SCENE_SCRIPT_FILENAME
    if not scene_script_path.exists() or not scene_script_path.is_file():
        raise InputLoadError(
            "The recap bundle is missing the required file "
            f"`{RECAP_SCENE_SCRIPT_FILENAME}`: {scene_script_path}"
        )
    return input_root_path, [scene_script_path.resolve()]


def _resolve_recap_to_assets_zimage_input_request(input_root_path: Path) -> tuple[Path, list[Path]] | None:
    if not input_root_path.exists():
        raise InputLoadError(f"Input path does not exist: {input_root_path}")

    if input_root_path.is_file():
        if input_root_path.name == RECAP_ASSETS_FILENAME:
            return input_root_path, [input_root_path]
        raise InputLoadError(
            "Recap To Assets Z-Image expects the stage-04 bridge folder or its "
            f"`{RECAP_ASSETS_FILENAME}` file. "
            f"Received unsupported file: {input_root_path.name}"
        )

    if not input_root_path.is_dir():
        raise InputLoadError(f"Input path is neither a file nor a directory: {input_root_path}")

    bridge_dir = _resolve_bridge_stage_dir(input_root_path)
    if bridge_dir is None:
        return None

    assets_path = bridge_dir / RECAP_ASSETS_FILENAME
    if not assets_path.exists() or not assets_path.is_file():
        raise InputLoadError(
            "Recap To Assets Z-Image found the bridge folder but it is missing "
            f"`{RECAP_ASSETS_FILENAME}`: {assets_path}"
        )
    return input_root_path, [assets_path.resolve()]


def _resolve_bridge_stage_dir(input_root_path: Path) -> Path | None:
    if input_root_path.name in RECAP_BRIDGE_STAGE_FOLDERS:
        return input_root_path

    for stage_folder in RECAP_BRIDGE_STAGE_FOLDERS:
        child_stage_dir = input_root_path / stage_folder
        if child_stage_dir.exists() and child_stage_dir.is_dir():
            return child_stage_dir
    return None


def _resolve_recap_to_keyscene_kontext_input_request(input_root_path: Path) -> tuple[Path, list[Path]] | None:
    if not input_root_path.exists():
        raise InputLoadError(f"Input path does not exist: {input_root_path}")

    run_root = _infer_keyscene_run_root(input_root_path)
    if run_root is None:
        raise InputLoadError(
            "Recap To Keyscene Kontext expects the story run folder, "
            "`04_recap_to_comfy_bridge/`, `05_assets_t2i/`, an asset-group subfolder, "
            "or a file inside either stage. "
            f"Received unsupported path: {input_root_path}"
        )

    bridge_dir = _resolve_keyscene_stage_dir(run_root, RECAP_BRIDGE_STAGE_FOLDERS)
    storyboard_path = (bridge_dir or run_root / RECAP_BRIDGE_STAGE_FOLDERS[0]) / "videoarc_storyboard.json"
    _validate_keyscene_storyboard(storyboard_path)
    _validate_keyscene_sibling_assets(run_root)
    return input_root_path, [storyboard_path.resolve()]


def _validate_keyscene_storyboard(storyboard_path: Path) -> None:
    if not storyboard_path.exists() or not storyboard_path.is_file():
        raise InputLoadError(
            "Recap To Keyscene Kontext could not find the required bridge storyboard: "
            f"{storyboard_path}"
        )


def _validate_keyscene_sibling_assets(run_root: Path) -> None:
    assets_dir = _resolve_keyscene_stage_dir(run_root, RECAP_ASSETS_STAGE_FOLDERS) or run_root / RECAP_ASSETS_STAGE_FOLDERS[0]
    missing: list[str] = []
    for folder_name in ("characters", "scenes", "props"):
        candidate = assets_dir / folder_name
        if not candidate.exists() or not candidate.is_dir():
            missing.append(str(candidate.relative_to(run_root)) if _is_relative_to(candidate, run_root) else str(candidate))
    if missing:
        raise InputLoadError(
            "Recap To Keyscene Kontext requires generated T2I asset folders from stage 05. "
            f"Missing from {assets_dir}: {', '.join(missing)}"
        )


def _infer_keyscene_run_root(input_root_path: Path) -> Path | None:
    anchor = input_root_path if input_root_path.is_dir() else input_root_path.parent
    if anchor.name in ("characters", "scenes", "props") and anchor.parent.name in RECAP_ASSETS_STAGE_FOLDERS:
        return anchor.parent.parent.resolve()
    if anchor.name in RECAP_BRIDGE_STAGE_FOLDERS or anchor.name in RECAP_ASSETS_STAGE_FOLDERS:
        return anchor.parent.resolve()
    if input_root_path.is_dir():
        return input_root_path.resolve()
    return None


def _resolve_keyscene_stage_dir(run_root: Path, stage_folders: tuple[str, ...]) -> Path | None:
    for stage_folder in stage_folders:
        candidate = run_root / stage_folder
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _resolve_preferred_single_file(skill, input_root_path: Path) -> Path | None:
    if not input_root_path.is_dir():
        return None

    skill_id = _skill_id(skill)
    preferred_filename_by_skill = {
        "recap_to_assets_zimage": RECAP_ASSETS_FILENAME,
    }
    preferred_name = preferred_filename_by_skill.get(skill_id)
    if not preferred_name:
        return None

    candidate = input_root_path / preferred_name
    if candidate.exists() and candidate.is_file():
        return candidate.resolve()
    return None


def _is_cp_production_dir(input_root_path: Path) -> bool:
    if not input_root_path.exists() or not input_root_path.is_dir():
        return False
    return any(
        (input_root_path / filename).exists()
        for filename in (
            CP_BEAT_SHEET_FILENAME,
            CP_ASSET_REGISTRY_FILENAME,
            CP_ANCHOR_PROMPTS_FILENAME,
            CP_VIDEO_PROMPTS_FILENAME,
        )
    )


def _preferred_cp_flux_input_file(input_root_path: Path) -> Path:
    for filename in (
        CP_BEAT_SHEET_FILENAME,
        CP_ASSET_REGISTRY_FILENAME,
        CP_ANCHOR_PROMPTS_FILENAME,
        CP_VIDEO_PROMPTS_FILENAME,
    ):
        candidate = input_root_path / filename
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise InputLoadError(f"Could not resolve a cp-production input file from: {input_root_path}")


def _preferred_cp_ltx_input_file(input_root_path: Path) -> Path:
    for filename in (
        CP_BEAT_SHEET_FILENAME,
        CP_VIDEO_PROMPTS_FILENAME,
        CP_ANCHOR_PROMPTS_FILENAME,
        CP_ASSET_REGISTRY_FILENAME,
    ):
        candidate = input_root_path / filename
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise InputLoadError(f"Could not resolve a cp-production input file from: {input_root_path}")


def _skill_id(skill) -> str:
    return str(getattr(skill, "skill_id", getattr(skill, "name", ""))).strip()
