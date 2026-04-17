from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.llm_client import call_chat_completion, describe_model_route, load_config_from_env, parse_json_response

from ltx_skill_module_loader import load_local_module

_build_ltx_prompt_requests = load_local_module("build_ltx_prompt_requests")
_validate_ltx_prompts = load_local_module("validate_ltx_prompts")

LtxPromptRequest = _build_ltx_prompt_requests.LtxPromptRequest
assemble_final_prompt_from_payload = _build_ltx_prompt_requests.assemble_final_prompt_from_payload
validate_generated_prompt_payload = _validate_ltx_prompts.validate_generated_prompt_payload

FIELD_LIMITS = {
    "episode_id": 16,
    "shot_id": 24,
    "shot_type": 32,
    "shot_mode": 32,
    "scene_setup": 80,
    "character_definition": 80,
    "action_sequence": 120,
    "camera_motion": 80,
    "environment_motion": 80,
    "audio_description": 64,
    "acting_cues": 72,
    "duration_hint": 8,
}
NORMALIZED_SHOT_TYPES = {
    "wide shot",
    "medium shot",
    "medium close-up",
    "close-up",
    "over-the-shoulder",
    "insert shot",
    "montage shot",
    "shot",
}
NORMALIZED_SHOT_MODES = {
    "closeup_emotion",
    "dialogue_speaking",
    "insert_prop_detail",
    "staging_environment",
    "action_movement",
}


@dataclass(frozen=True, slots=True)
class PromptDirectorResult:
    status: str
    source: str
    payload: dict[str, str]
    warning: str = ""
    fallback_reason: str = ""
    model_alias: str = ""
    model: str = ""
    route: str = ""
    raw_response_text: str = ""
    raw_response_json: dict[str, Any] | None = None


def direct_shot_prompt_with_gemini(
    *,
    repo_root: Path,
    skill: Any,
    request_payload: LtxPromptRequest,
    model_alias: str,
    llm_callable: Callable[..., Any] = call_chat_completion,
) -> PromptDirectorResult:
    try:
        config = load_config_from_env(repo_root, skill=skill, model_override=model_alias)
        route = describe_model_route(repo_root, skill=skill, model_override=model_alias)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        return PromptDirectorResult(
            status="config_error",
            source="fallback",
            payload=request_payload.fallback_payload,
            warning=f"Gemini prompt director unavailable; using fallback prompt. {detail}",
            fallback_reason="config_error",
            model_alias=model_alias,
        )

    try:
        response = llm_callable(
            config,
            request_payload.messages,
            json_mode=True,
            temperature=0.0,
        )
        parsed = parse_json_response(response)
        payload = validate_and_normalize_payload(parsed, fallback=request_payload.fallback_payload)
        validation = validate_generated_prompt_payload(payload)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.issues))
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        raw_text = response.text if "response" in locals() else ""
        raw_json = response.raw_response if "response" in locals() and isinstance(response.raw_response, dict) else None
        return PromptDirectorResult(
            status="fallback",
            source="fallback",
            payload=request_payload.fallback_payload,
            warning=f"Gemini returned invalid shot JSON; using fallback prompt. {detail}",
            fallback_reason=detail,
            model_alias=model_alias,
            model=getattr(response, "model", ""),
            route=route,
            raw_response_text=raw_text,
            raw_response_json=raw_json,
        )

    return PromptDirectorResult(
        status="success",
        source="gemini",
        payload=payload,
        model_alias=model_alias,
        model=getattr(response, "model", ""),
        route=route,
        raw_response_text=response.text,
        raw_response_json=response.raw_response if isinstance(response.raw_response, dict) else None,
    )


def validate_and_normalize_payload(payload: dict[str, Any], *, fallback: dict[str, str]) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("Prompt-director response was not a JSON object.")

    normalized: dict[str, str] = {}
    for key, default_value in fallback.items():
        if key == "final_prompt":
            continue
        value = payload.get(key, default_value)
        text = normalize_text(value)
        limit = FIELD_LIMITS.get(key)
        if limit and len(text) > limit:
            text = text[:limit].rstrip("，,；;。 ")
        normalized[key] = text or default_value

    if normalized["shot_type"].casefold() not in NORMALIZED_SHOT_TYPES:
        normalized["shot_type"] = fallback["shot_type"]
    if normalized["shot_mode"] not in NORMALIZED_SHOT_MODES:
        normalized["shot_mode"] = fallback["shot_mode"]
    if not normalized["duration_hint"].endswith("s"):
        normalized["duration_hint"] = fallback["duration_hint"]

    # The final prompt is assembled deterministically from the structured fields so
    # weak Gemini paragraph formatting does not leak recap-like output downstream.
    normalized["final_prompt"] = assemble_final_prompt_from_payload(normalized)
    normalized["prompt_language"] = "zh"
    normalized["raw_gemini_final_prompt"] = normalize_text(payload.get("final_prompt"))
    return normalized


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", " ").replace("\n", " ").split()).strip()
