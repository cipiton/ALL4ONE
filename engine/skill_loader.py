from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import (
    ChunkingConfig,
    OutputConfig,
    ReferenceDefinition,
    RuntimeInputDefinition,
    SkillDefinition,
    SkillStep,
    SkillSummary,
    StructuredStage,
)


class SkillLoadError(RuntimeError):
    """Raised when a skill cannot be discovered or parsed."""


def discover_skills(repo_root: Path) -> list[SkillSummary]:
    skills_root = repo_root / "skills"
    if not skills_root.exists():
        raise SkillLoadError(f"Skills directory not found: {skills_root}")

    summaries: list[SkillSummary] = []
    for candidate in sorted(skills_root.iterdir(), key=lambda path: path.name.casefold()):
        if not candidate.is_dir():
            continue
        skill_md_path = candidate / "SKILL.md"
        if not skill_md_path.exists():
            continue
        skill = load_skill(candidate)
        summaries.append(
            SkillSummary(
                name=skill.name,
                display_name=skill.display_name,
                description=skill.description,
                skill_dir=candidate,
            )
        )
    if not summaries:
        raise SkillLoadError(f"No valid skills found in {skills_root}")
    return summaries


def load_skill(skill_dir: Path) -> SkillDefinition:
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise SkillLoadError(f"SKILL.md not found in {skill_dir}")

    raw_text = skill_md_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw_text)
    if not isinstance(frontmatter, dict):
        raise SkillLoadError(f"Invalid frontmatter in {skill_md_path}")

    steps = _load_steps(frontmatter, skill_dir, body)
    references = _load_references(frontmatter, skill_dir, steps)
    stages = _load_stages(frontmatter)
    chunking = _load_chunking(frontmatter)
    output_config = _load_output_config(frontmatter)
    runtime_inputs = _load_runtime_inputs(frontmatter)
    name = str(frontmatter.get("name") or skill_dir.name)
    display_name = str(frontmatter.get("display_name") or name)
    description = str(frontmatter.get("description") or _extract_title(body) or name)
    execution = frontmatter.get("execution", {}) or {}
    strategy = str(execution.get("strategy") or ("structured_report" if stages else "step_prompt"))

    return SkillDefinition(
        name=name,
        display_name=display_name,
        description=description,
        skill_dir=skill_dir,
        skill_md_path=skill_md_path,
        body=body.strip(),
        supports_resume=bool(frontmatter.get("supports_resume", False)),
        execution_strategy=strategy,
        steps=steps,
        runtime_inputs=runtime_inputs,
        references=references,
        stages=stages,
        chunking=chunking,
        output_config=output_config,
        input_extensions=[str(item).lower() for item in frontmatter.get("input_extensions", [".txt"])],
        folder_mode=str(frontmatter.get("folder_mode", "non_recursive")),
    )


def load_reference_texts(skill: SkillDefinition, reference_ids: list[str]) -> dict[str, str]:
    loaded: dict[str, str] = {}
    for reference_id in reference_ids:
        reference = skill.get_reference(reference_id)
        if not reference.absolute_path.exists():
            raise SkillLoadError(
                f"Referenced file '{reference.relative_path}' is missing for skill '{skill.name}'."
            )
        try:
            loaded[reference_id] = reference.absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            loaded[reference_id] = reference.absolute_path.read_text(encoding="utf-8-sig")
    return loaded


def _split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    if not raw_text.startswith("---"):
        return {}, raw_text
    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        return {}, raw_text
    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip()
    return frontmatter, body


def _load_steps(frontmatter: dict[str, Any], skill_dir: Path, body: str) -> dict[int, SkillStep]:
    raw_steps = frontmatter.get("steps")
    if not raw_steps:
        return _infer_steps_from_body(skill_dir, body)

    steps: dict[int, SkillStep] = {}
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        number = int(raw_step["number"])
        steps[number] = SkillStep(
            number=number,
            title=str(raw_step.get("title") or f"Step {number}"),
            prompt_reference_id=_optional_string(raw_step.get("prompt_reference")),
            description=str(raw_step.get("description", "")),
            route_keywords_any=_to_string_list(raw_step.get("route_keywords_any")),
            route_keywords_all=_to_string_list(raw_step.get("route_keywords_all")),
            route_priority=int(raw_step.get("route_priority", 0)),
            requires_list_like=bool(raw_step.get("requires_list_like", False)),
            requires_script_like=bool(raw_step.get("requires_script_like", False)),
            default=bool(raw_step.get("default", False)),
        )
    if not steps:
        raise SkillLoadError("Skill defines no runnable steps.")
    return steps


