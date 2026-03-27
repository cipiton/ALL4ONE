from __future__ import annotations

from pathlib import Path

from .backend_adapter import GuiRuntimeInputField, GuiSkillOption
from .chat_state import ChatSessionState


QUESTION_PREFIXES = (
    "what",
    "why",
    "how",
    "can",
    "could",
    "should",
    "is",
    "are",
    "where",
    "when",
    "which",
    "who",
    "help",
    "explain",
    "tell me",
)


def should_route_to_workflow(skill: GuiSkillOption, session: ChatSessionState, text: str) -> bool:
    value = text.strip()
    if not value:
        return False

    stage = session.stage
    if stage == "awaiting_input":
        return _looks_like_primary_input(skill, value)
    if stage == "awaiting_step":
        return _looks_like_step_input(value)
    if stage == "awaiting_rewriting_mode":
        return _looks_like_rewriting_mode(value)
    if stage == "awaiting_rewriting_plan":
        return _looks_like_path_like_input(value)
    if stage == "awaiting_rewriting_bible":
        return value.isdigit() or _looks_like_path_like_input(value)
    if stage == "awaiting_rewriting_supplemental":
        return value.lower() in {"skip", "none"} or _looks_like_path_like_input(value)
    if stage == "awaiting_runtime":
        field = current_runtime_field(skill, session)
        if field is None:
            return False
        return _looks_like_runtime_value(field, value)
    if stage == "ready_to_run":
        return value.lower() in {"run", "start", "yes", "y", "go", "restart", "reset", "new"}
    return False


def is_question_like(text: str) -> bool:
    value = text.strip().lower()
    if not value:
        return False
    if "?" in value:
        return True
    return any(value.startswith(prefix) for prefix in QUESTION_PREFIXES)


def current_runtime_field(skill: GuiSkillOption, session: ChatSessionState) -> GuiRuntimeInputField | None:
    selected_step = session.selected_step_number
    visible_fields: list[GuiRuntimeInputField] = []
    for field in skill.runtime_inputs:
        if selected_step is not None and field.step_numbers and selected_step not in field.step_numbers:
            continue
        visible_fields.append(field)
    if session.runtime_field_index < 0 or session.runtime_field_index >= len(visible_fields):
        return None
    return visible_fields[session.runtime_field_index]


def _looks_like_primary_input(skill: GuiSkillOption, value: str) -> bool:
    if _looks_like_existing_path(value):
        path = Path(value.strip().strip('"')).expanduser()
        if path.is_dir():
            return skill.supports_folder_input
        return skill.supports_file_input
    if skill.supports_text_input and not is_question_like(value):
        return True
    return False


def _looks_like_step_input(value: str) -> bool:
    lowered = value.lower()
    return lowered in {"auto", "default"} or value.isdigit()


def _looks_like_rewriting_mode(value: str) -> bool:
    lowered = value.lower()
    return lowered in {
        "1",
        "2",
        "3",
        "auto",
        "default",
        "build_bible",
        "build bible",
        "rewrite_with_bible",
        "rewrite with bible",
        "build_bible_and_rewrite",
        "build bible and rewrite",
    }


def _looks_like_runtime_value(field: GuiRuntimeInputField, value: str) -> bool:
    lowered = value.lower()
    if lowered == "skip":
        return not field.required
    if field.field_type == "choice":
        if value.isdigit():
            index = int(value)
            return 1 <= index <= len(field.choices)
        return any(choice.casefold() == value.casefold() for choice in field.choices)
    if field.field_type == "int":
        return value.lstrip("+-").isdigit()
    if field.field_type == "bool":
        return lowered in {"1", "0", "true", "false", "yes", "no", "y", "n", "on", "off"}
    return not is_question_like(value)


def _looks_like_existing_path(value: str) -> bool:
    raw = value.strip().strip('"')
    if not raw:
        return False
    try:
        return Path(raw).expanduser().exists()
    except OSError:
        return False


def _looks_like_path_like_input(value: str) -> bool:
    raw = value.strip().strip('"')
    if not raw:
        return False
    if _looks_like_existing_path(raw):
        return True
    return any(separator in raw for separator in ("\\", "/")) or bool(Path(raw).suffix)
