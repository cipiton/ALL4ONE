from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import (
    ChunkingConfig,
    OutputConfig,
    ReferenceDefinition,
    SkillInputBlock,
    RuntimeInputDefinition,
    SkillDefinition,
    SkillExecutionPolicy,
    SkillRegistryEntry,
    SkillStartupPolicy,
    SkillStep,
    SkillSummary,
    StructuredStage,
    UtilityScriptConfig,
)


class SkillLoadError(RuntimeError):
    """Raised when a skill cannot be discovered or parsed."""


def discover_skills(repo_root: Path) -> list[SkillSummary]:
    skills_root = repo_root / "skills"
    if not skills_root.exists():
        raise SkillLoadError(f"Skills directory not found: {skills_root}")

    registry_path = skills_root / "registry.yaml"
    if registry_path.exists():
        return _discover_skills_from_registry(repo_root, registry_path)

    return _discover_skills_from_directories(skills_root)


def _discover_skills_from_directories(skills_root: Path) -> list[SkillSummary]:
    summaries: list[SkillSummary] = []
    for candidate in sorted(skills_root.iterdir(), key=lambda path: path.name.casefold()):
        if not candidate.is_dir():
            continue
        skill_md_path = candidate / "SKILL.md"
        if not skill_md_path.exists():
            continue
        skill = load_skill(candidate)
        summaries.append(_build_skill_summary(skill))
    if not summaries:
        raise SkillLoadError(f"No valid skills found in {skills_root}")
    return summaries


def _discover_skills_from_registry(repo_root: Path, registry_path: Path) -> list[SkillSummary]:
    entries = _load_registry_entries(repo_root, registry_path)
    summaries: list[SkillSummary] = []
    for entry in entries:
        if not entry.enabled:
            continue
        skill = load_skill(entry.spec_path.parent)
        summaries.append(_build_skill_summary(skill, entry))

    if not summaries:
        raise SkillLoadError(f"No enabled skills found in registry: {registry_path}")
    return summaries


def load_skill(skill_dir: Path) -> SkillDefinition:
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise SkillLoadError(f"SKILL.md not found in {skill_dir}")

    raw_text = skill_md_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(raw_text)
    if not isinstance(frontmatter, dict):
        raise SkillLoadError(f"Invalid frontmatter in {skill_md_path}")

    embedded_registry = _load_embedded_skill_registry(body, skill_md_path)
    body = _strip_embedded_skill_registry(body)
    metadata = frontmatter.get("metadata", {}) or {}
    steps = _load_steps(frontmatter, embedded_registry, skill_dir, body)
    references = _load_references(frontmatter, embedded_registry, skill_dir, steps)
    stages = _load_stages(frontmatter)
    chunking = _load_chunking(frontmatter)
    output_config = _load_output_config(frontmatter)
    runtime_inputs = _load_runtime_inputs(frontmatter, embedded_registry, steps)
    allow_inline_text_input, inline_input_prompt = _load_inline_input_settings(frontmatter, metadata, embedded_registry)
    name = str(frontmatter.get("name") or skill_dir.name)
    display_name = str(frontmatter.get("display_name") or metadata.get("display_name") or frontmatter.get("display") or name)
    description = str(frontmatter.get("description") or _extract_title(body) or name)
    execution = frontmatter.get("execution", {}) or {}
    strategy = str(execution.get("strategy") or ("structured_report" if stages else "step_prompt"))
    utility_script = _load_utility_script(frontmatter, skill_dir)
    if strategy == "utility_script" and utility_script is None:
        raise SkillLoadError(
            f"Skill '{name}' declares execution.strategy=utility_script but does not define execution.utility_script.path."
        )
    supports_resume = bool(
        frontmatter.get(
            "supports_resume",
            metadata.get("supports_resume", embedded_registry.get("supports_resume", False)),
        )
    )
    startup_policy = _load_startup_policy(frontmatter, metadata, steps, supports_resume)
    execution_policy = _load_execution_policy(frontmatter, metadata)
    system_instructions = _load_system_instructions(frontmatter, embedded_registry)

    return SkillDefinition(
        name=name,
        display_name=display_name,
        description=description,
        skill_dir=skill_dir,
        skill_md_path=skill_md_path,
        body=body.strip(),
        supports_resume=supports_resume,
        execution_strategy=strategy,
        steps=steps,
        runtime_inputs=runtime_inputs,
        references=references,
        stages=stages,
        chunking=chunking,
        output_config=output_config,
        input_extensions=_load_input_extensions(frontmatter, metadata),
        folder_mode=_load_folder_mode(frontmatter, metadata, embedded_registry),
        allow_inline_text_input=allow_inline_text_input,
        inline_input_prompt=inline_input_prompt,
        utility_script=utility_script,
        startup_policy=startup_policy,
        execution_policy=execution_policy,
        system_instructions=system_instructions,
    )


