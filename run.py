from __future__ import annotations  
  
import sys
from datetime import datetime
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
    repo_root = Path(__file__).resolve().parent
    raw_path = terminal_ui.prompt_for_input_path(skill)
    if not raw_path:
        raise RuntimeError('Cancelled.')

    if bool(getattr(skill, 'allow_inline_text_input', False)) and _should_treat_as_inline_text(raw_path):
        return _create_inline_input_paths(repo_root, skill, raw_path)

    return Path(raw_path), resolve_input_paths(
        raw_path,
        skill.input_extensions,
        folder_mode=skill.folder_mode,
    )


def _should_treat_as_inline_text(raw_value: str) -> bool:
    stripped = raw_value.strip().strip('"')
    if not stripped:
        return False
    if any(separator in stripped for separator in ('\\', '/')):
        return False
    if Path(stripped).suffix:
        return False
    return True


def _create_inline_input_paths(repo_root: Path, skill, brief_text: str) -> tuple[Path, list[Path]]:
    skill_id = str(getattr(skill, 'skill_id', getattr(skill, 'name', 'skill'))).strip().replace(' ', '_') or 'skill'
    inline_inputs_dir = repo_root / 'outputs' / '.internal' / 'inline_inputs'
    inline_inputs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    input_path = inline_inputs_dir / f'{skill_id}__{timestamp}.txt'
    input_path.write_text(brief_text.strip() + '\n', encoding='utf-8')
    synthetic_root = repo_root / f'{skill_id}_inline_brief.txt'
    return synthetic_root, [input_path]
  
  
if __name__ == '__main__':  
    raise SystemExit(main())  
