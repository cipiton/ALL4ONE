from __future__ import annotations  
  
from pathlib import Path  
from typing import Any, Protocol  
  
from app.skills.protocol import SkillResumePoint, SkillStartupPolicySummary, SkillStepSummary  
  
from .models import RuntimeInputDefinition, SkillDefinition  
  
  
class MenuSkill(Protocol):  
    display_name: str  
    description: str  
  
  
class InputSkill(Protocol):  
    input_extensions: list[str]  
  
  
INTRO_TEXT = 'Shared skill runner'  
  
  
def configure_console() -> None:  
    import sys  
  
    for stream in (sys.stdout, sys.stderr):  
        reconfigure = getattr(stream, 'reconfigure', None)  
        if callable(reconfigure):  
            reconfigure(encoding='utf-8', errors='replace')  
  
  
def print_intro(model_line: str) -> None:  
    print(INTRO_TEXT)  
    print(model_line)  
  
  
def choose_skill(skills: list[MenuSkill]) -> MenuSkill | None:  
    print()  
    print('Available skills:')  
    for index, skill in enumerate(skills, start=1):  
        print(f'{index}. {skill.display_name} - {skill.description}')  
    print('0. Exit')  
  
    while True:  
        raw_value = input('Choose a skill: ').strip()  
        if raw_value in {'0', 'q', 'quit', 'exit'}:  
            return None  
        try:  
            selected = int(raw_value)  
        except ValueError:  
            print('Enter a number from the menu.')  
            continue  
        if 1 <= selected <= len(skills):  
            return skills[selected - 1]  
        print('Enter a valid menu number.') 
  
def prompt_for_input_path(skill: SkillDefinition | InputSkill) -> str | None:
    suffixes = ', '.join(skill.input_extensions)
    allow_inline = bool(getattr(skill, 'allow_inline_text_input', False))
    inline_prompt = str(getattr(skill, 'inline_input_prompt', '') or '').strip()
    input_hint = _localized_skill_text(skill, 'input_hint')
    if input_hint:
        print(input_hint)
    if allow_inline:
        prompt = inline_prompt or f'Enter a file or folder path ({suffixes}) or type a brief directly (blank to cancel): '
    else:
        prompt = f'Enter a file or folder path ({suffixes}; blank to cancel): '
    raw_value = input(prompt).strip()  
    return raw_value or None  


def _localized_skill_text(skill: SkillDefinition | InputSkill, field_name: str, language: str = 'en') -> str:
    localized_text = getattr(skill, 'localized_text', None)
    if callable(localized_text):
        return str(localized_text(field_name, language, fallback='') or '').strip()
    return str(getattr(skill, field_name, '') or '').strip()
  
  
def ask_yes_no(prompt: str, default: bool = False) -> bool:  
    while True:  
        raw_value = input(prompt).strip().lower()  
        if not raw_value:  
            return default  
        if raw_value in {'y', 'yes'}:  
            return True  
        if raw_value in {'n', 'no'}:  
            return False  
        print('Please answer y or n.')  
  
  
def prompt_for_runtime_value(definition: RuntimeInputDefinition, current_value: Any = None) -> Any:  
    if definition.help_text:  
        print(definition.help_text)  
  
    while True:  
        if definition.field_type == 'choice':  
            print(definition.prompt)  
            for index, choice in enumerate(definition.choices, start=1):  
                suffix = ' (current)' if current_value == choice else ''  
                print(f'{index}. {choice}{suffix}')  
            raw_value = input('> ').strip()
        else:
            default_suffix = ''  
            if current_value is not None:  
                default_suffix = f' [{current_value}]'  
            elif definition.default is not None:  
                default_suffix = f' [{definition.default}]'  
            raw_value = input(f'{definition.prompt}{default_suffix}: ').strip()  
  
        if not raw_value:  
            if current_value is not None:  
                return current_value  
            if definition.default is not None:  
                return definition.default  
            if not definition.required:  
                return None  
            print('This value is required.')  
            continue  
  
        try:  
            return _parse_runtime_value(definition, raw_value)  
        except ValueError as exc:  
            print(exc)  
  
  
