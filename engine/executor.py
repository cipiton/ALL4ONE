from __future__ import annotations

from pathlib import Path
from typing import Any

from . import terminal_ui
from .input_loader import chunk_text, load_input_document, read_resource_text
from .llm_client import call_chat_completion, load_config_from_env, parse_json_response
from .runtime_config import load_runtime_config
from .models import DocumentResult, PromptMessage, RunState, SkillDefinition, StructuredStage
from .planner import build_execution_plan
from .prompts import build_step_prompt_messages, build_structured_stage_messages
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
) -> tuple[Path, list[DocumentResult]]:
    outputs_root = repo_root / "outputs"
    runtime_config = load_runtime_config(repo_root)
    single_resume = resume_state is not None and len(input_paths) == 1

    if single_resume:
        session_dir = Path(resume_state.output_directory)
        session_dir.mkdir(parents=True, exist_ok=True)
        timestamp = session_dir.name
    else:
        timestamp, session_dir = create_session_directory(outputs_root, skill.name, input_root_path or (input_paths[0] if input_paths else None))

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
            print(f"Error in {input_path.name}: {error_message}")
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
    verbose: bool = True,
) -> RunState:
    plan = build_execution_plan(skill, document.text, forced_step_number=forced_step_number)
    runtime_values = dict(resume_state.runtime_inputs) if resume_state else {}

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

    config = load_config_from_env(repo_root)

    if plan.strategy == "step_prompt" and skill.execution_policy.mode == "sequential_with_review":
        return _run_step_prompt_review_sequence(
            skill,
            document,
            output_dir,
            plan.step.number,
            runtime_values,
            resume_state,
            state,
            config,
            runtime_config,
            verbose,
        )

    if plan.strategy == "step_prompt":
        runtime_values = gather_runtime_inputs(plan.runtime_inputs, runtime_values)
        state.runtime_inputs = runtime_values
        save_state(state, output_dir, runtime_config)
        return _run_step_prompt(
            skill,
            document,
            output_dir,
            plan.step.number,
            runtime_values,
            resume_state,
            state,
            config,
            runtime_config,
            verbose,
        )

    if plan.strategy == "structured_report" and skill.execution_policy.mode == "sequential_with_review":
        return _run_structured_review_sequence(
            skill,
            document,
            output_dir,
            state,
            config,
            runtime_config,
            verbose,
        )

    return _run_structured(
        skill,
        document,
        output_dir,
        state,
        config,
        runtime_config,
        verbose,
    )


def gather_runtime_inputs(definitions, existing_values: dict[str, Any]) -> dict[str, Any]:
    values = dict(existing_values)
    for definition in definitions:
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
    if verbose:
        terminal_ui.print_progress(f"running step {step_number}: {skill.get_step(step_number).title}")
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
    )
    response = call_chat_completion(config, messages, json_mode=False)
    output_filename = step.output_filename or render_output_filename(
        skill.output_config.filename_template,
        document,
        step_number=step_number,
    )
    output_path = write_text_file(
        output_dir,
        output_filename,
        response.text,
    )
    if skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
        prompt_payload = {
            "model": response.model,
            "messages": [message.to_dict() for message in messages],
            "raw_response": response.raw_response,
        }
        _write_prompt_dump_files(output_dir, prompt_payload, step_number=step_number)
    state.output_files["primary"] = str(output_path)
    if step.output_key:
        state.output_files[step.output_key] = str(output_path)
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
    output_path = write_text_file(output_dir, output_filename, output_text)
    if prompt_payload and skill.output_config.include_prompt_dump and runtime_config.should_write_prompt_dump:
        _write_prompt_dump_files(output_dir, prompt_payload, step_number=step_number)
    state.output_files["primary"] = str(output_path)
    if step.output_key:
        state.output_files[step.output_key] = str(output_path)
    next_step_number = skill.next_step_number_for(step_number)
    state.working_input_path = str(output_path if next_step_number is not None else document.path)
    return output_path


 
def _build_restart_instruction(restart_request):  
    base_instruction = "Restart the current workflow step from scratch."  
    if restart_request:  
        return f"{base_instruction}\nAdditional restart instructions: {restart_request}"  
    return base_instruction  
  
  
def _run_step_prompt_review_sequence(skill, document, output_dir: Path, step_number: int, runtime_values: dict[str, Any], resume_state, state: RunState, config, runtime_config, verbose: bool):  
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
        runtime_values = gather_runtime_inputs(step_runtime_inputs, runtime_values)  
        state.runtime_inputs = runtime_values  
        save_state(state, output_dir, runtime_config)  
        if verbose:  
            terminal_ui.print_progress(f"running step {step.number}: {step.title}")  
  
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
                config,  
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
                if next_step_number is None:  
                    state.status = "completed"  
                    save_state(state, output_dir, runtime_config)  
                    return state  
                state.status = "completed_step"  
                save_state(state, output_dir, runtime_config)  
                if not skill.execution_policy.continue_until_end:  
                    return state  
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