def load_reference_texts(skill: SkillDefinition, reference_ids: list[str]) -> dict[str, str]:
    loaded: dict[str, str] = {}
    for reference_id in reference_ids:
        reference = skill.get_reference(reference_id)
        if not reference.absolute_path.exists():
            raise SkillLoadError(
                f"Referenced file '{reference.relative_path}' is missing for skill '{skill.name}'."
            )
        loaded[reference_id] = _read_reference_resource(reference.absolute_path)
    return loaded


def _load_registry_entries(repo_root: Path, registry_path: Path) -> list[SkillRegistryEntry]:
    try:
        raw_registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SkillLoadError(f"Invalid YAML in registry file {registry_path}: {exc}") from exc

    if not isinstance(raw_registry, dict):
        raise SkillLoadError(f"Registry file must contain a mapping at the top level: {registry_path}")

    version = raw_registry.get("version")
    if version != 1:
        raise SkillLoadError(
            f"Unsupported registry version in {registry_path}: expected 1, got {version!r}"
        )

    raw_skills = raw_registry.get("skills")
    if not isinstance(raw_skills, list):
        raise SkillLoadError(f"Registry file must define a 'skills' list: {registry_path}")

    entries: list[SkillRegistryEntry] = []
    seen_ids: set[str] = set()
    for index, raw_entry in enumerate(raw_skills, start=1):
        entry = _parse_registry_entry(repo_root, registry_path, raw_entry, index)
        if entry.id in seen_ids:
            raise SkillLoadError(
                f"Duplicate skill id '{entry.id}' in {registry_path} at entry #{index}."
            )
        seen_ids.add(entry.id)
        entries.append(entry)
    return entries


def _parse_registry_entry(
    repo_root: Path,
    registry_path: Path,
    raw_entry: Any,
    index: int,
) -> SkillRegistryEntry:
    if not isinstance(raw_entry, dict):
        raise SkillLoadError(
            f"Registry entry #{index} in {registry_path} must be a mapping."
        )

    entry_id = _require_registry_string(raw_entry, "id", registry_path, index)
    entry_type = _require_registry_string(raw_entry, "type", registry_path, index)
    raw_spec_path = _require_registry_string(raw_entry, "spec_path", registry_path, index)

    if entry_type != "skill":
        raise SkillLoadError(
            f"Unsupported registry type '{entry_type}' for skill '{entry_id}' in {registry_path}; "
            "Phase 1 only supports type: skill."
        )

    spec_path = _resolve_repo_path(repo_root, raw_spec_path, description=f"registry entry '{entry_id}' spec_path")
    if spec_path.name != "SKILL.md":
        raise SkillLoadError(
            f"Registry entry '{entry_id}' in {registry_path} must point to a SKILL.md file: {raw_spec_path}"
        )
    if not spec_path.exists():
        raise SkillLoadError(
            f"Registry entry '{entry_id}' points to a missing SKILL.md: {raw_spec_path}"
        )

    return SkillRegistryEntry(
        id=entry_id,
        entry_type=entry_type,
        adapter=str(raw_entry.get("adapter") or "skill_md"),
        spec_path=spec_path,
        enabled=bool(raw_entry.get("enabled", True)),
        display_name=str(raw_entry.get("display_name") or ""),
        description=str(raw_entry.get("description") or ""),
    )


def _require_registry_string(
    raw_entry: dict[str, Any],
    field_name: str,
    registry_path: Path,
    index: int,
) -> str:
    value = raw_entry.get(field_name)
    if value in (None, ""):
        raise SkillLoadError(
            f"Registry entry #{index} in {registry_path} is missing required field '{field_name}'."
        )
    return str(value)


def _build_skill_summary(
    skill: SkillDefinition,
    entry: SkillRegistryEntry | None = None,
) -> SkillSummary:
    return SkillSummary(
        name=entry.id if entry else skill.name,
        display_name=(entry.display_name if entry and entry.display_name else skill.display_name),
        description=(entry.description if entry and entry.description else skill.description),
        skill_dir=skill.skill_dir,
    )


def _split_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
    if not raw_text.startswith("---"):
        return {}, raw_text
    parts = raw_text.split("---", 2)
    if len(parts) < 3:
        return {}, raw_text
    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip()
    return frontmatter, body


