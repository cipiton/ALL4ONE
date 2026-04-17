from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from engine.llm_client import (
    call_chat_completion,
    describe_model_route,
    load_config_from_env,
    parse_json_response,
)
from engine.input_loader import read_text_with_fallbacks
from engine.models import PromptMessage
from engine.recap_structured_outputs import (
    assets_payload_to_bridge_summary,
    image_config_payload_to_bridge_entries,
    parse_asset_summary,
    parse_image_config_text,
)
from engine.writer import write_json_file


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
QWEN_PROMPT_COMPILER_MODEL_ALIAS = "qwen"
QWEN_PROMPT_COMPILER_VERSION = "qwen_asset_prompt_compiler_v1"
ASSET_GROUPS = ("characters", "scenes", "props")
ASSET_TYPE_BY_GROUP = {
    "characters": "character",
    "scenes": "scene",
    "props": "prop",
}


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
    del step_number, runtime_values, state

    source_bundle = resolve_source_bundle(document.path)
    storyboard_payload = json.loads(read_text_with_fallbacks(source_bundle["scene_script_json"]))
    assets_payload = _load_optional_json(source_bundle.get("assets_json"))
    image_config_payload = _load_optional_json(source_bundle.get("image_config_json"))

    if assets_payload is not None:
        asset_summary = assets_payload_to_bridge_summary(assets_payload)
    else:
        assets_text = read_text_with_fallbacks(source_bundle["assets"])
        asset_summary = parse_asset_summary(assets_text)

    if image_config_payload is not None:
        image_config = image_config_payload_to_bridge_entries(image_config_payload)
    else:
        image_config_text = read_text_with_fallbacks(source_bundle["image_config"])
        image_config = parse_image_config_text(image_config_text)

    asset_catalog = build_videoarc_assets_payload(
        source_bundle=source_bundle,
        asset_summary=asset_summary,
        image_config=image_config,
        storyboard_payload=storyboard_payload,
        assets_payload=assets_payload,
    )
    compiler_summary = compile_asset_prompts_with_qwen(
        repo_root=repo_root,
        skill=skill,
        asset_catalog=asset_catalog,
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
        compiler_summary=compiler_summary,
    )

    canonical_assets_path = write_json_file(output_dir, "assets.json", asset_catalog)
    assets_path = write_json_file(output_dir, "videoarc_assets.json", asset_catalog)
    storyboard_path = write_json_file(output_dir, "videoarc_storyboard.json", storyboard)
    summary_path = write_json_file(output_dir, "bridge_summary.json", summary)

    return {
        "primary_output": summary_path,
        "output_files": {
            "primary": summary_path,
            "assets": canonical_assets_path,
            "bridge_summary": summary_path,
            "videoarc_assets": assets_path,
            "videoarc_storyboard": storyboard_path,
        },
        "notes": [
            f"Source recap folder: {source_bundle['source_dir']}",
            f"Generated {canonical_assets_path.name}, {assets_path.name}, {storyboard_path.name}, and {summary_path.name}.",
            f"Episodes: {summary['episode_count']} | Scene beats: {summary['scene_beat_count']}",
            compiler_summary.get("note", ""),
        ],
        "status": "completed",
    }


def resolve_source_bundle(input_path: Path) -> dict[str, Path]:
    candidate = input_path.resolve()
    if candidate.name != "04_episode_scene_script.json":
        raise ValueError(
            "Recap To Comfy Bridge expects either the `02_recap_production` folder "
            "(resolved by the shared runtime) or the file `02_recap_production/04_episode_scene_script.json`. "
            f"Received unsupported file: {candidate.name}"
        )

    source_dir = candidate.parent
    resolved = {
        "source_dir": source_dir,
        "assets": source_dir / "02_assets.txt",
        "assets_json": source_dir / "02_assets.json",
        "image_config": source_dir / "03_image_config.txt",
        "image_config_json": source_dir / "03_image_config.json",
        "scene_script_json": source_dir / "04_episode_scene_script.json",
    }
    missing: list[str] = []
    if not resolved["scene_script_json"].exists():
        missing.append("scene_script_json")
    if not resolved["assets"].exists() and not resolved["assets_json"].exists():
        missing.append("assets")
    if not resolved["image_config"].exists() and not resolved["image_config_json"].exists():
        missing.append("image_config")
    if missing:
        missing_labels = ", ".join(sorted(missing))
        raise ValueError(
            "The recap bundle is incomplete. "
            "Please provide the `02_recap_production` folder or its "
            "`04_episode_scene_script.json` file, and make sure the sibling recap files exist. "
            f"Missing from {source_dir}: {missing_labels}"
        )
    return resolved


