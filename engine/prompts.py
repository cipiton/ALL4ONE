from __future__ import annotations  
  
import json  
from typing import Any  
  
from .models import InputDocument, PromptMessage, RunState, SkillDefinition, SkillStep, StructuredStage  
  
  
def build_step_prompt_messages(  
    skill: SkillDefinition,  
    step: SkillStep,  
    document: InputDocument,  
    reference_texts: dict[str, str],  
    runtime_values: dict[str, Any],  
    input_blocks: list[tuple[str, str]] | None = None,  
    resume_state: RunState | None = None,  
    draft_text: str | None = None,  
    revision_request: str | None = None,  
) -> list[PromptMessage]:  
    prompt_reference = ''  
    auxiliary_references: dict[str, str] = {}  
    for reference_id, text in reference_texts.items():  
        reference = skill.get_reference(reference_id)  
        if reference.kind == 'prompt' and reference_id == step.prompt_reference_id:  
            prompt_reference = text  
        else:  
            auxiliary_references[reference.relative_path] = text  
  
    messages = [  
        PromptMessage(  
            role='system',  
            content=(  
                f'Skill: {skill.display_name}\n'  
                f'Description: {skill.description}\n'  
                'Execution rules:\n'  
                '- Treat SKILL.md as the source of truth.\n'  
                '- Execute only the selected step for this run.\n'  
                '- Do not auto-chain to a later step.\n'  
                '- Preserve the workflow\'s required output structure.'  
            ),  
        ),  
        PromptMessage(role='system', content=f'Skill instructions excerpt:\n{distill_skill_body(skill)}'),  
    ]  
  
    if skill.system_instructions:  
        messages.append(PromptMessage(role='system', content=skill.system_instructions))  
  
    if prompt_reference:  
        messages.append(PromptMessage(role='system', content=prompt_reference))  
  
    if auxiliary_references:  
        messages.append(  
            PromptMessage(  
                role='system',  
                content=f'Additional references:\n{format_reference_texts(auxiliary_references)}',  
            )  
        ) 
  
    if input_blocks:  
        block_text = '\n\n'.join(f'{label}\n{text}' for label, text in input_blocks if text.strip())  
        messages.append(  
            PromptMessage(  
                role='user',  
                content=f'Source document ({document.path.name}) with resolved workflow inputs:\n\n{block_text}',  
            )  
        )  
    else:  
        messages.append(  
            PromptMessage(  
                role='user',  
                content=f'Input document ({document.path.name}):\n{document.text}',  
            )  
        )  
  
    if runtime_values:  
        runtime_lines = '\n'.join(f'- {key}: {value}' for key, value in runtime_values.items())  
        messages.append(PromptMessage(role='user', content=f'Runtime inputs:\n{runtime_lines}'))  
  
    if resume_state is not None:  
        messages.append(  
            PromptMessage(  
                role='user',  
                content=(  
                    'Resume context:\n'  
                    f'- Previous step: {resume_state.detected_step}\n'  
                    f'- Previous status: {resume_state.status}\n'  
                    f'- Previous output: {resume_state.primary_output_path or 'N/A'}'  
                ),  
            ),  
        )  
  
    if draft_text:  
        messages.append(PromptMessage(role='assistant', content=draft_text))  
  
    if revision_request:  
        messages.append(  
            PromptMessage(  
                role='user',  
                content=(  
                    'Revise the previous draft for the same workflow step.\n'  
                    f'Revision request: {revision_request}'  
                ),  
            ),  
        )  
  
    return messages  
  
  
def build_structured_stage_messages(  
    skill: SkillDefinition,  
    stage: StructuredStage,  
    document: InputDocument,  
    reference_texts: dict[str, str],  
    stage_outputs: dict[str, Any],  
    *,  
    document_text_override: str | None = None,  
    chunk_label: str | None = None,  
    merge_payload: list[dict[str, Any]] | None = None,  
) -> list[PromptMessage]:  
    schema = stage.merge_schema if merge_payload is not None and stage.merge_schema else stage.schema  
    objective = stage.merge_objective if merge_payload is not None and stage.merge_objective else stage.objective  
    references = {  
        skill.get_reference(reference_id).relative_path: reference_texts[reference_id]  
        for reference_id in stage.reference_ids  
        if reference_id in reference_texts  
    }  
    inputs = {key: stage_outputs[key] for key in stage.input_keys if key in stage_outputs} 
  
    return [  
        PromptMessage(  
            role='system',  
            content='You are a precise workflow runner. Return only a JSON object with no extra commentary.',  
        ),  
        PromptMessage(  
            role='user',  
            content=(  
                f'Skill: {skill.display_name}\n'  
                f'Description: {skill.description}\n'  
                f'Stage: {stage.name}\n'  
                f'Objective: {objective}\n\n'  
                f'Skill instructions excerpt:\n{distill_skill_body(skill)}\n\n'  
                f'Expected JSON schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n'  
                f'Reference materials:\n{format_reference_texts(references)}\n\n'  
                f'Previous stage outputs:\n{json.dumps(inputs or {}, ensure_ascii=False, indent=2)}\n\n'  
                f'{_build_stage_payload(document, document_text_override, chunk_label, merge_payload)}'  
            ),  
        ),  
    ]  
  
  
def distill_skill_body(skill: SkillDefinition) -> str:  
    lines = [line.strip() for line in skill.body.splitlines() if line.strip()]  
    if not lines:  
        return 'No additional instructions.'  
    return '\n'.join(lines[:14])  
  
  
def format_reference_texts(reference_texts: dict[str, str]) -> str:  
    if not reference_texts:  
        return 'No additional references.'  
    blocks = []  
    for path, text in reference_texts.items():  
        blocks.append(f'[{path}]\n{text.strip()}')  
    return '\n\n'.join(blocks)  
  
  
def _build_stage_payload(  
    document: InputDocument,  
    document_text_override: str | None,  
    chunk_label: str | None,  
    merge_payload: list[dict[str, Any]] | None,  
) -> str:  
    if merge_payload is not None:  
        return f'Chunk summaries to merge:\n{json.dumps(merge_payload, ensure_ascii=False, indent=2)}'  
  
    payload_label = chunk_label or f'Input document: {document.path.name}'  
    payload_text = document_text_override or document.text  
    return (  
        f'{payload_label}\n'  
        f'Characters: {len(payload_text)}\n'  
        f'Approx tokens: {document.estimated_tokens}\n\n'  
        f'Source text:\n{payload_text}'  
    )  

