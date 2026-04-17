from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def discover_repo_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / "config.ini").exists():
            return candidate
    return start_dir.parents[3]


REPO_ROOT = discover_repo_root(SCRIPT_DIR)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from build_flux_prompts import PromptBuildResult
from engine.llm_client import LLMClientError, call_chat_completion, load_config_from_env, parse_json_response
from engine.models import PromptMessage
from prompt_language import contains_cjk, prompt_uses_single_language


REFERENCE_FILES = {
    "prompt_writing": "references/prompt-writing.md",
    "asset_prompting": "references/asset-prompting.md",
    "scene_prompting": "references/scene-prompting.md",
    "prompt_policy": "references/prompt-policy.md",
    "flux_prompting": "references/flux2-klein-prompting-application.md",
}


def author_asset_prompt(
    *,
    repo_root: Path,
    fallback_result: PromptBuildResult,
    style_target: str,
    final_prompt_language: str,
    skill_definition=None,
) -> PromptBuildResult:
    payload = {
        "mode": "asset",
        "style_target": style_target,
        "final_prompt_language": final_prompt_language,
        "structured_input": fallback_result.source_structured_input,
        "reference_roles": [],
    }
    return _author_flux_prompt(
        repo_root=repo_root,
        mode="asset",
        payload=payload,
        fallback_result=fallback_result,
        skill_definition=skill_definition,
    )


def author_keyscene_prompt(
    *,
    repo_root: Path,
    fallback_result: PromptBuildResult,
    style_target: str,
    final_prompt_language: str,
    reference_roles: list[dict[str, str]],
    skill_definition=None,
) -> PromptBuildResult:
    payload = {
        "mode": "keyscene",
        "style_target": style_target,
        "final_prompt_language": final_prompt_language,
        "structured_input": fallback_result.source_structured_input,
        "reference_roles": reference_roles,
    }
    return _author_flux_prompt(
        repo_root=repo_root,
        mode="keyscene",
        payload=payload,
        fallback_result=fallback_result,
        skill_definition=skill_definition,
    )


def _author_flux_prompt(
    *,
    repo_root: Path,
    mode: str,
    payload: dict[str, Any],
    fallback_result: PromptBuildResult,
    skill_definition=None,
) -> PromptBuildResult:
    reference_texts = load_authoring_references(mode)
    try:
        config = load_config_from_env(repo_root, skill=skill_definition, route_role="final_deliverable")
        response = call_chat_completion(
            config,
            build_authoring_messages(reference_texts=reference_texts, payload=payload),
            json_mode=True,
            temperature=0.2,
        )
        parsed = parse_json_response(response)
        resolved_prompt = normalize_prompt_text(parsed.get("prompt"))
        validation_error = validate_authored_prompt(resolved_prompt, payload["final_prompt_language"])
        if validation_error:
            raise LLMClientError(validation_error)
        return PromptBuildResult(
            prompt=resolved_prompt,
            prompt_source="LLM-authored FLUX klein prompt",
            confidence="llm_authored",
            notes=(
                *fallback_result.notes,
                f"Final prompt authored by the LLM for FLUX.2 klein scene-first prose prompting.",
                f"Prompt authoring model: {response.model}.",
            ),
            final_prompt_language=fallback_result.final_prompt_language,
            source_structured_input=fallback_result.source_structured_input,
            metadata={
                **fallback_result.metadata,
                "prompt_author": "llm",
                "authoring_model": response.model,
                "authoring_mode": mode,
                "reference_role_summary": payload.get("reference_roles", []),
                "deterministic_fallback_prompt": fallback_result.prompt,
                "fallback_used": False,
                "raw_llm_response": response.text,
            },
        )
    except Exception as exc:  # noqa: BLE001
        fallback_metadata = dict(fallback_result.metadata)
        fallback_metadata.update(
            {
                "prompt_author": "deterministic_fallback",
                "authoring_mode": mode,
                "reference_role_summary": payload.get("reference_roles", []),
                "fallback_used": True,
                "fallback_reason": str(exc),
                "deterministic_fallback_prompt": fallback_result.prompt,
            }
        )
        return PromptBuildResult(
            prompt=fallback_result.prompt,
            prompt_source=f"{fallback_result.prompt_source} (deterministic fallback after LLM authoring failure)",
            confidence=fallback_result.confidence,
            notes=(
                *fallback_result.notes,
                f"LLM prompt authoring failed; deterministic fallback was used: {exc}",
            ),
            final_prompt_language=fallback_result.final_prompt_language,
            source_structured_input=fallback_result.source_structured_input,
            metadata=fallback_metadata,
        )


def load_authoring_references(mode: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    skill_dir = SCRIPT_DIR.parent
    selected = ["prompt_writing", "prompt_policy", "flux_prompting", "asset_prompting" if mode == "asset" else "scene_prompting"]
    for key in selected:
        path = skill_dir / REFERENCE_FILES[key]
        refs[key] = path.read_text(encoding="utf-8")
    return refs


def build_authoring_messages(*, reference_texts: dict[str, str], payload: dict[str, Any]) -> list[PromptMessage]:
    language = str(payload.get("final_prompt_language") or "en")
    mode = str(payload.get("mode") or "asset")
    return [
        PromptMessage(
            role="system",
            content=(
                "You write the final FLUX.2 klein image-generation prompt.\n"
                "Return only JSON with this shape: {\"prompt\": \"...\"}.\n"
                "The prompt must be one flowing paragraph in exactly one language.\n"
                f"Required final prompt language: {language}.\n"
                "Do not return bullets, markdown, or explanations.\n\n"
                f"General prompt-writing rules:\n{reference_texts['prompt_writing']}\n\n"
                f"Mode-specific rules:\n{reference_texts['asset_prompting' if mode == 'asset' else 'scene_prompting']}\n\n"
                f"Prompt policy:\n{reference_texts['prompt_policy']}\n\n"
                f"FLUX klein application notes:\n{reference_texts['flux_prompting']}"
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "Write the final FLUX.2 klein prompt from this structured payload.\n"
                "Respect the reference roles when present.\n"
                "Keep the prompt scene-specific, prose-first, lighting-explicit, and not redundant with the references.\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        ),
    ]


def normalize_prompt_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text.strip()


def validate_authored_prompt(prompt: str, language: str) -> str | None:
    if not prompt:
        return "The LLM returned an empty prompt."
    if "\n\n" in prompt:
        return "The LLM returned multiple paragraphs."
    if language == "en" and contains_cjk(prompt):
        return "The LLM returned mixed-language or Chinese text for an English-only prompt."
    if language == "zh" and not prompt_uses_single_language(prompt, "zh"):
        return "The LLM returned mixed-language or English-heavy text for a Chinese-only prompt."
    if len(prompt) < 40:
        return "The LLM-authored prompt was too short for production use."
    return None
