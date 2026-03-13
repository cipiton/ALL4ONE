"""Routing logic for selecting the correct workflow step."""

from __future__ import annotations

from typing import Iterable

from engine.models import SkillDefinition, StepDetectionResult


def detect_step(
    input_text: str,
    skill_definition: SkillDefinition,
    resumed_step_hint: int | None = None,
) -> StepDetectionResult:
    """Infer the workflow step using input heuristics and resume hints."""
    text = input_text.strip()
    lowered = text.lower()
    nonempty_lines = [line.strip() for line in text.splitlines() if line.strip()]

    asset_keywords = (
        "角色",
        "场景",
        "道具",
        "提示词",
        "音色",
        "seed",
        "资产",
        "配置",
        "character",
        "scene",
        "prop",
        "asset",
        "prompt",
        "voice",
        "config",
    )
    script_keywords = (
        "旁白",
        "对白",
        "分镜",
        "内景",
        "外景",
        "场次",
        "第1集",
        "第01集",
        "幕",
        "台词",
        "script",
        "dialogue",
        "narration",
        "episode",
        "act ",
    )
    synopsis_keywords = (
        "梗概",
        "大纲",
        "简介",
        "故事",
        "设定",
        "分析",
        "outline",
        "synopsis",
        "story",
        "analysis",
        "premise",
    )

    asset_score = _keyword_score(lowered, asset_keywords)
    script_score = _keyword_score(lowered, script_keywords)
    synopsis_score = _keyword_score(lowered, synopsis_keywords)
    looks_like_list = sum(1 for line in nonempty_lines if _looks_like_list_item(line)) >= 4
    looks_like_script = script_score >= 2 or _has_script_shape(nonempty_lines)
    looks_like_assets = asset_score >= 2 and looks_like_list

    if resumed_step_hint in skill_definition.steps and resumed_step_hint is not None:
        return StepDetectionResult(
            step_number=resumed_step_hint,
            reason=f"Resumed state suggests step {resumed_step_hint}.",
            resembles_asset_inventory=looks_like_assets,
            resembles_script=looks_like_script,
        )

    if looks_like_assets or ("生图配置" in text) or ("配置文件" in text):
        return StepDetectionResult(
            step_number=3,
            reason="Input looks like an asset/config inventory.",
            resembles_asset_inventory=True,
        )

    if looks_like_script or "提炼资产" in text or "already-written script" in lowered:
        return StepDetectionResult(
            step_number=2,
            reason="Input looks like a finished script that should move to asset extraction.",
            resembles_script=True,
        )

    needs_episode_count = synopsis_score > 0 or script_score == 0
    is_rewrite_task = "影视剧剧本" in text or "改写" in text or "rewrite" in lowered
    return StepDetectionResult(
        step_number=1,
        reason="Input looks like a synopsis, outline, or story analysis.",
        needs_episode_count=needs_episode_count and not is_rewrite_task,
        is_rewrite_task=is_rewrite_task,
        resembles_script=looks_like_script,
    )


def _keyword_score(text: str, keywords: Iterable[str]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _looks_like_list_item(line: str) -> bool:
    prefixes = ("-", "*", "•", "1.", "2.", "3.", "4.", "5.", "一、", "二、", "三、")
    return line.startswith(prefixes) or ":" in line or "：" in line


def _has_script_shape(lines: list[str]) -> bool:
    markers = 0
    for line in lines[:20]:
        if any(token in line for token in ("旁白", "对白", "台词", "内景", "外景", "角色", "场次", "第")):
            markers += 1
    return markers >= 3
