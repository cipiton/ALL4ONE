from __future__ import annotations  
  
import json  
from pathlib import Path  
  
from .models import RunState, SkillDefinition  
from .runtime_config import RuntimeConfig  
from .writer import create_internal_directory, write_json_file  
  
  
def save_state(state: RunState, output_dir: Path = None, runtime_config: RuntimeConfig = None):  
    target_dir = output_dir or Path(state.output_directory)  
    config = runtime_config or RuntimeConfig()  
    internal_dir = create_internal_directory(target_dir)  
    state_path = internal_dir / "state.json"  
    state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")  
    if config.should_write_visible_state:  
        write_json_file(target_dir, "state.json", state.to_dict())  
    return state_path  
  
  
def load_state(state_path: Path):  
    try:  
        payload = json.loads(state_path.read_text(encoding="utf-8"))  
        return RunState.from_dict(payload)  
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):  
        return None  
  
  
def save_batch_summary(session_dir: Path, payload: dict[str, object], runtime_config: RuntimeConfig = None):  
    config = runtime_config or RuntimeConfig()  
    internal_dir = create_internal_directory(session_dir)  
    path = write_json_file(internal_dir, "batch_summary.json", payload)  
    if config.should_write_visible_state:  
        write_json_file(session_dir, "batch_summary.json", payload)  
    return path  
  
  
def find_latest_resumable_state(outputs_root: Path, skill: SkillDefinition):
    skill_root = outputs_root / skill.name
    if not skill_root.exists():
        return None

    candidates = sorted(skill_root.rglob("state.json"), key=_candidate_sort_key, reverse=True)
    for candidate in candidates:  
        state = load_state(candidate)  
        if state is None or state.skill_name != skill.name:  
            continue  
        if is_resumable_state(skill, state):  
            return state  
    return None  
  
  
def is_resumable_state(skill: SkillDefinition, state: RunState):  
    if state.status in {"pending", "awaiting_input", "running", "error"}:  
        return True  
    if state.status == "completed_step" and skill.next_step_number_for(state.detected_step) is not None:  
        return True  
    return False  
  
  
def _candidate_sort_key(path: Path):
    internal_rank = 1 if path.parent.name == ".internal" else 0
    try:
        modified_at = path.stat().st_mtime_ns
    except OSError:
        modified_at = -1
    return (modified_at, internal_rank, str(path))
