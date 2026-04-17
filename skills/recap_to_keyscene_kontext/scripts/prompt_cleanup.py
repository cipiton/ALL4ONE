from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.llm_client import call_chat_completion, describe_model_route, load_config_from_env, parse_json_response
from engine.models import PromptMessage


PROMPT_CLEANUP_VERSION = "gemini_keyscene_prompt_cleanup_v1"
PROMPT_CLEANUP_MODES = ("off", "gemini")
VALID_SHOT_PRIORITIES = {"identity", "staging", "object"}
FIELD_LIMITS = {
    "shot_intent": 180,
    "framing": 120,
    "performance": 120,
    "scene": 140,
    "essential_prop": 80,
    "style_tail": 48,
    "shot_priority": 16,
    "negative_guidance": 80,
}
BANNED_METADATA_TOKENS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".json",
    "asset_id",
    "asset ids",
    "asset_id:",
    "manifest",
    "output_file",
    "payload_file",
    "videoarc",
    "reference_order",
    "workflow_substitutions",
    "asset_hints",
)


@dataclass(frozen=True, slots=True)
class PromptCleanupResult:
    mode: str
    source: str
    final_prompt: str
    structured_input: dict[str, Any]
    validated_payload: dict[str, Any] | None
    raw_response_text: str = ""
    raw_response_json: dict[str, Any] | None = None
    warning: str = ""
    model: str = ""
    route: str = ""
    model_alias: str = ""
    shot_priority: str = ""
    cleanup_status: str = "disabled"
    artifact_path: str = ""


def normalize_prompt_cleanup_mode(value: Any) -> str:
    text = str(value or "off").strip().casefold().replace("-", "_")
    if text not in PROMPT_CLEANUP_MODES:
        raise ValueError("Unsupported prompt cleanup mode. Choose one of: off, gemini.")
    return text


def normalize_model_alias(value: Any) -> str:
    return str(value or "gemini").strip() or "gemini"