def _load_references(
    frontmatter: dict[str, Any],
    skill_dir: Path,
    steps: dict[int, SkillStep],
) -> dict[str, ReferenceDefinition]:
    raw_references = frontmatter.get("references", []) or []
    references: dict[str, ReferenceDefinition] = {}
    for raw_reference in raw_references:
        if not isinstance(raw_reference, dict):
            continue
        relative_path = str(raw_reference["path"]).replace("\\", "/")
        reference_id = str(raw_reference.get("id") or Path(relative_path).stem.replace("-", "_"))
        absolute_path = skill_dir / Path(relative_path)
        references[reference_id] = ReferenceDefinition(
            reference_id=reference_id,
            relative_path=relative_path,
            absolute_path=absolute_path,
            kind=str(raw_reference.get("kind", "reference")),
            description=str(raw_reference.get("description", "")),
            step_numbers=[int(item) for item in raw_reference.get("step_numbers", [])],
            stage_names=_to_string_list(raw_reference.get("stage_names")),
            load=str(raw_reference.get("load", "auto")),
        )

    for step in steps.values():
        if step.prompt_reference_id and step.prompt_reference_id not in references:
            raise SkillLoadError(
                f"Step {step.number} references unknown prompt '{step.prompt_reference_id}'."
            )
    return references


def _load_runtime_inputs(frontmatter: dict[str, Any]) -> list[RuntimeInputDefinition]:
    definitions: list[RuntimeInputDefinition] = []
    for raw_definition in frontmatter.get("runtime_inputs", []) or []:
        if not isinstance(raw_definition, dict):
            continue
        definitions.append(
            RuntimeInputDefinition(
                name=str(raw_definition["name"]),
                prompt=str(raw_definition["prompt"]),
                field_type=str(raw_definition.get("type", "string")),
                required=bool(raw_definition.get("required", True)),
                step_numbers=[int(item) for item in raw_definition.get("step_numbers", [])],
                choices=_to_string_list(raw_definition.get("choices")),
                default=raw_definition.get("default"),
                min_value=_optional_int(raw_definition.get("min")),
                max_value=_optional_int(raw_definition.get("max")),
                help_text=str(raw_definition.get("help_text", "")),
                skip_if_input_contains_any=_to_string_list(raw_definition.get("skip_if_input_contains_any")),
                require_if_input_contains_any=_to_string_list(raw_definition.get("require_if_input_contains_any")),
            )
        )
    return definitions


def _load_stages(frontmatter: dict[str, Any]) -> list[StructuredStage]:
    execution = frontmatter.get("execution", {}) or {}
    raw_stages = execution.get("stages", []) or []
    stages: list[StructuredStage] = []
    for raw_stage in raw_stages:
        if not isinstance(raw_stage, dict):
            continue
        stages.append(
            StructuredStage(
                name=str(raw_stage["name"]),
                kind=str(raw_stage.get("kind", "context_json")),
                objective=str(raw_stage.get("objective", "")),
                schema=dict(raw_stage.get("schema", {}) or {}),
                input_keys=_to_string_list(raw_stage.get("input_keys")),
                reference_ids=_to_string_list(raw_stage.get("reference_ids")),
                chunkable=bool(raw_stage.get("chunkable", False)),
                merge_objective=str(raw_stage.get("merge_objective", "")),
                merge_schema=dict(raw_stage.get("merge_schema", {}) or {}),
            )
        )
    return stages


def _load_chunking(frontmatter: dict[str, Any]) -> ChunkingConfig:
    execution = frontmatter.get("execution", {}) or {}
    raw_chunking = execution.get("chunking", {}) or {}
    return ChunkingConfig(
        enabled=bool(raw_chunking.get("enabled", True)),
        threshold_chars=int(raw_chunking.get("threshold_chars", 18_000)),
        chunk_size=int(raw_chunking.get("chunk_size", 12_000)),
        overlap=int(raw_chunking.get("overlap", 1_200)),
    )


def _load_output_config(frontmatter: dict[str, Any]) -> OutputConfig:
    raw_output = frontmatter.get("output", {}) or {}
    return OutputConfig(
        mode=str(raw_output.get("mode", "text")),
        filename_template=str(raw_output.get("filename_template", "output.txt")),
        sections=_to_string_list(raw_output.get("sections")),
        include_prompt_dump=bool(raw_output.get("include_prompt_dump", True)),
    )


def _infer_steps_from_body(skill_dir: Path, body: str) -> dict[int, SkillStep]:
    pattern = re.compile(r"references/(step(\d+)-prompt\.md)")
    steps: dict[int, SkillStep] = {}
    for match in pattern.finditer(body):
        prompt_file = match.group(1)
        step_number = int(match.group(2))
        reference_id = Path(prompt_file).stem.replace("-", "_")
        steps[step_number] = SkillStep(
            number=step_number,
            title=f"Step {step_number}",
            prompt_reference_id=reference_id,
            default=step_number == 1,
        )
    if steps:
        return steps

    return {
        1: SkillStep(
            number=1,
            title=_extract_title(body) or skill_dir.name,
            default=True,
        )
    }


def _extract_title(body: str) -> str:
    match = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _to_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
