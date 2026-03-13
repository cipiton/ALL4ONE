from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ReferenceResource:
    """A reference file mentioned by the skill."""

    name: str
    relative_path: str
    absolute_path: Path
    exists: bool
    purpose: str = ""
    when_to_read: str = ""


@dataclass(slots=True)
class SkillConfig:
    """Normalized skill metadata extracted from SKILL.md."""

    name: str
    description: str
    skill_dir: Path
    skill_md_path: Path
    frontmatter: dict[str, Any] = field(default_factory=dict)
    workflow_steps: list[str] = field(default_factory=list)
    output_expectations: list[str] = field(default_factory=list)
    referenced_files: list[ReferenceResource] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["skill_dir"] = str(self.skill_dir)
        data["skill_md_path"] = str(self.skill_md_path)
        for item in data["referenced_files"]:
            item["absolute_path"] = str(item["absolute_path"])
        return data


@dataclass(slots=True)
class DocumentChunk:
    """Deterministic text chunk metadata."""

    chunk_id: str
    index: int
    start_char: int
    end_char: int
    text: str
    character_count: int
    estimated_tokens: int


@dataclass(slots=True)
class InputDocument:
    """Normalized input document."""

    path: Path
    text: str
    character_count: int
    line_count: int
    estimated_tokens: int
    chunks: list[DocumentChunk] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(slots=True)
class LLMTask:
    """One staged reasoning task."""

    name: str
    description: str
    references: list[ReferenceResource] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionPlan:
    """Inspectable runtime plan derived from the skill and input."""

    direct_read: bool
    needs_chunking: bool
    chunk_size: int
    chunk_overlap: int
    input_facts: dict[str, Any]
    references_to_load: list[ReferenceResource]
    llm_tasks: list[LLMTask]
    postprocess_tasks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "direct_read": self.direct_read,
            "needs_chunking": self.needs_chunking,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "input_facts": self.input_facts,
            "references_to_load": [
                {
                    "name": item.name,
                    "relative_path": item.relative_path,
                    "absolute_path": str(item.absolute_path),
                    "exists": item.exists,
                    "purpose": item.purpose,
                    "when_to_read": item.when_to_read,
                }
                for item in self.references_to_load
            ],
            "llm_tasks": [
                {
                    "name": task.name,
                    "description": task.description,
                    "references": [item.relative_path for item in task.references],
                    "depends_on": task.depends_on,
                }
                for task in self.llm_tasks
            ],
            "postprocess_tasks": list(self.postprocess_tasks),
        }


@dataclass(slots=True)
class AnalysisResult:
    """Aggregated staged analysis and final report."""

    stage_outputs: dict[str, Any] = field(default_factory=dict)
    final_sections: dict[str, str] = field(default_factory=dict)
    final_report_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
