from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import RuntimeInputDefinition, SkillDefinition, SkillSummary


INTRO_TEXT = (
    "RECAP123 shared multi-skill runner\n"
    "Select a skill, point it at a .txt file or a folder of .txt files, and the shared engine will execute it."
)


def configure_console() -> None:
    import sys

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def print_intro() -> None:
    print(INTRO_TEXT)


def choose_skill(skills: list[SkillSummary]) -> SkillSummary | None:
    print()
    print("Available skills:")
    for index, skill in enumerate(skills, start=1):
        print(f"{index}. {skill.display_name} - {skill.description}")
    print("0. Exit")

    while True:
        raw_value = input("Choose a skill: ").strip()
        if raw_value in {"0", "q", "quit", "exit"}:
            return None
        try:
            selected = int(raw_value)
        except ValueError:
            print("Enter a number from the menu.")
            continue
        if 1 <= selected <= len(skills):
            return skills[selected - 1]
        print("Enter a valid menu number.")


def prompt_for_input_path(skill: SkillDefinition) -> str | None:
    suffixes = ", ".join(skill.input_extensions)
    raw_value = input(f"Enter a file or folder path ({suffixes}; blank to cancel): ").strip()
    return raw_value or None


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    while True:
        raw_value = input(prompt).strip().lower()
        if not raw_value:
            return default
        if raw_value in {"y", "yes"}:
            return True
        if raw_value in {"n", "no"}:
            return False
        print("Please answer y or n.")


def prompt_for_runtime_value(
    definition: RuntimeInputDefinition,
    current_value: Any = None,
) -> Any:
    if definition.help_text:
        print(definition.help_text)

    while True:
        if definition.field_type == "choice":
            print(definition.prompt)
            for index, choice in enumerate(definition.choices, start=1):
                suffix = " (current)" if current_value == choice else ""
                print(f"{index}. {choice}{suffix}")
            raw_value = input("> ").strip()
        else:
            default_suffix = ""
            if current_value is not None:
                default_suffix = f" [{current_value}]"
            elif definition.default is not None:
                default_suffix = f" [{definition.default}]"
            raw_value = input(f"{definition.prompt}{default_suffix}: ").strip()

        if not raw_value:
            if current_value is not None:
                return current_value
            if definition.default is not None:
                return definition.default
            if not definition.required:
                return None
            print("This value is required.")
            continue

        try:
            return _parse_runtime_value(definition, raw_value)
        except ValueError as exc:
            print(exc)


def print_progress(message: str) -> None:
    print(f"[...] {message}")


def print_batch_progress(index: int, total: int, document_path: Path) -> None:
    print(f"[{index}/{total}] processing {document_path.name}")


def print_run_summary(successes: int, failures: int, session_dir: Path) -> None:
    print()
    print(f"Completed with {successes} success(es) and {failures} failure(s).")
    print(f"Outputs: {session_dir}")


def _parse_runtime_value(definition: RuntimeInputDefinition, raw_value: str) -> Any:
    if definition.field_type == "int":
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ValueError("Enter a whole number.") from exc
        if definition.min_value is not None and value < definition.min_value:
            raise ValueError(f"Value must be >= {definition.min_value}.")
        if definition.max_value is not None and value > definition.max_value:
            raise ValueError(f"Value must be <= {definition.max_value}.")
        return value

    if definition.field_type == "bool":
        lowered = raw_value.lower()
        if lowered in {"y", "yes", "true", "1"}:
            return True
        if lowered in {"n", "no", "false", "0"}:
            return False
        raise ValueError("Enter yes or no.")

    if definition.field_type == "choice":
        if raw_value.isdigit():
            index = int(raw_value)
            if 1 <= index <= len(definition.choices):
                return definition.choices[index - 1]
        for choice in definition.choices:
            if raw_value == choice:
                return choice
        raise ValueError("Choose one of the listed values.")

    return raw_value
