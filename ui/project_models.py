from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .chat_state import ChatMessage, utc_now_iso


@dataclass(slots=True)
class ProjectSource:
    kind: str
    path: str
    name: str
    original_path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "path": self.path,
            "name": self.name,
            "original_path": self.original_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectSource":
        return cls(
            kind=str(payload.get("kind", "file")),
            path=str(payload.get("path", "")),
            name=str(payload.get("name", "")),
            original_path=str(payload.get("original_path", "")),
        )


@dataclass(slots=True)
class ProjectState:
    id: str
    name: str
    description: str
    workspace_path: str
    inputs_path: str
    outputs_path: str
    intermediate_path: str
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    selected_skill_id: str = ""
    selected_skill_name: str = ""
    source_inputs: list[ProjectSource] = field(default_factory=list)
    messages: list[ChatMessage] = field(default_factory=list)
    stage: str = "idle"
    current_prompt: str = ""
    current_choices: list[str] = field(default_factory=list)
    execution_in_progress: bool = False
    assistant_reply_pending: bool = False
    input_path: str = ""
    direct_text: str = ""
    selected_step_number: int | None = None
    runtime_values: dict[str, Any] = field(default_factory=dict)
    runtime_field_index: int = 0
    rewriting_mode: str = "build_bible_and_rewrite"
    rewriting_plan_path: str = ""
    rewriting_bible_path: str = ""
    rewriting_supplemental_path: str = ""
    latest_result: Any = None

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def reset_for_new_skill_run(self) -> None:
        self.stage = "idle"
        self.current_prompt = ""
        self.current_choices = []
        self.execution_in_progress = False
        self.assistant_reply_pending = False
        self.input_path = ""
        self.direct_text = ""
        self.selected_step_number = None
        self.runtime_values.clear()
        self.runtime_field_index = 0
        self.rewriting_mode = "build_bible_and_rewrite"
        self.rewriting_plan_path = ""
        self.rewriting_bible_path = ""
        self.rewriting_supplemental_path = ""
        self.latest_result = None
        self.touch()

    def project_root(self) -> Path:
        return Path(self.workspace_path)

    def inputs_dir(self) -> Path:
        return Path(self.inputs_path)

    def outputs_dir(self) -> Path:
        return Path(self.outputs_path)

    def intermediate_dir(self) -> Path:
        return Path(self.intermediate_path)

    def to_dict(self) -> dict[str, Any]:
        latest_result_payload: dict[str, Any] | None = None
        if self.latest_result is not None:
            latest_result_payload = {
                "session_dir": str(self.latest_result.session_dir),
                "success_count": self.latest_result.success_count,
                "failure_count": self.latest_result.failure_count,
                "primary_output": str(self.latest_result.primary_output) if self.latest_result.primary_output else "",
                "output_cards": [
                    {
                        "title": card.title,
                        "path": str(card.path),
                        "output_dir": str(card.output_dir),
                        "preview_text": card.preview_text,
                    }
                    for card in self.latest_result.output_cards
                ],
            }

        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "workspace_path": self.workspace_path,
            "inputs_path": self.inputs_path,
            "outputs_path": self.outputs_path,
            "intermediate_path": self.intermediate_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "selected_skill_id": self.selected_skill_id,
            "selected_skill_name": self.selected_skill_name,
            "source_inputs": [item.to_dict() for item in self.source_inputs],
            "messages": [message.to_dict() for message in self.messages],
            "stage": self.stage,
            "current_prompt": self.current_prompt,
            "current_choices": list(self.current_choices),
            "execution_in_progress": self.execution_in_progress,
            "assistant_reply_pending": self.assistant_reply_pending,
            "input_path": self.input_path,
            "direct_text": self.direct_text,
            "selected_step_number": self.selected_step_number,
            "runtime_values": dict(self.runtime_values),
            "runtime_field_index": self.runtime_field_index,
            "rewriting_mode": self.rewriting_mode,
            "rewriting_plan_path": self.rewriting_plan_path,
            "rewriting_bible_path": self.rewriting_bible_path,
            "rewriting_supplemental_path": self.rewriting_supplemental_path,
            "latest_result": latest_result_payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectState":
        from .backend_adapter import GuiOutputCard, GuiRunResult

        latest_result = None
        latest_payload = payload.get("latest_result")
        if isinstance(latest_payload, dict):
            output_cards = [
                GuiOutputCard(
                    title=str(card.get("title", "")),
                    path=Path(str(card.get("path", ""))),
                    output_dir=Path(str(card.get("output_dir", ""))),
                    preview_text=str(card.get("preview_text", "")),
                )
                for card in latest_payload.get("output_cards", [])
            ]
            latest_result = GuiRunResult(
                session_dir=Path(str(latest_payload.get("session_dir", ""))),
                success_count=int(latest_payload.get("success_count", 0)),
                failure_count=int(latest_payload.get("failure_count", 0)),
                primary_output=Path(str(latest_payload["primary_output"])) if latest_payload.get("primary_output") else None,
                output_cards=output_cards,
            )

        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            workspace_path=str(payload.get("workspace_path", "")),
            inputs_path=str(payload.get("inputs_path", "")),
            outputs_path=str(payload.get("outputs_path", "")),
            intermediate_path=str(payload.get("intermediate_path", "")),
            created_at=str(payload.get("created_at", utc_now_iso())),
            updated_at=str(payload.get("updated_at", utc_now_iso())),
            selected_skill_id=str(payload.get("selected_skill_id", "")),
            selected_skill_name=str(payload.get("selected_skill_name", "")),
            source_inputs=[ProjectSource.from_dict(item) for item in payload.get("source_inputs", []) if isinstance(item, dict)],
            messages=[ChatMessage.from_dict(message) for message in payload.get("messages", []) if isinstance(message, dict)],
            stage=str(payload.get("stage", "idle")),
            current_prompt=str(payload.get("current_prompt", "")),
            current_choices=[str(choice) for choice in payload.get("current_choices", [])],
            execution_in_progress=bool(payload.get("execution_in_progress", False)),
            assistant_reply_pending=bool(payload.get("assistant_reply_pending", False)),
            input_path=str(payload.get("input_path", "")),
            direct_text=str(payload.get("direct_text", "")),
            selected_step_number=payload.get("selected_step_number"),
            runtime_values=dict(payload.get("runtime_values", {})),
            runtime_field_index=int(payload.get("runtime_field_index", 0)),
            rewriting_mode=str(payload.get("rewriting_mode", "build_bible_and_rewrite")),
            rewriting_plan_path=str(payload.get("rewriting_plan_path", "")),
            rewriting_bible_path=str(payload.get("rewriting_bible_path", "")),
            rewriting_supplemental_path=str(payload.get("rewriting_supplemental_path", "")),
            latest_result=latest_result,
        )