def build_prompt_cleanup_input(*, beat: dict[str, Any], selected_assets: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    camera = beat.get("camera") if isinstance(beat.get("camera"), dict) else {}
    return {
        "shot_id": str(beat.get("shot_id") or beat.get("scene_id") or beat.get("source_scene_id") or "").strip(),
        "episode_number": beat.get("episode_number"),
        "beat_summary": _compact_text(beat.get("description"), limit=220),
        "visual_prompt": _compact_text(beat.get("prompt") or beat.get("visual_prompt"), limit=280),
        "anchor_text": _compact_text(beat.get("anchor_text"), limit=120),
        "mood": _compact_text(beat.get("mood"), limit=64),
        "asset_focus": _compact_text(beat.get("asset_focus"), limit=40),
        "shot_type": _compact_text(camera.get("shot_type") or beat.get("shot_type"), limit=40),
        "camera_motion": _compact_text(camera.get("camera_motion") or beat.get("camera_motion"), limit=40),
        "selected_references": {
            role: {
                "asset_name": _compact_text(item.get("asset_name"), limit=80),
                "kind": _compact_text(item.get("kind"), limit=24),
            }
            for role, item in selected_assets.items()
            if isinstance(item, dict)
        },
    }


def build_prompt_cleanup_messages(compact_input: dict[str, Any]) -> list[PromptMessage]:
    schema = {
        "shot_intent": "one clear visual event sentence",
        "framing": "shot size / composition / subject relation only",
        "performance": "expression / gaze / posture only",
        "scene": "only visually relevant environment / lighting / time-of-day",
        "essential_prop": "only if visually necessary, else empty string",
        "style_tail": "one short phrase like cinematic realism",
        "shot_priority": "identity|staging|object",
        "negative_guidance": "optional short phrase, else empty string",
    }
    return [
        PromptMessage(
            role="system",
            content=(
                "You are the ONE4ALL keyscene prompt director / prompt normalizer. "
                "You convert one recap beat into a compact, literal, cinematic structured prompt payload. "
                "You are not a story writer and not an image generator. Return JSON only.\n\n"
                "Guardrails:\n"
                "- Preserve the story beat exactly.\n"
                "- Do not add new characters.\n"
                "- Do not add objects not implied by the beat or selected references.\n"
                "- Do not invent story facts, brands, dialogue, or locations.\n"
                "- Do not over-stylize, do not write poetically, do not output keyword soup.\n"
                "- Keep each field short, visual, and focused.\n"
                "- If uncertain, stay minimal.\n"
                "- Never output asset IDs, filenames, manifest keys, JSON schema commentary, or internal metadata.\n"
                "- shot_priority must be one of identity, staging, object.\n"
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "Normalize this beat into the target JSON schema.\n"
                f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                f"Compact beat input:\n{json.dumps(compact_input, ensure_ascii=False, indent=2)}"
            ),
        ),
    ]


def validate_prompt_cleanup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    for field_name, limit in FIELD_LIMITS.items():
        cleaned = _sanitize_cleanup_field(field_name, payload.get(field_name), limit=limit)
        validated[field_name] = cleaned
    if not validated["shot_intent"]:
        raise ValueError("Prompt cleanup response is missing shot_intent.")
    if validated["shot_priority"] not in VALID_SHOT_PRIORITIES:
        raise ValueError("Prompt cleanup response is missing a valid shot_priority.")
    non_empty_fields = sum(1 for key, value in validated.items() if key != "negative_guidance" and value)
    if non_empty_fields < 3:
        raise ValueError("Prompt cleanup response is too sparse to use safely.")
    total_length = sum(len(str(value)) for value in validated.values())
    if total_length > 620:
        raise ValueError("Prompt cleanup response is too verbose.")
    return validated


def assemble_prompt_from_payload(payload: dict[str, Any]) -> str:
    ordered_fields = (
        "shot_intent",
        "framing",
        "performance",
        "scene",
        "essential_prop",
        "style_tail",
    )
    sections: list[str] = []
    seen: set[str] = set()
    for field_name in ordered_fields:
        text = _clean_sentence(payload.get(field_name))
        if not text:
            continue
        normalized = _normalize_for_dedupe(text)
        if normalized in seen or any(normalized in existing or existing in normalized for existing in seen):
            continue
        sections.append(text)
        seen.add(normalized)
    negative = _clean_sentence(payload.get("negative_guidance"))
    if negative:
        lowered_negative = negative.casefold()
        negative_text = negative
        if not lowered_negative.startswith(("avoid ", "no ", "without ")):
            negative_text = f"Avoid {negative}"
        normalized_negative = _normalize_for_dedupe(negative_text)
        if normalized_negative not in seen:
            sections.append(negative_text)
    cleaned_sections = [section.rstrip(". 。!！?？ ") for section in sections if section]
    return ". ".join(cleaned_sections).strip() + "."


def cleanup_prompt_with_gemini(
    *,
    repo_root: Path,
    skill: Any,
    compact_input: dict[str, Any],
    legacy_prompt: str,
    model_alias: str,
) -> PromptCleanupResult:
    try:
        config = load_config_from_env(repo_root, skill=skill, model_override=model_alias)
        route = describe_model_route(repo_root, skill=skill, model_override=model_alias)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        return PromptCleanupResult(
            mode="gemini",
            source="legacy",
            final_prompt=legacy_prompt,
            structured_input=compact_input,
            validated_payload=None,
            warning=f"Gemini prompt cleanup unavailable; using legacy prompt. {detail}",
            model_alias=model_alias,
            cleanup_status="config_error",
        )

    try:
        response = call_chat_completion(
            config,
            build_prompt_cleanup_messages(compact_input),
            json_mode=True,
            temperature=0.0,
        )
        payload = parse_json_response(response)
        validated = validate_prompt_cleanup_payload(payload)
        final_prompt = assemble_prompt_from_payload(validated)
        if len(final_prompt) < 24:
            raise ValueError("Prompt cleanup assembled an empty or too-short final prompt.")
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        raw_text = response.text if "response" in locals() else ""
        raw_json = response.raw_response if "response" in locals() else None
        return PromptCleanupResult(
            mode="gemini",
            source="legacy",
            final_prompt=legacy_prompt,
            structured_input=compact_input,
            validated_payload=None,
            raw_response_text=raw_text,
            raw_response_json=raw_json if isinstance(raw_json, dict) else None,
            warning=f"Gemini prompt cleanup failed; using legacy prompt. {detail}",
            model=getattr(response, "model", ""),
            route=route,
            model_alias=model_alias,
            cleanup_status="fallback",
        )

    return PromptCleanupResult(
        mode="gemini",
        source="gemini",
        final_prompt=final_prompt,
        structured_input=compact_input,
        validated_payload=validated,
        raw_response_text=response.text,
        raw_response_json=response.raw_response if isinstance(response.raw_response, dict) else None,
        model=response.model,
        route=route,
        model_alias=model_alias,
        shot_priority=str(validated.get("shot_priority") or ""),
        cleanup_status="success",
    )


def _compact_text(value: Any, *, limit: int) -> str:
    cleaned = _clean_sentence(value)
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit].rstrip(" ,;:，；：")
    return truncated


def _sanitize_cleanup_field(field_name: str, value: Any, *, limit: int) -> str:
    text = _clean_sentence(value)
    if not text:
        return ""
    lowered = text.casefold()
    if any(token in lowered for token in BANNED_METADATA_TOKENS):
        raise ValueError(f"Prompt cleanup field '{field_name}' leaked internal metadata.")
    if field_name == "shot_priority":
        normalized = lowered.replace("priority", "").strip(" -_:")
        aliases = {
            "identity": "identity",
            "identity_first": "identity",
            "character": "identity",
            "staging": "staging",
            "staging_first": "staging",
            "scene": "staging",
            "object": "object",
            "object_first": "object",
            "prop": "object",
        }
        return aliases.get(normalized, "")
    if len(text) > limit:
        raise ValueError(f"Prompt cleanup field '{field_name}' is too long.")
    return text


def _clean_sentence(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("`\"'{}[]")
    text = re.sub(r"^(shot_intent|framing|performance|scene|essential_prop|style_tail|shot_priority|negative_guidance)\s*:\s*", "", text, flags=re.I)
    return text.strip(" ,;:，；：")


def _normalize_for_dedupe(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())
