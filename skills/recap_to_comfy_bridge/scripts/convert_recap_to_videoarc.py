from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from engine.input_loader import read_text_with_fallbacks
from engine.writer import safe_stem, write_json_file


REQUIRED_SOURCE_FILES = (
    "02_assets.txt",
    "03_image_config.txt",
    "04_episode_scene_script.json",
)
SECTION_LABELS = {
    "角色": "characters",
    "场景": "scenes",
    "道具": "props",
}
ASSET_SUMMARY_PATTERNS = {
    "characters": re.compile(r"^\s*角色[:：]\s*(.+)\s*$"),
    "scenes": re.compile(r"^\s*场景[:：]\s*(.+)\s*$"),
    "props": re.compile(r"^\s*道具[:：]\s*(.+)\s*$"),
}
COMMA_SPLIT_RE = re.compile(r"[，,、]\s*")


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
    del repo_root, skill, step_number, runtime_values, state

    source_bundle = resolve_source_bundle(document.path)
    assets_text = read_text_with_fallbacks(source_bundle["assets"])
    image_config_text = read_text_with_fallbacks(source_bundle["image_config"])
    storyboard_payload = json.loads(read_text_with_fallbacks(source_bundle["scene_script_json"]))

    asset_summary = parse_asset_summary(assets_text)
    image_config = parse_image_config(image_config_text)
    asset_catalog = build_videoarc_assets_payload(
        source_bundle=source_bundle,
        asset_summary=asset_summary,
        image_config=image_config,
        storyboard_payload=storyboard_payload,
    )
    storyboard = build_videoarc_storyboard_payload(
        source_bundle=source_bundle,
        storyboard_payload=storyboard_payload,
        asset_catalog=asset_catalog,
    )
    summary = build_bridge_summary(
        source_bundle=source_bundle,
        asset_catalog=asset_catalog,
        storyboard=storyboard,
    )

    assets_path = write_json_file(output_dir, "videoarc_assets.json", asset_catalog)
    storyboard_path = write_json_file(output_dir, "videoarc_storyboard.json", storyboard)
    summary_path = write_json_file(output_dir, "bridge_summary.json", summary)

    return {
        "primary_output": summary_path,
        "output_files": {
            "primary": summary_path,
            "bridge_summary": summary_path,
            "videoarc_assets": assets_path,
            "videoarc_storyboard": storyboard_path,
        },
        "notes": [
            f"Source recap folder: {source_bundle['source_dir']}",
            f"Generated {assets_path.name}, {storyboard_path.name}, and {summary_path.name}.",
            f"Episodes: {summary['episode_count']} | Scene beats: {summary['scene_beat_count']}",
        ],
        "status": "completed",
    }


def resolve_source_bundle(input_path: Path) -> dict[str, Path]:
    candidate = input_path.resolve()
    if candidate.name != "04_episode_scene_script.json":
        raise ValueError(
            "This bridge skill expects the recap bundle's top-level "
            "`04_episode_scene_script.json` as the resolved input. "
            f"Received: {candidate.name}"
        )

    source_dir = candidate.parent
    resolved = {
        "source_dir": source_dir,
        "assets": source_dir / "02_assets.txt",
        "image_config": source_dir / "03_image_config.txt",
        "scene_script_json": source_dir / "04_episode_scene_script.json",
    }
    missing = [name for name, path in resolved.items() if name != "source_dir" and not path.exists()]
    if missing:
        missing_labels = ", ".join(sorted(missing))
        raise ValueError(
            "Required recap_production files are missing from "
            f"{source_dir}: {missing_labels}"
        )
    return resolved


def parse_asset_summary(text: str) -> dict[str, list[str]]:
    summary = {"characters": [], "scenes": [], "props": []}
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        for key, pattern in ASSET_SUMMARY_PATTERNS.items():
            match = pattern.match(line)
            if not match:
                continue
            summary[key] = [
                item.strip()
                for item in COMMA_SPLIT_RE.split(match.group(1).strip())
                if item.strip()
            ]
    return summary


def parse_image_config(text: str) -> dict[str, list[dict[str, Any]]]:
    normalized_lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    parsed = {"characters": [], "scenes": [], "props": []}
    current_section: str | None = None
    index = 0

    while index < len(normalized_lines):
        line = normalized_lines[index]
        if line in SECTION_LABELS:
            current_section = SECTION_LABELS[line]
            index += 1
            continue

        if current_section is None:
            index += 1
            continue

        if not re.fullmatch(r"\d+", line):
            index += 1
            continue

        order = int(line)
        index += 1
        if index >= len(normalized_lines):
            break
        name = normalized_lines[index]
        index += 1

        body_lines: list[str] = []
        while index < len(normalized_lines):
            candidate = normalized_lines[index]
            if candidate in SECTION_LABELS:
                break
            if re.fullmatch(r"\d+", candidate):
                break
            body_lines.append(candidate)
            index += 1

        parsed[current_section].append(parse_image_config_entry(current_section, order, name, body_lines))

    return parsed