def build_videoarc_assets_payload(
    *,
    source_bundle: dict[str, Path],
    asset_summary: dict[str, list[str]],
    image_config: dict[str, list[dict[str, Any]]],
    storyboard_payload: dict[str, Any],
    assets_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered_characters = order_assets(image_config["characters"], asset_summary["characters"])
    ordered_scenes = order_assets(image_config["scenes"], asset_summary["scenes"])
    ordered_props = order_assets(image_config["props"], asset_summary["props"])
    enriched_lookup = _build_enriched_asset_lookup(assets_payload)

    style_hint = detect_style_hint(ordered_characters, ordered_scenes, ordered_props)
    series_title = str(
        storyboard_payload.get("series_title")
        or (assets_payload or {}).get("series_title")
        or source_bundle["source_dir"].name
    )

    return {
        "schema": "videoarc_assets_v1",
        "bridge_source": "recap_production",
        "series_title": series_title,
        "source_folder": str(source_bundle["source_dir"]),
        "style_preset": (assets_payload or {}).get("style_preset"),
        "source_files": {
            "assets": str(source_bundle["assets"]),
            "assets_json": str(source_bundle["assets_json"]) if source_bundle["assets_json"].exists() else None,
            "image_config": str(source_bundle["image_config"]),
            "image_config_json": str(source_bundle["image_config_json"]) if source_bundle["image_config_json"].exists() else None,
            "scene_script_json": str(source_bundle["scene_script_json"]),
        },
        "style_hint": style_hint,
        "counts": {
            "characters": len(ordered_characters),
            "scenes": len(ordered_scenes),
            "props": len(ordered_props),
        },
        "characters": [build_asset_record("character", entry, enriched_lookup=enriched_lookup) for entry in ordered_characters],
        "scenes": [build_asset_record("scene", entry, enriched_lookup=enriched_lookup) for entry in ordered_scenes],
        "props": [build_asset_record("prop", entry, enriched_lookup=enriched_lookup) for entry in ordered_props],
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


def build_asset_record(kind: str, entry: dict[str, Any], *, enriched_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prompt_fields = _sanitize_prompt_fields(dict(entry.get("prompt_fields", {})))
    enriched_entry = _match_enriched_asset(enriched_lookup, entry)
    raw_lines = entry.get("source_text_lines") or entry.get("raw_lines", [])
    return {
        "asset_id": entry.get("asset_id"),
        "name": entry.get("name"),
        "kind": kind,
        "order": entry.get("order"),
        "prompt": _sanitize_layout_text(entry.get("prompt") or entry.get("prompt_text", "")),
        "prompt_fields": prompt_fields,
        "style_lighting": prompt_fields.get("风格及光线", ""),
        "output_requirements": prompt_fields.get("输出要求", ""),
        "subject_content": prompt_fields.get("主体内容", ""),
        "core_feature": prompt_fields.get("核心特征", ""),
        "voice": entry.get("voice_text", ""),
        "description": enriched_entry.get("description") if enriched_entry else "",
        "role": enriched_entry.get("role") if enriched_entry else None,
        "personality_traits": enriched_entry.get("personality_traits") if enriched_entry else None,
        "source": {
            "type": "03_image_config.json" if entry.get("source_text_lines") else "03_image_config.txt",
            "raw_lines": [_sanitize_layout_text(line) for line in raw_lines if _sanitize_layout_text(line)],
        },
    }


def compile_asset_prompts_with_qwen(
    *,
    repo_root: Path,
    skill,
    asset_catalog: dict[str, Any],
) -> dict[str, Any]:
    if _env_flag_disabled("ONE4ALL_QWEN_ASSET_PROMPT_COMPILER"):
        return {
            "enabled": False,
            "model_alias": QWEN_PROMPT_COMPILER_MODEL_ALIAS,
            "version": QWEN_PROMPT_COMPILER_VERSION,
            "success_count": 0,
            "failure_count": 0,
            "note": "Qwen prompt compiler disabled by ONE4ALL_QWEN_ASSET_PROMPT_COMPILER=0.",
        }

    try:
        config = load_config_from_env(
            repo_root,
            skill=skill,
            model_override=QWEN_PROMPT_COMPILER_MODEL_ALIAS,
        )
        route_description = describe_model_route(
            repo_root,
            skill=skill,
            model_override=QWEN_PROMPT_COMPILER_MODEL_ALIAS,
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        return {
            "enabled": False,
            "model_alias": QWEN_PROMPT_COMPILER_MODEL_ALIAS,
            "version": QWEN_PROMPT_COMPILER_VERSION,
            "success_count": 0,
            "failure_count": _asset_count(asset_catalog),
            "note": f"Qwen prompt compiler unavailable; deterministic bridge fields retained. {detail}",
            "error": detail,
        }

    success_count = 0
    failure_count = 0
    errors: list[dict[str, str]] = []
    compiled_model = config.model

    for group_name in ASSET_GROUPS:
        for asset in asset_catalog.get(group_name, []) or []:
            if not isinstance(asset, dict):
                continue
            asset_type = ASSET_TYPE_BY_GROUP[group_name]
            try:
                compiled = compile_single_asset_prompt_with_qwen(
                    config=config,
                    asset=asset,
                    asset_type=asset_type,
                    asset_catalog=asset_catalog,
                )
            except Exception as exc:  # noqa: BLE001
                failure_count += 1
                detail = str(exc).strip() or exc.__class__.__name__
                errors.append(
                    {
                        "asset_id": str(asset.get("asset_id") or ""),
                        "name": str(asset.get("name") or ""),
                        "error": detail,
                    }
                )
                continue

            asset["compiled_prompt"] = compiled["compiled_prompt"]
            asset["compiled_prompt_model"] = compiled.get("model") or compiled_model
            asset["compiled_prompt_version"] = QWEN_PROMPT_COMPILER_VERSION
            asset["compiled_prompt_source"] = "qwen_prompt_compiler"
            asset["compiled_from_fields"] = compiled["compiled_from_fields"]
            if compiled.get("rationale"):
                asset["compiled_prompt_rationale"] = compiled["rationale"]
            success_count += 1

    note = (
        f"Qwen prompt compiler route: {route_description}; "
        f"compiled {success_count} asset prompt(s), {failure_count} fallback(s)."
    )
    return {
        "enabled": True,
        "model_alias": QWEN_PROMPT_COMPILER_MODEL_ALIAS,
        "model": compiled_model,
        "route": route_description,
        "version": QWEN_PROMPT_COMPILER_VERSION,
        "success_count": success_count,
        "failure_count": failure_count,
        "errors": errors[:10],
        "note": note,
    }


def compile_single_asset_prompt_with_qwen(
    *,
    config,
    asset: dict[str, Any],
    asset_type: str,
    asset_catalog: dict[str, Any],
) -> dict[str, Any]:
    fields = _asset_prompt_compiler_fields(asset, asset_type, asset_catalog)
    response = call_chat_completion(
        config,
        build_prompt_compiler_messages(fields),
        json_mode=True,
        temperature=0.0,
    )
    payload = parse_json_response(response)
    compiled_prompt = _sanitize_layout_text(payload.get("compiled_prompt"))
    if len(compiled_prompt) < 40:
        raise ValueError("Qwen compiler returned an empty or too-short compiled_prompt.")
    return {
        "compiled_prompt": compiled_prompt,
        "rationale": _sanitize_layout_text(payload.get("rationale")),
        "compiled_from_fields": fields["compiled_from_fields"],
        "model": response.model,
    }


def build_prompt_compiler_messages(fields: dict[str, Any]) -> list[PromptMessage]:
    schema = {
        "compiled_prompt": "single final Z-Image prompt string",
        "rationale": "optional short debug note, 1 sentence max",
    }
    return [
        PromptMessage(
            role="system",
            content=(
                "You are the ONE4ALL recap_to_comfy_bridge asset prompt compiler. "
                "Compile one final image generation prompt for Z-Image from the provided structured asset data. "
                "You are not a story writer. Preserve the asset identity, age, role, object category, scene meaning, "
                "and all important visual facts. Do not invent story facts, new people, new brands, new locations, "
                "or new props. Return only a JSON object matching the requested schema.\n\n"
                "Hard layout rules: generate a single clean asset image prompt. Forbid and omit multi-angle sheets, "
                "three-view layouts, contact sheets, collages, split panels, inset poses, turnaround sheets, "
                "labeled angles, diagrams, and all-in-one board layouts. Also omit these phrases if they appear in "
                "legacy source data: 三视图, 正面/侧面/背面, 2-4不同角度, 多角度展示, 集中放在同一张图输出.\n\n"
                "Style rules: strongly follow style_preset and style_hint. For 2D, explicitly use high-quality "
                "anime style / 动漫风格 2D animated illustration language, refined anime linework, controlled clean "
                "line art, polished cel-shaded or painterly animated coloring, stylized illustrated design, and "
                "non-photorealistic wording. Avoid photorealistic render, realistic 3D render, product render, "
                "studio product photo, glossy catalog shot, and live-action photography. For 3D, use stylized 3D CG "
                "animated render language. Tailor the prompt to asset_type: character, scene, or prop."
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "Compile the following structured asset into one final Z-Image prompt.\n"
                "Output JSON schema:\n"
                f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                "Structured asset data:\n"
                f"{json.dumps(fields, ensure_ascii=False, indent=2)}"
            ),
        ),
    ]


def _asset_prompt_compiler_fields(
    asset: dict[str, Any],
    asset_type: str,
    asset_catalog: dict[str, Any],
) -> dict[str, Any]:
    source = asset.get("source") if isinstance(asset.get("source"), dict) else {}
    prompt_fields = asset.get("prompt_fields") if isinstance(asset.get("prompt_fields"), dict) else {}
    fields = {
        "asset_type": asset_type,
        "asset_id": asset.get("asset_id"),
        "name": asset.get("name"),
        "style_preset": _first_non_empty(asset.get("style_preset"), asset_catalog.get("style_preset")),
        "style_hint": _first_non_empty(asset.get("style_hint"), asset_catalog.get("style_hint")),
        "style_lighting": asset.get("style_lighting"),
        "core_feature": asset.get("core_feature"),
        "subject_content": asset.get("subject_content"),
        "description": asset.get("description"),
        "role": asset.get("role"),
        "personality_traits": asset.get("personality_traits"),
        "prompt_fields": prompt_fields,
        "source_raw_lines": source.get("raw_lines") if isinstance(source.get("raw_lines"), list) else [],
        "fallback_prompt": asset.get("prompt"),
    }
    fields["compiled_from_fields"] = [
        key
        for key, value in fields.items()
        if key != "compiled_from_fields" and value not in (None, "", [], {})
    ]
    return fields


def _asset_count(asset_catalog: dict[str, Any]) -> int:
    return sum(
        len(asset_catalog.get(group_name, []) or [])
        for group_name in ASSET_GROUPS
        if isinstance(asset_catalog.get(group_name, []) or [], list)
    )


def _env_flag_disabled(name: str) -> bool:
    value = str(os.environ.get(name) or "").strip().lower()
    return value in {"0", "false", "no", "off", "disabled"}


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value in (None, "", [], {}):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _sanitize_prompt_fields(prompt_fields: dict[str, Any]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in prompt_fields.items():
        text = _sanitize_layout_text(value)
        if text:
            sanitized[str(key)] = text
    return sanitized


def _sanitize_layout_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    for pattern in BAD_ASSET_LAYOUT_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(no|without)\s+([.,;])", r"\2", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s*([，,、;；])\s*([.。])", r"\2", text)
    text = re.sub(r"([，,、;；]){2,}", r"\1", text)
    return text.strip(" ，,、;；")


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
    compiler_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "videoarc_bridge_summary_v1",
        "bridge_skill": "recap_to_comfy_bridge",
        "source_folder": str(source_bundle["source_dir"]),
        "files_found": {
            "02_assets.txt": str(source_bundle["assets"]),
            "02_assets.json": str(source_bundle["assets_json"]) if source_bundle["assets_json"].exists() else None,
            "03_image_config.txt": str(source_bundle["image_config"]),
            "03_image_config.json": str(source_bundle["image_config_json"]) if source_bundle["image_config_json"].exists() else None,
            "04_episode_scene_script.json": str(source_bundle["scene_script_json"]),
        },
        "files_generated": [
            "assets.json",
            "videoarc_assets.json",
            "videoarc_storyboard.json",
            "bridge_summary.json",
        ],
        "series_title": storyboard.get("series_title", ""),
        "episode_count": storyboard.get("episode_count", 0),
        "scene_beat_count": storyboard.get("scene_beat_count", 0),
        "asset_counts": dict(asset_catalog.get("counts", {})),
        "qwen_prompt_compiler": compiler_summary or {},
    }


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(read_text_with_fallbacks(path))


def _build_enriched_asset_lookup(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return lookup
    for group_name in ("characters", "scenes", "props"):
        for item in payload.get(group_name, []) or []:
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("asset_id") or "").strip()
            name = str(item.get("name") or "").strip()
            if asset_id:
                lookup[f"id:{asset_id}"] = item
            if name:
                lookup[f"name:{name}"] = item
    return lookup


def _match_enriched_asset(lookup: dict[str, dict[str, Any]], entry: dict[str, Any]) -> dict[str, Any] | None:
    asset_id = str(entry.get("asset_id") or "").strip()
    name = str(entry.get("name") or "").strip()
    if asset_id and f"id:{asset_id}" in lookup:
        return lookup[f"id:{asset_id}"]
    if name and f"name:{name}" in lookup:
        return lookup[f"name:{name}"]
    return None
