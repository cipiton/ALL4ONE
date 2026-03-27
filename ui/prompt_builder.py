from __future__ import annotations

from pathlib import Path

from engine.models import PromptMessage

from .backend_adapter import GuiSkillOption
from .chat_state import ChatSessionState


def build_llm_messages(
    *,
    skill: GuiSkillOption,
    session: ChatSessionState,
    project_name: str,
    output_root: Path,
    user_message: str,
) -> list[PromptMessage]:
    system_parts = [
        "You are Fake Agent, the embedded helper for a structured workflow desktop app.",
        "You help users understand the current workflow, expected inputs, steps, settings, and troubleshooting.",
        "Do not claim that a workflow ran, a file was created, validation passed, or outputs exist unless the conversation history explicitly confirms it.",
        "Do not fabricate paths, outputs, or completed actions.",
        "If the app is waiting for a file, folder, step number, or confirmation, explain that clearly and concisely.",
        f"Active workflow: {skill.display_name}",
        f"Workflow description: {skill.description or 'No description available.'}",
        f"Current workflow stage: {session.stage}",
        f"Current expected prompt: {session.current_prompt or 'No active prompt.'}",
        f"Project: {project_name or 'No active project'}",
        f"Output root: {output_root}",
    ]

    if skill.step_summaries:
        step_lines = [f"{step.number}. {step.title}" for step in skill.step_summaries[:12]]
        system_parts.append("Workflow steps:\n" + "\n".join(step_lines))

    if skill.runtime_inputs:
        runtime_names = ", ".join(field.prompt for field in skill.runtime_inputs[:8])
        system_parts.append(f"Known workflow runtime inputs: {runtime_names}")

    messages = [PromptMessage(role="system", content="\n".join(system_parts))]

    recent_history = session.messages[-8:]
    for item in recent_history:
        if item.role == "user":
            messages.append(PromptMessage(role="user", content=item.text))
            continue

        prefix = {
            "assistant": "Assistant",
            "status": "Status",
            "result": "Result",
            "error": "Error",
        }.get(item.role, "Assistant")
        messages.append(PromptMessage(role="assistant", content=f"{prefix}: {item.text}"))

    if not recent_history or recent_history[-1].role != "user" or recent_history[-1].text != user_message:
        messages.append(PromptMessage(role="user", content=user_message))

    return messages
