"""Prompt assembly helpers."""

from __future__ import annotations

from engine.models import ChatMessage, SessionContext, SkillDefinition


def distill_workflow_rules(skill_definition: SkillDefinition) -> str:
    """Create a concise system message from SKILL.md."""
    lines = [
        f"Skill name: {skill_definition.intro_name}",
        f"Description: {skill_definition.description or 'N/A'}",
        "Workflow rules:",
        "- Follow SKILL.md as the source of truth.",
        "- Execute only the selected step for this run.",
        "- Do not chain later steps automatically.",
        "- Preserve the current workflow stage and output expectations.",
    ]
    if skill_definition.auto_chain_disabled:
        lines.append("- Wait for user confirmation before any later step outside this run.")
    ordered_steps = ", ".join(
        f"{step.number}:{step.title}" for step in sorted(skill_definition.steps.values(), key=lambda item: item.number)
    )
    lines.append(f"- Known steps: {ordered_steps}")
    return "\n".join(lines)


def build_messages(
    workflow_rules: str,
    step_prompt: str,
    context: SessionContext,
) -> list[ChatMessage]:
    """Assemble the exact message list sent to the model."""
    messages = [
        ChatMessage(role="system", content=workflow_rules),
        ChatMessage(role="system", content=step_prompt),
        ChatMessage(role="user", content=context.input_text),
    ]

    if context.chosen_style:
        messages.append(ChatMessage(role="user", content=f"Asset style choice: {context.chosen_style}"))
    if context.episode_count is not None:
        messages.append(ChatMessage(role="user", content=f"Requested episode count: {context.episode_count}"))
    if context.resume_source:
        messages.append(
            ChatMessage(
                role="user",
                content=(
                    "Resume context:\n"
                    f"- Previous run timestamp: {context.resume_source.timestamp}\n"
                    f"- Previous status: {context.resume_source.status}\n"
                    f"- Previous detected step: {context.resume_source.detected_step}\n"
                    f"- Previous output path: {context.resume_source.output_path or 'N/A'}"
                ),
            )
        )
    return messages
