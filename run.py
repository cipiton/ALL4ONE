from __future__ import annotations  
  
import sys  
from pathlib import Path  
  
from app.skills.catalog import SkillCatalog, SkillCatalogError  
from app.skills.protocol import SkillResumeRequest, SkillRunRequest  
from engine import terminal_ui  
from engine.input_loader import InputLoadError, resolve_input_paths  
from engine.llm_client import LLMClientError, describe_active_model, load_env_file  
  
  
def main() -> int:  
    repo_root = Path(__file__).resolve().parent  
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
            print(f'Error: {exc}', file=sys.stderr)  
            print()  
  
  
def prompt_for_paths(skill) -> tuple[Path, list[Path]]:  
    raw_path = terminal_ui.prompt_for_input_path(skill)  
    if not raw_path:  
        raise RuntimeError('Cancelled.')  
    return Path(raw_path), resolve_input_paths(  
        raw_path,  
        skill.input_extensions,  
        folder_mode=skill.folder_mode,  
    )  
  
  
if __name__ == '__main__':  
    raise SystemExit(main())  
