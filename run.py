from __future__ import annotations  
  
import sys
from pathlib import Path
  
from app.skills.catalog import SkillCatalog, SkillCatalogError  
from app.skills.protocol import SkillResumeRequest, SkillRunRequest  
from engine.app_paths import get_app_root
from engine import terminal_ui  
from engine.input_loader import InputLoadError
from engine.input_requests import resolve_skill_input_request
from engine.llm_client import (
    LLMClientError,
    describe_active_model,
    format_runtime_error_message,
    load_env_file,
)
from engine.rewriting_project import prompt_rewriting_launch
from engine.runtime_config import load_runtime_config
  
  
def main() -> int:  
    repo_root = get_app_root(__file__)
    runtime_config = load_runtime_config(repo_root)
    terminal_ui.configure_console()  
    load_env_file(repo_root / '.env')  
    terminal_ui.print_intro(describe_active_model(repo_root))  
  
    while True:  
        try:  
            catalog = SkillCatalog.load(repo_root)  
            summaries = catalog.menu_summaries()  
            summary = terminal_ui.choose_skill(summaries)  
            if summary is None:  
                return 0  
  
            skill = catalog.get_skill(summary.skill_id)  
            latest_state = skill.find_resume_point(repo_root / 'outputs') if skill.supports_resume else None  

            if getattr(skill, 'skill_id', '') == 'rewriting':
                input_root_path, input_paths, launch_options = prompt_rewriting_launch(repo_root)
                result = skill.run(
                    SkillRunRequest(
                        repo_root=repo_root,
                        input_paths=input_paths,
                        input_root_path=input_root_path,
                        launch_options=launch_options,
                    )
                )
                terminal_ui.print_run_summary(
                    result.success_count,
                    result.failure_count,
                    result.session_dir,
                )
                if not terminal_ui.ask_yes_no('Run another job? [Y/n]: ', default=True):
                    return 0
                continue
  
            if skill.startup_policy.mode == 'explicit_step_selection':  
                input_root_path, input_paths = prompt_for_paths(skill)  
                action, selected_step = terminal_ui.choose_start_mode(  
                    skill.step_summaries,  
                    skill.startup_policy,  
                    latest_state if skill.startup_policy.allow_resume else None,  
                )  
                if action == 'resume':  
                    if latest_state is None:  
                        raise RuntimeError('No resumable run is available for this skill.')  
                    result = skill.resume(  
                        SkillResumeRequest(  
                            repo_root=repo_root,  
                            resume_point=latest_state,  
                        )  
                    )  
                else:  
                    result = skill.run(  
                        SkillRunRequest(  
                            repo_root=repo_root,  
                            input_paths=input_paths,  
                            input_root_path=input_root_path,  
                            selected_step_number=selected_step,  
                        )  
                    ) 
            elif skill.supports_resume and latest_state is not None and terminal_ui.ask_yes_no(  
                'Resume the latest unfinished workflow for this skill? [y/N]: ',  
                default=False,  
            ):  
                result = skill.resume(  
                    SkillResumeRequest(  
                        repo_root=repo_root,  
                        resume_point=latest_state,  
                    )  
                )  
            else:  
                input_root_path, input_paths = prompt_for_paths(skill)  
                result = skill.run(  
                    SkillRunRequest(  
                        repo_root=repo_root,  
                        input_paths=input_paths,  
                        input_root_path=input_root_path,  
                    )  
                )  
  
            terminal_ui.print_run_summary(  
                result.success_count,  
                result.failure_count,  
                result.session_dir,  
            )  
  
            if not terminal_ui.ask_yes_no('Run another job? [Y/n]: ', default=True):  
                return 0  
        except (SkillCatalogError, InputLoadError, LLMClientError, RuntimeError) as exc:  
            message = format_runtime_error_message(
                exc,
                troubleshooting_mode=runtime_config.troubleshooting_mode,
            )
            print(f'Error: {message}', file=sys.stderr)  
            print()  
  
  
def prompt_for_paths(skill) -> tuple[Path, list[Path]]:
    repo_root = get_app_root(__file__)
    raw_path = terminal_ui.prompt_for_input_path(skill)
    if not raw_path:
        raise RuntimeError('Cancelled.')
    return resolve_skill_input_request(repo_root, skill, raw_path=raw_path)
  
  
if __name__ == '__main__':  
    raise SystemExit(main())  
