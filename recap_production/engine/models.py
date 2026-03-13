"""Shared data models for the interactive runner."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


RunStatus = Literal[
    "completed_step",
    "awaiting_missing_input",
    "awaiting_user_confirmation",
    "error",
]


@dataclass(slots=True)
class StepDefinition:
    """A single workflow step parsed from SKILL.md."""

    number: int
    title: str
    prompt_path: str


@dataclass(slots=True)
class SkillDefinition:
    """Parsed workflow metadata derived from SKILL.md."""

    skill_path: str
    skill_md_path: str
    skill_md_text: str
    intro_name: str
    description: str
    step_based: bool
    auto_chain_disabled: bool
    steps: dict[int, StepDefinition]

    def get_step(self, step_number: int) -> StepDefinition:
        """Return a configured step or raise a useful error."""
        try:
            return self.steps[step_number]
        except KeyError as exc:
            raise ValueError(f"Step {step_number} is not defined in SKILL.md.") from exc


@dataclass(slots=True)
class StepDetectionResult:
    """Routing decision for the current input."""

    step_number: int
    reason: str
    needs_episode_count: bool = False
    is_rewrite_task: bool = False
    resembles_asset_inventory: bool = False
    resembles_script: bool = False


@dataclass(slots=True)
class ChatMessage:
    """Single chat message sent to the provider."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        """Serialize the message for the provider."""
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMConfig:
    """Runtime configuration sourced from environment variables."""

    api_key: str
    base_url: str | None
    model: str


@dataclass(slots=True)
class LLMResult:
    """Structured response returned by the LLM provider."""

    text: str
    model: str
    raw_response: dict[str, Any]


@dataclass(slots=True)
class RunState:
    """Persisted state for a single skill run."""

    timestamp: str
    skill_path: str
    input_file_path: str
    detected_step: int
    chosen_style: str | None
    episode_count: int | None
    output_path: str | None
    status: RunStatus
    output_directory: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the state into JSON-safe values."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        """Deserialize a stored state payload."""
        return cls(
            timestamp=str(data["timestamp"]),
            skill_path=str(data["skill_path"]),
            input_file_path=str(data["input_file_path"]),
            detected_step=int(data["detected_step"]),
            chosen_style=data.get("chosen_style"),
            episode_count=_coerce_optional_int(data.get("episode_count")),
            output_path=data.get("output_path"),
            status=data["status"],
            output_directory=str(data["output_directory"]),
            notes=[str(item) for item in data.get("notes", [])],
        )


@dataclass(slots=True)
class SessionContext:
    """Resolved context for the current interactive session."""

    root_path: str
    skill_path: str
    input_file_path: str
    input_text: str
    detected_step: StepDetectionResult
    chosen_style: str | None = None
    resume_source: RunState | None = None
    episode_count: int | None = None


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