def parse_image_config_entry(section: str, order: int, name: str, body_lines: list[str]) -> dict[str, Any]:
    prompt_fields: dict[str, str] = {}
    voice_label = ""
    voice_text = ""
    prompt_lines: list[str] = []

    index = 0
    while index < len(body_lines):
        line = body_lines[index]
        if line.endswith("音色") and index + 1 < len(body_lines):
            voice_label = line
            voice_text = body_lines[index + 1]
            index += 2
            continue

        key, value = split_field_line(line)
        if key is not None:
            prompt_fields[key] = value
        prompt_lines.append(line)
        index += 1

    prompt_text = "\n".join(prompt_lines).strip()
    return {
        "order": order,
        "name": name,
        "asset_id": f"{section[:-1]}_{safe_stem(name)}",
        "prompt_text": prompt_text,
        "prompt_fields": prompt_fields,
        "voice_label": voice_label,
        "voice_text": voice_text,
        "raw_lines": list(body_lines),
    }


def split_field_line(line: str) -> tuple[str | None, str]:
    match = re.match(r"^([^:：]+)[:：]\s*(.*)$", line)
    if not match:
        return None, line
    return match.group(1).strip(), match.group(2).strip()


def build_videoarc_assets_payload(
    *,
    source_bundle: dict[str, Path],
    asset_summary: dict[str, list[str]],
    image_config: dict[str, list[dict[str, Any]]],
    storyboard_payload: dict[str, Any],
) -> dict[str, Any]:
    ordered_characters = order_assets(image_config["characters"], asset_summary["characters"])
    ordered_scenes = order_assets(image_config["scenes"], asset_summary["scenes"])
    ordered_props = order_assets(image_config["props"], asset_summary["props"])

    style_hint = detect_style_hint(ordered_characters, ordered_scenes, ordered_props)
    series_title = str(storyboard_payload.get("series_title") or source_bundle["source_dir"].name)

    return {
        "schema": "videoarc_assets_v1",
        "bridge_source": "recap_production",
        "series_title": series_title,
        "source_folder": str(source_bundle["source_dir"]),
        "source_files": {
            "assets": str(source_bundle["assets"]),
            "image_config": str(source_bundle["image_config"]),
            "scene_script_json": str(source_bundle["scene_script_json"]),
        },
        "style_hint": style_hint,
        "counts": {
            "characters": len(ordered_characters),
            "scenes": len(ordered_scenes),
            "props": len(ordered_props),
        },
        "characters": [build_asset_record("character", entry) for entry in ordered_characters],
        "scenes": [build_asset_record("scene", entry) for entry in ordered_scenes],
        "props": [build_asset_record("prop", entry) for entry in ordered_props],
    }


def order_assets(entries: list[dict[str, Any]], summary_names: list[str]) -> list[dict[str, Any]]:
    if not summary_names:
        return sorted(entries, key=lambda item: (item.get("order", 0), str(item.get("name", "")).casefold()))

    indexed = {str(entry.get("name")): entry for entry in entries}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    for name in summary_names:
        entry = indexed.get(name)
        if entry is None:
            continue
        ordered.append(entry)
        seen.add(name)

    for entry in sorted(entries, key=lambda item: (item.get("order", 0), str(item.get("name", "")).casefold())):
        name = str(entry.get("name"))
        if name in seen:
            continue
        ordered.append(entry)
    return ordered


def detect_style_hint(*groups: list[dict[str, Any]]) -> str:
    for group in groups:
        for entry in group:
            style = entry.get("prompt_fields", {}).get("风格及光线", "")
            if style:
                return style
    return ""