def choose_start_mode(  
    steps: list[SkillStepSummary],  
    startup_policy: SkillStartupPolicySummary,  
    resume_point: SkillResumePoint | None = None,  
) -> tuple[str, int | None]:  
    default_step = startup_policy.default_step_number  
    if default_step is None and steps:  
        default_step = steps[0].number 
  
    print()  
    print('Available steps:')  
    for step in steps:  
        suffix = ' (default)' if step.number == default_step else ''  
        detail = f' - {step.description}' if step.description else ''  
        print(f'{step.number}. {step.title}{suffix}{detail}')  
    if startup_policy.allow_resume and resume_point is not None:  
        next_step = resume_point.next_step_number or resume_point.detected_step  
        print(f'R. Resume latest unfinished run (next step {next_step})')  
  
    while True:  
        raw_value = input('Choose a step (Enter for default): ').strip()  
        if not raw_value:  
            return 'run', default_step  
        if raw_value.lower() == 'r':  
            if startup_policy.allow_resume and resume_point is not None:  
                return 'resume', None  
            print('Resume is not available for this skill right now.')  
            continue  
        if raw_value.isdigit():  
            selected = int(raw_value)  
            if any(step.number == selected for step in steps):  
                return 'run', selected  
        print('Choose a listed step number, press Enter, or use R to resume.')  
  
  
def show_step_output_preview(step_title: str, text: str, *, max_lines: int = 18, max_chars: int = 1400) -> None:  
    print()  
    print(f'Preview: {step_title}')  
    preview_text = text[:max_chars]  
    preview_lines = preview_text.splitlines()  
    truncated_lines = len(preview_lines) > max_lines  
    if truncated_lines:  
        preview_lines = preview_lines[:max_lines]  
    print('-' * 60)  
    print('\n'.join(preview_lines).strip() or '(empty output)')  
    if truncated_lines or len(text) > len(preview_text):  
        print('...')  
    print('-' * 60)  
  
  
def prompt_for_review_action() -> str:  
    while True:  
        raw_value = input('Choose: [A]ccept, [I]mprove, [R]estart, [V]iew full, [C]ancel: ').strip().lower()  
        if raw_value in {'', 'a', 'accept'}:  
            return 'accept'  
        if raw_value in {'i', 'improve'}:  
            return 'improve'  
        if raw_value in {'r', 'restart'}:  
            return 'restart'  
        if raw_value in {'v', 'view', 'full', 'view_full'}:  
            return 'view_full'  
        if raw_value in {'c', 'cancel', 'q', 'quit'}:  
            return 'cancel'  
        print('Choose A, I, R, V, or C.') 
  
def prompt_for_improvement_request() -> str:  
    return input('Improvement instructions: ').strip()  
  
  
def prompt_for_restart_request() -> str:  
    return input('Restart instructions (optional): ').strip()  
  
  
def print_full_output(step_title: str, text: str) -> None:  
    print()  
    print(f'Full output: {step_title}')  
    print('=' * 60)  
    print(text.rstrip() or '(empty output)')  
    print('=' * 60)  
  
  
def print_progress(message: str) -> None:  
    print(f'[...] {message}')  
  
  
def print_batch_progress(index: int, total: int, document_path: Path) -> None:  
    print(f'[{index}/{total}] processing {document_path.name}')  
  
  
def print_run_summary(successes: int, failures: int, session_dir: Path) -> None:  
    print()  
    print(f'Completed with {successes} success(es) and {failures} failure(s).')  
    print(f'Outputs: {session_dir}')  
  
  