def _load_steps(
    frontmatter: dict[str, Any],
    embedded_registry: dict[str, Any],
    skill_dir: Path,
    body: str,
) -> dict[int, SkillStep]:
    raw_steps = frontmatter.get("steps")
    if not raw_steps:
        raw_steps = embedded_registry.get("steps")
        if raw_steps:
            return _load_registry_steps(embedded_registry)
    if not raw_steps:
        return _infer_steps_from_body(skill_dir, body)

    steps: dict[int, SkillStep] = {}
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        number = int(raw_step["number"])
        steps[number] = SkillStep(
            number=number,
            step_id=str(raw_step.get("id") or f"step{number}"),
            title=str(raw_step.get("title") or f"Step {number}"),
            prompt_reference_id=_optional_string(raw_step.get("prompt_reference")),
            description=str(raw_step.get("description", "")),
            route_keywords_any=_to_string_list(raw_step.get("route_keywords_any")),
            route_keywords_all=_to_string_list(raw_step.get("route_keywords_all")),
            route_priority=int(raw_step.get("route_priority", 0)),
            requires_list_like=bool(raw_step.get("requires_list_like", False)),
            requires_script_like=bool(raw_step.get("requires_script_like", False)),
            input_blocks=_load_input_blocks(raw_step.get("input_blocks")),
            output_key=_optional_string(raw_step.get("write_to")),
            output_filename=_optional_string(raw_step.get("output_filename")),
            default=bool(raw_step.get("default", False)),
        )
    if not steps:
        raise SkillLoadError("Skill defines no runnable steps.")
    return steps


def _load_references(
    frontmatter: dict[str, Any],
    embedded_registry: dict[str, Any],
    skill_dir: Path,
    steps: dict[int, SkillStep],
) -> dict[str, ReferenceDefinition]:
    raw_references = frontmatter.get("references", []) or []
    if not raw_references:
        raw_references = embedded_registry.get("references", []) or []
    references: dict[str, ReferenceDefinition] = {}
    step_id_to_number = {step.step_id or f"step{step.number}": step.number for step in steps.values()}
    for raw_reference in raw_references:
        if not isinstance(raw_reference, dict):
            continue
        relative_path = str(raw_reference["path"]).replace("\\", "/")
        reference_id = str(raw_reference.get("id") or Path(relative_path).stem.replace("-", "_"))
        absolute_path = _resolve_skill_path(
            skill_dir,
            relative_path,
            description=f"reference '{reference_id}' for skill '{skill_dir.name}'",
        )
        references[reference_id] = ReferenceDefinition(
            reference_id=reference_id,
            relative_path=relative_path,
            absolute_path=absolute_path,
            kind=str(raw_reference.get("kind", "reference")),
            description=str(raw_reference.get("description", "")),
            step_numbers=_resolve_step_numbers(raw_reference, step_id_to_number),
            stage_names=_to_string_list(raw_reference.get("stage_names")),
            load=str(raw_reference.get("load", "auto")),
        )

    for step in steps.values():
        if not step.prompt_reference_id:
            continue
        if step.prompt_reference_id in references:
            continue
        relative_path = embedded_registry_path_for_step(embedded_registry, step.step_id or f"step{step.number}")
        if not relative_path:
            continue
        references[step.prompt_reference_id] = ReferenceDefinition(
            reference_id=step.prompt_reference_id,
            relative_path=relative_path,
            absolute_path=_resolve_skill_path(
                skill_dir,
                relative_path,
                description=f"prompt reference '{step.prompt_reference_id}' for skill '{skill_dir.name}'",
            ),
            kind="prompt",
            description=f"Prompt for {step.title}",
            step_numbers=[step.number],
        )

    for step in steps.values():
        if step.prompt_reference_id and step.prompt_reference_id not in references:
            raise SkillLoadError(
                f"Step {step.number} references unknown prompt '{step.prompt_reference_id}'."
            )
    return references