def build_asset_record(kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    prompt_fields = dict(entry.get("prompt_fields", {}))
    return {
        "asset_id": entry.get("asset_id"),
        "name": entry.get("name"),
        "kind": kind,
        "order": entry.get("order"),
        "prompt": entry.get("prompt_text", ""),
        "style_lighting": prompt_fields.get("风格及光线", ""),
        "output_requirements": prompt_fields.get("输出要求", ""),
        "subject_content": prompt_fields.get("主体内容", ""),
        "core_feature": prompt_fields.get("核心特征", ""),
        "voice": entry.get("voice_text", ""),
        "source": {
            "type": "03_image_config.txt",
            "raw_lines": entry.get("raw_lines", []),
        },
    }


def build_videoarc_storyboard_payload(
    *,
    source_bundle: dict[str, Path],
    storyboard_payload: dict[str, Any],
    asset_catalog: dict[str, Any],
) -> dict[str, Any]:
    episodes = list(storyboard_payload.get("episodes") or [])
    asset_names = {
        "characters": [item["name"] for item in asset_catalog.get("characters", [])],
        "scenes": [item["name"] for item in asset_catalog.get("scenes", [])],
        "props": [item["name"] for item in asset_catalog.get("props", [])],
    }

    episode_payloads: list[dict[str, Any]] = []
    flat_shots: list[dict[str, Any]] = []
    total_shots = 0
    for episode in episodes:
        episode_number = int(episode.get("episode_number") or 0)
        shots: list[dict[str, Any]] = []
        for index, beat in enumerate(list(episode.get("scene_beats") or []), start=1):
            shot = build_storyboard_shot(episode_number, index, beat, asset_names)
            shots.append(shot)
            flat_shots.append(shot)
        total_shots += len(shots)
        episode_payloads.append(
            {
                "episode_number": episode_number,
                "shot_count": len(shots),
                "shots": shots,
            }
        )

    return {
        "schema": "videoarc_storyboard_v1",
        "bridge_source": "recap_production",
        "series_title": str(storyboard_payload.get("series_title") or source_bundle["source_dir"].name),
        "source_folder": str(source_bundle["source_dir"]),
        "source_scene_script_json": str(source_bundle["scene_script_json"]),
        "episode_count": len(episode_payloads),
        "scene_beat_count": total_shots,
        "episodes": episode_payloads,
        "storyboard_shots": flat_shots,
    }


def build_storyboard_shot(
    episode_number: int,
    index: int,
    beat: dict[str, Any],
    asset_names: dict[str, list[str]],
) -> dict[str, Any]:
    shot_id = str(beat.get("scene_id") or f"ep{episode_number:02d}_s{index:02d}")
    prompt = str(beat.get("visual_prompt") or "").strip()
    summary = str(beat.get("summary") or "").strip()
    anchor_text = str(beat.get("anchor_text") or "").strip()
    mood = str(beat.get("mood") or "").strip()
    shot_type = str(beat.get("shot_type") or "").strip()
    camera_motion = str(beat.get("camera_motion") or "").strip()
    priority = str(beat.get("priority") or "").strip()
    beat_role = str(beat.get("beat_role") or "").strip()
    pace_weight = str(beat.get("pace_weight") or "").strip()
    asset_focus = str(beat.get("asset_focus") or "").strip()
    asset_hints = infer_asset_hints(
        beat_text="\n".join(part for part in (summary, prompt, anchor_text) if part),
        asset_names=asset_names,
        asset_focus=asset_focus,
    )

    return {
        "shot_id": shot_id,
        "source_scene_id": shot_id,
        "episode_number": episode_number,
        "description": summary,
        "prompt": prompt,
        "anchor_text": anchor_text,
        "camera": {
            "shot_type": shot_type,
            "camera_motion": camera_motion,
        },
        "mood": mood,
        "priority": priority,
        "beat_role": beat_role,
        "pace_weight": pace_weight,
        "asset_focus": asset_focus,
        "asset_hints": asset_hints,
    }


def infer_asset_hints(
    *,
    beat_text: str,
    asset_names: dict[str, list[str]],
    asset_focus: str,
) -> dict[str, Any]:
    matched = {
        "characters": [],
        "scenes": [],
        "props": [],
    }
    for category, names in asset_names.items():
        for name in names:
            if name and name in beat_text:
                matched[category].append(name)

    return {
        "characters": dedupe_preserve_order(matched["characters"]),
        "scenes": dedupe_preserve_order(matched["scenes"]),
        "props": dedupe_preserve_order(matched["props"]),
        "primary_focus": asset_focus,
    }


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    return ordered


def build_bridge_summary(
    *,
    source_bundle: dict[str, Path],
    asset_catalog: dict[str, Any],
    storyboard: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "videoarc_bridge_summary_v1",
        "bridge_skill": "recap_to_comfy_bridge",
        "source_folder": str(source_bundle["source_dir"]),
        "files_found": {
            "02_assets.txt": str(source_bundle["assets"]),
            "03_image_config.txt": str(source_bundle["image_config"]),
            "04_episode_scene_script.json": str(source_bundle["scene_script_json"]),
        },
        "files_generated": [
            "videoarc_assets.json",
            "videoarc_storyboard.json",
            "bridge_summary.json",
        ],
        "series_title": storyboard.get("series_title", ""),
        "episode_count": storyboard.get("episode_count", 0),
        "scene_beat_count": storyboard.get("scene_beat_count", 0),
        "asset_counts": dict(asset_catalog.get("counts", {})),
    }
