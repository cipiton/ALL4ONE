from __future__ import annotations

from pathlib import Path

from engine.executor import execute_input_paths, load_resume_document
from engine.models import DocumentResult, RunState, SkillDefinition, SkillRegistryEntry
from engine.skill_loader import load_skill
from engine.state_store import find_latest_resumable_state

from ..protocol import (
    SkillAdapter,
    SkillDocumentResult,
    SkillMenuSummary,
    SkillResumePoint,
    SkillResumeRequest,
    SkillRunRequest,
    SkillRunResult,
    SkillStartupPolicySummary,
    SkillStepSummary,
)


class SkillMdAdapter(SkillAdapter):
    """Adapter that bridges app-level requests to SKILL.md-based engine execution."""

    def __init__(self, repo_root: Path, entry: SkillRegistryEntry) -> None:
        self._repo_root = repo_root
        self._entry = entry
        self._skill: SkillDefinition | None = None

    @property
    def skill_id(self) -> str:
        return self._entry.id

    @property
    def display_name(self) -> str:
        return self._entry.display_name or self._skill_definition.display_name

    @property
    def description(self) -> str:
        return self._entry.description or self._skill_definition.description

    @property
    def spec_path(self) -> Path:
        return self._entry.spec_path

    @property
    def supports_resume(self) -> bool:
        return self._skill_definition.supports_resume

    @property
    def input_extensions(self) -> list[str]:
        return list(self._skill_definition.input_extensions)

    @property
    def folder_mode(self) -> str:
        return self._skill_definition.folder_mode

    @property
    def startup_policy(self) -> SkillStartupPolicySummary:
        policy = self._skill_definition.startup_policy
        return SkillStartupPolicySummary(
            mode=policy.mode,
            default_step_number=policy.default_step_number or self._skill_definition.default_step_number,
            allow_resume=bool(policy.allow_resume and self.supports_resume),
            allow_auto_route=policy.allow_auto_route,
        )

    @property
    def step_summaries(self) -> list[SkillStepSummary]:
        return [
            SkillStepSummary(number=step.number, title=step.title, description=step.description)
            for step in self._skill_definition.ordered_steps()
        ]

    @property
    def _skill_definition(self) -> SkillDefinition:
        if self._skill is None:
            self._skill = load_skill(self._entry.spec_path.parent)
        return self._skill

    def to_summary(self) -> SkillMenuSummary:
        return SkillMenuSummary(
            skill_id=self.skill_id,
            display_name=self.display_name,
            description=self.description,
        )

    def run(self, request: SkillRunRequest) -> SkillRunResult:
        forced_step_number = request.selected_step_number
        if forced_step_number is None and not self.startup_policy.allow_auto_route:
            forced_step_number = self.startup_policy.default_step_number

        session_dir, results = execute_input_paths(
            request.repo_root,
            self._skill_definition,
            request.input_paths,
            forced_step_number=forced_step_number,
            input_root_path=request.input_root_path,
        )
        return SkillRunResult(
            session_dir=session_dir,
            document_results=[_map_document_result(result) for result in results],
            resumed=False,
        )

    def find_resume_point(self, outputs_root: Path) -> SkillResumePoint | None:
        if not self.supports_resume:
            return None

        state = find_latest_resumable_state(outputs_root, self._skill_definition)
        if state is None:
            return None

        next_step = state.detected_step
        if state.status == "completed_step":
            resolved_next = self._skill_definition.next_step_number_for(state.detected_step)
            if resolved_next is not None:
                next_step = resolved_next

        return SkillResumePoint(
            output_directory=Path(state.output_directory),
            resume_input_path=Path(state.primary_output_path or state.working_input_path or state.input_path),
            status=state.status,
            detected_step=state.detected_step,
            next_step_number=next_step,
            state_token=state,
        )

    def resume(self, request: SkillResumeRequest) -> SkillRunResult:
        if not self.supports_resume:
            raise RuntimeError(f"Skill '{self.skill_id}' does not support resume.")

        state = request.resume_point.state_token
        if not isinstance(state, RunState):
            raise RuntimeError(f"Resume state is not available for skill '{self.skill_id}'.")

        resume_document, forced_step_number = load_resume_document(self._skill_definition, state)
        session_dir, results = execute_input_paths(
            request.repo_root,
            self._skill_definition,
            [resume_document.path],
            resume_state=state,
            forced_step_number=forced_step_number,
        )
        return SkillRunResult(
            session_dir=session_dir,
            document_results=[_map_document_result(result) for result in results],
            resumed=True,
        )


def _map_document_result(result: DocumentResult) -> SkillDocumentResult:
    return SkillDocumentResult(
        document_path=result.document_path,
        output_directory=result.output_directory,
        status=result.status,
        primary_output=result.primary_output,
        error_message=result.error_message,
    )
