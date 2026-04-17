from __future__ import annotations

import json
import os
import sys
from pathlib import Path

reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(reconfigure):
    reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import prompt_cleanup as cleanup
from engine.models import LLMConfig, LLMResponse
from run_keyscene_kontext import _extract_beats, _load_json, build_legacy_prompt


def main() -> int:
    storyboard = _load_json(
        REPO_ROOT / "outputs" / "stories" / "zxmoto" / "20260414_102315" / "04_recap_to_comfy_bridge" / "videoarc_storyboard.json"
    )
    beat = next(beat for beat in _extract_beats(storyboard) if beat.get("shot_id") == "ep01_s06")
    compact_input = cleanup.build_prompt_cleanup_input(
        beat=beat,
        selected_assets={
            "character": {"asset_name": "张雪", "kind": "character"},
            "scene": {"asset_name": "加油站", "kind": "scene"},
            "prop": {"asset_name": "摄像机", "kind": "prop"},
        },
    )
    legacy_prompt = build_legacy_prompt(beat)

    good_payload = {
        "shot_intent": "张雪在加油站灯下直视镜头，要求记者拍摄发动机。",
        "framing": "medium close-up, 张雪与摄像机同框，发动机位于前景边缘。",
        "performance": "眼神灼热，身体前倾，姿态强硬克制。",
        "scene": "夜间加油站冷白灯光，地面潮湿，空气里有雨后水汽。",
        "essential_prop": "摄像机和裸露发动机细节。",
        "style_tail": "cinematic realism",
        "shot_priority": "identity",
        "negative_guidance": "no subtitles or watermark",
    }
    validated_payload = cleanup.validate_prompt_cleanup_payload(good_payload)
    assembled_prompt = cleanup.assemble_prompt_from_payload(validated_payload)

    original_load = cleanup.load_config_from_env
    original_describe = cleanup.describe_model_route
    original_call = cleanup.call_chat_completion
    original_parse = cleanup.parse_json_response
    try:
        cleanup.load_config_from_env = lambda *args, **kwargs: LLMConfig(  # type: ignore[assignment]
            provider="openrouter",
            api_key="test",
            model="google/gemini-2.5-flash",
            base_url="https://example.com",
            timeout=10,
            max_retries=1,
            headers={},
        )
        cleanup.describe_model_route = lambda *args, **kwargs: "step override: openrouter / google/gemini-2.5-flash (step override)"  # type: ignore[assignment]
        cleanup.call_chat_completion = lambda *args, **kwargs: LLMResponse(  # type: ignore[assignment]
            text=json.dumps(good_payload, ensure_ascii=False),
            model="google/gemini-2.5-flash",
            raw_response={"choices": [{"message": {"content": json.dumps(good_payload, ensure_ascii=False)}}]},
        )
        cleanup.parse_json_response = lambda response: json.loads(response.text)  # type: ignore[assignment]
        success_result = cleanup.cleanup_prompt_with_gemini(
            repo_root=REPO_ROOT,
            skill=None,
            compact_input=compact_input,
            legacy_prompt=legacy_prompt,
            model_alias="gemini",
        )

        cleanup.call_chat_completion = lambda *args, **kwargs: LLMResponse(  # type: ignore[assignment]
            text="not-json",
            model="google/gemini-2.5-flash",
            raw_response={"choices": [{"message": {"content": "not-json"}}]},
        )
        cleanup.parse_json_response = lambda response: (_ for _ in ()).throw(ValueError("Model returned invalid JSON: not-json"))  # type: ignore[assignment]
        fallback_result = cleanup.cleanup_prompt_with_gemini(
            repo_root=REPO_ROOT,
            skill=None,
            compact_input=compact_input,
            legacy_prompt=legacy_prompt,
            model_alias="gemini",
        )
    finally:
        cleanup.load_config_from_env = original_load  # type: ignore[assignment]
        cleanup.describe_model_route = original_describe  # type: ignore[assignment]
        cleanup.call_chat_completion = original_call  # type: ignore[assignment]
        cleanup.parse_json_response = original_parse  # type: ignore[assignment]

    report = {
        "live_openrouter_key_present": bool(os.getenv("OPENROUTER_API_KEY")),
        "compact_input_keys": sorted(compact_input.keys()),
        "assembled_prompt": assembled_prompt,
        "legacy_prompt_length": len(legacy_prompt),
        "assembled_prompt_length": len(assembled_prompt),
        "shorter_than_legacy": len(assembled_prompt) < len(legacy_prompt),
        "success_result": {
            "cleanup_status": success_result.cleanup_status,
            "source": success_result.source,
            "shot_priority": success_result.shot_priority,
            "final_prompt": success_result.final_prompt,
        },
        "fallback_result": {
            "cleanup_status": fallback_result.cleanup_status,
            "source": fallback_result.source,
            "warning": fallback_result.warning,
            "final_prompt_matches_legacy": fallback_result.final_prompt == legacy_prompt,
        },
        "empty_section_omitted": "  " not in assembled_prompt and "{}" not in assembled_prompt,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
