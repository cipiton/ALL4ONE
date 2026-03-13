from __future__ import annotations

import json
from pathlib import Path

from .models import RunState, SkillDefinition


def save_state(state: RunState, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or Path(state.output_directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    state_path = target_dir / "state.json"
    state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path


def load_state(state_path: Path) -> RunState | None:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return RunState.from_dict(payload)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def save_batch_summary(session_dir: Path, payload: dict[str, object]) -> Path:
    path = session_dir / "state.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def find_latest_resumable_state(outputs_root: Path, skill: SkillDefinition) -> RunState | None:
    skill_root = outputs_root / skill.name
    if not skill_root.exists():
        return None

    candidates = sorted(
        skill_root.rglob("state.json"),
        key=lambda path: str(path.parent),
        reverse=True,
    )
    for candidate in candidates:
        state = load_state(candidate)
        if state is None or state.skill_name != skill.name:
            continue
        if is_resumable_state(skill, state):
            return state
    return None


def is_resumable_state(skill: SkillDefinition, state: RunState) -> bool:
    if state.status in {"pending", "awaiting_input", "running", "error"}:
        return True
    if state.status == "completed_step" and state.detected_step < skill.final_step_number:
        return True
    return False
