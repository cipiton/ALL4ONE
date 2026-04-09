from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import terminal_ui
from .episode_generation import (
    build_episode_batches,
    collect_regeneration_context,
    format_batch_filename,
    format_episode_range,
    format_episode_selection,
    infer_total_planned_episodes,
    parse_episode_selection,
)
from .input_loader import chunk_text, load_input_document, read_resource_text
from .llm_client import (
    call_chat_completion,
    describe_model_route,
    format_runtime_error_message,
    load_config_from_env,
    parse_json_response,
)
from .runtime_config import load_runtime_config
from .models import DocumentResult, PromptMessage, RunState, SkillDefinition, StructuredStage
from .planner import build_execution_plan
from .prompts import build_step_prompt_messages, build_structured_stage_messages
from .project_ingestion import execute_project_ingestion, should_use_project_ingestion
from .rewriting_project import execute_rewriting_project, should_offer_rewriting_project_mode
from .skill_loader import load_reference_texts
from .state_store import save_batch_summary, save_state
from .writer import (
    create_document_directory,
    create_internal_directory,
    create_session_directory,
    render_output_filename,
    render_section_report,
    write_json_file,
    write_text_file,
)


class ExecutionError(RuntimeError):
    """Raised for execution-specific failures."""


def execute_input_paths(
    repo_root: Path,
    skill: SkillDefinition,
    input_paths: list[Path],
    *,
    resume_state: RunState | None = None,
    forced_step_number: int | None = None,
    input_root_path: Path | None = None,
    outputs_root: Path | None = None,
    runtime_values: dict[str, Any] | None = None,
    auto_accept_review_steps: bool | None = None,
    launch_options: dict[str, Any] | None = None,
) -> tuple[Path, list[DocumentResult]]:
    outputs_root = (outputs_root or (repo_root / "outputs")).resolve()
    runtime_config = load_runtime_config(repo_root)
    if auto_accept_review_steps is not None:
        runtime_config.auto_accept_review_steps = bool(auto_accept_review_steps)
    single_resume = resume_state is not None and len(input_paths) == 1
    launch_options = launch_options or {}
    runtime_values = dict(runtime_values or {})
    rewriting_bible_only_mode = (
        not single_resume
        and skill.name == "rewriting"
        and str(launch_options.get("rewriting_project_mode") or "").strip() == "build_bible"
    )

    if single_resume:
        session_dir = Path(resume_state.output_directory)
        session_dir.mkdir(parents=True, exist_ok=True)
        timestamp = session_dir.name
    elif rewriting_bible_only_mode:
        session_dir = None
        timestamp = ""
    else:
        timestamp, session_dir = create_session_directory(
            outputs_root,
            skill.name,
            input_root_path or (input_paths[0] if input_paths else None),
            input_paths=input_paths,
        )

    if not single_resume and should_offer_rewriting_project_mode(
        skill,
        input_paths,
        input_root_path=input_root_path,
    ):
        project_result = execute_rewriting_project(
            repo_root,
            skill,
            input_paths,
            input_root_path=input_root_path,
            session_dir=session_dir,
            outputs_root=outputs_root,
            launch_options=launch_options,
            verbose=True,
        )
        if project_result is not None:
            return project_result
        if session_dir is None:
            raise RuntimeError("Rewriting bible-only mode did not return a project result.")

    if not single_resume and should_use_project_ingestion(
        skill,
        input_paths,
        input_root_path=input_root_path,
        runtime_config=runtime_config,
    ):
        return execute_project_ingestion(
            repo_root,
            skill,
            input_paths,
            input_root_path=input_root_path,
            session_dir=session_dir,
            forced_step_number=forced_step_number,
            runtime_config=runtime_config,
            execute_document_fn=execute_document,
            verbose=True,
        )

    results: list[DocumentResult] = []
    total = len(input_paths)
    batch_summary: dict[str, Any] = {
        "timestamp": timestamp,
        "skill_name": skill.name,
        "input_count": total,
        "documents": [],
    }
    if total > 1:
        save_batch_summary(session_dir, batch_summary, runtime_config)

    for index, input_path in enumerate(input_paths, start=1):
        if total > 1:
            terminal_ui.print_batch_progress(index, total, input_path)
        verbose = total == 1
        try:
            document = load_input_document(input_path, index=index, total=total)
            output_dir = session_dir if total == 1 else create_document_directory(session_dir, document)
            active_resume_state = resume_state if index == 1 and total == 1 else None
            state = execute_document(
                repo_root,
                skill,
                document,
                output_dir,
                resume_state=active_resume_state,
                forced_step_number=forced_step_number,
                runtime_config=runtime_config,
                initial_runtime_values=runtime_values,
                verbose=verbose,
            )
            primary_output = Path(state.primary_output_path) if state.primary_output_path else None
            results.append(
                DocumentResult(
                    document_path=input_path,
                    output_directory=output_dir,
                    status=state.status,
                    primary_output=primary_output,
                )
            )
            batch_summary["documents"].append(
                {
                    "document_path": str(input_path),
                    "status": state.status,
                    "output_directory": str(output_dir),
                    "primary_output": str(primary_output) if primary_output else None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            display_message = format_runtime_error_message(
                exc,
                troubleshooting_mode=runtime_config.troubleshooting_mode,
            )
            results.append(
                DocumentResult(
                    document_path=input_path,
                    output_directory=session_dir,
                    status="error",
                    error_message=error_message,
                )
            )
            batch_summary["documents"].append(
                {
                    "document_path": str(input_path),
                    "status": "error",
                    "error_message": error_message,
                }
            )
            print(f"Error in {input_path.name}: {display_message}")
        finally:
            if total > 1:
                save_batch_summary(session_dir, batch_summary, runtime_config)

    return session_dir, results


def execute_document(
    repo_root: Path,
    skill: SkillDefinition,
    document,
    output_dir: Path,
    *,
    resume_state=None,
    forced_step_number=None,
    runtime_config=None,
    initial_runtime_values: dict[str, Any] | None = None,
    verbose: bool = True,
) -> RunState:
    plan = build_execution_plan(skill, document.text, forced_step_number=forced_step_number)
    runtime_values = dict(initial_runtime_values or {})
    if resume_state:
        runtime_values.update(resume_state.runtime_inputs)

    state = RunState(
        timestamp=Path(output_dir).name,
        skill_name=skill.name,
        input_path=str(document.path),
        working_input_path=str(document.path),
        detected_step=plan.step.number,
        step_title=plan.step.title,
        step_reason=plan.detected_step.reason,
        runtime_inputs=runtime_values,
        status="running",
        output_directory=str(output_dir),
        output_files=dict(resume_state.output_files) if resume_state else {},
        strategy=skill.execution_strategy,
        notes=[plan.detected_step.reason],
        resume_from=resume_state.output_directory if resume_state else None,
    )
    save_state(state, output_dir, runtime_config)

    if plan.strategy == "step_prompt" and skill.execution_policy.mode == "sequential_with_review":
        return _run_step_prompt_review_sequence(
            repo_root,
            skill,
            document,
            output_dir,
            plan.step.number,
            runtime_values,
            resume_state,
            state,
            runtime_config,
            verbose,
        )

    if plan.strategy == "step_prompt":
        step_config = load_config_from_env(
            repo_root,
            skill=skill,
            step=plan.step,
            model_override=plan.step.model_override,
        )
        runtime_values = gather_runtime_inputs(
            plan.runtime_inputs,
            runtime_values,
            output_dir=output_dir,
            input_text=document.text,
            runtime_config=runtime_config,
        )
        state.runtime_inputs = runtime_values
        save_state(state, output_dir, runtime_config)
        return _run_step_prompt(
            repo_root,
            skill,
            document,
            output_dir,
            plan.step.number,
            runtime_values,
            resume_state,
            state,
            step_config,
            runtime_config,
            verbose,
        )

    if plan.strategy == "utility_script":
        runtime_values = gather_runtime_inputs(
            plan.runtime_inputs,
            runtime_values,
            output_dir=output_dir,
            input_text=document.text,
            runtime_config=runtime_config,
        )
        state.runtime_inputs = runtime_values
        save_state(state, output_dir, runtime_config)
        return _run_utility_script(
            repo_root,
            skill,
            document,
            output_dir,
            plan.step.number,
            runtime_values,
            state,
            runtime_config,
            verbose,
        )

    if plan.strategy == "structured_report" and skill.execution_policy.mode == "sequential_with_review":
        config = load_config_from_env(repo_root, skill=skill, route_role="step_execution")
        return _run_structured_review_sequence(
            skill,
            document,
            output_dir,
            state,
            config,
            runtime_config,
            verbose,
        )

    config = load_config_from_env(repo_root, skill=skill, route_role="step_execution")
    return _run_structured(
        skill,
        document,
        output_dir,
        state,
        config,
        runtime_config,
        verbose,
    )


def _resolve_step_route_role(skill: SkillDefinition, step) -> str:
    if step.model_role:
        return step.model_role
    title = f"{step.title} {step.step_id}".casefold()
    if any(token in title for token in ("qa", "质检", "polish", "final check", "统一")):
        return "qa_final_polish"
    if step.number == skill.final_step_number:
        return "final_deliverable"
    return "step_execution"


def gather_runtime_inputs(
    definitions,
    existing_values: dict[str, Any],
    *,
    output_dir: Path | None = None,
    input_text: str,
    runtime_config,
) -> dict[str, Any]:
    values = dict(existing_values)
    for definition in definitions:
        if definition.field_type == "episode_range":
            if definition.name in values and values.get("episode_batches"):
                continue
            total_episodes = infer_total_planned_episodes(input_text)
            if total_episodes is None:
                raise ExecutionError(
                    "Could not determine the total planned episodes from this adaptation plan. "
                    "Please make sure the plan includes a total episode count or numbered episode rows."
                )
            print(f"[setup] detected total episodes={total_episodes} from adaptation plan (local parse, no model)")
            generation_mode = str(values.get("generation_mode") or "generate").strip().lower() or "generate"
            existing_selection = values.get(definition.name)
            if existing_selection not in (None, ""):
                raw_selection = str(existing_selection)
                print(f"[setup] using provided episode selection={raw_selection}")
            else:
                raw_selection = terminal_ui.prompt_for_episode_selection(
                    total_episodes,
                    mode=generation_mode,
                    current_value=values.get(definition.name),
                )
            selection = parse_episode_selection(
                raw_selection,
                total_episodes,
                allow_blank_all=generation_mode != "regenerate",
            )
            batch_size = min(
                runtime_config.novel_to_drama_script_max_episodes_per_file,
                runtime_config.novel_to_drama_script_default_episodes_per_file,
            )
            if generation_mode == "regenerate":
                batch_size = 1
            elif selection.start_episode == selection.end_episode:
                batch_size = 1
            batches = build_episode_batches(
                selection,
                batch_size,
                preserve_exact_selection=generation_mode == "regenerate",
            )
            values[definition.name] = format_episode_selection(selection)
            values["detected_total_episodes"] = selection.total_episodes
            values["episodes_per_file"] = batch_size
            values["generation_mode"] = generation_mode
            values["selected_episode_numbers"] = list(selection.episodes)
            values["episode_batches"] = [
                {"start_episode": start_episode, "end_episode": end_episode}
                for start_episode, end_episode in batches
            ]
            if generation_mode == "regenerate":
                regeneration_instruction = values.get("regeneration_instruction")
                if regeneration_instruction in (None, ""):
                    regeneration_instruction = terminal_ui.prompt_for_regeneration_instruction(
                        current_value=values.get("regeneration_instruction"),
                    )
                values["regeneration_instruction"] = (
                    regeneration_instruction or values.get("regeneration_instruction") or ""
                )
                if output_dir is not None:
                    values.update(
                        collect_regeneration_context(
                            output_dir,
                            total_episodes=selection.total_episodes,
                            target_episodes=selection.episodes,
                        )
                    )
                if "existing_episode_reference" not in values and "neighboring_episode_context" not in values:
                    print("[setup] no prior episode drafts found; regeneration will use the adaptation plan and character context only")
            print(
                f"[setup] mode={generation_mode} selected episodes={format_episode_selection(selection)} "
                f"episodes_per_file={batch_size} batches={len(batches)} (local setup, no model)"
            )
            continue

        if definition.name in values and values[definition.name] not in (None, ""):
            continue
        values[definition.name] = terminal_ui.prompt_for_runtime_value(
            definition,
            current_value=values.get(definition.name),
        )
    return values


def load_resume_document(skill: SkillDefinition, state: RunState):
    resume_path = Path(state.primary_output_path or state.working_input_path or state.input_path)
    if not resume_path.exists():
        raise ExecutionError(f"Resume file does not exist: {resume_path}")

    forced_step_number = state.detected_step
    if state.status == "completed_step":
        next_step = skill.next_step_number_for(state.detected_step)
        if next_step is not None:
            forced_step_number = next_step
    return load_input_document(resume_path), forced_step_number


def _run_step_prompt(
    repo_root: Path,
    skill: SkillDefinition,
    document,
    output_dir: Path,
    step_number: int,
    runtime_values: dict[str, Any],
    resume_state: RunState | None,
    state: RunState,
    config,
    runtime_config,
    verbose: bool,
) -> RunState:
    step = skill.get_step(step_number)
    if runtime_values.get("episode_batches"):
        return _run_batched_step_prompt(
            repo_root,
            skill,
            document,
            output_dir,
            step,
            runtime_values,
            resume_state,
            state,
            config,
            runtime_config,
            verbose,
        )
    if verbose:
        terminal_ui.print_progress(f"running step {step_number}: {step.title}")
        terminal_ui.print_progress(
            f"model: {describe_model_route(repo_root, skill=skill, step=step, model_override=step.model_override)}"
        )
    reference_ids = []
    if step.prompt_reference_id:
        reference_ids.append(step.prompt_reference_id)
    for reference in skill.references.values():
        if reference.reference_id in reference_ids:
            continue
        if reference.load == "always" or (reference.step_numbers and step_number in reference.step_numbers):
            reference_ids.append(reference.reference_id)

    reference_texts = load_reference_texts(skill, reference_ids)
    input_blocks = _resolve_step_input_blocks(skill, step, document, state)
    messages = build_step_prompt_messages(
        skill,
        step,
        document,
        reference_texts,
        runtime_values,
        input_blocks=input_blocks,
        resume_state=resume_state,
    )
    response = call_chat_completion(config, messages, json_mode=False)
    output_filename = step.output_filename or render_output_filename(
        skill.output_config.filename_template,
        document,
        step_number=step_number,
    )
    output_path = _write_step_output_artifacts(
        step,
        output_dir,
        output_filename,
        response.text,
        state=state,
    )
    if skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
        prompt_payload = {
            "model": response.model,
            "messages": [message.to_dict() for message in messages],
            "raw_response": response.raw_response,
        }
        _write_prompt_dump_files(output_dir, prompt_payload, step_number=step_number)
    state.working_input_path = str(output_path if step_number < skill.final_step_number else document.path)
    state.status = "completed_step" if step_number < skill.final_step_number else "completed"
    save_state(state, output_dir, runtime_config)
    return state


def _generate_step_draft(skill, document, step_number: int, runtime_values: dict[str, Any], state: RunState, config, *, resume_state=None, draft_text=None, revision_request=None, user_instruction=None):
    step = skill.get_step(step_number)
    reference_ids = []
    if step.prompt_reference_id:
        reference_ids.append(step.prompt_reference_id)
    for reference in skill.references.values():
        if reference.reference_id in reference_ids:
            continue
        if reference.load == "always" or (reference.step_numbers and step_number in reference.step_numbers):
            reference_ids.append(reference.reference_id)

    reference_texts = load_reference_texts(skill, reference_ids)
    input_blocks = _resolve_step_input_blocks(skill, step, document, state)
    messages = build_step_prompt_messages(
        skill,
        step,
        document,
        reference_texts,
        runtime_values,
        input_blocks=input_blocks,
        resume_state=resume_state,
        draft_text=draft_text,
        revision_request=revision_request,
        user_instruction=user_instruction,
    )
    response = call_chat_completion(config, messages, json_mode=False)
    prompt_payload = {
        "model": response.model,
        "messages": [message.to_dict() for message in messages],
        "raw_response": response.raw_response,
    }
    return response.text, prompt_payload
def _persist_accepted_step_output(skill, document, output_dir: Path, step_number: int, output_text: str, state: RunState, runtime_config, prompt_payload=None) -> Path:
    step = skill.get_step(step_number)
    output_filename = step.output_filename or render_output_filename(
        skill.output_config.filename_template,
        document,
        step_number=step_number,
    )
    output_path = _write_step_output_artifacts(
        step,
        output_dir,
        output_filename,
        output_text,
        state=state,
    )
    if prompt_payload and skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
        _write_prompt_dump_files(output_dir, prompt_payload, step_number=step_number)
    next_step_number = skill.next_step_number_for(step_number)
    state.working_input_path = str(output_path if next_step_number is not None else document.path)
    return output_path


def _write_step_output_artifacts(step, output_dir: Path, output_filename: str, output_text: str, *, state: RunState) -> Path:
    output_path = write_text_file(output_dir, output_filename, output_text)
    resolved_outputs = {"primary": str(output_path)}
    if step.output_key:
        resolved_outputs[step.output_key] = str(output_path)
    if step.json_output_filename:
        json_payload = _extract_step_json_payload(step, output_text)
        json_path = write_json_file(output_dir, step.json_output_filename, json_payload)
        if step.json_output_key:
            resolved_outputs[step.json_output_key] = str(json_path)
    state.output_files.update(resolved_outputs)
    return output_path


def _extract_step_json_payload(step, output_text: str) -> Any:
    if not step.json_output_filename:
        raise ExecutionError(f"Step {step.number} does not define a JSON sidecar output.")

    matches = list(re.finditer(r"```json\s*(.*?)\s*```", output_text, flags=re.IGNORECASE | re.DOTALL))
    if not matches:
        raise ExecutionError(
            f"Step {step.number} requires a fenced JSON code block so '{step.json_output_filename}' can be written."
        )

    payload_text = matches[-1].group(1).strip()
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ExecutionError(
            f"Step {step.number} produced invalid JSON for '{step.json_output_filename}': {exc}"
        ) from exc


 
def _build_restart_instruction(restart_request):  
    base_instruction = "Restart the current workflow step from scratch."  
    if restart_request:  
        return f"{base_instruction}\nAdditional restart instructions: {restart_request}"  
    return base_instruction  
  
  
def _run_step_prompt_review_sequence(repo_root: Path, skill, document, output_dir: Path, step_number: int, runtime_values: dict[str, Any], resume_state, state: RunState, runtime_config, verbose: bool):  
    current_step_number = step_number  
    current_resume_state = resume_state  
    current_document = document
    while current_step_number is not None:  
        working_input_path = Path(state.working_input_path)
        if working_input_path != current_document.path:
            current_document = load_input_document(
                working_input_path,
                index=document.index,
                total=document.total,
            )
        step = skill.get_step(current_step_number)  
        step_runtime_inputs = [
            definition for definition in skill.runtime_inputs if definition.applies_to(step.number, current_document.text)
        ]
        runtime_values = gather_runtime_inputs(
            step_runtime_inputs,
            runtime_values,
            output_dir=output_dir,
            input_text=current_document.text,
            runtime_config=runtime_config,
        )  
        state.runtime_inputs = runtime_values  
        save_state(state, output_dir, runtime_config)  
        step_config = load_config_from_env(
            repo_root,
            skill=skill,
            step=step,
            model_override=step.model_override,
        )
        if verbose:  
            terminal_ui.print_progress(f"running step {step.number}: {step.title}")  
            terminal_ui.print_progress(
                f"model: {describe_model_route(repo_root, skill=skill, step=step, model_override=step.model_override)}"
            )
  
        draft_text = None  
        revision_request = None  
        user_instruction = None  
        while True:  
            draft_text, prompt_payload = _generate_step_draft(  
                skill,  
                current_document,  
                step.number,  
                runtime_values,  
                state,  
                step_config,  
                resume_state=current_resume_state,  
                draft_text=draft_text,  
                revision_request=revision_request,  
                user_instruction=user_instruction,  
            ) 
            current_resume_state = None  
            revision_request = None  
            user_instruction = None  
  
            while True:  
                if skill.execution_policy.preview_before_save:  
                    terminal_ui.show_step_output_preview(step.title, draft_text)  
                if runtime_config.auto_accept_review_steps:
                    if verbose:
                        terminal_ui.print_progress("auto-accept enabled; accepting current draft")
                    action = "accept"
                else:
                    action = terminal_ui.prompt_for_review_action()  
                if action == "view_full":  
                    terminal_ui.print_full_output(step.title, draft_text)  
                    continue  
                if action == "improve":  
                    revision_request = terminal_ui.prompt_for_improvement_request()  
                    if not revision_request:  
                        continue  
                    break  
                if action == "restart":  
                    restart_request = terminal_ui.prompt_for_restart_request()  
                    draft_text = None  
                    user_instruction = _build_restart_instruction(restart_request)  
                    break  
                if action == "cancel":  
                    return _finalize_review_cancellation(skill, output_dir, state, runtime_config)  
  
                _persist_accepted_step_output(  
                    skill,  
                    current_document,  
                    output_dir,  
                    step.number,  
                    draft_text,  
                    state,  
                    runtime_config,  
                    prompt_payload=prompt_payload,  
                )  
                state.detected_step = step.number  
                state.step_title = step.title  
                state.step_reason = f"Accepted step {step.number}: {step.title}."  
                next_step_number = skill.next_step_number_for(step.number)  
                if verbose:
                    terminal_ui.print_progress(f"accepted step {step.number}: {step.title}")
                if next_step_number is None:  
                    if verbose:
                        terminal_ui.print_progress("no next step found; workflow completed")
                    state.status = "completed"  
                    save_state(state, output_dir, runtime_config)  
                    return state  
                state.status = "completed_step"  
                save_state(state, output_dir, runtime_config)  
                if not skill.execution_policy.continue_until_end:  
                    if verbose:
                        terminal_ui.print_progress(
                            f"stopping after accepted step {step.number}; continue_until_end is disabled"
                        )
                    return state  
                if verbose:
                    try:
                        next_step = skill.get_step(next_step_number)
                        next_title = next_step.title
                    except ValueError:
                        next_title = str(next_step_number)
                    terminal_ui.print_progress(f"advancing to step {next_step_number}: {next_title}")
                current_step_number = next_step_number  
                draft_text = None  
                break  
  
            if action in {"improve", "restart"}:  
                continue  
            break  
  
    return state

def _finalize_review_cancellation(skill, output_dir: Path, state: RunState, runtime_config):  
    if state.output_files:  
        next_step_number = skill.next_step_number_for(state.detected_step)  
        state.status = "completed" if next_step_number is None else "completed_step"  
    else:  
        state.status = "awaiting_input"  
    state.notes.append("Run cancelled during review.")  
    save_state(state, output_dir, runtime_config)  
    return state 


def _run_structured_review_sequence(
    skill: SkillDefinition,
    document,
    output_dir: Path,
    state: RunState,
    config,
    runtime_config,
    verbose: bool,
) -> RunState:
    report_text = None
    prompt_payload = None
    model_name = config.model
    revision_request = None

    while True:
        if report_text is None:
            if verbose:
                terminal_ui.print_progress("running structured workflow")
                terminal_ui.print_progress(f"model: {config.model}")
            stage_outputs, prompt_dump, model_name = run_structured_workflow(
                skill,
                document,
                config,
                verbose=verbose,
            )
            final_sections = _extract_final_sections(stage_outputs)
            report_text = render_section_report(skill, document, final_sections, model_name=model_name)
            prompt_payload = {
                "model": model_name,
                "stages": prompt_dump.get("stages", {}),
                "stage_outputs": stage_outputs,
            }
        elif revision_request:
            report_text, prompt_payload, model_name = _revise_structured_report(
                skill,
                document,
                report_text,
                revision_request,
                config,
                model_name=model_name,
            )
            revision_request = None

        if skill.execution_policy.preview_before_save:
            terminal_ui.show_step_output_preview("Structured report", report_text)

        while True:
            if runtime_config.auto_accept_review_steps:
                if verbose:
                    terminal_ui.print_progress("auto-accept enabled; accepting current draft")
                action = "accept"
            else:
                action = terminal_ui.prompt_for_review_action()
            if action == "view_full":
                terminal_ui.print_full_output("Structured report", report_text)
                continue
            if action == "improve":
                revision_request = terminal_ui.prompt_for_improvement_request()
                if not revision_request:
                    continue
                break
            if action == "restart":
                restart_request = terminal_ui.prompt_for_restart_request()
                report_text = None
                prompt_payload = None
                revision_request = None
                if restart_request:
                    state.notes.append(f"Structured workflow restart request: {restart_request}")
                break
            if action == "cancel":
                state.status = "awaiting_input"
                state.notes.append("Run cancelled during structured review.")
                save_state(state, output_dir, runtime_config)
                return state

            output_path = write_text_file(
                output_dir,
                render_output_filename(
                    skill.output_config.filename_template,
                    document,
                    step_number=state.detected_step,
                ),
                report_text,
            )
            write_json_file(output_dir, "stage_outputs.json", prompt_payload.get("stage_outputs", {}))
            if skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
                _write_prompt_dump_files(output_dir, prompt_payload)

            state.output_files = {
                "primary": str(output_path),
                "stage_outputs": str(output_dir / "stage_outputs.json"),
            }
            state.status = "completed"
            save_state(state, output_dir, runtime_config)
            return state

        if action in {"improve", "restart"}:
            continue

    return state


def _revise_structured_report(
    skill: SkillDefinition,
    document,
    current_report: str,
    revision_request: str,
    config,
    *,
    model_name: str,
) -> tuple[str, dict[str, Any], str]:
    messages = [
        PromptMessage(
            role="system",
            content=(
                "You are revising a workflow output. Return only the complete revised report text. "
                "Preserve the report language, section structure, and useful factual content unless the revision request requires changes."
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                f"Skill: {skill.display_name}\n"
                f"Description: {skill.description}\n"
                f"Input document: {document.path.name}\n\n"
                f"Current report:\n{current_report}\n\n"
                f"Revision request:\n{revision_request}"
            ),
        ),
    ]
    response = call_chat_completion(config, messages, json_mode=False)
    payload = {
        "model": response.model,
        "revision_request": revision_request,
        "messages": [message.to_dict() for message in messages],
        "raw_response": response.raw_response,
    }
    return response.text, payload, response.model
def _run_structured(
    skill: SkillDefinition,
    document,
    output_dir: Path,
    state: RunState,
    config,
    runtime_config,
    verbose: bool,
) -> RunState:
    if verbose:
        terminal_ui.print_progress("running structured workflow")
        terminal_ui.print_progress(f"model: {config.model}")
    stage_outputs, prompt_dump, model_name = run_structured_workflow(
        skill,
        document,
        config,
        verbose=verbose,
    )
    write_json_file(output_dir, "stage_outputs.json", stage_outputs)

    final_sections = _extract_final_sections(stage_outputs)
    report_text = render_section_report(skill, document, final_sections, model_name=model_name)
    output_path = write_text_file(
        output_dir,
        render_output_filename(skill.output_config.filename_template, document, step_number=state.detected_step),
        report_text,
    )
    if skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
        _write_prompt_dump_files(output_dir, prompt_dump)

    state.output_files = {
        "primary": str(output_path),
        "stage_outputs": str(output_dir / "stage_outputs.json"),
    }
    state.status = "completed"
    save_state(state, output_dir, runtime_config)
    return state


def _run_batched_step_prompt(
    repo_root: Path,
    skill: SkillDefinition,
    document,
    output_dir: Path,
    step,
    runtime_values: dict[str, Any],
    resume_state: RunState | None,
    state: RunState,
    config,
    runtime_config,
    verbose: bool,
) -> RunState:
    reference_ids = []
    if step.prompt_reference_id:
        reference_ids.append(step.prompt_reference_id)
    for reference in skill.references.values():
        if reference.reference_id in reference_ids:
            continue
        if reference.load == "always" or (reference.step_numbers and step.number in reference.step_numbers):
            reference_ids.append(reference.reference_id)

    reference_texts = load_reference_texts(skill, reference_ids)
    input_blocks = _resolve_step_input_blocks(skill, step, document, state)
    total_episodes = int(runtime_values.get("detected_total_episodes") or 0)
    batch_specs = list(runtime_values.get("episode_batches") or [])
    selected_range = str(runtime_values.get("episode_range") or "all")
    generation_mode = str(runtime_values.get("generation_mode") or "generate")
    generated_files: list[Path] = []
    failures: list[dict[str, Any]] = []
    route_role = _resolve_step_route_role(skill, step)
    batch_output_dir = output_dir / "regenerated" if generation_mode == "regenerate" else output_dir

    for index, batch in enumerate(batch_specs, start=1):
        start_episode = int(batch["start_episode"])
        end_episode = int(batch["end_episode"])
        batch_range = format_episode_range(start_episode, end_episode, total_episodes=total_episodes)
        batch_runtime_values = dict(runtime_values)
        batch_runtime_values.pop("episode_batches", None)
        batch_runtime_values.pop("selected_episode_numbers", None)
        batch_runtime_values["episode_range"] = batch_range
        batch_runtime_values["selected_episode_range"] = selected_range
        batch_runtime_values["current_batch_index"] = f"{index}/{len(batch_specs)}"
        batch_runtime_values["current_batch_range"] = batch_range
        batch_runtime_values["generation_mode"] = generation_mode

        if verbose:
            print(
                f"[batch {index}/{len(batch_specs)}] "
                f"route={route_role} "
                f"model={config.model} "
                f"mode={generation_mode} "
                f"episodes {batch_range}"
            )

        messages = build_step_prompt_messages(
            skill,
            step,
            document,
            reference_texts,
            batch_runtime_values,
            input_blocks=input_blocks,
            resume_state=resume_state,
        )
        try:
            response = call_chat_completion(config, messages, json_mode=False)
        except Exception as exc:  # noqa: BLE001
            failures.append({"range": batch_range, "error": str(exc)})
            continue

        output_filename = format_batch_filename(
            start_episode,
            end_episode,
            total_episodes=total_episodes,
            regeneration=generation_mode == "regenerate",
        )
        output_path = write_text_file(batch_output_dir, output_filename, response.text)
        generated_files.append(output_path)

        if skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
            internal_dir = create_internal_directory(batch_output_dir)
            write_json_file(
                internal_dir,
                f"prompt_dump_step_{step.number}_{output_filename.replace('.txt', '')}.json",
                {
                    "model": response.model,
                    "messages": [message.to_dict() for message in messages],
                    "raw_response": response.raw_response,
                },
            )

    if not generated_files:
        failure_details = "; ".join(f"{item['range']}: {item['error']}" for item in failures) or "no batches generated"
        raise ExecutionError(f"Episode batch generation failed: {failure_details}")

    manifest_payload = {
        "generation_mode": generation_mode,
        "detected_total_episodes": total_episodes,
        "selected_episode_range": selected_range,
        "episodes_per_file": runtime_values.get("episodes_per_file"),
        "generated_files": [path.name for path in generated_files],
        "failures": failures,
    }
    manifest_filename = "episode_regenerations.json" if generation_mode == "regenerate" else "episode_batches.json"
    manifest_path = write_json_file(batch_output_dir, manifest_filename, manifest_payload)

    state.output_files["primary"] = str(generated_files[0])
    state.output_files["episode_batch_manifest"] = str(manifest_path)
    state.output_files["episode_batches"] = str(manifest_path)
    if generation_mode == "regenerate":
        state.output_files["episode_regenerations"] = str(manifest_path)
    if step.output_key:
        state.output_files[step.output_key] = str(generated_files[0])
    if failures:
        state.notes.append(
            "Batch failures: " + "; ".join(f"{item['range']}: {item['error']}" for item in failures)
        )
    state.working_input_path = str(document.path)
    state.status = "completed_step" if step.number < skill.final_step_number else "completed"
    save_state(state, output_dir, runtime_config)
    return state


def _run_utility_script(
    repo_root: Path,
    skill: SkillDefinition,
    document,
    output_dir: Path,
    step_number: int,
    runtime_values: dict[str, Any],
    state: RunState,
    runtime_config,
    verbose: bool,
) -> RunState:
    step = skill.get_step(step_number)
    if verbose:
        terminal_ui.print_progress(f"running utility step {step_number}: {step.title}")

    utility = skill.utility_script
    if utility is None:
        raise ExecutionError(f"Skill '{skill.name}' is missing utility script configuration.")
    if not utility.absolute_path.exists():
        raise ExecutionError(f"Utility script does not exist: {utility.absolute_path}")

    module_name = f"_skill_utility_{skill.name}_{step_number}"
    spec = importlib.util.spec_from_file_location(module_name, utility.absolute_path)
    if spec is None or spec.loader is None:
        raise ExecutionError(f"Could not load utility script: {utility.absolute_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    entrypoint = getattr(module, utility.entrypoint, None)
    if not callable(entrypoint):
        raise ExecutionError(
            f"Utility script '{utility.relative_path}' does not define callable entrypoint '{utility.entrypoint}'."
        )

    raw_result = entrypoint(
        repo_root=repo_root,
        skill=skill,
        document=document,
        output_dir=output_dir,
        step_number=step_number,
        runtime_values=dict(runtime_values),
        state=state,
    )
    result = raw_result if isinstance(raw_result, dict) else {}

    resolved_outputs: dict[str, str] = {}
    raw_output_files = result.get("output_files", {})
    if isinstance(raw_output_files, dict):
        for key, value in raw_output_files.items():
            resolved_outputs[str(key)] = str(_resolve_utility_output_path(output_dir, value))

    primary_candidate = result.get("primary_output")
    if primary_candidate in (None, "") and "primary" in resolved_outputs:
        primary_candidate = resolved_outputs["primary"]
    primary_path = (
        _resolve_utility_output_path(output_dir, primary_candidate)
        if primary_candidate not in (None, "")
        else _resolve_default_utility_primary_output(output_dir)
    )
    resolved_outputs["primary"] = str(primary_path)
    if step.output_key and step.output_key not in resolved_outputs:
        resolved_outputs[step.output_key] = str(primary_path)

    state.output_files.update(resolved_outputs)
    state.working_input_path = str(
        _resolve_utility_output_path(output_dir, result["working_input_path"])
        if result.get("working_input_path") not in (None, "")
        else document.path
    )

    notes = result.get("notes", [])
    if isinstance(notes, list):
        state.notes.extend(str(item) for item in notes if str(item).strip())

    status = str(result.get("status") or "completed")
    if status not in {"completed", "completed_step", "awaiting_input", "running", "error"}:
        status = "completed"
    state.status = status
    save_state(state, output_dir, runtime_config)
    return state


def run_structured_workflow(
    skill: SkillDefinition,
    document,
    config,
    *,
    verbose: bool,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    reference_ids = []
    for stage in skill.stages:
        for reference_id in stage.reference_ids:
            if reference_id not in reference_ids:
                reference_ids.append(reference_id)
        for reference in skill.references.values():
            if stage.name in reference.stage_names and reference.reference_id not in reference_ids:
                reference_ids.append(reference.reference_id)
    reference_texts = load_reference_texts(skill, reference_ids)

    stage_outputs: dict[str, Any] = {}
    prompt_dump: dict[str, Any] = {"stages": {}}
    last_model_name = config.model

    for stage in skill.stages:
        if verbose:
            terminal_ui.print_progress(f"stage: {stage.name}")
        stage_output, stage_prompt_dump, last_model_name = run_structured_stage(
            skill,
            stage,
            document,
            reference_texts,
            stage_outputs,
            config,
        )
        stage_outputs[stage.name] = stage_output
        prompt_dump["stages"][stage.name] = stage_prompt_dump

    prompt_dump["model"] = last_model_name
    return stage_outputs, prompt_dump, last_model_name


def run_structured_stage(
    skill: SkillDefinition,
    stage: StructuredStage,
    document,
    reference_texts: dict[str, str],
    stage_outputs: dict[str, Any],
    config,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    if stage.kind == "document_json" and stage.chunkable and skill.chunking.enabled:
        chunks = []
        if document.character_count > skill.chunking.threshold_chars:
            chunks = chunk_text(document.text, skill.chunking.chunk_size, skill.chunking.overlap)
        if len(chunks) > 1:
            return _run_chunked_stage(skill, stage, document, reference_texts, stage_outputs, config, chunks)

    messages = build_structured_stage_messages(
        skill,
        stage,
        document,
        reference_texts,
        stage_outputs,
    )
    response = call_chat_completion(config, messages, json_mode=True)
    parsed = parse_json_response(response)
    prompt_dump = {
        "messages": [message.to_dict() for message in messages],
        "raw_response": response.raw_response,
    }
    return parsed, prompt_dump, response.model


def _run_chunked_stage(
    skill: SkillDefinition,
    stage: StructuredStage,
    document,
    reference_texts: dict[str, str],
    stage_outputs: dict[str, Any],
    config,
    chunks: list[str],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    chunk_results: list[dict[str, Any]] = []
    chunk_prompt_dump: dict[str, Any] = {"chunks": []}
    model_name = config.model

    for index, chunk in enumerate(chunks, start=1):
        messages = build_structured_stage_messages(
            skill,
            stage,
            document,
            reference_texts,
            stage_outputs,
            document_text_override=chunk,
            chunk_label=f"Input chunk {index}/{len(chunks)} from {document.path.name}",
        )
        response = call_chat_completion(config, messages, json_mode=True)
        model_name = response.model
        parsed = parse_json_response(response)
        chunk_results.append(parsed)
        chunk_prompt_dump["chunks"].append(
            {
                "chunk_index": index,
                "messages": [message.to_dict() for message in messages],
                "raw_response": response.raw_response,
            }
        )

    merge_messages = build_structured_stage_messages(
        skill,
        stage,
        document,
        reference_texts,
        stage_outputs,
        merge_payload=chunk_results,
    )
    merge_response = call_chat_completion(config, merge_messages, json_mode=True)
    merged = parse_json_response(merge_response)
    chunk_prompt_dump["merge"] = {
        "messages": [message.to_dict() for message in merge_messages],
        "raw_response": merge_response.raw_response,
    }
    return merged, chunk_prompt_dump, merge_response.model


def _write_prompt_dump_files(output_dir: Path, payload: dict[str, Any], step_number: int | None = None) -> None:
    internal_dir = create_internal_directory(output_dir)
    write_json_file(internal_dir, "prompt_dump.json", payload)
    if step_number is not None:
        write_json_file(internal_dir, f"prompt_dump_step_{step_number}.json", payload)


def _extract_final_sections(stage_outputs: dict[str, Any]) -> dict[str, Any]:
    for key in ("final_report", "final_sections", "report"):
        candidate = stage_outputs.get(key)
        if isinstance(candidate, dict) and isinstance(candidate.get("sections"), dict):
            return dict(candidate["sections"])
    for value in reversed(list(stage_outputs.values())):
        if isinstance(value, dict) and isinstance(value.get("sections"), dict):
            return dict(value["sections"])
    raise ExecutionError("Structured workflow did not return a final sections payload.")


def _resolve_step_input_blocks(
    skill: SkillDefinition,
    step,
    document,
    state: RunState,
) -> list[tuple[str, str]] | None:
    if not step.input_blocks:
        return None

    resolved: list[tuple[str, str]] = []
    used_document_fallback = False
    for block in step.input_blocks:
        content = _resolve_input_block_content(block.source_key, document, state, used_document_fallback)
        if content is None:
            if block.required:
                raise ExecutionError(
                    f"Required input block '{block.source_key}' is missing for skill '{skill.name}' step {step.number}."
                )
            continue
        if block.source_key != "user_brief" and content == document.text and not used_document_fallback:
            used_document_fallback = True
        resolved.append((block.label, content))
    return resolved


def _resolve_input_block_content(
    source_key: str,
    document,
    state: RunState,
    used_document_fallback: bool,
) -> str | None:
    if source_key == "user_brief":
        return document.text

    output_path = state.output_files.get(source_key)
    if output_path:
        candidate = Path(output_path)
        if candidate.exists():
            return read_resource_text(candidate).strip()

    if not used_document_fallback:
        return document.text
    return None


def _resolve_utility_output_path(output_dir: Path, value: Any) -> Path:
    if value in (None, ""):
        raise ExecutionError("Utility script returned an empty output path.")
    candidate = Path(str(value))
    if not candidate.is_absolute():
        candidate = output_dir / candidate
    candidate = candidate.resolve()
    base_dir = output_dir.resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as exc:
        raise ExecutionError(f"Utility output escapes the session directory: {value}") from exc
    if not candidate.exists():
        raise ExecutionError(f"Utility output path does not exist: {candidate}")
    return candidate


def _resolve_default_utility_primary_output(output_dir: Path) -> Path:
    default_index = output_dir / "index.txt"
    if default_index.exists():
        return default_index.resolve()
    raise ExecutionError("Utility script did not return a primary output and no default index.txt was found.")

