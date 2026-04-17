from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .output_paths import resolve_story_title_from_path, story_slug_from_title
from .writer import safe_stem


SECTION_HEADERS = {
    "## 角色资产详情": "characters",
    "## 场景资产详情": "scenes",
    "## 道具资产详情": "props",
}
IMAGE_CONFIG_SECTION_LABELS = {
    "角色": "characters",
    "场景": "scenes",
    "道具": "props",
}
ASSET_TYPE_BY_GROUP = {
    "characters": "character",
    "scenes": "scene",
    "props": "prop",
}
ASPECT_BY_GROUP = {
    "characters": "portrait",
    "scenes": "landscape",
    "props": "square",
}
STYLE_PRESET_MAP = {
    "写实": "写实",
    "2D": "2D",
    "3D": "3D",
}
BAD_ASSET_LAYOUT_PATTERNS = (
    r"头部正面特写布局在左边[，,、\s]*",
    r"正面/侧面/背面全身三视图布局在右边[，,、\s]*",
    r"全部集中在一张图片输出",
    r"全部集中在一张图输出",
    r"集中放在同一张图输出",
    r"2-4不同角度展示并标注好角度[，,、\s]*",
    r"正面和背面两个角度展示并标注好角度[，,、\s]*",
    r"标注好角度",
    r"标注角度",
    r"三视图",
    r"多视图",
    r"多角度",
    r"同一张图",
    r"拼贴",
    r"分格",
    r"转面图",
    r"转身图",
    r"角色设定图",
    r"character\s+sheet",
    r"model\s+sheet",
    r"turnaround\s+sheet",
    r"contact[-\s]+sheet",
    r"multi[-\s]+angle",
    r"multi[-\s]+view",
    r"three[-\s]+view",
    r"split\s+panels?",
    r"collage",
    r"inset\s+poses?",
    r"labeled\s+angles?",
)

RECAP_STRUCTURED_STEP_NUMBERS = {2, 3}

ASSETS_STEP_SCHEMA = {
    "series_title": "string",
    "planned_episode_count": 1,
    "characters": [
        {
            "name": "string",
            "role": "string or null",
            "description": "string",
            "core_feature": "string",
            "style_lighting": "string",
            "output_requirements": "string",
            "subject_content": "string",
            "visual_prompt": "string",
            "voice": {
                "label": "string",
                "text": "string",
                "seed": 123456,
            },
            "personality_traits": [
                {
                    "trait": "string",
                    "description": "string",
                }
            ],
        }
    ],
    "scenes": [
        {
            "name": "string",
            "description": "string",
            "style_lighting": "string",
            "output_requirements": "string",
            "subject_content": "string",
            "visual_prompt": "string",
        }
    ],
    "props": [
        {
            "name": "string",
            "description": "string",
            "style_lighting": "string",
            "output_requirements": "string",
            "subject_content": "string",
            "visual_prompt": "string",
        }
    ],
}

IMAGE_CONFIG_GUIDANCE_SCHEMA = {
    "global_style": {
        "visual_style": "string",
        "lighting": "string",
        "color_palette": "string or null",
        "camera_language": "string or null",
        "consistency_rules": ["string"],
    },
    "asset_generation": {
        "characters": {"notes": "string"},
        "scenes": {"notes": "string"},
        "props": {"notes": "string"},
    },
}


def build_recap_step_json_payload(
    *,
    step_number: int,
    output_text: str,
    document_path: Path,
    output_dir: Path,
    runtime_inputs: dict[str, Any],
    extracted_payload: Any | None = None,
) -> Any:
    story_title = resolve_story_title_from_path(output_dir) or resolve_story_title_from_path(document_path)
    if not story_title:
        story_title = safe_stem(document_path.stem)
    story_slug = story_slug_from_title(story_title)

    if step_number == 2:
        return build_assets_payload(
            output_text,
            series_title=story_title,
            story_slug=story_slug,
            runtime_inputs=runtime_inputs,
        )
    if step_number == 3:
        return build_image_config_payload(
            output_text,
            series_title=story_title,
            story_slug=story_slug,
            runtime_inputs=runtime_inputs,
        )
    if step_number == 4:
        if not isinstance(extracted_payload, dict):
            return extracted_payload
        normalized = dict(extracted_payload)
        normalized["schema"] = "recap_episode_scene_script_v1"
        normalized["series_title"] = story_title
        normalized["story_slug"] = story_slug
        episodes = normalized.get("episodes")
        if isinstance(episodes, list):
            normalized["episodes"] = [
                _normalize_scene_episode(episode, episode_index=index)
                for index, episode in enumerate(episodes, start=1)
            ]
        return normalized
    raise ValueError(f"Unsupported recap_production step for JSON payload generation: {step_number}")


def uses_structured_recap_step_generation(skill_name: str, step_number: int) -> bool:
    return skill_name == "recap_production" and step_number in RECAP_STRUCTURED_STEP_NUMBERS


def recap_structured_step_schema(step_number: int) -> dict[str, Any]:
    if step_number == 2:
        return deepcopy(ASSETS_STEP_SCHEMA)
    if step_number == 3:
        return deepcopy(IMAGE_CONFIG_GUIDANCE_SCHEMA)
    raise ValueError(f"Unsupported recap structured step schema request: {step_number}")


