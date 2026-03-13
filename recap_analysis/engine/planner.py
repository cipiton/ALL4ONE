from __future__ import annotations

from pathlib import Path

from .models import ExecutionPlan, InputDocument, LLMTask, ReferenceResource, SkillConfig

CHUNK_CHAR_THRESHOLD = 18_000
DEFAULT_CHUNK_SIZE = 12_000
DEFAULT_CHUNK_OVERLAP = 1_200


def build_execution_plan(skill_config: SkillConfig, document: InputDocument) -> ExecutionPlan:
    """Create an explicit execution plan from the skill and input facts."""
    llm_tasks = _build_llm_tasks(skill_config)
    references_to_load = _collect_references(llm_tasks)

    return ExecutionPlan(
        direct_read=True,
        needs_chunking=document.character_count > CHUNK_CHAR_THRESHOLD,
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
        input_facts={
            "file_name": document.path.name,
            "file_suffix": document.path.suffix.lower(),
            "character_count": document.character_count,
            "line_count": document.line_count,
            "estimated_tokens": document.estimated_tokens,
        },
        references_to_load=references_to_load,
        llm_tasks=llm_tasks,
        postprocess_tasks=["normalize_result", "format_report", "write_report"],
    )


def _build_llm_tasks(skill_config: SkillConfig) -> list[LLMTask]:
    adaptation_refs = _match_references(skill_config.referenced_files, ("adaptation", "规则"))
    episode_refs = _match_references(skill_config.referenced_files, ("episode", "集数"))

    tasks = [
        LLMTask(
            name="structural_summary",
            description="提取主题、情节、角色和故事类型。",
        ),
        LLMTask(
            name="adaptation_evaluation",
            description="依据改编规则评估适配度、评分和风险。",
            references=adaptation_refs,
            depends_on=["structural_summary"],
        ),
        LLMTask(
            name="episode_recommendation",
            description="依据集数指南计算推荐集数和拆分理由。",
            references=episode_refs,
            depends_on=["structural_summary"],
        ),
        LLMTask(
            name="audience_analysis",
            description="分析目标受众、兴趣偏好和消费场景。",
            depends_on=["structural_summary"],
        ),
        LLMTask(
            name="final_report_generation",
            description="综合前序结果并按技能要求组织最终报告。",
            depends_on=[
                "structural_summary",
                "adaptation_evaluation",
                "episode_recommendation",
                "audience_analysis",
            ],
        ),
    ]
    return tasks


def _collect_references(tasks: list[LLMTask]) -> list[ReferenceResource]:
    references: list[ReferenceResource] = []
    seen: set[Path] = set()
    for task in tasks:
        for ref in task.references:
            if not ref.exists or ref.absolute_path in seen:
                continue
            seen.add(ref.absolute_path)
            references.append(ref)
    return references


def _match_references(
    references: list[ReferenceResource], keywords: tuple[str, ...]
) -> list[ReferenceResource]:
    matched = []
    for reference in references:
        haystack = " ".join(
            [reference.name, reference.relative_path, reference.purpose, reference.when_to_read]
        ).lower()
        if any(keyword.lower() in haystack for keyword in keywords):
            matched.append(reference)
    return matched
