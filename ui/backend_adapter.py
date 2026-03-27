from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.skills.catalog import SkillCatalog
from app.skills.protocol import SkillRunRequest, SkillStepSummary
from engine.input_loader import resolve_input_paths
from engine.input_requests import resolve_skill_input_request
from engine.llm_client import load_env_file
from engine.models import RuntimeInputDefinition
from engine.rewriting_project import list_available_rewriting_bibles


@dataclass(slots=True)
class GuiRuntimeInputField:
    name: str
    prompt: str
    field_type: str
    required: bool
    choices: list[str] = field(default_factory=list)
    default: Any = None
    min_value: int | None = None
    max_value: int | None = None
    help_text: str = ""
    step_numbers: list[int] = field(default_factory=list)


@dataclass(slots=True)
class GuiSkillOption:
    skill_id: str
    display_name: str
    description: str
    input_extensions: list[str]
    folder_mode: str
    startup_mode: str
    default_step_number: int | None
    allow_auto_route: bool
    step_summaries: list[SkillStepSummary]
    runtime_inputs: list[GuiRuntimeInputField]
    supports_file_input: bool = True
    supports_folder_input: bool = True
    supports_text_input: bool = False
    text_input_prompt: str = ""
    allow_inline_text_input: bool = False


@dataclass(slots=True)
class GuiRunRequest:
    skill_id: str
    input_path: str
    outputs_root: str
    direct_text: str = ""
    selected_step_number: int | None = None
    runtime_values: dict[str, Any] = field(default_factory=dict)
    auto_accept_review_steps: bool = True
    rewriting_mode: str = ""
    rewriting_plan_path: str = ""
    rewriting_bible_path: str = ""
    rewriting_supplemental_path: str = ""


@dataclass(slots=True)
class GuiRunResult:
    session_dir: Path
    success_count: int
    failure_count: int
    primary_output: Path | None = None
    output_cards: list["GuiOutputCard"] = field(default_factory=list)


@dataclass(slots=True)
class GuiOutputCard:
    title: str
    path: Path
    output_dir: Path
    preview_text: str = ""


class GuiBackend:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def load_skills(self) -> list[GuiSkillOption]:
        load_env_file(self.repo_root / ".env")
        catalog = SkillCatalog.load(self.repo_root)
        options: list[GuiSkillOption] = []
        for skill in catalog.list_skills():
            runtime_inputs = [
                _map_runtime_input(definition)
                for definition in getattr(skill, "runtime_input_definitions", [])
            ]
            options.append(
                GuiSkillOption(
                    skill_id=skill.skill_id,
                    display_name=skill.display_name,
                    description=skill.description,
                    input_extensions=list(skill.input_extensions),
                    folder_mode=skill.folder_mode,
                    startup_mode=skill.startup_policy.mode,
                    default_step_number=skill.startup_policy.default_step_number,
                    allow_auto_route=skill.startup_policy.allow_auto_route,
                    step_summaries=list(skill.step_summaries),
                    runtime_inputs=runtime_inputs,
                    supports_file_input=True,
                    supports_folder_input=True,
                    supports_text_input=bool(getattr(skill, "allow_inline_text_input", False)),
                    text_input_prompt=str(getattr(skill, "inline_input_prompt", "") or ""),
                    allow_inline_text_input=bool(getattr(skill, "allow_inline_text_input", False)),
                )
            )
        return options

    def list_rewriting_bibles(self, outputs_root: str | Path) -> list[tuple[str, str]]:
        return list_available_rewriting_bibles(Path(outputs_root).expanduser().resolve())

    def run(self, request: GuiRunRequest) -> GuiRunResult:
        load_env_file(self.repo_root / ".env")
        catalog = SkillCatalog.load(self.repo_root)
        skill = catalog.get_skill(request.skill_id)
        input_root_path, input_paths = resolve_skill_input_request(
            self.repo_root,
            skill,
            raw_path=request.input_path,
            direct_text=request.direct_text,
        )
        outputs_root = Path(request.outputs_root).expanduser().resolve()
        outputs_root.mkdir(parents=True, exist_ok=True)

        launch_options: dict[str, Any] = {}
        if request.rewriting_mode:
            launch_options["rewriting_project_mode"] = request.rewriting_mode
        if request.rewriting_plan_path:
            launch_options["plan_path"] = str(Path(request.rewriting_plan_path).expanduser().resolve())
        if request.rewriting_bible_path:
            launch_options["selected_bible_path"] = str(Path(request.rewriting_bible_path).expanduser().resolve())
        if request.rewriting_supplemental_path:
            launch_options["supplemental_script_paths"] = [
                str(path)
                for path in resolve_input_paths(
                    request.rewriting_supplemental_path,
                    [".txt"],
                    folder_mode="non_recursive",
                )
            ]

        coerced_runtime_values = _coerce_runtime_values(
            request.runtime_values,
            getattr(skill, "runtime_input_definitions", []),
        )

        result = skill.run(
            SkillRunRequest(
                repo_root=self.repo_root,
                input_paths=input_paths,
                input_root_path=input_root_path,
                selected_step_number=request.selected_step_number,
                outputs_root=outputs_root,
                runtime_values=coerced_runtime_values,
                auto_accept_review_steps=request.auto_accept_review_steps,
                launch_options=launch_options,
            )
        )
        primary_output = next(
            (item.primary_output for item in result.document_results if item.primary_output is not None),
            None,
        )
        output_cards = _build_output_cards(result.document_results)
        return GuiRunResult(
            session_dir=result.session_dir,
            success_count=result.success_count,
            failure_count=result.failure_count,
            primary_output=primary_output,
            output_cards=output_cards,
        )


def _map_runtime_input(definition: RuntimeInputDefinition) -> GuiRuntimeInputField:
    return GuiRuntimeInputField(
        name=definition.name,
        prompt=definition.prompt,
        field_type=definition.field_type,
        required=definition.required,
        choices=list(definition.choices),
        default=definition.default,
        min_value=definition.min_value,
        max_value=definition.max_value,
        help_text=definition.help_text,
        step_numbers=list(definition.step_numbers),
    )


def _coerce_runtime_values(
    raw_values: dict[str, Any],
    definitions: list[RuntimeInputDefinition],
) -> dict[str, Any]:
    definition_map = {definition.name: definition for definition in definitions}
    coerced: dict[str, Any] = {}
    for name, raw_value in raw_values.items():
        if raw_value in (None, ""):
            continue
        definition = definition_map.get(name)
        if definition is None:
            coerced[name] = raw_value
            continue
        coerced[name] = _coerce_runtime_value(raw_value, definition)
    return coerced


def _coerce_runtime_value(raw_value: Any, definition: RuntimeInputDefinition) -> Any:
    if definition.field_type == "int":
        return int(str(raw_value).strip())
    if definition.field_type == "bool":
        lowered = str(raw_value).strip().lower()
        return lowered in {"1", "true", "yes", "y", "on"}
    return str(raw_value).strip()


def _build_output_cards(document_results) -> list[GuiOutputCard]:
    cards: list[GuiOutputCard] = []
    for result in document_results:
        if result.primary_output is None:
            continue
        cards.append(
            GuiOutputCard(
                title=result.primary_output.name,
                path=result.primary_output,
                output_dir=result.output_directory,
                preview_text=_load_preview_text(result.primary_output),
            )
        )
    return cards


def _load_preview_text(path: Path, *, limit: int = 500) -> str:
    if path.suffix.lower() not in {".txt", ".md", ".json", ".csv", ".yaml", ".yml"}:
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            return ""
    except OSError:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."
