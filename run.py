from __future__ import annotations

import sys
from pathlib import Path

from engine import terminal_ui
from engine.executor import execute_input_paths, load_resume_document
from engine.input_loader import InputLoadError, resolve_input_paths
from engine.llm_client import LLMClientError, load_env_file
from engine.skill_loader import SkillLoadError, discover_skills, load_skill
from engine.state_store import find_latest_resumable_state


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    terminal_ui.configure_console()
    load_env_file(repo_root / ".env")
    terminal_ui.print_intro()

    while True:
        try:
            summaries = discover_skills(repo_root)
            summary = terminal_ui.choose_skill(summaries)
            if summary is None:
                return 0

            skill = load_skill(summary.skill_dir)
            resume_state = None
            resumed_step_hint = None

            if skill.supports_resume:
                latest_state = find_latest_resumable_state(repo_root / "outputs", skill)
                if latest_state is not None and terminal_ui.ask_yes_no(
                    "Resume the latest unfinished workflow for this skill? [y/N]: ",
                    default=False,
                ):
                    resume_document, resumed_step_hint = load_resume_document(skill, latest_state)
                    resume_state = latest_state
                    input_paths = [resume_document.path]
                else:
                    input_paths = prompt_for_paths(skill)
            else:
                input_paths = prompt_for_paths(skill)

            session_dir, results = execute_input_paths(
                repo_root,
                skill,
                input_paths,
                resume_state=resume_state,
                resumed_step_hint=resumed_step_hint,
            )
            successes = sum(1 for result in results if result.status in {"completed", "completed_step"})
            failures = len(results) - successes
            terminal_ui.print_run_summary(successes, failures, session_dir)

            if not terminal_ui.ask_yes_no("Run another job? [Y/n]: ", default=True):
                return 0
        except (SkillLoadError, InputLoadError, LLMClientError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print()


def prompt_for_paths(skill) -> list[Path]:
    raw_path = terminal_ui.prompt_for_input_path(skill)
    if not raw_path:
        raise RuntimeError("Cancelled.")
    return resolve_input_paths(raw_path, skill.input_extensions)


if __name__ == "__main__":
    raise SystemExit(main())
