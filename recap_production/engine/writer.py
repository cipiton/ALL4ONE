"""State and output persistence helpers."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from engine.models import ChatMessage, RunState


def create_output_directory(root_path: Path) -> tuple[str, Path]:
    """Create a timestamped output directory under outputs/."""
    base_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    attempt = 0

    while True:
        timestamp = base_timestamp if attempt == 0 else f"{base_timestamp}_{attempt:02d}"
        output_directory = root_path / "outputs" / timestamp
        try:
            output_directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            attempt += 1
            continue
        return timestamp, output_directory


def save_state(state: RunState, output_directory: Path | None = None) -> Path:
    """Write the current run state to state.json."""
    target_directory = output_directory or Path(state.output_directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    state_path = target_directory / "state.json"
    state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path


def load_latest_state(root_path: Path) -> RunState | None:
    """Load the most recent state.json from outputs/ if present."""
    outputs_directory = root_path / "outputs"
    if not outputs_directory.exists():
        return None

    state_files = sorted(outputs_directory.glob("*/state.json"), key=lambda path: path.parent.name, reverse=True)
    for state_file in state_files:
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
            return RunState.from_dict(payload)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return None


def write_model_output(output_directory: Path, step_number: int, content: str) -> Path:
    """Write the model output to a step-specific text file."""
    output_path = output_directory / f"step_{step_number}_output.txt"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def write_prompt_dump(output_directory: Path, model: str, messages: list[ChatMessage], raw_response: dict[str, Any]) -> Path:
    """Persist the assembled prompt/messages for debugging and resume."""
    payload = {
        "model": model,
        "messages": [message.to_dict() for message in messages],
        "raw_response": raw_response,
    }
    dump_path = output_directory / "prompt_dump.json"
    dump_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return dump_path
