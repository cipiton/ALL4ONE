from __future__ import annotations

import sys
from pathlib import Path

from app.skills.catalog import SkillCatalog, SkillCatalogError
from app.skills.protocol import SkillAdapter, SkillResumeRequest, SkillRunRequest
from engine import terminal_ui
from engine.input_loader import InputLoadError, resolve_input_paths
from engine.llm_client import LLMClientError, load_env_file


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    terminal_ui.configure_console()
    load_env_file(repo_root / ".env")
    terminal_ui.print_intro()

    while True:
        try:
            catalog = SkillCatalog.load(repo_root)
            summaries = catalog.menu_summaries()
            summary = terminal_ui.choose_skill(summaries)
            if summary is None:
                return 0

            skill = catalog.get_skill(summary.skill_id)

            if skill.supports_resume:
                latest_state = skill.find_resume_point(repo_root / "outputs")
                if latest_state is not None and terminal_ui.ask_yes_no(
                    "Resume the latest unfinished workflow for this skill? [y/N]: ",
                    default=False,
                ):
                    result = skill.resume(
                        SkillResumeRequest(
                            repo_root=repo_root,
                            resume_point=latest_state,
                        )
                    )
                else:
                    input_paths = prompt_for_paths(skill)
                    result = skill.run(
                        SkillRunRequest(
                            repo_root=repo_root,
                            input_paths=input_paths,
                        )
                    )
            else:
                input_paths = prompt_for_paths(skill)
                result = skill.run(
                    SkillRunRequest(
                        repo_root=repo_root,
                        input_paths=input_paths,
                    )
                )

            terminal_ui.print_run_summary(
                result.success_count,
                result.failure_count,
                result.session_dir,
            )

            if not terminal_ui.ask_yes_no("Run another job? [Y/n]: ", default=True):
                return 0
        except (SkillCatalogError, InputLoadError, LLMClientError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print()


def prompt_for_paths(skill: SkillAdapter) -> list[Path]:
    raw_path = terminal_ui.prompt_for_input_path(skill)
    if not raw_path:
        raise RuntimeError("Cancelled.")
    return resolve_input_paths(raw_path, skill.input_extensions)


if __name__ == "__main__":
    raise SystemExit(main())
