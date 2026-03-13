from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


RunStatus = Literal[
    "pending",
    "awaiting_input",
    "running",
    "completed_step",
    "completed",
    "error",
]


@dataclass(slots=True)
class SkillSummary:
    name: str
    display_name: str
    description: str
    skill_dir: Path


@dataclass(slots=True)
class SkillRegistryEntry:
    id: str
    entry_type: str
    spec_path: Path
    adapter: str = "skill_md"
    enabled: bool = True
    display_name: str = ""
    description: str = ""


@dataclass(slots=True)
class ReferenceDefinition:
    reference_id: str
    relative_path: str
    absolute_path: Path
    kind: str = "reference"
    description: str = ""
    step_numbers: list[int] = field(default_factory=list)
    stage_names: list[str] = field(default_factory=list)
    load: str = "auto"


@dataclass(slots=True)
class RuntimeInputDefinition:
    name: str
    prompt: str
    field_type: str
    required: bool = True
    step_numbers: list[int] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    default: Any = None
    min_value: int | None = None
    max_value: int | None = None
    help_text: str = ""
    skip_if_input_contains_any: list[str] = field(default_factory=list)
    require_if_input_contains_any: list[str] = field(default_factory=list)

    def applies_to(self, step_number: int, input_text: str) -> bool:
        if self.step_numbers and step_number not in self.step_numbers:
            return False

        lowered = input_text.lower()
        if self.require_if_input_contains_any:
            if not any(token.lower() in lowered for token in self.require_if_input_contains_any):
                return False
        if self.skip_if_input_contains_any:
            if any(token.lower() in lowered for token in self.skip_if_input_contains_any):
                return False
        return True


@dataclass(slots=True)
class SkillStep:
    number: int
    title: str
    prompt_reference_id: str | None = None
    description: str = ""
    route_keywords_any: list[str] = field(default_factory=list)
    route_keywords_all: list[str] = field(default_factory=list)
    route_priority: int = 0
    requires_list_like: bool = False
    requires_script_like: bool = False
    default: bool = False


@dataclass(slots=True)
class StructuredStage:
    name: str
    kind: str
    objective: str
    schema: dict[str, Any] = field(default_factory=dict)
    input_keys: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    chunkable: bool = False
    merge_objective: str = ""
    merge_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChunkingConfig:
    enabled: bool = True
    threshold_chars: int = 18_000
    chunk_size: int = 12_000
    overlap: int = 1_200


@dataclass(slots=True)
class OutputConfig:
    mode: str = "text"
    filename_template: str = "output.txt"
    sections: list[str] = field(default_factory=list)
    include_prompt_dump: bool = True


@dataclass(slots=True)
class SkillDefinition:
    name: str
    display_name: str
    description: str
    skill_dir: Path
    skill_md_path: Path
    body: str
    supports_resume: bool
    execution_strategy: str
    steps: dict[int, SkillStep]
    runtime_inputs: list[RuntimeInputDefinition]
    references: dict[str, ReferenceDefinition]
    stages: list[StructuredStage]
    chunking: ChunkingConfig
    output_config: OutputConfig
    input_extensions: list[str]
    folder_mode: str = "non_recursive"

    def ordered_steps(self) -> list[SkillStep]:
        return [self.steps[number] for number in sorted(self.steps)]

    def get_step(self, step_number: int) -> SkillStep:
        try:
            return self.steps[step_number]
        except KeyError as exc:
            raise ValueError(f"Step {step_number} is not defined for skill '{self.name}'.") from exc

    def get_reference(self, reference_id: str) -> ReferenceDefinition:
        try:
            return self.references[reference_id]
        except KeyError as exc:
            raise ValueError(
                f"Reference '{reference_id}' is not defined for skill '{self.name}'."
            ) from exc

    @property
    def default_step_number(self) -> int:
        for step in self.ordered_steps():
            if step.default:
                return step.number
        return self.ordered_steps()[0].number

    @property
    def final_step_number(self) -> int:
        return self.ordered_steps()[-1].number


@dataclass(slots=True)
class InputDocument:
    path: Path
    text: str
    character_count: int
    line_count: int
    estimated_tokens: int
    index: int = 1
    total: int = 1


@dataclass(slots=True)
class DetectedStep:
    step_number: int
    reason: str
    scores: dict[int, int] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionPlan:
    strategy: str
    step: SkillStep
    detected_step: DetectedStep
    runtime_inputs: list[RuntimeInputDefinition]
    reference_ids: list[str]
    stage_names: list[str]


@dataclass(slots=True)
class PromptMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    timeout: float
    max_retries: int
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    raw_response: dict[str, Any]


@dataclass(slots=True)
class RunState:
    timestamp: str
    skill_name: str
    input_path: str
    working_input_path: str
    detected_step: int
    step_title: str
    step_reason: str
    runtime_inputs: dict[str, Any]
    status: RunStatus
    output_directory: str
    output_files: dict[str, str] = field(default_factory=dict)
    strategy: str = ""
    notes: list[str] = field(default_factory=list)
    error_message: str | None = None
    resume_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        return cls(
            timestamp=str(data["timestamp"]),
            skill_name=str(data["skill_name"]),
            input_path=str(data["input_path"]),
            working_input_path=str(data.get("working_input_path", data["input_path"])),
            detected_step=int(data["detected_step"]),
            step_title=str(data.get("step_title", "")),
            step_reason=str(data.get("step_reason", "")),
            runtime_inputs=dict(data.get("runtime_inputs", {})),
            status=str(data["status"]),
            output_directory=str(data["output_directory"]),
            output_files={
                str(key): str(value) for key, value in dict(data.get("output_files", {})).items()
            },
            strategy=str(data.get("strategy", "")),
            notes=[str(item) for item in data.get("notes", [])],
            error_message=data.get("error_message"),
            resume_from=data.get("resume_from"),
        )

    @property
    def primary_output_path(self) -> str | None:
        return self.output_files.get("primary")


@dataclass(slots=True)
class DocumentResult:
    document_path: Path
    output_directory: Path
    status: RunStatus
    primary_output: Path | None = None
    error_message: str | None = None
