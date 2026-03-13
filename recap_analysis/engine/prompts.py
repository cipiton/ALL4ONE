from __future__ import annotations

import json
from typing import Any

from .models import DocumentChunk, InputDocument, SkillConfig


def build_chunk_summary_messages(
    skill_config: SkillConfig,
    chunk: DocumentChunk,
    total_chunks: int,
) -> list[dict[str, str]]:
    distilled = distill_skill_context(skill_config, ("分析", "主题", "情节", "人物"))
    schema = {
        "chunk_id": chunk.chunk_id,
        "story_title": "string",
        "themes": ["string"],
        "plot_points": ["string"],
        "characters": ["string"],
        "story_type": "string",
        "tone": "string",
        "risks": ["string"],
    }
    return [
        {
            "role": "system",
            "content": "你是一个严谨的小说分析助手。只返回 JSON 对象，不要输出额外说明。",
        },
        {
            "role": "user",
            "content": (
                f"{distilled}\n\n"
                f"当前任务:为第 {chunk.index}/{total_chunks} 个文本分块生成结构化摘要。\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                f"文本分块:\n{chunk.text}"
            ),
        },
    ]


def build_summary_merge_messages(
    skill_config: SkillConfig,
    chunk_summaries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    distilled = distill_skill_context(skill_config, ("分析", "主题", "情节", "人物"))
    schema = {
        "story_title": "string",
        "story_theme": "string",
        "core_plot": "string",
        "character_setup": "string",
        "story_type": "string",
        "tone": "string",
        "plot_density": "高密度|中密度|低密度",
        "character_complexity": "复杂|中等|简单",
        "source_highlights": ["string"],
        "open_questions": ["string"],
    }
    return [
        {
            "role": "system",
            "content": "你负责合并多个小说摘要并产出统一 JSON。",
        },
        {
            "role": "user",
            "content": (
                f"{distilled}\n\n"
                f"请合并以下分块摘要，形成整本小说的统一结构化认知。\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                f"分块摘要:\n{json.dumps(chunk_summaries, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_structural_summary_messages(
    skill_config: SkillConfig,
    document: InputDocument,
) -> list[dict[str, str]]:
    distilled = distill_skill_context(skill_config, ("读取", "分析", "主题", "情节", "人物"))
    schema = {
        "story_title": "string",
        "story_theme": "string",
        "core_plot": "string",
        "character_setup": "string",
        "story_type": "string",
        "tone": "string",
        "plot_density": "高密度|中密度|低密度",
        "character_complexity": "复杂|中等|简单",
        "source_highlights": ["string"],
        "open_questions": ["string"],
    }
    return [
        {
            "role": "system",
            "content": "你负责为小说改编评估生成基础结构化摘要，只返回 JSON。",
        },
        {
            "role": "user",
            "content": (
                f"{distilled}\n\n"
                f"输入文档: {document.path.name}\n"
                f"字数: {document.character_count} 字符，约 {document.estimated_tokens} token-ish。\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                f"小说正文:\n{document.text}"
            ),
        },
    ]


def build_adaptation_evaluation_messages(
    skill_config: SkillConfig,
    structural_summary: dict[str, Any],
    reference_texts: dict[str, str],
) -> list[dict[str, str]]:
    distilled = distill_skill_context(skill_config, ("评估", "规则", "适配"))
    schema = {
        "score_breakdown": {
            "plot_integrity": 0,
            "character_distinctiveness": 0,
            "theme_expression": 0,
            "narrative_adaptability": 0,
            "content_compliance": 0,
        },
        "total_score": 0,
        "adaptation_level": "极高适配|高度适配|中度适配|低度适配|不适配",
        "strengths": ["string"],
        "risks": ["string"],
        "optimization_suggestions": ["string"],
    }
    refs = format_reference_texts(reference_texts)
    return [
        {
            "role": "system",
            "content": "你负责依据规则进行改编适配评估，只返回 JSON。",
        },
        {
            "role": "user",
            "content": (
                f"{distilled}\n\n"
                f"评估规则:\n{refs}\n\n"
                f"结构化摘要:\n{json.dumps(structural_summary, ensure_ascii=False, indent=2)}\n\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_episode_recommendation_messages(
    skill_config: SkillConfig,
    structural_summary: dict[str, Any],
    document: InputDocument,
    reference_texts: dict[str, str],
) -> list[dict[str, str]]:
    distilled = distill_skill_context(skill_config, ("推荐", "集数", "节奏"))
    schema = {
        "base_episode_estimate": "string",
        "recommended_episode_range": "string",
        "reasoning": ["string"],
        "pace_notes": ["string"],
        "assumptions": ["string"],
    }
    refs = format_reference_texts(reference_texts)
    return [
        {
            "role": "system",
            "content": "你负责给出 AI 解说剧集数建议，只返回 JSON。",
        },
        {
            "role": "user",
            "content": (
                f"{distilled}\n\n"
                f"集数指南:\n{refs}\n\n"
                f"输入规模: {document.character_count} 字符，约 {document.estimated_tokens} token-ish。\n"
                f"结构化摘要:\n{json.dumps(structural_summary, ensure_ascii=False, indent=2)}\n\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_audience_analysis_messages(
    skill_config: SkillConfig,
    structural_summary: dict[str, Any],
) -> list[dict[str, str]]:
    distilled = distill_skill_context(skill_config, ("受众", "年龄", "兴趣"))
    schema = {
        "target_age_group": "string",
        "interest_preferences": ["string"],
        "viewing_scenarios": ["string"],
        "audience_fit_explanation": "string",
    }
    return [
        {
            "role": "system",
            "content": "你负责受众画像分析，只返回 JSON。",
        },
        {
            "role": "user",
            "content": (
                f"{distilled}\n\n"
                f"结构化摘要:\n{json.dumps(structural_summary, ensure_ascii=False, indent=2)}\n\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_final_report_messages(
    skill_config: SkillConfig,
    document: InputDocument,
    stage_outputs: dict[str, Any],
) -> list[dict[str, str]]:
    schema = {
        "sections": {
            "小说名称": "string",
            "故事主题": "string",
            "核心情节": "string",
            "人物设定": "string",
            "改编适配度评估": "string",
            "推荐集数": "string",
            "目标受众": "string",
            "风险点": "string",
            "结论": "string",
        }
    }
    output_expectations = "\n".join(f"- {item}" for item in skill_config.output_expectations) or "- 文本格式输出"
    return [
        {
            "role": "system",
            "content": "你负责整合分析结果并生成最终报告结构，只返回 JSON。",
        },
        {
            "role": "user",
            "content": (
                f"技能名称: {skill_config.name}\n"
                f"技能描述: {skill_config.description}\n"
                f"输出要求:\n{output_expectations}\n\n"
                f"输入文档: {document.path.name}\n"
                f"阶段结果:\n{json.dumps(stage_outputs, ensure_ascii=False, indent=2)}\n\n"
                f"请整理为稳定的最终报告 sections。\n"
                f"输出 JSON Schema 示例:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def distill_skill_context(skill_config: SkillConfig, keywords: tuple[str, ...]) -> str:
    lines = [
        f"技能名称: {skill_config.name}",
        f"技能描述: {skill_config.description}",
    ]

    for step in skill_config.workflow_steps:
        if any(keyword in step for keyword in keywords):
            lines.append(f"相关步骤: {step}")

    for note in skill_config.notes:
        if any(keyword in note for keyword in keywords) or "文本" in note:
            lines.append(f"注意事项: {note}")

    if not any(line.startswith("相关步骤") for line in lines):
        lines.extend(f"步骤参考: {step}" for step in skill_config.workflow_steps[:3])

    return "\n".join(lines)


def format_reference_texts(reference_texts: dict[str, str]) -> str:
    if not reference_texts:
        return "未提供额外参考文件。"
    return "\n\n".join(
        f"[{path}]\n{text.strip()}" for path, text in reference_texts.items()
    )