def recap_structured_step_objective(step_number: int, runtime_inputs: dict[str, Any]) -> str:
    style = str(runtime_inputs.get("style") or "").strip()
    if step_number == 2:
        style_line = f"Use the already-confirmed style preset '{style}'." if style else "Use the provided runtime style if available."
        return (
            "Extract the recap's reusable image-generation assets as populated structured data. "
            f"{style_line} Do not ask the user to reconfirm style, do not ask follow-up questions, and do not return a questionnaire. "
            "Return complete characters, scenes, and props with actual content when the recap script supports them."
        )
    if step_number == 3:
        return (
            "Review the structured asset catalog and return only image-config guidance metadata. "
            "Do not duplicate the full asset item list in the response; that will be derived deterministically from the structured assets. "
            "Return non-empty global style values and useful per-group notes when the asset catalog supports them."
        )
    raise ValueError(f"Unsupported recap structured step objective request: {step_number}")


def normalize_recap_structured_step_payload(
    *,
    step_number: int,
    raw_payload: dict[str, Any],
    document_path: Path,
    output_dir: Path,
    runtime_inputs: dict[str, Any],
    structured_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    story_title = resolve_story_title_from_path(output_dir) or resolve_story_title_from_path(document_path)
    if not story_title:
        story_title = safe_stem(document_path.stem)
    story_slug = story_slug_from_title(story_title)

    if step_number == 2:
        return normalize_assets_payload(
            raw_payload,
            series_title=story_title,
            story_slug=story_slug,
            runtime_inputs=runtime_inputs,
        )
    if step_number == 3:
        assets_payload = _coerce_assets_payload_from_structured_inputs(
            structured_inputs,
            series_title=story_title,
            story_slug=story_slug,
            runtime_inputs=runtime_inputs,
        )
        return build_image_config_from_assets_payload(
            assets_payload,
            series_title=story_title,
            story_slug=story_slug,
            runtime_inputs=runtime_inputs,
            guidance_payload=raw_payload,
        )
    raise ValueError(f"Unsupported recap structured step normalization request: {step_number}")


def render_recap_step_text(step_number: int, payload: dict[str, Any]) -> str:
    if step_number == 2:
        return render_assets_text(payload)
    if step_number == 3:
        return render_image_config_text(payload)
    raise ValueError(f"Unsupported recap structured step render request: {step_number}")


def build_assets_payload(
    text: str,
    *,
    series_title: str,
    story_slug: str,
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    summary = parse_asset_summary(text)
    details = parse_asset_details(text)
    style_preset = _resolve_style_preset(runtime_inputs, details)
    planned_episode_count = _coerce_int(runtime_inputs.get("episode_count"))

    payload = {
        "schema": "recap_assets_v1",
        "series_title": series_title,
        "story_slug": story_slug,
        "asset_scope": "series",
        "planned_episode_count": planned_episode_count,
        "style_preset": style_preset,
        "summary": {
            "characters": [item["name"] for item in details["characters"]],
            "scenes": [item["name"] for item in details["scenes"]],
            "props": [item["name"] for item in details["props"]],
        },
        "counts": {
            "characters": len(details["characters"]),
            "scenes": len(details["scenes"]),
            "props": len(details["props"]),
        },
        "characters": details["characters"],
        "scenes": details["scenes"],
        "props": details["props"],
        "source_summary": summary,
    }
    return payload


def normalize_assets_payload(
    raw_payload: dict[str, Any],
    *,
    series_title: str,
    story_slug: str,
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    source_summary = _extract_summary_from_raw_assets(raw_payload)
    style_preset = _resolve_style_preset(runtime_inputs, raw_payload)
    planned_episode_count = _coerce_int(
        raw_payload.get("planned_episode_count") if isinstance(raw_payload, dict) else None
    ) or _coerce_int(runtime_inputs.get("episode_count"))

    characters = _normalize_asset_group("characters", raw_payload, style_preset=style_preset)
    scenes = _normalize_asset_group("scenes", raw_payload, style_preset=style_preset)
    props = _normalize_asset_group("props", raw_payload, style_preset=style_preset)

    return {
        "schema": "recap_assets_v1",
        "series_title": series_title,
        "story_slug": story_slug,
        "asset_scope": "series",
        "planned_episode_count": planned_episode_count,
        "style_preset": style_preset,
        "summary": {
            "characters": [item["name"] for item in characters],
            "scenes": [item["name"] for item in scenes],
            "props": [item["name"] for item in props],
        },
        "counts": {
            "characters": len(characters),
            "scenes": len(scenes),
            "props": len(props),
        },
        "characters": characters,
        "scenes": scenes,
        "props": props,
        "source_summary": source_summary,
    }


def build_image_config_payload(
    text: str,
    *,
    series_title: str,
    story_slug: str,
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    parsed = parse_image_config_text(text)
    style_preset = _resolve_style_preset(runtime_inputs, parsed)

    character_style = _first_non_empty(parsed["characters"], "prompt_fields", "风格及光线")
    scene_style = _first_non_empty(parsed["scenes"], "prompt_fields", "风格及光线")
    prop_style = _first_non_empty(parsed["props"], "prompt_fields", "风格及光线")
    visual_style, lighting = _split_style_line(character_style or scene_style or prop_style or "")

    payload = {
        "schema": "recap_image_config_v1",
        "series_title": series_title,
        "story_slug": story_slug,
        "global_style": {
            "style_preset": style_preset,
            "visual_style": visual_style,
            "lighting": lighting,
            "color_palette": None,
            "camera_language": None,
            "consistency_rules": [],
        },
        "asset_generation": {
            "characters": {
                "default_aspect": ASPECT_BY_GROUP["characters"],
                "notes": _common_output_requirements(parsed["characters"]),
                "items": parsed["characters"],
            },
            "scenes": {
                "default_aspect": ASPECT_BY_GROUP["scenes"],
                "notes": _common_output_requirements(parsed["scenes"]),
                "items": parsed["scenes"],
            },
            "props": {
                "default_aspect": ASPECT_BY_GROUP["props"],
                "notes": _common_output_requirements(parsed["props"]),
                "items": parsed["props"],
            },
        },
    }
    return payload


def build_image_config_from_assets_payload(
    assets_payload: dict[str, Any],
    *,
    series_title: str,
    story_slug: str,
    runtime_inputs: dict[str, Any],
    guidance_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    style_preset = _resolve_style_preset(runtime_inputs, assets_payload)
    guidance_payload = dict(guidance_payload or {})
    base_groups = {
        "characters": [
            _image_config_item_from_asset("characters", item, index=index)
            for index, item in enumerate(list(assets_payload.get("characters") or []), start=1)
        ],
        "scenes": [
            _image_config_item_from_asset("scenes", item, index=index)
            for index, item in enumerate(list(assets_payload.get("scenes") or []), start=1)
        ],
        "props": [
            _image_config_item_from_asset("props", item, index=index)
            for index, item in enumerate(list(assets_payload.get("props") or []), start=1)
        ],
    }

    global_style_payload = guidance_payload.get("global_style") if isinstance(guidance_payload, dict) else {}
    if not isinstance(global_style_payload, dict):
        global_style_payload = {}

    style_source = (
        str(global_style_payload.get("visual_style") or "").strip(),
        str(global_style_payload.get("lighting") or "").strip(),
    )
    if not any(style_source):
        visual_style, lighting = _split_style_line(
            _first_non_empty(base_groups["characters"], "prompt_fields", "风格及光线")
            or _first_non_empty(base_groups["scenes"], "prompt_fields", "风格及光线")
            or _first_non_empty(base_groups["props"], "prompt_fields", "风格及光线")
            or ""
        )
    else:
        visual_style, lighting = style_source

    asset_generation_guidance = guidance_payload.get("asset_generation") if isinstance(guidance_payload, dict) else {}
    if not isinstance(asset_generation_guidance, dict):
        asset_generation_guidance = {}

    payload = {
        "schema": "recap_image_config_v1",
        "series_title": series_title,
        "story_slug": story_slug,
        "global_style": {
            "style_preset": style_preset,
            "visual_style": visual_style or None,
            "lighting": lighting or None,
            "color_palette": _optional_text(global_style_payload.get("color_palette")),
            "camera_language": _optional_text(global_style_payload.get("camera_language")),
            "consistency_rules": _normalize_consistency_rules(global_style_payload.get("consistency_rules")),
        },
        "asset_generation": {},
    }

    for group_name, items in base_groups.items():
        group_guidance = asset_generation_guidance.get(group_name) if isinstance(asset_generation_guidance, dict) else {}
        if not isinstance(group_guidance, dict):
            group_guidance = {}
        payload["asset_generation"][group_name] = {
            "default_aspect": ASPECT_BY_GROUP[group_name],
            "notes": _optional_text(group_guidance.get("notes")) or _common_output_requirements(items),
            "items": items,
        }
    return payload


def normalize_image_config_guidance_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    global_style = raw_payload.get("global_style") if isinstance(raw_payload, dict) else {}
    if not isinstance(global_style, dict):
        global_style = {}
    asset_generation = raw_payload.get("asset_generation") if isinstance(raw_payload, dict) else {}
    if not isinstance(asset_generation, dict):
        asset_generation = {}

    return {
        "global_style": {
            "visual_style": _optional_text(global_style.get("visual_style")),
            "lighting": _optional_text(global_style.get("lighting")),
            "color_palette": _optional_text(global_style.get("color_palette")),
            "camera_language": _optional_text(global_style.get("camera_language")),
            "consistency_rules": _normalize_consistency_rules(global_style.get("consistency_rules")),
        },
        "asset_generation": {
            "characters": {"notes": _optional_text((asset_generation.get("characters") or {}).get("notes"))},
            "scenes": {"notes": _optional_text((asset_generation.get("scenes") or {}).get("notes"))},
            "props": {"notes": _optional_text((asset_generation.get("props") or {}).get("notes"))},
        },
    }


def parse_asset_summary(text: str) -> dict[str, list[str]]:
    summary = {"characters": [], "scenes": [], "props": []}
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        key = None
        if line.startswith("角色："):
            key = "characters"
        elif line.startswith("场景："):
            key = "scenes"
        elif line.startswith("道具："):
            key = "props"
        if key is None:
            continue
        values = [item.strip() for item in re.split(r"[，,、]\s*", line.split("：", 1)[1]) if item.strip()]
        summary[key] = values
    return summary


def parse_asset_details(text: str) -> dict[str, list[dict[str, Any]]]:
    normalized = text.replace("\r\n", "\n")
    current_group: str | None = None
    group_lines: dict[str, list[str]] = {key: [] for key in ASSET_TYPE_BY_GROUP}

    for line in normalized.split("\n"):
        stripped = line.strip()
        if stripped in SECTION_HEADERS:
            current_group = SECTION_HEADERS[stripped]
            continue
        if stripped.startswith("---"):
            current_group = None
            continue
        if current_group is not None:
            group_lines[current_group].append(line)

    parsed: dict[str, list[dict[str, Any]]] = {key: [] for key in ASSET_TYPE_BY_GROUP}
    for group_name, lines in group_lines.items():
        blocks = _split_markdown_blocks(lines)
        for index, block in enumerate(blocks, start=1):
            parsed[group_name].append(_parse_asset_detail_block(group_name, index, block))
    return parsed


def parse_image_config_text(text: str) -> dict[str, list[dict[str, Any]]]:
    normalized_lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    parsed = {"characters": [], "scenes": [], "props": []}
    current_section: str | None = None
    index = 0

    while index < len(normalized_lines):
        line = normalized_lines[index]
        if line in IMAGE_CONFIG_SECTION_LABELS:
            current_section = IMAGE_CONFIG_SECTION_LABELS[line]
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
            if candidate in IMAGE_CONFIG_SECTION_LABELS:
                break
            if re.fullmatch(r"\d+", candidate):
                break
            body_lines.append(candidate)
            index += 1

        parsed[current_section].append(_parse_image_config_entry(current_section, order, name, body_lines))

    return parsed


def image_config_payload_to_bridge_entries(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    generation = payload.get("asset_generation")
    if not isinstance(generation, dict):
        raise ValueError("image_config.json is missing 'asset_generation'.")
    result = {"characters": [], "scenes": [], "props": []}
    for group_name in result:
        group_payload = generation.get(group_name) or {}
        items = group_payload.get("items") or []
        if not isinstance(items, list):
            raise ValueError(f"image_config.json group '{group_name}' has invalid 'items'.")
        result[group_name] = [dict(item) for item in items if isinstance(item, dict)]
    return result


def assets_payload_to_bridge_summary(payload: dict[str, Any]) -> dict[str, list[str]]:
    summary = payload.get("summary")
    if isinstance(summary, dict):
        return {
            "characters": [str(item).strip() for item in summary.get("characters", []) if str(item).strip()],
            "scenes": [str(item).strip() for item in summary.get("scenes", []) if str(item).strip()],
            "props": [str(item).strip() for item in summary.get("props", []) if str(item).strip()],
        }
    return {
        "characters": [str(item.get("name", "")).strip() for item in payload.get("characters", []) if isinstance(item, dict) and str(item.get("name", "")).strip()],
        "scenes": [str(item.get("name", "")).strip() for item in payload.get("scenes", []) if isinstance(item, dict) and str(item.get("name", "")).strip()],
        "props": [str(item.get("name", "")).strip() for item in payload.get("props", []) if isinstance(item, dict) and str(item.get("name", "")).strip()],
    }


def render_assets_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    lines.append(f"角色：{_render_summary_names(summary.get('characters'))}")
    lines.append(f"场景：{_render_summary_names(summary.get('scenes'))}")
    lines.append(f"道具：{_render_summary_names(summary.get('props'))}")

    section_map = (
        ("## 角色资产详情", "characters"),
        ("## 场景资产详情", "scenes"),
        ("## 道具资产详情", "props"),
    )
    for header, group_name in section_map:
        items = payload.get(group_name) or []
        if not isinstance(items, list) or not items:
            continue
        lines.append("")
        lines.append(header)
        for item in items:
            if not isinstance(item, dict):
                continue
            lines.extend(_render_asset_detail_block(group_name, item))
            lines.append("")

    while lines and not str(lines[-1]).strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def render_image_config_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    generation = payload.get("asset_generation") if isinstance(payload, dict) else {}
    if not isinstance(generation, dict):
        generation = {}

    for label, group_name in (("角色", "characters"), ("场景", "scenes"), ("道具", "props")):
        group = generation.get(group_name) or {}
        items = group.get("items") if isinstance(group, dict) else []
        if not isinstance(items, list) or not items:
            continue
        if lines:
            lines.append("")
        lines.append(label)
        for item in items:
            if not isinstance(item, dict):
                continue
            lines.extend(_render_image_config_item(group_name, item))
    while lines and not str(lines[-1]).strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def _normalize_scene_episode(raw_episode: Any, *, episode_index: int) -> dict[str, Any]:
    episode = dict(raw_episode) if isinstance(raw_episode, dict) else {}
    episode_number = _coerce_int(episode.get("episode_number")) or episode_index
    beats = episode.get("scene_beats")
    normalized_beats: list[dict[str, Any]] = []
    if isinstance(beats, list):
        for beat_index, raw_beat in enumerate(beats, start=1):
            beat = dict(raw_beat) if isinstance(raw_beat, dict) else {}
            beat.setdefault("scene_id", f"ep{episode_number:02d}_s{beat_index:02d}")
            normalized_beats.append(beat)
    episode["episode_number"] = episode_number
    episode["scene_beats"] = normalized_beats
    return episode


def _coerce_assets_payload_from_structured_inputs(
    structured_inputs: dict[str, Any] | None,
    *,
    series_title: str,
    story_slug: str,
    runtime_inputs: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(structured_inputs, dict) and structured_inputs:
        if structured_inputs.get("schema") == "recap_assets_v1":
            return dict(structured_inputs)
        return normalize_assets_payload(
            structured_inputs,
            series_title=series_title,
            story_slug=story_slug,
            runtime_inputs=runtime_inputs,
        )
    return {
        "schema": "recap_assets_v1",
        "series_title": series_title,
        "story_slug": story_slug,
        "asset_scope": "series",
        "planned_episode_count": _coerce_int(runtime_inputs.get("episode_count")),
        "style_preset": _resolve_style_preset(runtime_inputs, {}),
        "summary": {"characters": [], "scenes": [], "props": []},
        "counts": {"characters": 0, "scenes": 0, "props": 0},
        "characters": [],
        "scenes": [],
        "props": [],
        "source_summary": {"characters": [], "scenes": [], "props": []},
    }


def _split_markdown_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("### "):
            if current:
                blocks.append(current)
            current = [stripped[4:].strip()]
            continue
        if current:
            current.append(raw_line)
    if current:
        blocks.append(current)
    return blocks


def _extract_summary_from_raw_assets(raw_payload: dict[str, Any]) -> dict[str, list[str]]:
    summary = raw_payload.get("summary") if isinstance(raw_payload, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    assets = raw_payload.get("assets") if isinstance(raw_payload, dict) else {}
    if not isinstance(assets, dict):
        assets = {}
    result: dict[str, list[str]] = {}
    for group_name in ASSET_TYPE_BY_GROUP:
        names = summary.get(group_name)
        if isinstance(names, list):
            result[group_name] = [str(item).strip() for item in names if str(item).strip()]
            continue
        items = assets.get(group_name) if group_name in assets else raw_payload.get(group_name)
        normalized_items = items if isinstance(items, list) else []
        result[group_name] = [
            str(item.get("name") or item.get("asset_name") or "").strip()
            for item in normalized_items
            if isinstance(item, dict) and str(item.get("name") or item.get("asset_name") or "").strip()
        ]
    return result


def _normalize_asset_group(group_name: str, raw_payload: dict[str, Any], *, style_preset: str | None) -> list[dict[str, Any]]:
    assets = raw_payload.get("assets") if isinstance(raw_payload, dict) else {}
    if not isinstance(assets, dict):
        assets = {}
    raw_items = assets.get(group_name) if group_name in assets else raw_payload.get(group_name)
    if not isinstance(raw_items, list):
        raw_items = []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        entry = _normalize_asset_entry(group_name, index, item, style_preset=style_preset)
        if entry is not None:
            normalized.append(entry)
    return normalized


def _normalize_asset_entry(
    group_name: str,
    order: int,
    raw_item: dict[str, Any],
    *,
    style_preset: str | None,
) -> dict[str, Any] | None:
    name = _optional_text(raw_item.get("name") or raw_item.get("asset_name"))
    if not name:
        return None

    asset_type = ASSET_TYPE_BY_GROUP[group_name]
    prompt_fields = _normalize_prompt_fields(
        raw_item.get("prompt_fields"),
        core_feature=raw_item.get("core_feature"),
        style_lighting=raw_item.get("style_lighting"),
        output_requirements=raw_item.get("output_requirements"),
        subject_content=raw_item.get("subject_content"),
        visual_prompt=raw_item.get("visual_prompt"),
        style_preset=style_preset,
    )
    visual_prompt = _compose_visual_prompt_from_fields(prompt_fields)
    description = _optional_text(raw_item.get("description")) or prompt_fields.get("主体内容", "")

    entry: dict[str, Any] = {
        "order": order,
        "asset_id": _optional_text(raw_item.get("asset_id")) or f"{asset_type}_{safe_stem(name)}",
        "name": name,
        "asset_type": asset_type,
        "description": description,
        "visual_prompt": visual_prompt,
        "prompt_fields": prompt_fields,
        "core_feature": prompt_fields.get("核心特征", ""),
        "style_lighting": prompt_fields.get("风格及光线", ""),
        "output_requirements": prompt_fields.get("输出要求", ""),
        "subject_content": prompt_fields.get("主体内容", ""),
    }

    if group_name == "characters":
        entry["role"] = _optional_text(raw_item.get("role"))
        entry["voice"] = _normalize_voice_payload(raw_item.get("voice"), name)
        entry["personality_traits"] = _normalize_personality_traits(raw_item.get("personality_traits"))
    return entry


def _normalize_prompt_fields(
    raw_prompt_fields: Any,
    *,
    core_feature: Any = None,
    style_lighting: Any = None,
    output_requirements: Any = None,
    subject_content: Any = None,
    visual_prompt: Any = None,
    style_preset: str | None = None,
) -> dict[str, str]:
    prompt_fields: dict[str, str] = {}
    if isinstance(raw_prompt_fields, dict):
        for raw_key, raw_value in raw_prompt_fields.items():
            key = str(raw_key).strip()
            value = _optional_text(raw_value)
            if key and value:
                prompt_fields[key] = value

    parsed_visual_fields = _prompt_fields_from_visual_prompt(_optional_text(visual_prompt))
    for key, value in parsed_visual_fields.items():
        prompt_fields.setdefault(key, value)

    direct_fields = {
        "核心特征": _optional_text(core_feature),
        "风格及光线": _optional_text(style_lighting),
        "输出要求": _optional_text(output_requirements),
        "主体内容": _optional_text(subject_content),
    }
    for key, value in direct_fields.items():
        if value:
            prompt_fields[key] = value

    if "风格及光线" not in prompt_fields and style_preset:
        prompt_fields["风格及光线"] = _default_style_line(style_preset)
    prompt_fields = _sanitize_prompt_fields(prompt_fields)
    return prompt_fields


def _prompt_fields_from_visual_prompt(visual_prompt: str) -> dict[str, str]:
    prompt_fields: dict[str, str] = {}
    for raw_line in visual_prompt.replace("\r\n", "\n").split("\n"):
        key, value = _split_field_line(raw_line.strip())
        if key is None:
            continue
        if key in {"核心特征", "风格及光线", "输出要求", "主体内容"} and value:
            prompt_fields[key] = value
    return prompt_fields


def _compose_visual_prompt_from_fields(prompt_fields: dict[str, str]) -> str:
    ordered_keys = ("核心特征", "风格及光线", "输出要求", "主体内容")
    lines = [f"{key}：{prompt_fields[key]}" for key in ordered_keys if prompt_fields.get(key)]
    return "\n".join(lines).strip()


def _sanitize_prompt_fields(prompt_fields: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in prompt_fields.items():
        cleaned = _sanitize_asset_layout_text(value)
        if cleaned:
            sanitized[key] = cleaned
    return sanitized


def _sanitize_asset_layout_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    for pattern in BAD_ASSET_LAYOUT_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"([，,、;；]){2,}", r"\1", text)
    return text.strip(" ，,、;；")


def _default_style_line(style_preset: str) -> str:
    style = str(style_preset or "").strip()
    if style == "2D":
        return "2D AI漫剧风格，光影质感细腻、层次丰富"
    if style == "3D":
        return "高精度3D CG风格，光影质感真实细腻，柔和自然光"
    if style == "写实":
        return "照片级写实，电影质感，柔和自然光"
    return ""


def _normalize_voice_payload(raw_voice: Any, character_name: str) -> dict[str, Any] | None:
    if isinstance(raw_voice, dict):
        label = _optional_text(raw_voice.get("label")) or f"{character_name}音色"
        text = _optional_text(raw_voice.get("text"))
        seed = raw_voice.get("seed")
        normalized_seed = _coerce_int(seed)
        if text or normalized_seed is not None:
            return {"label": label, "text": text, "seed": normalized_seed}
    text = _optional_text(raw_voice)
    if not text:
        return None
    return _build_voice_payload(f"{character_name}音色", text)


def _normalize_personality_traits(raw_traits: Any) -> list[dict[str, str]]:
    if not isinstance(raw_traits, list):
        return []
    normalized: list[dict[str, str]] = []
    for raw_trait in raw_traits:
        if isinstance(raw_trait, dict):
            trait = _optional_text(raw_trait.get("trait"))
            description = _optional_text(raw_trait.get("description"))
        else:
            trait, description = _split_trait_line(str(raw_trait).strip())
        if trait:
            normalized.append({"trait": trait, "description": description})
    return normalized


def _image_config_item_from_asset(group_name: str, item: dict[str, Any], *, index: int) -> dict[str, Any]:
    prompt_fields = _sanitize_prompt_fields(dict(item.get("prompt_fields") or {}))
    voice = item.get("voice") if isinstance(item.get("voice"), dict) else {}
    entry = {
        "order": _coerce_int(item.get("order")) or index,
        "name": _optional_text(item.get("name")),
        "asset_id": _optional_text(item.get("asset_id")) or f"{ASSET_TYPE_BY_GROUP[group_name]}_{safe_stem(str(item.get('name') or index))}",
        "asset_type": ASSET_TYPE_BY_GROUP[group_name],
        "prompt": _compose_visual_prompt_from_fields(prompt_fields),
        "prompt_fields": prompt_fields,
        "style_lighting": _sanitize_asset_layout_text(_optional_text(item.get("style_lighting")) or prompt_fields.get("风格及光线", "")),
        "output_requirements": _sanitize_asset_layout_text(_optional_text(item.get("output_requirements")) or prompt_fields.get("输出要求", "")),
        "subject_content": _sanitize_asset_layout_text(_optional_text(item.get("subject_content")) or prompt_fields.get("主体内容", "")),
        "source_text_lines": _compose_visual_prompt_from_fields(prompt_fields).splitlines(),
    }
    if group_name == "characters":
        entry["core_feature"] = _sanitize_asset_layout_text(_optional_text(item.get("core_feature")) or prompt_fields.get("核心特征", ""))
        entry["voice_label"] = _optional_text(voice.get("label"))
        entry["voice_text"] = _optional_text(voice.get("text"))
    return entry


def _normalize_consistency_rules(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value not in (None, "") else ""
    return text or None


def _render_summary_names(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "，".join(str(item).strip() for item in values if str(item).strip())


def _render_asset_detail_block(group_name: str, item: dict[str, Any]) -> list[str]:
    lines = [f"### {item.get('name', '')}"]
    prompt_fields = _sanitize_prompt_fields(dict(item.get("prompt_fields") or {}))
    for key in ("核心特征", "风格及光线", "输出要求", "主体内容"):
        if group_name != "characters" and key == "核心特征":
            continue
        value = _optional_text(prompt_fields.get(key))
        if value:
            lines.append(f"{key}：{value}")

    if group_name == "characters":
        voice = item.get("voice") if isinstance(item.get("voice"), dict) else {}
        voice_label = _optional_text(voice.get("label")) or f"{item.get('name', '')}音色"
        voice_text = _optional_text(voice.get("text"))
        if voice_text:
            lines.append(voice_label)
            lines.append(voice_text)
        description = _optional_text(item.get("description"))
        if description:
            lines.append("人物小传：")
            lines.append(description)
        traits = item.get("personality_traits") if isinstance(item.get("personality_traits"), list) else []
        if traits:
            lines.append("性格特征：")
            for trait in traits:
                if not isinstance(trait, dict):
                    continue
                trait_name = _optional_text(trait.get("trait"))
                trait_description = _optional_text(trait.get("description"))
                if trait_name and trait_description:
                    lines.append(f"- {trait_name}：{trait_description}")
                elif trait_name:
                    lines.append(f"- {trait_name}")
    else:
        description = _optional_text(item.get("description"))
        if description and "主体内容" not in prompt_fields:
            lines.append(f"主体内容：{description}")
    return lines


def _render_image_config_item(group_name: str, item: dict[str, Any]) -> list[str]:
    lines = [
        str(_coerce_int(item.get("order")) or 1),
        str(item.get("name") or ""),
    ]
    prompt_fields = _sanitize_prompt_fields(dict(item.get("prompt_fields") or {}))
    for key in ("核心特征", "风格及光线", "输出要求", "主体内容"):
        if group_name != "characters" and key == "核心特征":
            continue
        value = _optional_text(prompt_fields.get(key))
        if value:
            lines.append(f"{key}：{value}")
    if group_name == "characters":
        voice_label = _optional_text(item.get("voice_label")) or f"{item.get('name', '')}音色"
        voice_text = _optional_text(item.get("voice_text"))
        if voice_text:
            lines.append(voice_label)
            lines.append(voice_text)
    return lines


def _parse_asset_detail_block(group_name: str, order: int, block: list[str]) -> dict[str, Any]:
    name = block[0].strip()
    asset_type = ASSET_TYPE_BY_GROUP[group_name]
    voice_label = ""
    voice_text = ""
    bio = ""
    traits: list[dict[str, str]] = []
    prompt_fields: dict[str, str] = {}
    prompt_lines: list[str] = []
    raw_lines: list[str] = []

    mode = "prompt"
    index = 1
    while index < len(block):
        line = block[index].strip()
        raw_lines.append(line)
        if not line:
            index += 1
            continue

        if line.endswith("音色") and line.startswith(name):
            voice_label = line
            if index + 1 < len(block):
                voice_text = block[index + 1].strip()
                raw_lines.append(voice_text)
                index += 2
                continue

        if line == "人物小传：":
            mode = "bio"
            index += 1
            continue
        if line == "性格特征：":
            mode = "traits"
            index += 1
            continue

        if mode == "prompt":
            key, value = _split_field_line(line)
            if key is not None:
                prompt_fields[key] = value
            prompt_lines.append(line)
        elif mode == "bio":
            bio = f"{bio}\n{line}".strip() if bio else line
        elif mode == "traits" and line.startswith("-"):
            trait_line = line[1:].strip()
            trait, description = _split_trait_line(trait_line)
            traits.append({"trait": trait, "description": description})
        index += 1

    payload = {
        "order": order,
        "asset_id": f"{asset_type}_{safe_stem(name)}",
        "name": name,
        "asset_type": asset_type,
        "role": None,
        "description": bio or prompt_fields.get("主体内容", ""),
        "visual_prompt": _compose_visual_prompt_from_fields(_sanitize_prompt_fields(prompt_fields)),
        "prompt_fields": _sanitize_prompt_fields(prompt_fields),
        "core_feature": _sanitize_prompt_fields(prompt_fields).get("核心特征", ""),
        "style_lighting": _sanitize_prompt_fields(prompt_fields).get("风格及光线", ""),
        "output_requirements": _sanitize_prompt_fields(prompt_fields).get("输出要求", ""),
        "subject_content": _sanitize_prompt_fields(prompt_fields).get("主体内容", ""),
        "voice": _build_voice_payload(voice_label, voice_text) if voice_label or voice_text else None,
        "personality_traits": traits,
        "source_text_lines": [line for line in raw_lines if line],
    }
    if group_name != "characters":
        payload.pop("role", None)
        payload.pop("voice", None)
        payload.pop("personality_traits", None)
    return payload


def _parse_image_config_entry(group_name: str, order: int, name: str, body_lines: list[str]) -> dict[str, Any]:
    prompt_fields: dict[str, str] = {}
    prompt_lines: list[str] = []
    voice_label = ""
    voice_text = ""

    index = 0
    while index < len(body_lines):
        line = body_lines[index].strip()
        if line.endswith("音色") and index + 1 < len(body_lines):
            voice_label = line
            voice_text = body_lines[index + 1].strip()
            index += 2
            continue
        key, value = _split_field_line(line)
        if key is not None:
            prompt_fields[key] = value
        prompt_lines.append(line)
        index += 1

    entry = {
        "order": order,
        "name": name,
        "asset_id": f"{ASSET_TYPE_BY_GROUP[group_name]}_{safe_stem(name)}",
        "asset_type": ASSET_TYPE_BY_GROUP[group_name],
        "prompt": _compose_visual_prompt_from_fields(_sanitize_prompt_fields(prompt_fields)),
        "prompt_fields": _sanitize_prompt_fields(prompt_fields),
        "style_lighting": _sanitize_prompt_fields(prompt_fields).get("风格及光线", ""),
        "output_requirements": _sanitize_prompt_fields(prompt_fields).get("输出要求", ""),
        "subject_content": _sanitize_prompt_fields(prompt_fields).get("主体内容", ""),
        "core_feature": _sanitize_prompt_fields(prompt_fields).get("核心特征", ""),
        "voice_label": voice_label,
        "voice_text": voice_text,
        "source_text_lines": list(body_lines),
    }
    if group_name != "characters":
        entry.pop("voice_label", None)
        entry.pop("voice_text", None)
        entry.pop("core_feature", None)
    return entry


def _split_field_line(line: str) -> tuple[str | None, str]:
    match = re.match(r"^([^:：]+)[:：]\s*(.*)$", line)
    if not match:
        return None, line
    return match.group(1).strip(), match.group(2).strip()


def _split_trait_line(line: str) -> tuple[str, str]:
    if "：" in line:
        trait, description = line.split("：", 1)
        return trait.strip(), description.strip()
    if ":" in line:
        trait, description = line.split(":", 1)
        return trait.strip(), description.strip()
    return line.strip(), ""


def _build_voice_payload(label: str, text: str) -> dict[str, Any]:
    match = re.search(r"seed\s*:\s*(\d+)", text, flags=re.IGNORECASE)
    return {
        "label": label,
        "text": text,
        "seed": int(match.group(1)) if match else None,
    }


def _resolve_style_preset(runtime_inputs: dict[str, Any], payload: Any) -> str | None:
    raw_style = str(runtime_inputs.get("style") or "").strip()
    if raw_style in STYLE_PRESET_MAP:
        return STYLE_PRESET_MAP[raw_style]

    style_candidates: list[str] = []
    if isinstance(payload, dict):
        for group_name in ("characters", "scenes", "props"):
            for item in payload.get(group_name, []) or []:
                if not isinstance(item, dict):
                    continue
                style_line = str(
                    item.get("style_lighting")
                    or (item.get("prompt_fields") or {}).get("风格及光线")
                    or ""
                ).strip()
                if style_line:
                    style_candidates.append(style_line)
    if any("2D" in line for line in style_candidates):
        return "2D"
    if any("3D" in line for line in style_candidates):
        return "3D"
    if any("照片级写实" in line for line in style_candidates):
        return "写实"
    return None


def _common_output_requirements(items: list[dict[str, Any]]) -> str:
    values = [
        str(item.get("output_requirements") or "").strip()
        for item in items
        if str(item.get("output_requirements") or "").strip()
    ]
    if not values:
        return ""
    if all(value == values[0] for value in values[1:]):
        return values[0]
    return values[0]


def _first_non_empty(items: list[dict[str, Any]], *path: str) -> str:
    for item in items:
        current: Any = item
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        text = str(current or "").strip()
        if text:
            return text
    return ""


def _split_style_line(style_line: str) -> tuple[str | None, str | None]:
    text = str(style_line).strip()
    if not text:
        return None, None
    parts = [part.strip() for part in text.split("，") if part.strip()]
    if len(parts) == 1:
        return parts[0], None
    return parts[0], "，".join(parts[1:])


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
