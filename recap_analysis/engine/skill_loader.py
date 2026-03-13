from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import ReferenceResource, SkillConfig

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


class SkillLoadError(RuntimeError):
    """Raised when the runtime cannot locate or parse a skill."""


def discover_skill_dir(base_dir: Path) -> Path:
    """Find the most likely extracted skill directory containing SKILL.md."""
    preferred = base_dir
    if (preferred / "SKILL.md").exists():
        return preferred

    candidates = sorted(path.parent for path in base_dir.rglob("SKILL.md"))
    if not candidates:
        raise SkillLoadError(f"未找到 SKILL.md: {base_dir}")
    return candidates[0]


def load_skill(skill_dir: Path) -> SkillConfig:
    """Load and normalize the skill configuration from SKILL.md."""
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise SkillLoadError(f"缺少 SKILL.md: {skill_md_path}")

    raw_markdown = skill_md_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(raw_markdown)
    sections = _extract_sections(body)
    workflow_steps = _extract_workflow_steps(sections)
    output_expectations = _extract_output_expectations(sections, workflow_steps)
    referenced_files = _extract_references(skill_dir, body)
    notes = _extract_notes(sections)

    name = str(frontmatter.get("name") or _extract_title(body) or skill_dir.name)
    description = str(
        frontmatter.get("description")
        or _first_nonempty_line(sections.get("任务目标", ""))
        or "Skill description unavailable."
    )

    return SkillConfig(
        name=name,
        description=description,
        skill_dir=skill_dir,
        skill_md_path=skill_md_path,
        frontmatter=frontmatter,
        workflow_steps=workflow_steps,
        output_expectations=output_expectations,
        referenced_files=referenced_files,
        sections=sections,
        notes=notes,
    )


def load_reference_texts(resources: list[ReferenceResource]) -> dict[str, str]:
    """Read only the requested reference files that exist."""
    loaded: dict[str, str] = {}
    for resource in resources:
        if not resource.exists:
            continue
        try:
            loaded[resource.relative_path] = resource.absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            loaded[resource.relative_path] = resource.absolute_path.read_text(encoding="utf-8-sig")
    return loaded


def _parse_frontmatter(markdown_text: str) -> tuple[dict[str, Any], str]:
    if not markdown_text.startswith("---"):
        return {}, markdown_text

    parts = markdown_text.split("---", 2)
    if len(parts) < 3:
        return {}, markdown_text

    frontmatter_text = parts[1].strip()
    body = parts[2].lstrip()
    if not frontmatter_text:
        return {}, body

    if yaml is not None:
        parsed = yaml.safe_load(frontmatter_text) or {}
        if isinstance(parsed, dict):
            return parsed, body

    return _fallback_frontmatter(frontmatter_text), body


def _fallback_frontmatter(frontmatter_text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _extract_sections(body: str) -> dict[str, str]:
    pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def _extract_workflow_steps(sections: dict[str, str]) -> list[str]:
    workflow_body = sections.get("操作步骤", "")
    if not workflow_body:
        return []

    steps: list[str] = []
    for line in workflow_body.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\.\s+", stripped):
            steps.append(re.sub(r"^\d+\.\s+", "", stripped))
            continue
        if stripped.startswith("- ") and ("包含:" in stripped or "返回:" in stripped):
            steps.append(stripped[2:].strip())
    return steps


def _extract_output_expectations(
    sections: dict[str, str], workflow_steps: list[str]
) -> list[str]:
    expectations: list[str] = []
    for step in workflow_steps:
        if "输出" in step or "报告" in step or "包含" in step:
            expectations.append(step)

    for title, body in sections.items():
        if "注意事项" in title or "任务目标" in title:
            for line in body.splitlines():
                stripped = line.strip()
                if stripped.startswith("- ") and ("输出" in stripped or "文本" in stripped):
                    expectations.append(stripped[2:].strip())
    return _dedupe(expectations)


def _extract_references(skill_dir: Path, body: str) -> list[ReferenceResource]:
    references: list[ReferenceResource] = []
    lines = body.splitlines()
    pattern = re.compile(r"\[([^\]]+)\]\((references/[^)]+)\)")

    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        display_name, relative_path = match.groups()
        purpose = line.strip().lstrip("- ").strip()
        when_to_read = ""
        if "何时读取:" in line:
            when_to_read = line.split("何时读取:", 1)[1].split(")", 1)[0].strip()
        absolute_path = skill_dir / Path(relative_path)
        references.append(
            ReferenceResource(
                name=display_name.strip(),
                relative_path=relative_path,
                absolute_path=absolute_path,
                exists=absolute_path.exists(),
                purpose=purpose,
                when_to_read=when_to_read,
            )
        )

    if references:
        return _dedupe_references(references)

    fallback_paths = sorted((skill_dir / "references").glob("*.md"))[:3]
    for path in fallback_paths:
        references.append(
            ReferenceResource(
                name=path.stem,
                relative_path=str(path.relative_to(skill_dir)).replace("\\", "/"),
                absolute_path=path,
                exists=True,
                purpose="Fallback reference selected because SKILL.md did not specify explicit references.",
                when_to_read="按需读取",
            )
        )
    return references


def _extract_notes(sections: dict[str, str]) -> list[str]:
    notes_body = sections.get("注意事项", "")
    notes = []
    for line in notes_body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            notes.append(stripped[2:].strip())
    return notes


def _extract_title(body: str) -> str:
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if stripped:
            return stripped
    return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _dedupe_references(values: list[ReferenceResource]) -> list[ReferenceResource]:
    seen: set[str] = set()
    ordered: list[ReferenceResource] = []
    for value in values:
        if value.relative_path in seen:
            continue
        seen.add(value.relative_path)
        ordered.append(value)
    return ordered
