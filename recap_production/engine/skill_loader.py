"""Helpers for loading SKILL.md and workflow prompts."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from engine.models import SkillDefinition, StepDefinition


STEP_TITLE_PATTERN = re.compile(r"\*\*步骤([一二三四五六七八九十0-9]+)[：:](.+?)\*\*")
PROMPT_PATTERN = re.compile(r"references/(step(\d+)-prompt\.md)")

CHINESE_NUMERALS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def load_skill_definition(skill_path: Path) -> SkillDefinition:
    """Parse SKILL.md and derive workflow metadata from it."""
    skill_md_path = skill_path / "SKILL.md"
    if not skill_md_path.exists():
        raise FileNotFoundError(f"SKILL.md not found in {skill_path}")

    skill_md_text = skill_md_path.read_text(encoding="utf-8")
    prompt_matches = list(PROMPT_PATTERN.finditer(skill_md_text))
    if not prompt_matches:
        raise ValueError("SKILL.md does not define any step prompt files.")

    steps = _build_steps(skill_path, skill_md_text, prompt_matches)
    intro_name = _extract_front_matter_name(skill_md_text) or skill_path.name
    description = _extract_front_matter_description(skill_md_text)

    return SkillDefinition(
        skill_path=str(skill_path),
        skill_md_path=str(skill_md_path),
        skill_md_text=skill_md_text,
        intro_name=intro_name,
        description=description,
        step_based="步骤" in skill_md_text and bool(steps),
        auto_chain_disabled="严禁自动连续执行多个步骤" in skill_md_text,
        steps=steps,
    )


def load_step_prompt(skill_definition: SkillDefinition, step_number: int) -> str:
    """Load exactly one prompt file for the selected workflow step."""
    step = skill_definition.get_step(step_number)
    prompt_path = Path(step.prompt_path)
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _build_steps(
    skill_path: Path,
    skill_md_text: str,
    prompt_matches: Iterable[re.Match[str]],
) -> dict[int, StepDefinition]:
    titles = _extract_step_titles(skill_md_text)
    steps: dict[int, StepDefinition] = {}
    for match in prompt_matches:
        prompt_file_name = match.group(1)
        step_number = int(match.group(2))
        if step_number in steps:
            continue
        steps[step_number] = StepDefinition(
            number=step_number,
            title=titles.get(step_number, f"Step {step_number}"),
            prompt_path=str(skill_path / "references" / prompt_file_name),
        )
    return steps


def _extract_step_titles(skill_md_text: str) -> dict[int, str]:
    titles: dict[int, str] = {}
    for match in STEP_TITLE_PATTERN.finditer(skill_md_text):
        step_number = _parse_step_number(match.group(1))
        if step_number is None or step_number in titles:
            continue
        titles[step_number] = match.group(2).strip()
    return titles


def _extract_front_matter_name(skill_md_text: str) -> str | None:
    match = re.search(r"^name:\s*(.+)$", skill_md_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _extract_front_matter_description(skill_md_text: str) -> str:
    match = re.search(r"^description:\s*(.+)$", skill_md_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _parse_step_number(raw_value: str) -> int | None:
    raw_value = raw_value.strip()
    if raw_value.isdigit():
        return int(raw_value)
    return CHINESE_NUMERALS.get(raw_value)