def _parse_runtime_value(definition: RuntimeInputDefinition, raw_value: str) -> Any:  
    if definition.field_type == 'int':  
        try:  
            value = int(raw_value)  
        except ValueError as exc:  
            raise ValueError('Enter a whole number.') from exc  
        if definition.min_value is not None and value < definition.min_value:  
            raise ValueError(f'Value must be >= {definition.min_value}.')  
        if definition.max_value is not None and value > definition.max_value:  
            raise ValueError(f'Value must be <= {definition.max_value}.')  
        return value  
  
    if definition.field_type == 'bool':  
        lowered = raw_value.lower()  
        if lowered in {'y', 'yes', 'true', '1'}:  
            return True  
        if lowered in {'n', 'no', 'false', '0'}:  
            return False  
        raise ValueError('Enter yes or no.')  
  
    if definition.field_type == 'choice':  
        if raw_value.isdigit():  
            index = int(raw_value)  
            if 1 <= index <= len(definition.choices):  
                return definition.choices[index - 1]  
        for choice in definition.choices:  
            if raw_value == choice:  
                return choice  
        raise ValueError('Choose one of the listed values.')  
  
    return raw_value  


def prompt_for_episode_selection(
    total_episodes: int,
    *,
    mode: str,
    current_value: str | None = None,
) -> str:
    action = 'generated' if mode == 'generate' else 'regenerated'
    print(f"There are {total_episodes} episodes in this adaptation plan.")
    print(f"Which episodes should be {action}?")
    if mode == 'generate':
        print("Examples: blank = all, all, 1-10, 11-20, 60, 15,18,22")
        default_suffix = f" [{current_value}]" if current_value else " [all]"
    else:
        print("Examples: 15, 15-16, 02-05, 15,18,22")
        default_suffix = f" [{current_value}]" if current_value else ''
    return input(f"Episode selection{default_suffix}: ").strip()


def prompt_for_regeneration_instruction(current_value: str | None = None) -> str:
    print("Optional regeneration instruction.")
    print("Examples: more detailed, improve pacing, stronger hook, better dialogue, preserve current structure")
    default_suffix = f" [{current_value}]" if current_value else ''
    return input(f"Regeneration instruction{default_suffix}: ").strip()


def prompt_for_folder_processing_mode(file_count: int) -> str:
    print(f"Detected a folder with {file_count} txt files.")
    print("Choose processing mode:")
    print("1. shared (Recommended) - treat the folder as one coordinated rewrite project")
    print("2. individual - process each txt independently")
    raw_value = input("Mode [shared]: ").strip().lower()
    if raw_value in {"", "1", "shared", "project"}:
        return "shared"
    if raw_value in {"2", "individual", "independent"}:
        return "individual"
    print("Defaulting to shared project mode.")
    return "shared"


def prompt_for_rewriting_mode(default_mode: str) -> str:
    print("Choose rewriting workflow mode:")
    print("1. Create refresh bible")
    print("2. Rewrite using existing refresh bible")
    print("3. Create bible and rewrite")
    labels = {
        "build_bible": "1",
        "rewrite_with_bible": "2",
        "build_bible_and_rewrite": "3",
    }
    default_label = labels.get(default_mode, "1")
    raw_value = input(f"Mode [{default_label}]: ").strip().lower()
    if raw_value in {"", default_label}:
        return default_mode
    if raw_value in {"1", "build", "build_bible", "bible"}:
        return "build_bible"
    if raw_value in {"2", "rewrite", "rewrite_with_bible"}:
        return "rewrite_with_bible"
    if raw_value in {"3", "both", "build_bible_and_rewrite", "build_and_rewrite"}:
        return "build_bible_and_rewrite"
    print(f"Defaulting to {default_mode}.")
    return default_mode


def prompt_for_path(prompt: str, *, required: bool = False) -> str | None:
    while True:
        raw_value = input(prompt).strip()
        if raw_value:
            return raw_value
        if not required:
            return None
        print("This path is required.")


def prompt_for_existing_bible(options: list[tuple[str, str]]) -> str | None:
    if not options:
        return None
    print("Available refresh bibles:")
    for index, (label, path) in enumerate(options, start=1):
        print(f"{index}. {label} - {path}")
    while True:
        raw_value = input("Choose a bible (blank to cancel): ").strip()
        if not raw_value:
            return None
        if raw_value.isdigit():
            selected = int(raw_value)
            if 1 <= selected <= len(options):
                return options[selected - 1][1]
        print("Choose a listed bible number.")
