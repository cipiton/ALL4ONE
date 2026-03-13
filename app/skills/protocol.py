from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class SkillMenuSummary:
    skill_id: str
    display_name: str
    description: str


@dataclass(slots=True)
class SkillRunRequest:
    repo_root: Path
    input_paths: list[Path]


@dataclass(slots=True)
class SkillResumePoint:
    output_directory: Path
    resume_input_path: Path
    status: str
    detected_step: int
    next_step_number: int | None = None
    state_token: object | None = None


@dataclass(slots=True)
class SkillResumeRequest:
    repo_root: Path
    resume_point: SkillResumePoint


@dataclass(slots=True)
class SkillDocumentResult:
    document_path: Path
    output_directory: Path
    status: str
    primary_output: Path | None = None
    error_message: str | None = None


@dataclass(slots=True)
class SkillRunResult:
    session_dir: Path
    document_results: list[SkillDocumentResult] = field(default_factory=list)
    resumed: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.document_results if result.status in {"completed", "completed_step"})

    @property
    def failure_count(self) -> int:
        return len(self.document_results) - self.success_count


class SkillAdapter(Protocol):
    @property
    def skill_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def spec_path(self) -> Path: ...

    @property
    def supports_resume(self) -> bool: ...

    @property
    def input_extensions(self) -> list[str]: ...

    def to_summary(self) -> SkillMenuSummary: ...

    def run(self, request: SkillRunRequest) -> SkillRunResult: ...

    def find_resume_point(self, outputs_root: Path) -> SkillResumePoint | None: ...

    def resume(self, request: SkillResumeRequest) -> SkillRunResult: ...
