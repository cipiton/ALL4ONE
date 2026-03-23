from __future__ import annotations  
  
from .models import ExecutionPlan, SkillDefinition  
from .router import detect_step  
  
  
def build_execution_plan(skill: SkillDefinition, input_text: str, forced_step_number: int = None):  
    detected_step = detect_step(input_text, skill, forced_step_number=forced_step_number)  
    step = skill.get_step(detected_step.step_number)  
  
    applicable_inputs = [  
        definition  
        for definition in skill.runtime_inputs  
        if definition.applies_to(step.number, input_text)  
    ]  
  
    reference_ids: list[str] = []  
    if skill.execution_strategy == "step_prompt":  
        if step.prompt_reference_id:  
            reference_ids.append(step.prompt_reference_id)  
        for reference in skill.references.values():  
            if reference.reference_id in reference_ids:  
                continue  
            if reference.load == "always":  
                reference_ids.append(reference.reference_id)  
                continue  
            if reference.step_numbers and step.number in reference.step_numbers:  
                reference_ids.append(reference.reference_id)  
    elif skill.execution_strategy == "structured_report":  
        for stage in skill.stages:  
            for reference_id in stage.reference_ids:  
                if reference_id not in reference_ids:  
                    reference_ids.append(reference_id)  
            for reference in skill.references.values():  
                if stage.name in reference.stage_names and reference.reference_id not in reference_ids:  
                    reference_ids.append(reference.reference_id)  
        for reference in skill.references.values():  
            if reference.load == "always" and reference.reference_id not in reference_ids:  
                reference_ids.append(reference.reference_id)  
  
    return ExecutionPlan(  
        strategy=skill.execution_strategy,  
        step=step,  
        detected_step=detected_step,  
        runtime_inputs=applicable_inputs,  
        reference_ids=reference_ids,  
        stage_names=[stage.name for stage in skill.stages],  
    ) 