def _load_runtime_inputs(
    frontmatter: dict[str, Any],
    embedded_registry: dict[str, Any],
    steps: dict[int, SkillStep],
) -> list[RuntimeInputDefinition]:
    definitions: list[RuntimeInputDefinition] = []
    raw_definitions = frontmatter.get("runtime_inputs", []) or []
    if not raw_definitions:
        raw_definitions = embedded_registry.get("runtime_inputs", []) or []

    step_id_to_number = {step.step_id or f"step{step.number}": step.number for step in steps.values()}
    for raw_definition in raw_definitions:
        if not isinstance(raw_definition, dict):
            continue
        definitions.append(
            RuntimeInputDefinition(
                name=str(raw_definition["name"]),
                prompt=str(raw_definition["prompt"]),
                field_type=str(raw_definition.get("type", "string")),
                required=bool(raw_definition.get("required", True)),
                step_numbers=_resolve_step_numbers(raw_definition, step_id_to_number),
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


def _load_utility_script(frontmatter: dict[str, Any], skill_dir: Path) -> UtilityScriptConfig | None:
    execution = frontmatter.get("execution", {}) or {}
    raw_utility = execution.get("utility_script") or {}
    if not isinstance(raw_utility, dict):
        raw_utility = {}

    relative_path = _optional_string(raw_utility.get("path"))
    if not relative_path:
        return None

    return UtilityScriptConfig(
        relative_path=relative_path.replace("\\", "/"),
        absolute_path=_resolve_skill_path(
            skill_dir,
            relative_path,
            description=f"utility script for skill '{skill_dir.name}'",
        ),
        entrypoint=str(raw_utility.get("entrypoint") or "run"),
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
            step_id=f"step{step_number}",
            title=f"Step {step_number}",
            prompt_reference_id=reference_id,
            default=step_number == 1,
        )
    if steps:
        return steps

    return {
        1: SkillStep(
            number=1,
            step_id="step1",
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


def _load_embedded_skill_registry(body: str, skill_md_path: Path) -> dict[str, Any]:
    match = re.search(r"```skill-registry\s*\n(.*?)```", body, flags=re.DOTALL)
    if not match:
        return {}
    try:
        payload = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillLoadError(f"Invalid skill-registry block in {skill_md_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SkillLoadError(f"skill-registry block must decode to a mapping in {skill_md_path}")
    return payload


def _strip_embedded_skill_registry(body: str) -> str:
    return re.sub(r"\n?```skill-registry\s*\n.*?```", "", body, flags=re.DOTALL).strip()


def _load_registry_steps(embedded_registry: dict[str, Any]) -> dict[int, SkillStep]:
    raw_steps = embedded_registry.get("steps", []) or []
    entrypoint = str(embedded_registry.get("entrypoint") or "")
    step_id_to_number: dict[str, int] = {}
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            continue
        step_id = str(raw_step.get("id") or f"step{index}")
        step_id_to_number[step_id] = index

    steps: dict[int, SkillStep] = {}
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            continue
        step_id = str(raw_step.get("id") or f"step{index}")
        prompt_path = _optional_string(raw_step.get("prompt"))
        prompt_reference_id = (
            str(raw_step.get("prompt_reference_id"))
            if raw_step.get("prompt_reference_id") not in (None, "")
            else (Path(prompt_path).stem.replace("-", "_") if prompt_path else None)
        )
        next_value = _optional_string(raw_step.get("next"))
        next_step_number = None if next_value in (None, "END") else step_id_to_number.get(next_value)
        steps[index] = SkillStep(
            number=index,
            step_id=step_id,
            title=str(raw_step.get("title") or f"Step {index}"),
            prompt_reference_id=prompt_reference_id,
            description=str(raw_step.get("description", "")),
            route_keywords_any=_to_string_list(raw_step.get("route_keywords_any")),
            route_keywords_all=_to_string_list(raw_step.get("route_keywords_all")),
            route_priority=int(raw_step.get("route_priority", 0)),
            requires_list_like=bool(raw_step.get("requires_list_like", False)),
            requires_script_like=bool(raw_step.get("requires_script_like", False)),
            input_blocks=_load_input_blocks(raw_step.get("input_blocks")),
            output_key=_optional_string(raw_step.get("write_to")),
            output_filename=_optional_string(raw_step.get("output_filename")),
            next_step_number=next_step_number,
            default=bool(raw_step.get("default", False) or step_id == entrypoint or (not entrypoint and index == 1)),
        )
    if not steps:
        raise SkillLoadError("Embedded skill-registry defines no runnable steps.")
    return steps


def embedded_registry_path_for_step(embedded_registry: dict[str, Any], step_id: str) -> str | None:
    for raw_step in embedded_registry.get("steps", []) or []:
        if isinstance(raw_step, dict) and str(raw_step.get("id") or "") == step_id:
            return _optional_string(raw_step.get("prompt"))
    return None


def _resolve_step_numbers(raw_item: dict[str, Any], step_id_to_number: dict[str, int]) -> list[int]:
    if raw_item.get("step_numbers"):
        return [int(item) for item in raw_item.get("step_numbers", [])]
    step_ids = _to_string_list(raw_item.get("step_ids"))
    numbers = [step_id_to_number[step_id] for step_id in step_ids if step_id in step_id_to_number]
    return numbers


def _load_input_blocks(raw_blocks: Any) -> list[SkillInputBlock]:
    blocks: list[SkillInputBlock] = []
    for raw_block in raw_blocks or []:
        if not isinstance(raw_block, dict):
            continue
        blocks.append(
            SkillInputBlock(
                label=str(raw_block.get("label") or raw_block.get("from") or "Input"),
                source_key=str(raw_block.get("from") or ""),
                required=bool(raw_block.get("required", True)),
            )
        )
    return blocks


def _load_system_instructions(frontmatter: dict[str, Any], embedded_registry: dict[str, Any]) -> str:
    llm_config = embedded_registry.get("llm", {}) or {}
    return str(frontmatter.get("system_instructions") or llm_config.get("instructions") or "")


def _load_input_extensions(frontmatter: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    raw_extensions = frontmatter.get("input_extensions") or metadata.get("input_extensions") or [".txt"]
    return [str(item).lower() for item in raw_extensions]


def _load_folder_mode(frontmatter: dict[str, Any], metadata: dict[str, Any], embedded_registry: dict[str, Any]) -> str:
    if frontmatter.get("folder_mode"):
        return str(frontmatter["folder_mode"])
    if metadata.get("folder_mode"):
        return str(metadata["folder_mode"])
    intake = embedded_registry.get("intake", {}) or {}
    if intake.get("recursive_txt_search"):
        return "recursive"
    return "non_recursive"


def _load_inline_input_settings(
    frontmatter: dict[str, Any],
    metadata: dict[str, Any],
    embedded_registry: dict[str, Any],
) -> tuple[bool, str]:
    raw_intake = metadata.get("intake") or frontmatter.get("intake") or {}
    if not isinstance(raw_intake, dict):
        raw_intake = {}
    embedded_intake = embedded_registry.get("intake") or {}
    if not isinstance(embedded_intake, dict):
        embedded_intake = {}

    allow_inline_text_input = bool(
        raw_intake.get(
            "allow_inline_text_input",
            embedded_intake.get("allow_inline_text_input", False),
        )
    )
    inline_input_prompt = str(
        raw_intake.get("inline_input_prompt")
        or embedded_intake.get("inline_input_prompt")
        or ""
    )
    return allow_inline_text_input, inline_input_prompt


def _load_startup_policy(
    frontmatter: dict[str, Any],
    metadata: dict[str, Any],
    steps: dict[int, SkillStep],
    supports_resume: bool,
) -> SkillStartupPolicy:
    raw_startup = metadata.get("startup") or frontmatter.get("startup") or {}
    if not isinstance(raw_startup, dict):
        raw_startup = {}

    default_step_number = _optional_int(raw_startup.get("default_step"))
    if default_step_number not in steps:
        default_step_number = next((step.number for step in steps.values() if step.default), None)
    if default_step_number not in steps and steps:
        default_step_number = min(steps)

    return SkillStartupPolicy(
        mode=str(raw_startup.get("mode", "auto_route")),
        default_step_number=default_step_number,
        allow_resume=bool(raw_startup.get("allow_resume", supports_resume)),
        allow_auto_route=bool(raw_startup.get("allow_auto_route", True)),
    )




def _load_execution_policy(frontmatter: dict[str, Any], metadata: dict[str, Any]) -> SkillExecutionPolicy:
    raw_execution = metadata.get("execution") or frontmatter.get("execution_policy") or {}
    if not isinstance(raw_execution, dict):
        raw_execution = {}
    return SkillExecutionPolicy(
        mode=str(raw_execution.get("mode", "single_step")),
        continue_until_end=bool(raw_execution.get("continue_until_end", False)),
        preview_before_save=bool(raw_execution.get("preview_before_save", False)),
        save_only_on_accept=bool(raw_execution.get("save_only_on_accept", False)),
    )
def _read_reference_resource(path: Path) -> str:
    try:
        from .input_loader import read_resource_text

        return read_resource_text(path)
    except Exception as exc:  # noqa: BLE001
        raise SkillLoadError(f"Could not load reference resource: {path}") from exc


def _resolve_repo_path(repo_root: Path, raw_path: str, *, description: str) -> Path:
    repo_root = repo_root.resolve()
    candidate = (repo_root / Path(raw_path)).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise SkillLoadError(f"{description} escapes the repository root: {raw_path}") from exc
    return candidate


def _resolve_skill_path(skill_dir: Path, raw_path: str, *, description: str) -> Path:
    skill_dir = skill_dir.resolve()
    candidate = (skill_dir / Path(raw_path)).resolve()
    try:
        candidate.relative_to(skill_dir)
    except ValueError as exc:
        raise SkillLoadError(f"{description} escapes the skill directory: {raw_path}") from exc
    return candidate
