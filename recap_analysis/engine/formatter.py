from __future__ import annotations

from typing import Any

from .models import AnalysisResult, InputDocument, SkillConfig

DEFAULT_VALUE = "未明确提及"
DEFAULT_SECTION_ORDER = [
    "小说名称",
    "故事主题",
    "核心情节",
    "人物设定",
    "改编适配度评估",
    "推荐集数",
    "目标受众",
    "风险点",
    "结论",
]


def finalize_report(
    result: AnalysisResult,
    *,
    skill_config: SkillConfig,
    document: InputDocument,
) -> AnalysisResult:
    """Normalize model output and render a plain-text report."""
    stage_outputs = result.stage_outputs
    structural = stage_outputs.get("structural_summary", {})
    adaptation = stage_outputs.get("adaptation_evaluation", {})
    episode = stage_outputs.get("episode_recommendation", {})
    audience = stage_outputs.get("audience_analysis", {})
    final_sections = dict(result.final_sections or {})

    defaults = {
        "小说名称": _coalesce(
            final_sections.get("小说名称"),
            structural.get("story_title"),
            document.path.stem,
        ),
        "故事主题": _coalesce(
            final_sections.get("故事主题"),
            structural.get("story_theme"),
        ),
        "核心情节": _coalesce(
            final_sections.get("核心情节"),
            structural.get("core_plot"),
        ),
        "人物设定": _coalesce(
            final_sections.get("人物设定"),
            structural.get("character_setup"),
        ),
        "改编适配度评估": _coalesce(
            final_sections.get("改编适配度评估"),
            _format_adaptation(adaptation),
        ),
        "推荐集数": _coalesce(
            final_sections.get("推荐集数"),
            _format_episode(episode),
        ),
        "目标受众": _coalesce(
            final_sections.get("目标受众"),
            _format_audience(audience),
        ),
        "风险点": _coalesce(
            final_sections.get("风险点"),
            _join_lines(adaptation.get("risks")),
        ),
        "结论": _coalesce(
            final_sections.get("结论"),
            _build_conclusion(adaptation, episode, audience),
        ),
    }

    normalized_sections = {section: defaults.get(section, DEFAULT_VALUE) for section in DEFAULT_SECTION_ORDER}
    for key, value in final_sections.items():
        if key not in normalized_sections:
            normalized_sections[key] = _stringify(value)

    report_lines = [
        f"技能: {skill_config.name}",
        f"输入文件: {document.path.name}",
        f"model: {_stringify(result.metadata.get('model'))}",
        "",
    ]
    for section in DEFAULT_SECTION_ORDER:
        report_lines.append(f"{section}")
        report_lines.append(normalized_sections.get(section, DEFAULT_VALUE))
        report_lines.append("")

    extra_sections = [key for key in normalized_sections if key not in DEFAULT_SECTION_ORDER]
    for section in extra_sections:
        report_lines.append(section)
        report_lines.append(normalized_sections[section] or DEFAULT_VALUE)
        report_lines.append("")

    result.final_sections = normalized_sections
    result.final_report_text = "\n".join(report_lines).rstrip() + "\n"
    return result


def _format_adaptation(adaptation: dict[str, Any]) -> str:
    if not adaptation:
        return DEFAULT_VALUE
    level = adaptation.get("adaptation_level", DEFAULT_VALUE)
    score = adaptation.get("total_score", DEFAULT_VALUE)
    strengths = _join_lines(adaptation.get("strengths"))
    suggestions = _join_lines(adaptation.get("optimization_suggestions"))
    return f"总分: {score}；适配度: {level}。优势: {strengths}。优化建议: {suggestions}"


def _format_episode(episode: dict[str, Any]) -> str:
    if not episode:
        return DEFAULT_VALUE
    base = episode.get("base_episode_estimate", DEFAULT_VALUE)
    recommended = episode.get("recommended_episode_range", DEFAULT_VALUE)
    reasoning = _join_lines(episode.get("reasoning"))
    return f"基础估算: {base}；推荐集数: {recommended}。依据: {reasoning}"


def _format_audience(audience: dict[str, Any]) -> str:
    if not audience:
        return DEFAULT_VALUE
    age = audience.get("target_age_group", DEFAULT_VALUE)
    interests = _join_lines(audience.get("interest_preferences"))
    scenarios = _join_lines(audience.get("viewing_scenarios"))
    explanation = audience.get("audience_fit_explanation", DEFAULT_VALUE)
    return f"年龄层: {age}；兴趣偏好: {interests}；观看场景: {scenarios}。说明: {explanation}"


def _build_conclusion(
    adaptation: dict[str, Any],
    episode: dict[str, Any],
    audience: dict[str, Any],
) -> str:
    level = adaptation.get("adaptation_level", DEFAULT_VALUE)
    recommended = episode.get("recommended_episode_range", DEFAULT_VALUE)
    age = audience.get("target_age_group", DEFAULT_VALUE)
    return f"综合判断为{level}，建议按 {recommended} 规划解说剧体量，核心受众以 {age} 为主。"


def _join_lines(value: Any) -> str:
    if isinstance(value, list):
        cleaned = [_stringify(item) for item in value if _stringify(item)]
        return "；".join(cleaned) if cleaned else DEFAULT_VALUE
    return _stringify(value)


def _coalesce(*values: Any) -> str:
    for value in values:
        text = _stringify(value)
        if text and text != DEFAULT_VALUE:
            return text
    return DEFAULT_VALUE


def _stringify(value: Any) -> str:
    if value is None:
        return DEFAULT_VALUE
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or DEFAULT_VALUE
    return str(value).strip() or DEFAULT_VALUE
