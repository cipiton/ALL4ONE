from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ltx_skill_module_loader import load_local_module


REQUIRED_FIELDS = (
    "episode_id",
    "shot_id",
    "shot_type",
    "shot_mode",
    "scene_setup",
    "action_sequence",
    "camera_motion",
    "duration_hint",
    "final_prompt",
)
STRUCTURED_FIELDS = (
    "character_definition",
    "environment_motion",
    "audio_description",
    "acting_cues",
)
RECAP_LIKE_TOKENS = (
    "画面强调",
    "象征",
    "预示",
    "意味着",
    "命运",
    "主题",
    "故事里",
    "这一段讲的是",
    "这说明",
    "传奇",
    "形成强反差",
    "代表着",
)
CAMERA_TOKENS = (
    "镜头",
    "机位",
    "推进",
    "拉远",
    "平移",
    "跟随",
    "手持",
    "静止",
    "越肩",
    "下倾",
    "上仰",
)
ACTION_TOKENS = (
    "追",
    "冲",
    "跑",
    "停",
    "逼近",
    "转头",
    "回头",
    "抬手",
    "抬眼",
    "摘",
    "说",
    "开口",
    "喊",
    "发力",
    "稳住",
    "抓",
    "握",
    "焊",
    "切",
    "推开",
    "压住",
    "滑",
    "甩",
    "走",
    "落下",
)
ABSTRACT_EMOTION_TOKENS = (
    "悲伤",
    "难过",
    "焦虑",
    "痛苦",
    "绝望",
    "紧张",
    "愤怒",
    "犹豫",
    "害怕",
    "伤感",
)
SLIDESHOW_PATTERNS = (
    re.compile(r"人物.*在.*地方.*(悲伤|焦虑|难过|绝望)"),
    re.compile(r"镜头里.*人物.*只是.*站着"),
    re.compile(r"^[^。]{0,60}(人物|角色|少年|张雪).*(悲伤|绝望|倔强)[。]?$"),
)
LONG_DURATION_MIN_CHARS = 120
DEFAULT_MAX_PROMPT_CHARS = 520


@dataclass(frozen=True, slots=True)
class PromptValidationResult:
    is_valid: bool
    issues: tuple[str, ...]
    stats: dict[str, Any]


def validate_generated_prompt_payload(payload: dict[str, Any]) -> PromptValidationResult:
    issues: list[str] = []
    if not isinstance(payload, dict):
        return PromptValidationResult(
            is_valid=False,
            issues=("payload is not a JSON object",),
            stats={},
        )

    for field_name in REQUIRED_FIELDS:
        value = normalize_text(payload.get(field_name))
        if not value:
            issues.append(f"missing required field: {field_name}")
    for field_name in STRUCTURED_FIELDS:
        if field_name not in payload:
            issues.append(f"missing structured field: {field_name}")

    final_prompt_raw = str(payload.get("final_prompt") or "")
    final_prompt = normalize_text(final_prompt_raw)
    sentence_count = count_sentences(final_prompt)
    duration_hint = normalize_text(payload.get("duration_hint"))
    shot_mode = normalize_text(payload.get("shot_mode"))
    prompt_language = normalize_text(payload.get("prompt_language") or "zh")
    min_sentences, max_sentences = expected_sentence_range(shot_mode=shot_mode, duration_hint=duration_hint)

    if not final_prompt:
        issues.append("final_prompt is empty")
    if "\n" in final_prompt_raw:
        issues.append("final_prompt must be a single paragraph")
    if len(final_prompt) > DEFAULT_MAX_PROMPT_CHARS:
        issues.append(f"final_prompt is too long ({len(final_prompt)} chars > {DEFAULT_MAX_PROMPT_CHARS})")
    if sentence_count < min_sentences:
        issues.append(f"final_prompt has too few sentences for the shot ({sentence_count} < {min_sentences})")
    if sentence_count > max_sentences:
        issues.append(f"final_prompt has too many sentences for the shot ({sentence_count} > {max_sentences})")
    if duration_hint == "4-6s" and len(final_prompt) < LONG_DURATION_MIN_CHARS:
        issues.append("final_prompt is too short for a longer clip")

    lowered = final_prompt.casefold()
    if any(token.casefold() in lowered for token in RECAP_LIKE_TOKENS):
        issues.append("final_prompt still looks recap-like instead of shot-action-focused")
    if not has_visible_action(payload):
        issues.append("final_prompt lacks a clear visible action progression")
    if not has_camera_language(payload):
        issues.append("final_prompt lacks camera movement or a clear static-frame choice")
    if looks_like_slideshow_prompt(final_prompt):
        issues.append("final_prompt still looks static or slideshow-like")
    if uses_abstract_emotion_without_cues(payload):
        issues.append("prompt relies on abstract emotion labels without visible acting cues")
    if prompt_language == "zh" and contains_mixed_language(final_prompt):
        issues.append("final_prompt mixes English into a Chinese prompt")

    return PromptValidationResult(
        is_valid=not issues,
        issues=tuple(issues),
        stats={
            "sentence_count": sentence_count,
            "character_count": len(final_prompt),
            "duration_hint": duration_hint,
            "shot_mode": shot_mode,
        },
    )


