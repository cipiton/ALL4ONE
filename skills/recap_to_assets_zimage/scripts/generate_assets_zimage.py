from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STEPS = 8
DEFAULT_GUIDANCE_SCALE = 0.0
DEFAULT_CHARACTER_SIZE = (512, 768)
DEFAULT_SCENE_SIZE = (768, 512)
DEFAULT_PROP_SIZE = (512, 512)
SEED_RE = re.compile(r"(?:^|[\s,;])seed\s*[:=]\s*(\d+)", re.IGNORECASE)
ASSET_GROUPS = ("characters", "scenes", "props")
ASSET_TYPE_BY_GROUP = {
    "characters": "character",
    "scenes": "scene",
    "props": "prop",
}
GROUP_OUTPUT_SIZE = {
    "characters": DEFAULT_CHARACTER_SIZE,
    "scenes": DEFAULT_SCENE_SIZE,
    "props": DEFAULT_PROP_SIZE,
}
CHARACTER_REFERENCE_PROMPT_PREFIX = (
    "Single clean character identity reference image, optimized for downstream "
    "image-to-image and video identity preservation. "
    "Composition: one person only, full body visible from head to toe, front-facing, "
    "neutral standing pose, centered in frame, plain clean unobtrusive background. "
    "Identity clarity: sharp clear face, distinctive hair, outfit, body silhouette, "
    "age, gender, and defining features; keep this person visually distinct from "
    "other characters."
)
CHARACTER_REFERENCE_PROMPT_NEGATIVE = (
    "Keep the image to one clean centered person with no extra people, text, "
    "watermarks, duplicated variants, board presentation, or additional poses."
)
BAD_LAYOUT_PATTERNS = (
    r"头部正面特写布局在左边[，,、\s]*",
    r"正面/侧面/背面全身三视图布局在右边[，,、\s]*",
    r"正面/侧面/背面",
    r"全部集中在一张图片输出",
    r"全部集中在一张图输出",
    r"集中放在同一张图输出",
    r"2-4不同角度展示并标注好角度[，,、\s]*",
    r"2\s*-\s*4\s*不同角度",
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
CHARACTER_LAYOUT_PATTERNS = BAD_LAYOUT_PATTERNS
PROP_LAYOUT_PATTERNS = BAD_LAYOUT_PATTERNS
SCENE_LAYOUT_PATTERNS = BAD_LAYOUT_PATTERNS
SPECIALIZED_PROP_REFERENCE_PROMPT_PREFIX = (
    "Single-object prop reference image for downstream image-to-image "
    "and video asset use. Composition: one isolated prop only, one clean view, "
    "centered in frame, full object visible, plain clean unobtrusive background, "
    "sharp silhouette, accurate materials, no labels or callouts."
)
SPECIALIZED_PROP_REFERENCE_PROMPT_NEGATIVE = (
    "Keep the image to one clean centered object with no duplicated variants, "
    "text, watermarks, board presentation, diagrams, or extra objects."
)
SPECIALIZED_PROP_LAYOUT_PATTERNS = PROP_LAYOUT_PATTERNS
PROP_REFERENCE_PROMPT_PREFIX = (
    "Single clean prop reference image for downstream image-to-image and video asset use. "
    "Composition: one prop only, one clean view, centered in frame, full object visible, "
    "simple unobtrusive background, sharp silhouette, clear materials."
)
PROP_REFERENCE_PROMPT_NEGATIVE = SPECIALIZED_PROP_REFERENCE_PROMPT_NEGATIVE
SCENE_REFERENCE_PROMPT_PREFIX = (
    "Single clean environment reference image for downstream image-to-image and video asset use. "
    "Composition: one coherent environment image, no asset board presentation, "
    "clear readable space, stable establishing view, rich environmental detail."
)
MOTORCYCLE_TERMS = (
    "motorcycle",
    "motorbike",
    "motocross",
    "enduro",
    "dirt bike",
    "trail bike",
    "off-road bike",
    "offroad bike",
    "sportbike",
    "superbike",
    "摩托",
    "摩托车",
    "机车",
    "越野摩托",
    "林道摩托",
    "赛道摩托",
)
OFFROAD_MOTORCYCLE_TERMS = (
    "motocross",
    "enduro",
    "dirt bike",
    "trail bike",
    "off-road bike",
    "offroad bike",
    "越野摩托",
    "林道摩托",
    "越野",
)
SPORT_MOTORCYCLE_TERMS = (
    "sportbike",
    "superbike",
    "race bike",
    "racing motorcycle",
    "sport motorcycle",
    "rr",
    "赛道",
    "竞速",
    "跑车",
    "整流罩",
)
BICYCLE_TERMS = (
    "bicycle",
    "mountain bike",
    "road bike",
    "pedal bike",
    "cycling bike",
    "自行车",
    "单车",
    "脚踏车",
    "山地车",
)
HELMET_TERMS = (
    "helmet",
    "头盔",
)
MOTORCYCLE_HELMET_TERMS = (
    "motorcycle helmet",
    "motorbike helmet",
    "motocross helmet",
    "enduro helmet",
    "full-face helmet",
    "off-road helmet",
    "offroad helmet",
    "摩托头盔",
    "摩托车头盔",
    "越野头盔",
    "骑行头盔",
    "骑行防护",
)
BICYCLE_HELMET_TERMS = (
    "bicycle helmet",
    "cycling helmet",
    "自行车头盔",
    "单车头盔",
)
ENGINE_TERMS = (
    "engine",
    "引擎",
    "发动机",
)
TRIPLE_ENGINE_TERMS = (
    "inline-three",
    "inline three",
    "inline-3",
    "inline 3",
    "triple-cylinder",
    "triple cylinder",
    "three-cylinder",
    "three cylinder",
    "3-cylinder",
    "3 cylinder",
    "三缸",
    "三汽缸",
    "三气缸",
)


@dataclass(frozen=True, slots=True)
class BackendConfig:
    repo_root: Path
    python_executable: Path
    model_path: Path
    script_path: Path
    steps: int = DEFAULT_STEPS
    guidance_scale: float = DEFAULT_GUIDANCE_SCALE


@dataclass(frozen=True, slots=True)
class AssetRequest:
    group_name: str
    asset_type: str
    asset_id: str
    asset_name: str
    prompt: str
    output_name: str
    width: int
    height: int
    seed: int
    source_entry: dict[str, Any]


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
    del skill, step_number, runtime_values, state

    payload = _load_assets_payload(document.path, document.text)
    story_title = _resolve_story_title(document.path, payload)
    backend_config = _resolve_backend_config(repo_root)
    asset_requests = _extract_asset_requests(payload)

    if not asset_requests:
        raise ValueError(
            f"No asset entries were found in {document.path.name}. "
            "Expected grouped arrays under 'characters', 'scenes', and/or 'props'."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    for group_name in ASSET_GROUPS:
        (output_dir / group_name).mkdir(parents=True, exist_ok=True)

    manifest_items: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    _safe_print(
        f"[recap_to_assets_zimage] loaded {len(asset_requests)} asset(s) from {document.path.name} "
        f"for story '{story_title}'"
    )
    _safe_print(f"[recap_to_assets_zimage] backend python: {backend_config.python_executable}")
    _safe_print(f"[recap_to_assets_zimage] z-image repo: {backend_config.repo_root}")
    _safe_print(f"[recap_to_assets_zimage] model path: {backend_config.model_path}")

    for index, asset in enumerate(asset_requests, start=1):
        target_path = output_dir / asset.group_name / asset.output_name
        _safe_print(
            f"[recap_to_assets_zimage] [{index}/{len(asset_requests)}] generating "
            f"{asset.asset_type} '{asset.asset_name}' -> {target_path.name} "
            f"({asset.width}x{asset.height}, seed={asset.seed})"
        )
        try:
            backend_logs = _invoke_backend_generation(
                config=backend_config,
                asset=asset,
                output_path=target_path,
            )
            success_count += 1
            manifest_items.append(
                {
                    "asset_id": asset.asset_id,
                    "asset_name": asset.asset_name,
                    "asset_type": asset.asset_type,
                    "group": asset.group_name,
                    "prompt": asset.prompt,
                    "output_file": str(target_path.relative_to(output_dir)),
                    "seed": asset.seed,
                    "width": asset.width,
                    "height": asset.height,
                    "status": "success",
                    "backend_logs": backend_logs,
                }
            )
        except Exception as exc:  # noqa: BLE001
            failure_count += 1
            error_detail = "".join(
                traceback.format_exception_only(type(exc), exc)
            ).strip() or str(exc)
            _safe_print(
                f"[recap_to_assets_zimage] asset failed: {asset.asset_name} ({asset.asset_id}) | {error_detail}"
            )
            manifest_items.append(
                {
                    "asset_id": asset.asset_id,
                    "asset_name": asset.asset_name,
                    "asset_type": asset.asset_type,
                    "group": asset.group_name,
                    "prompt": asset.prompt,
                    "output_file": str(target_path.relative_to(output_dir)),
                    "seed": asset.seed,
                    "width": asset.width,
                    "height": asset.height,
                    "status": "error",
                    "error": error_detail,
                }
            )

    manifest_payload = {
        "schema": "one4all_assets_t2i_manifest_v1",
        "story_title": story_title,
        "source_assets_file": str(document.path),
        "asset_count": len(asset_requests),
        "success_count": success_count,
        "failure_count": failure_count,
        "backend": {
            "type": "z-image-turbo-local",
            "repo_root": str(backend_config.repo_root),
            "python_executable": str(backend_config.python_executable),
            "model_path": str(backend_config.model_path),
            "steps": backend_config.steps,
            "guidance_scale": backend_config.guidance_scale,
            "attention_backend": "native",
        },
        "items": manifest_items,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    notes = [
        f"Loaded {len(asset_requests)} asset(s) from {document.path.name}.",
        f"Generated {success_count} image(s); {failure_count} asset(s) failed.",
        f"Wrote stage manifest to {manifest_path}.",
    ]

    return {
        "primary_output": manifest_path,
        "output_files": {
            "primary": manifest_path,
            "manifest": manifest_path,
            "characters_dir": output_dir / "characters",
            "scenes_dir": output_dir / "scenes",
            "props_dir": output_dir / "props",
        },
        "notes": notes,
        "status": "completed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ONE4ALL Z-Image asset generator helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backend_parser = subparsers.add_parser("backend-generate", help="Run one Z-Image-Turbo generation job")
    backend_parser.add_argument("--zimage-repo", required=True, help="Absolute path to the local z-image repo root.")
    backend_parser.add_argument("--model-path", required=True, help="Absolute path to the Z-Image-Turbo model directory.")
    backend_parser.add_argument("--prompt", required=True, help="Prompt to render.")
    backend_parser.add_argument("--output", required=True, help="Target image path.")
    backend_parser.add_argument("--width", type=int, required=True, help="Output width in pixels.")
    backend_parser.add_argument("--height", type=int, required=True, help="Output height in pixels.")
    backend_parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help="Inference steps.")
    backend_parser.add_argument("--guidance-scale", type=float, default=DEFAULT_GUIDANCE_SCALE, help="Guidance scale.")
    backend_parser.add_argument("--seed", type=int, required=True, help="Deterministic random seed.")

    args = parser.parse_args(argv)
    if args.command == "backend-generate":
        return _backend_generate(args)
    raise ValueError(f"Unsupported command: {args.command}")


def _backend_generate(args: argparse.Namespace) -> int:
    _configure_utf8_console()
    zimage_repo = Path(args.zimage_repo).expanduser().resolve()
    src_root = zimage_repo / "src"
    if not src_root.exists():
        raise FileNotFoundError(f"Z-Image src directory does not exist: {src_root}")

    os.environ["PYTHONPATH"] = str(src_root)
    os.environ["ZIMAGE_ATTENTION"] = "native"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    os.chdir(zimage_repo)

    import torch  # noqa: PLC0415
    from utils import ensure_model_weights, load_from_local_dir, set_attention_backend  # noqa: PLC0415
    from zimage import generate  # noqa: PLC0415

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model_path = ensure_model_weights(str(Path(args.model_path).expanduser().resolve()), verify=False)
    components = load_from_local_dir(model_path, device=device, dtype=dtype, compile=False)
    set_attention_backend("native")

    images = generate(
        prompt=str(args.prompt),
        **components,
        height=int(args.height),
        width=int(args.width),
        num_inference_steps=int(args.steps),
        guidance_scale=float(args.guidance_scale),
        generator=torch.Generator(device).manual_seed(int(args.seed)),
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(output_path)
    _safe_print(f"[zimage-backend] saved {output_path}")
    return 0


def _load_assets_payload(input_path: Path, input_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(input_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"assets.json is not valid JSON: {input_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"assets.json must contain a top-level JSON object: {input_path}")
    if not any(isinstance(payload.get(group_name), list) for group_name in ASSET_GROUPS):
        raise ValueError(
            "assets.json is missing grouped asset arrays. "
            "Expected at least one of: characters, scenes, props."
        )
    return payload


def _resolve_story_title(document_path: Path, payload: dict[str, Any]) -> str:
    title = str(payload.get("story_title") or payload.get("series_title") or "").strip()
    if title:
        return title
    try:
        from engine.output_paths import resolve_story_title_from_path  # noqa: PLC0415

        resolved = resolve_story_title_from_path(document_path)
        if resolved:
            return resolved
    except Exception:  # noqa: BLE001
        pass
    return document_path.stem


def _resolve_backend_config(repo_root: Path) -> BackendConfig:
    zimage_repo = Path(
        os.environ.get("ONE4ALL_ZIMAGE_REPO") or (repo_root / "z-image")
    ).expanduser().resolve()
    python_executable = Path(
        os.environ.get("ONE4ALL_ZIMAGE_PYTHON") or (zimage_repo / ".venv" / "Scripts" / "python.exe")
    ).expanduser().resolve()
    model_path = Path(
        os.environ.get("ONE4ALL_ZIMAGE_MODEL") or (zimage_repo / "ckpts" / "Z-Image-Turbo")
    ).expanduser().resolve()
    script_path = Path(__file__).resolve()

    if not zimage_repo.exists():
        raise FileNotFoundError(f"Z-Image repo root does not exist: {zimage_repo}")
    if not python_executable.exists():
        raise FileNotFoundError(
            f"Z-Image Python executable does not exist: {python_executable}. "
            "Set ONE4ALL_ZIMAGE_PYTHON if the venv lives elsewhere."
        )
    if not model_path.exists():
        raise FileNotFoundError(
            f"Z-Image model directory does not exist: {model_path}. "
            "Set ONE4ALL_ZIMAGE_MODEL if the checkpoint lives elsewhere."
        )

    return BackendConfig(
        repo_root=zimage_repo,
        python_executable=python_executable,
        model_path=model_path,
        script_path=script_path,
    )


def _extract_asset_requests(payload: dict[str, Any]) -> list[AssetRequest]:
    requests: list[AssetRequest] = []
    payload_context = _build_payload_prompt_context(payload)
    for group_name in ASSET_GROUPS:
        raw_entries = payload.get(group_name) or []
        if raw_entries in (None, ""):
            continue
        if not isinstance(raw_entries, list):
            raise ValueError(f"'{group_name}' must be a JSON array.")

        for index, raw_entry in enumerate(raw_entries, start=1):
            if not isinstance(raw_entry, dict):
                raise ValueError(f"Asset entry {group_name}[{index}] must be a JSON object.")
            asset_type = ASSET_TYPE_BY_GROUP[group_name]
            asset_name = str(raw_entry.get("name") or raw_entry.get("asset_name") or "").strip()
            asset_id = str(raw_entry.get("asset_id") or "").strip()
            source_prompt = str(
                raw_entry.get("compiled_prompt")
                or raw_entry.get("prompt")
                or raw_entry.get("prompt_text")
                or raw_entry.get("visual_prompt")
                or ""
            ).strip()
            if not asset_name:
                asset_name = asset_id or f"{asset_type}_{index:03d}"
            if not asset_id:
                asset_id = f"{asset_type}_{_safe_stem(asset_name)}"
            if not source_prompt and not _has_structured_prompt_material(raw_entry):
                raise ValueError(
                    f"Asset '{asset_name}' in group '{group_name}' is missing a prompt. "
                    "Expected structured asset fields or a fallback 'prompt' / 'prompt_text'."
                )

            prompt = _resolve_generation_prompt(
                group_name=group_name,
                raw_entry=raw_entry,
                source_prompt=source_prompt,
                asset_id=asset_id,
                asset_name=asset_name,
                payload_context=payload_context,
            )
            width, height = _resolve_output_size(group_name, raw_entry)
            seed = _resolve_seed(asset_id, raw_entry, source_prompt)
            output_name = f"{_safe_stem(asset_id)}.png"
            requests.append(
                AssetRequest(
                    group_name=group_name,
                    asset_type=asset_type,
                    asset_id=asset_id,
                    asset_name=asset_name,
                    prompt=prompt,
                    output_name=output_name,
                    width=width,
                    height=height,
                    seed=seed,
                    source_entry=dict(raw_entry),
                )
            )
    return requests


def _resolve_generation_prompt(
    *,
    group_name: str,
    raw_entry: dict[str, Any],
    source_prompt: str,
    asset_id: str,
    asset_name: str,
    payload_context: dict[str, str],
) -> str:
    compiled_prompt = _sanitize_compiled_prompt(raw_entry.get("compiled_prompt"))
    if compiled_prompt:
        asset_type = ASSET_TYPE_BY_GROUP.get(group_name, group_name.rstrip("s"))
        return _build_compiled_generation_prompt(
            raw_entry=raw_entry,
            compiled_prompt=compiled_prompt,
            source_prompt=source_prompt,
            asset_type=asset_type,
            payload_context=payload_context,
        )
    if group_name == "characters":
        return _build_character_reference_prompt(raw_entry, source_prompt, asset_id, asset_name, payload_context)
    if group_name == "props":
        return _build_prop_generation_prompt(raw_entry, source_prompt, asset_id, asset_name, payload_context)
    return _build_scene_generation_prompt(raw_entry, source_prompt, asset_id, asset_name, payload_context)


def _build_compiled_generation_prompt(
    *,
    raw_entry: dict[str, Any],
    compiled_prompt: str,
    source_prompt: str,
    asset_type: str,
    payload_context: dict[str, str],
) -> str:
    style_preset = _entry_style_preset(
        raw_entry,
        "\n".join(part for part in (compiled_prompt, source_prompt) if part),
        payload_context,
    )
    parts: list[str] = []
    if _compiled_prompt_needs_style_prefix(compiled_prompt, style_preset):
        style_prefix = _style_prompt_prefix(asset_type, style_preset)
        if style_prefix:
            parts.append(style_prefix)
    parts.append(compiled_prompt)
    if asset_type == "character":
        parts.append(CHARACTER_REFERENCE_PROMPT_NEGATIVE)
    elif asset_type == "prop":
        parts.append(PROP_REFERENCE_PROMPT_NEGATIVE)
    elif asset_type == "scene":
        parts.append("Keep the image to one coherent environment with no board presentation, text, or watermarks.")
    return "\n".join(part for part in parts if part).strip()


def _sanitize_compiled_prompt(value: Any) -> str:
    if value in (None, ""):
        return ""
    cleaned_lines: list[str] = []
    for line in str(value).splitlines():
        cleaned = _sanitize_prompt_fragment(line)
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines).strip()


def _compiled_prompt_needs_style_prefix(compiled_prompt: str, style_preset: str) -> bool:
    text = str(compiled_prompt or "").casefold()
    if style_preset == "2D":
        return not any(token.casefold() in text for token in ("anime", "动漫", "2d", "animated illustration"))
    if style_preset == "3D":
        return not any(token.casefold() in text for token in ("3d", "cg", "三维"))
    if style_preset == "写实":
        return not any(token.casefold() in text for token in ("photoreal", "写实", "照片级", "live-action"))
    return False


def _build_payload_prompt_context(payload: dict[str, Any]) -> dict[str, str]:
    global_style = payload.get("global_style") if isinstance(payload.get("global_style"), dict) else {}
    return {
        "style_preset": _first_non_empty(
            payload.get("style_preset"),
            global_style.get("style_preset"),
        ),
        "style_hint": _first_non_empty(
            payload.get("style_hint"),
            payload.get("style_lighting"),
            global_style.get("visual_style"),
        ),
        "style_lighting": _first_non_empty(
            payload.get("style_lighting"),
            payload.get("style_hint"),
            global_style.get("lighting"),
            global_style.get("visual_style"),
        ),
    }


def _has_structured_prompt_material(raw_entry: dict[str, Any]) -> bool:
    if not isinstance(raw_entry, dict):
        return False
    for key in (
        "style_preset",
        "style_hint",
        "style_lighting",
        "core_feature",
        "subject_content",
        "description",
        "compiled_prompt",
        "prompt_fields",
        "source",
    ):
        value = raw_entry.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


def _build_character_reference_prompt(
    raw_entry: dict[str, Any],
    source_prompt: str,
    asset_id: str,
    asset_name: str,
    payload_context: dict[str, str],
) -> str:
    style_preset = _entry_style_preset(raw_entry, source_prompt, payload_context)
    core_feature = _entry_structured_text(raw_entry, source_prompt, "核心特征", "core_feature")
    style_lighting = _entry_style_text(raw_entry, source_prompt, payload_context)
    subject_content = _first_non_empty(
        _entry_structured_text(raw_entry, source_prompt, "主体内容", "subject_content"),
        _sanitize_character_source_prompt(source_prompt),
    )
    role = _sanitize_prompt_fragment(_first_non_empty(raw_entry.get("role")))
    description = _sanitize_prompt_fragment(_entry_structured_text(raw_entry, source_prompt, None, "description"))
    traits = _format_personality_traits(raw_entry.get("personality_traits"))

    parts = [
        _style_prompt_prefix("character", style_preset),
        CHARACTER_REFERENCE_PROMPT_PREFIX,
        f"Character identity key: {asset_name} / {asset_id}.",
    ]
    if core_feature:
        parts.append(f"Core distinguishing feature: {core_feature}.")
    if subject_content:
        parts.append(f"Subject visual details: {subject_content}.")
    if role:
        parts.append(f"Role cue for identity separation: {role}.")
    if description:
        parts.append(f"Story identity cue: {description}.")
    if traits:
        parts.append(f"Personality cues for expression and presence: {traits}.")
    if style_lighting:
        parts.append(f"Visual style and lighting: {style_lighting}.")
    parts.append(CHARACTER_REFERENCE_PROMPT_NEGATIVE)
    return "\n".join(parts)


def _extract_labeled_prompt_field(prompt: str, label: str) -> str:
    for line in str(prompt).splitlines():
        stripped = line.strip()
        for separator in ("：", ":"):
            prefix = f"{label}{separator}"
            if stripped.startswith(prefix):
                return _sanitize_prompt_fragment(stripped[len(prefix) :].strip())
    return ""


def _entry_structured_text(
    raw_entry: dict[str, Any],
    source_prompt: str,
    label: str | None,
    *keys: str,
) -> str:
    prompt_fields = raw_entry.get("prompt_fields") if isinstance(raw_entry.get("prompt_fields"), dict) else {}
    source_lines = _source_raw_lines(raw_entry)
    candidates: list[Any] = []
    for key in keys:
        candidates.append(raw_entry.get(key))
    if label:
        candidates.append(prompt_fields.get(label))
        candidates.append(_extract_labeled_lines_field(source_lines, label))
        candidates.append(_extract_labeled_prompt_field(source_prompt, label))
    for candidate in candidates:
        text = _sanitize_prompt_fragment(candidate)
        if text:
            return text
    return ""


def _entry_style_text(raw_entry: dict[str, Any], source_prompt: str, payload_context: dict[str, str]) -> str:
    style_preset = _entry_style_preset(raw_entry, source_prompt, payload_context)
    return _first_non_empty(
        _entry_structured_text(raw_entry, source_prompt, "风格及光线", "style_lighting", "style_hint"),
        _sanitize_prompt_fragment(payload_context.get("style_lighting")),
        _sanitize_prompt_fragment(payload_context.get("style_hint")),
        _default_style_line(style_preset),
    )


def _entry_style_preset(raw_entry: dict[str, Any], source_prompt: str, payload_context: dict[str, str]) -> str:
    explicit = _first_non_empty(raw_entry.get("style_preset"), payload_context.get("style_preset"))
    if explicit:
        normalized = _normalize_style_preset(explicit)
        if normalized:
            return normalized

    style_text = " ".join(
        part
        for part in (
            _entry_structured_text(raw_entry, source_prompt, "风格及光线", "style_lighting", "style_hint"),
            _sanitize_prompt_fragment(payload_context.get("style_lighting")),
            _sanitize_prompt_fragment(payload_context.get("style_hint")),
            source_prompt,
            "\n".join(_source_raw_lines(raw_entry)),
        )
        if part
    )
    return _normalize_style_preset(style_text)


def _normalize_style_preset(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "2d" in text or "anime" in text or "漫剧" in text or "动漫" in text or "动画" in text or "漫画" in text:
        return "2D"
    if "3d" in text or "cg" in text or "三维" in text:
        return "3D"
    if "写实" in text or "photoreal" in text or "photo-real" in text or "照片级" in text:
        return "写实"
    return ""


def _style_prompt_prefix(asset_type: str, style_preset: str) -> str:
    if style_preset == "2D":
        if asset_type == "character":
            return (
                "Style mandate: high-quality anime style 2D character illustration, "
                "动漫风格, mature animated-drama character design, expressive but "
                "grounded proportions, refined anime linework, detailed painted "
                "shading, cinematic short-drama lighting. Keep it clearly anime-style "
                "2D illustrated, not chibi, not children's cartoon, not flat vector "
                "cartoon, not photorealistic live-action, and not a realistic 3D render."
            )
        if asset_type == "scene":
            return (
                "Style mandate: high-quality anime style 2D background illustration, "
                "动漫风格, cinematic anime environment art, layered painted atmosphere, "
                "expressive composition, grounded materials, dramatic light and shadow. "
                "Keep it clearly anime-style 2D illustrated, not children's cartoon, "
                "not flat vector cartoon, not photorealistic live-action, not realistic "
                "3D render, and not a studio set render."
            )
        return (
            "Style mandate: high-quality anime style 2D prop illustration, 动漫风格, "
            "anime production asset design, refined anime linework, detailed painted "
            "materials, grounded cinematic lighting, clear readable object design. "
            "Keep it clearly anime-style 2D illustrated, not children's cartoon, not "
            "flat vector cartoon, not photorealistic live-action, not realistic 3D "
            "render; not product render, not studio product photo, not glossy catalog "
            "shot."
        )
    if style_preset == "3D":
        if asset_type == "character":
            return (
                "Style mandate: stylized 3D CG character asset, clean sculpted forms, "
                "controlled animation-style materials, readable silhouette, not a "
                "photorealistic live-action portrait."
            )
        if asset_type == "scene":
            return (
                "Style mandate: stylized 3D CG environment asset, cinematic short-drama "
                "set design, readable space, controlled stylized lighting, not a "
                "photorealistic live-action plate."
            )
        return (
            "Style mandate: stylized 3D CG prop asset, clear modeled object, simplified "
            "materials, readable silhouette, not a studio product photo or catalog render."
        )
    if style_preset == "写实":
        return "Style mandate: photorealistic cinematic asset image with natural light and grounded real-world materials."
    return ""


def _default_style_line(style_preset: str) -> str:
    style = str(style_preset or "").strip()
    if style == "2D":
        return "2D AI漫剧风格，光影质感细腻、层次丰富"
    if style == "3D":
        return "高精度3D CG风格，光影质感真实细腻，柔和自然光"
    if style == "写实":
        return "照片级写实，电影质感，柔和自然光"
    return ""


def _source_raw_lines(raw_entry: dict[str, Any]) -> list[str]:
    source = raw_entry.get("source") if isinstance(raw_entry.get("source"), dict) else {}
    raw_lines = source.get("raw_lines") if isinstance(source, dict) else None
    if isinstance(raw_lines, list):
        return [str(line).strip() for line in raw_lines if str(line).strip()]
    return []


def _extract_labeled_lines_field(raw_lines: list[str], label: str) -> str:
    for line in raw_lines:
        text = _extract_labeled_prompt_field(line, label)
        if text:
            return text
    return ""


def _raw_lines_enrichment(raw_entry: dict[str, Any], *, skip_labels: set[str] | None = None) -> str:
    skip_labels = skip_labels or set()
    fragments: list[str] = []
    for line in _source_raw_lines(raw_entry):
        key, value = _split_prompt_line(line)
        if key and key in skip_labels:
            continue
        cleaned = _sanitize_prompt_fragment(value if key else line)
        if cleaned and cleaned not in fragments:
            fragments.append(cleaned)
    return "; ".join(fragments[:4])


def _split_prompt_line(line: str) -> tuple[str | None, str]:
    match = re.match(r"^([^:：]+)[:：]\s*(.*)$", str(line).strip())
    if not match:
        return None, str(line).strip()
    return match.group(1).strip(), match.group(2).strip()


def _sanitize_prompt_fragment(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    for pattern in BAD_LAYOUT_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(no|without)\s+([.,;])", r"\2", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s*([，,、;；])\s*([.。])", r"\2", text)
    text = re.sub(r"([，,、;；]){2,}", r"\1", text)
    return text.strip(" ，,、;；")


def _sanitize_character_source_prompt(prompt: str) -> str:
    cleaned_lines: list[str] = []
    for line in str(prompt).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("输出要求：", "输出要求:")):
            continue
        cleaned = _sanitize_prompt_fragment(stripped)
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines).strip()


def _sanitize_scene_source_prompt(prompt: str) -> str:
    cleaned_lines: list[str] = []
    for line in str(prompt).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("输出要求：", "输出要求:")):
            continue
        cleaned = _sanitize_prompt_fragment(stripped)
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines).strip()


def _build_prop_generation_prompt(
    raw_entry: dict[str, Any],
    source_prompt: str,
    asset_id: str,
    asset_name: str,
    payload_context: dict[str, str],
) -> str:
    profile = _detect_specialized_prop_profile(raw_entry, source_prompt, asset_name)
    style_preset = _entry_style_preset(raw_entry, source_prompt, payload_context)
    core_feature = _entry_structured_text(raw_entry, source_prompt, "核心特征", "core_feature")
    style_lighting = _entry_style_text(raw_entry, source_prompt, payload_context)
    subject_content = _first_non_empty(
        _entry_structured_text(raw_entry, source_prompt, "主体内容", "subject_content"),
        _sanitize_specialized_prop_source_prompt(source_prompt),
    )
    description = _entry_structured_text(raw_entry, source_prompt, None, "description")

    if not profile:
        parts = [
            _style_prompt_prefix("prop", style_preset),
            PROP_REFERENCE_PROMPT_PREFIX,
            f"Prop identity key: {asset_name} / {asset_id}.",
        ]
        if core_feature:
            parts.append(f"Core distinguishing feature: {core_feature}.")
        if subject_content:
            parts.append(f"Source visual details to preserve: {subject_content}.")
        if description:
            parts.append(f"Story/use cue: {description}.")
        if style_lighting:
            parts.append(f"Visual style and lighting: {style_lighting}.")
        raw_enrichment = _raw_lines_enrichment(raw_entry, skip_labels={"输出要求"})
        if raw_enrichment:
            parts.append(f"Additional structured source cues: {raw_enrichment}.")
        parts.append(PROP_REFERENCE_PROMPT_NEGATIVE)
        return "\n".join(parts)

    parts = [
        _style_prompt_prefix("prop", style_preset),
        SPECIALIZED_PROP_REFERENCE_PROMPT_PREFIX,
        f"Prop identity key: {asset_name} / {asset_id}.",
        f"Specialized prop category: {profile['category']}.",
        f"Category-specific morphology: {profile['morphology']}.",
    ]
    if core_feature:
        parts.append(f"Core distinguishing feature: {core_feature}.")
    if subject_content:
        parts.append(f"Source visual details to preserve: {subject_content}.")
    if description:
        parts.append(f"Story/use cue: {description}.")
    if style_lighting:
        parts.append(f"Visual style and lighting: {style_lighting}.")
    parts.append(f"Category negative constraints: {profile['negative']}.")
    parts.append(SPECIALIZED_PROP_REFERENCE_PROMPT_NEGATIVE)
    return "\n".join(parts)


def _build_scene_generation_prompt(
    raw_entry: dict[str, Any],
    source_prompt: str,
    asset_id: str,
    asset_name: str,
    payload_context: dict[str, str],
) -> str:
    style_preset = _entry_style_preset(raw_entry, source_prompt, payload_context)
    style_lighting = _entry_style_text(raw_entry, source_prompt, payload_context)
    subject_content = _first_non_empty(
        _entry_structured_text(raw_entry, source_prompt, "主体内容", "subject_content"),
        _sanitize_scene_source_prompt(source_prompt),
    )
    description = _entry_structured_text(raw_entry, source_prompt, None, "description")
    core_feature = _entry_structured_text(raw_entry, source_prompt, "核心特征", "core_feature")

    parts = [
        _style_prompt_prefix("scene", style_preset),
        SCENE_REFERENCE_PROMPT_PREFIX,
        f"Scene identity key: {asset_name} / {asset_id}.",
    ]
    if core_feature:
        parts.append(f"Core environment feature: {core_feature}.")
    if subject_content:
        parts.append(f"Environment visual details: {subject_content}.")
    if description:
        parts.append(f"Story/use cue: {description}.")
    if style_lighting:
        parts.append(f"Visual style and lighting: {style_lighting}.")
    raw_enrichment = _raw_lines_enrichment(raw_entry, skip_labels={"输出要求"})
    if raw_enrichment:
        parts.append(f"Additional structured source cues: {raw_enrichment}.")
    return "\n".join(parts)


def _detect_specialized_prop_profile(
    raw_entry: dict[str, Any],
    source_prompt: str,
    asset_name: str,
) -> dict[str, str] | None:
    text = _collect_prop_detection_text(raw_entry, source_prompt, asset_name)
    name_text = " ".join(
        str(field).lower()
        for field in (asset_name, raw_entry.get("asset_id"), raw_entry.get("name"))
        if field not in (None, "")
    )
    has_motorcycle = _contains_any(text, MOTORCYCLE_TERMS)
    has_engine = _contains_any(text, ENGINE_TERMS)
    has_triple_engine = _contains_any(text, TRIPLE_ENGINE_TERMS)
    has_helmet = _contains_any(text, HELMET_TERMS)
    has_bicycle = _contains_any(text, BICYCLE_TERMS)

    if has_engine and (has_triple_engine or _contains_any(name_text, ENGINE_TERMS)):
        return _engine_prop_profile(has_triple_engine)

    if has_helmet and _is_motorcycle_helmet_context(text, has_motorcycle):
        return _helmet_prop_profile(_contains_any(text, OFFROAD_MOTORCYCLE_TERMS))

    if _is_motorcycle_vehicle_context(text, has_motorcycle, has_bicycle):
        return _motorcycle_vehicle_prop_profile(
            is_offroad=_contains_any(text, OFFROAD_MOTORCYCLE_TERMS),
            is_sport=_contains_any(text, SPORT_MOTORCYCLE_TERMS),
        )

    return None


def _engine_prop_profile(has_triple_engine: bool) -> dict[str, str]:
    if has_triple_engine:
        return {
            "category": "inline-three motorcycle engine",
            "morphology": (
                "single exposed inline-three motorcycle engine; compact triple-cylinder "
                "layout with three cylinders arranged in one straight row, visible "
                "cylinder head, crankcase, intake and exhaust ports, cooling passages, "
                "bolts, hoses, and machined metal texture"
            ),
            "negative": (
                "not V-twin, not cruiser engine, not car engine, not generic engine "
                "block, not two separate engines"
            ),
        }
    return {
        "category": "motorcycle engine",
        "morphology": (
            "single exposed motorcycle engine assembly; compact engine block, visible "
            "cylinder head, crankcase, intake and exhaust ports, cooling parts, bolts, "
            "hoses, brackets, and machined metal surfaces"
        ),
        "negative": "not car engine, not bicycle part, not scooter body, not duplicate engines",
    }


def _helmet_prop_profile(is_offroad: bool) -> dict[str, str]:
    if is_offroad:
        morphology = (
            "full-face off-road motorcycle helmet in motocross/enduro style; hard shell, "
            "extended chin bar, visor peak, large goggle opening, thick rim, padded "
            "interior, chin strap, scuffed protective surface if aging is described"
        )
    else:
        morphology = (
            "single motorcycle riding helmet; hard protective shell, substantial chin "
            "bar or face-shield area, thick rim, padded interior, secure chin strap, "
            "heavier protective geometry than a cycling helmet"
        )
    return {
        "category": "motorcycle helmet",
        "morphology": morphology,
        "negative": "not bicycle helmet, not cycling helmet, not skate helmet, not construction hard hat",
    }


def _motorcycle_vehicle_prop_profile(is_offroad: bool, is_sport: bool) -> dict[str, str]:
    if is_offroad:
        return {
            "category": "off-road trail motorcycle",
            "morphology": (
                "lightweight off-road trail motorcycle/dirt bike; slim enduro-style "
                "frame, high front fender, long-travel front fork, narrow seat, raised "
                "ground clearance, spoke wheels, knobby off-road tires, exposed engine, "
                "chain drive, handlebar controls, compact fuel tank"
            ),
            "negative": "not mountain bicycle, not road bicycle, not pedal bicycle, not e-bike, not scooter, not car",
        }
    if is_sport:
        return {
            "category": "sport motorcycle prototype",
            "morphology": (
                "complete high-performance sport motorcycle; aerodynamic fairing, "
                "aggressive front cowl, compact racing proportions, twin-spar frame, "
                "visible engine mass, front forks, swingarm, disc brakes, exhaust, "
                "two motorcycle wheels, performance tires"
            ),
            "negative": "not bicycle, not scooter, not car, not toy model, not generic futuristic vehicle",
        }
    return {
        "category": "motorcycle",
        "morphology": (
            "complete motorcycle; rigid frame, fuel tank, seat, front fork, swingarm, "
            "visible engine, exhaust, chain or belt drive, disc brakes, handlebars, "
            "two motorcycle wheels with substantial tires"
        ),
        "negative": "not bicycle, not mountain bicycle, not road bicycle, not scooter, not car",
    }


def _collect_prop_detection_text(
    raw_entry: dict[str, Any],
    source_prompt: str,
    asset_name: str,
) -> str:
    fields = [
        asset_name,
        raw_entry.get("asset_id"),
        raw_entry.get("name"),
        raw_entry.get("core_feature"),
        raw_entry.get("subject_content"),
        raw_entry.get("description"),
        raw_entry.get("role"),
        source_prompt,
        json.dumps(raw_entry.get("prompt_fields", {}), ensure_ascii=False),
        "\n".join(_source_raw_lines(raw_entry)),
    ]
    return " ".join(str(field).lower() for field in fields if field not in (None, ""))


def _is_motorcycle_helmet_context(text: str, has_motorcycle: bool) -> bool:
    if _contains_any(text, BICYCLE_HELMET_TERMS):
        return False
    return has_motorcycle or _contains_any(text, MOTORCYCLE_HELMET_TERMS)


def _is_motorcycle_vehicle_context(text: str, has_motorcycle: bool, has_bicycle: bool) -> bool:
    if not has_motorcycle:
        return False
    if _contains_any(text, ("trail bike", "dirt bike", "off-road bike", "offroad bike")):
        return not _contains_any(text, ("mountain bicycle", "road bicycle", "pedal bicycle"))
    return not (has_bicycle and not _contains_any(text, MOTORCYCLE_TERMS))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _sanitize_specialized_prop_source_prompt(prompt: str) -> str:
    cleaned_lines: list[str] = []
    for line in str(prompt).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("输出要求：", "输出要求:")):
            continue
        cleaned = _sanitize_prompt_fragment(stripped)
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines).strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value in (None, ""):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _format_personality_traits(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        formatted: list[str] = []
        for item in value:
            if isinstance(item, dict):
                trait = _sanitize_prompt_fragment(_first_non_empty(item.get("trait")))
                description = _sanitize_prompt_fragment(_first_non_empty(item.get("description")))
                if trait and description:
                    formatted.append(f"{trait} - {description}")
                elif trait or description:
                    formatted.append(trait or description)
            else:
                text = _sanitize_prompt_fragment(_first_non_empty(item))
                if text:
                    formatted.append(text)
        return "; ".join(formatted)
    if isinstance(value, dict):
        return "; ".join(
            f"{_sanitize_prompt_fragment(key)}: {_sanitize_prompt_fragment(val)}"
            for key, val in value.items()
            if _sanitize_prompt_fragment(key) and _sanitize_prompt_fragment(val)
        )
    return _sanitize_prompt_fragment(value)


def _resolve_output_size(group_name: str, raw_entry: dict[str, Any]) -> tuple[int, int]:
    width = _coerce_positive_int(raw_entry.get("width"))
    height = _coerce_positive_int(raw_entry.get("height"))
    if width and height:
        return width, height
    return GROUP_OUTPUT_SIZE[group_name]


def _coerce_positive_int(value: Any) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _resolve_seed(asset_id: str, raw_entry: dict[str, Any], prompt: str) -> int:
    explicit_seed = _coerce_positive_int(raw_entry.get("seed"))
    if explicit_seed is not None:
        return explicit_seed

    for candidate in (
        raw_entry.get("voice"),
        raw_entry.get("prompt"),
        raw_entry.get("prompt_text"),
        json.dumps(raw_entry.get("source", {}), ensure_ascii=False),
    ):
        if candidate in (None, ""):
            continue
        match = SEED_RE.search(str(candidate))
        if match:
            return int(match.group(1))

    digest = hashlib.sha256(f"{asset_id}\n{prompt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _invoke_backend_generation(
    *,
    config: BackendConfig,
    asset: AssetRequest,
    output_path: Path,
) -> str:
    env = os.environ.copy()
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    src_root = config.repo_root / "src"
    env["PYTHONPATH"] = str(src_root) if not existing_pythonpath else f"{src_root}{os.pathsep}{existing_pythonpath}"
    env["ZIMAGE_ATTENTION"] = "native"

    command = [
        str(config.python_executable),
        str(config.script_path),
        "backend-generate",
        "--zimage-repo",
        str(config.repo_root),
        "--model-path",
        str(config.model_path),
        "--prompt",
        asset.prompt,
        "--output",
        str(output_path),
        "--width",
        str(asset.width),
        "--height",
        str(asset.height),
        "--steps",
        str(config.steps),
        "--guidance-scale",
        str(config.guidance_scale),
        "--seed",
        str(asset.seed),
    ]
    completed = subprocess.run(
        command,
        cwd=str(config.repo_root),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    backend_logs = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if str(part).strip()
    ).strip()
    if completed.returncode != 0:
        if output_path.exists() and _is_console_encoding_only_failure(backend_logs):
            return backend_logs
        raise RuntimeError(
            f"Z-Image generation failed for {asset.asset_id} with exit code {completed.returncode}."
            + (f"\n{backend_logs}" if backend_logs else "")
        )
    if not output_path.exists():
        raise RuntimeError(f"Z-Image backend reported success but no file was created: {output_path}")
    return backend_logs


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", str(value).strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:96] or "asset"


def _configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                continue


def _safe_print(message: str) -> None:
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def _is_console_encoding_only_failure(backend_logs: str) -> bool:
    lowered = backend_logs.lower()
    return "unicodeencodeerror" in lowered and "cp1252" in lowered


if __name__ == "__main__":
    raise SystemExit(main())
