from __future__ import annotations  
  
from dataclasses import dataclass, field  
from pathlib import Path  
from typing import Optional, Protocol  
  
  
@dataclass(slots=True)  
class SkillMenuSummary:  
    skill_id: str  
    display_name: str  
    description: str  
  
  
@dataclass(slots=True)  
class SkillStepSummary:  
    number: int  
    title: str  
    description: str = ""  
  
  
@dataclass(slots=True)  
class SkillStartupPolicySummary:  
    mode: str = "auto_route"  
    default_step_number: Optional[int] = None  
    allow_resume: bool = True  
    allow_auto_route: bool = True  
  
  
@dataclass(slots=True)  
class SkillRunRequest:  
    repo_root: Path  
    input_paths: list[Path]  
    input_root_path: Optional[Path] = None
    selected_step_number: Optional[int] = None  
  
  
@dataclass(slots=True)  
class SkillResumePoint:  
    output_directory: Path  
    resume_input_path: Path  
    status: str  
    detected_step: int  
    next_step_number: Optional[int] = None  
    state_token: Optional[object] = None  
  
  
@dataclass(slots=True)  
class SkillResumeRequest:  
    repo_root: Path  
    resume_point: SkillResumePoint  
  
  
@dataclass(slots=True)  
class SkillDocumentResult:  
    document_path: Path  
    output_directory: Path  
    status: str  
    primary_output: Optional[Path] = None  
    error_message: Optional[str] = None  
  
  
@dataclass(slots=True)  
class SkillRunResult:  
    session_dir: Path  
    document_results: list[SkillDocumentResult] = field(default_factory=list)  
    resumed: bool = False  
  
    @property  
    def success_count(self):  
        return sum(1 for result in self.document_results if result.status in {"completed", "completed_step"})  
  
    @property  
    def failure_count(self):  
        return len(self.document_results) - self.success_count  
  
  
class SkillAdapter(Protocol):  
    @property  
    def skill_id(self): ...  
  
    @property  
    def display_name(self): ...  
  
    @property  
    def description(self): ...  
  
    @property  
    def spec_path(self): ...  
  
    @property  
    def supports_resume(self): ...  
  
    @property  
    def input_extensions(self): ...  
  
    @property  
    def folder_mode(self): ...  
  
    @property  
    def startup_policy(self): ...  
  
    @property  
    def step_summaries(self): ...  
  
    def to_summary(self): ...  
  
    def run(self, request): ...  
  
    def find_resume_point(self, outputs_root): ...  
  
    def resume(self, request): ... 
