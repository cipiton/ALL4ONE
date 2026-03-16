from __future__ import annotations  
  
from .models import DetectedStep, SkillDefinition  
  
  
def detect_step(input_text: str, skill: SkillDefinition, forced_step_number: int = None):  
    if forced_step_number is not None and forced_step_number in skill.steps:  
        return DetectedStep(  
            step_number=forced_step_number,  
            reason=f"Startup policy selected step {forced_step_number}.",  
            scores={forced_step_number: 999},  
        )  
  
    if len(skill.steps) == 1:  
        step_number = skill.default_step_number  
        return DetectedStep(  
            step_number=step_number,  
            reason=f"Skill defines a single runnable step ({step_number}).",  
            scores={step_number: 1},  
        )  
  
    lowered = input_text.lower()  
    nonempty_lines = [line.strip() for line in input_text.splitlines() if line.strip()]  
    looks_like_list = _looks_like_list(nonempty_lines)  
    looks_like_script = _looks_like_script(nonempty_lines)  
  
    best_step = skill.default_step_number  
    best_score = -1  
    scores: dict[int, int] = {}  
    reasons: list[str] = []  
  
    for step in skill.ordered_steps():  
        score = step.route_priority  
        matched_tokens: list[str] = []  
  
        for token in step.route_keywords_any:  
            if token.lower() in lowered:  
                score += 2  
                matched_tokens.append(token)  
  
        if step.route_keywords_all and all(token.lower() in lowered for token in step.route_keywords_all):  
            score += 3  
            matched_tokens.extend(step.route_keywords_all)  
  
        if step.requires_list_like and looks_like_list:  
            score += 1  
        if step.requires_script_like and looks_like_script:  
            score += 1  
  
        scores[step.number] = score  
        if score > best_score:  
            best_step = step.number  
            best_score = score  
            reasons = matched_tokens  
  
    if best_score <= 0:  
        return DetectedStep(  
            step_number=skill.default_step_number,  
            reason=f"No strong routing signal matched; using default step {skill.default_step_number}.",  
            scores=scores,  
        )  
  
    if reasons:  
        reason = f"Matched routing hints for step {best_step}: {', '.join(dict.fromkeys(reasons))}."  
    else:  
        reason = f"Generic shape heuristics favored step {best_step}."  
    return DetectedStep(step_number=best_step, reason=reason, scores=scores)  
  
  
def _looks_like_list(lines: list[str]):  
    if len(lines) < 3:  
        return False  
    markers = 0  
    for line in lines[:20]:  
        if line.startswith(("-", "*", "", "1.", "2.", "3.", "??", "??")) or ":" in line or ":" in line:  
            markers += 1  
    return markers >= 4  
  
  
def _looks_like_script(lines: list[str]):  
    markers = 0  
    for line in lines[:20]:  
        if any(token in line for token in ("??", "??", "??", "??", "??", "??", "?", "Narration", "Dialogue", "Episode")):  
            markers += 1  