def validate_prompts_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"`items` array not found in {path}")
    per_shot: list[dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        result = validate_generated_prompt_payload(item)
        if result.is_valid:
            valid_count += 1
        else:
            invalid_count += 1
        per_shot.append(
            {
                "shot_id": item.get("shot_id"),
                "is_valid": result.is_valid,
                "issues": list(result.issues),
                "stats": result.stats,
            }
        )
    return {
        "prompts_file": str(path.resolve()),
        "item_count": len(per_shot),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "items": per_shot,
    }


def run_fallback_self_test(repo_root: Path) -> dict[str, Any]:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    build_ltx_prompt_request = load_local_module("build_ltx_prompt_requests").build_ltx_prompt_request
    direct_shot_prompt_with_gemini = load_local_module("gemini_prompt_director").direct_shot_prompt_with_gemini
    RecapShot = load_local_module("load_recap_production").RecapShot

    shot = RecapShot(
        shot_id="ep99_s01",
        episode_number=99,
        summary="张雪骑着黄摩托冲进暴雨乡道。",
        visual_prompt="暴雨乡道上，黄摩托冲起泥水，镜头继续跟住主体前进。",
        shot_type="wide shot",
        camera_motion="slow pan right",
        mood="urgent, stormy",
        anchor_text="他继续往前冲。",
        priority="high",
        beat_role="hook",
        pace_weight="short",
        asset_focus="interaction",
        source_payload={},
    )
    request = build_ltx_prompt_request(shot, total_shots=1, shot_index=1)

    class StubResponse:
        text = "{not-json"
        raw_response = {"choices": []}
        model = "google/gemini-2.5-flash"

    result = direct_shot_prompt_with_gemini(
        repo_root=repo_root,
        skill=None,
        request_payload=request,
        model_alias="gemini",
        llm_callable=lambda *args, **kwargs: StubResponse(),
    )
    validation = validate_generated_prompt_payload(result.payload)
    return {
        "status": result.status,
        "warning": result.warning,
        "fallback_reason": result.fallback_reason,
        "source": result.source,
        "payload": result.payload,
        "validation": {
            "is_valid": validation.is_valid,
            "issues": list(validation.issues),
            "stats": validation.stats,
        },
    }


def expected_sentence_range(*, shot_mode: str, duration_hint: str) -> tuple[int, int]:
    if shot_mode == "insert_prop_detail":
        return (4, 5)
    if shot_mode == "dialogue_speaking":
        return (5, 7)
    if duration_hint == "4-6s":
        return (5, 8)
    return (4, 8)


def count_sentences(text: str) -> int:
    sentences = [part.strip() for part in re.split(r"[。!?！？]+", text) if part.strip()]
    return len(sentences)


def has_visible_action(payload: dict[str, Any]) -> bool:
    action_sequence = normalize_text(payload.get("action_sequence"))
    final_prompt = normalize_text(payload.get("final_prompt"))
    text = f"{action_sequence} {final_prompt}"
    return any(token in text for token in ACTION_TOKENS)


def has_camera_language(payload: dict[str, Any]) -> bool:
    final_prompt = normalize_text(payload.get("final_prompt"))
    return any(token in final_prompt for token in CAMERA_TOKENS)


def looks_like_slideshow_prompt(final_prompt: str) -> bool:
    if count_sentences(final_prompt) <= 2:
        return True
    for pattern in SLIDESHOW_PATTERNS:
        if pattern.search(final_prompt):
            return True
    if "只是" in final_prompt and not any(token in final_prompt for token in ACTION_TOKENS):
        return True
    return False


def uses_abstract_emotion_without_cues(payload: dict[str, Any]) -> bool:
    final_prompt = normalize_text(payload.get("final_prompt"))
    acting_cues = normalize_text(payload.get("acting_cues"))
    if acting_cues:
        return False
    return any(token in final_prompt for token in ABSTRACT_EMOTION_TOKENS)


def contains_mixed_language(text: str) -> bool:
    words = re.findall(r"[A-Za-z]{3,}", text)
    return len(words) >= 2


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", " ").replace("\n", " ").split()).strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated LTX prompt outputs or run the malformed-Gemini fallback self-test.")
    parser.add_argument("path", nargs="?", help="Path to prompts.json or a generated_ltx_prompts output directory.")
    parser.add_argument("--self-test-fallback", action="store_true", help="Run a malformed-Gemini fallback test.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[3]
    if args.self_test_fallback:
        print(json.dumps(run_fallback_self_test(repo_root), ensure_ascii=False, indent=2))
        return 0
    if not args.path:
        raise ValueError("Provide a prompts.json path or use --self-test-fallback.")
    candidate = Path(args.path).expanduser().resolve()
    prompts_file = candidate / "prompts.json" if candidate.is_dir() else candidate
    print(json.dumps(validate_prompts_file(prompts_file), ensure_ascii=False, indent=2))
    return 0


def configure_utf8_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except OSError:
                continue


if __name__ == "__main__":
    raise SystemExit(main())
