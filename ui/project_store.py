from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from .project_models import ProjectSource, ProjectState
from .workspace_manager import WorkspaceManager


class ProjectStore:
    def __init__(self, workspace_manager: WorkspaceManager) -> None:
        self.workspace_manager = workspace_manager

    def list_projects(self) -> list[ProjectState]:
        projects: list[ProjectState] = []
        for info in self.workspace_manager.list_projects():
            state = self.load(info.root)
            if state is not None:
                projects.append(state)
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def create_project(
        self,
        *,
        name: str,
        description: str = "",
        source_path: str = "",
        selected_skill_id: str = "",
        selected_skill_name: str = "",
    ) -> ProjectState:
        info = self.workspace_manager.create_project(name)
        intermediate_dir = info.root / "intermediate"
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState(
            id=uuid.uuid4().hex,
            name=info.name,
            description=description.strip(),
            workspace_path=str(info.root),
            inputs_path=str(info.inputs_dir),
            outputs_path=str(info.outputs_dir),
            intermediate_path=str(intermediate_dir),
            selected_skill_id=selected_skill_id,
            selected_skill_name=selected_skill_name,
        )
        if source_path.strip():
            self.attach_source(state, source_path)
        self.save(state)
        return state

    def load(self, project_root: str | Path) -> ProjectState | None:
        metadata_path = Path(project_root) / "project.json"
        if not metadata_path.exists():
            return self._build_legacy_state(Path(project_root))
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._build_legacy_state(Path(project_root))
        if not isinstance(payload, dict):
            return self._build_legacy_state(Path(project_root))
        state = ProjectState.from_dict(payload)
        self._ensure_structure(state)
        return state

    def save(self, project: ProjectState) -> None:
        self._ensure_structure(project)
        project.touch()
        metadata_path = project.project_root() / "project.json"
        metadata_path.write_text(
            json.dumps(project.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete(self, project: ProjectState) -> None:
        shutil.rmtree(project.project_root(), ignore_errors=True)

    def attach_source(self, project: ProjectState, raw_source_path: str | Path) -> ProjectSource:
        source_path = Path(raw_source_path).expanduser().resolve()
        if not source_path.exists():
            raise ValueError(f"Source path does not exist: {source_path}")
        inputs_dir = project.inputs_dir()
        inputs_dir.mkdir(parents=True, exist_ok=True)

        destination = inputs_dir / source_path.name
        destination = self._dedupe_destination(destination)
        if source_path.is_dir():
            shutil.copytree(source_path, destination)
            kind = "folder"
        else:
            shutil.copy2(source_path, destination)
            kind = "file"

        source = ProjectSource(
            kind=kind,
            path=str(destination),
            name=destination.name,
            original_path=str(source_path),
        )
        project.source_inputs.append(source)
        project.touch()
        self.save(project)
        return source

    def refresh_sources(self, project: ProjectState) -> None:
        refreshed: list[ProjectSource] = []
        for source in project.source_inputs:
            path = Path(source.path)
            if path.exists():
                source.name = path.name
                refreshed.append(source)
        project.source_inputs = refreshed
        self.save(project)

    def _ensure_structure(self, project: ProjectState) -> None:
        project.project_root().mkdir(parents=True, exist_ok=True)
        project.inputs_dir().mkdir(parents=True, exist_ok=True)
        project.outputs_dir().mkdir(parents=True, exist_ok=True)
        project.intermediate_dir().mkdir(parents=True, exist_ok=True)

    def _build_legacy_state(self, project_root: Path) -> ProjectState | None:
        info = self.workspace_manager.get_project(project_root.name)
        if not info.root.exists():
            return None
        intermediate_dir = info.root / "intermediate"
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        state = ProjectState(
            id=uuid.uuid4().hex,
            name=info.name,
            description="",
            workspace_path=str(info.root),
            inputs_path=str(info.inputs_dir),
            outputs_path=str(info.outputs_dir),
            intermediate_path=str(intermediate_dir),
        )
        for child in sorted(info.inputs_dir.iterdir(), key=lambda path: path.name.casefold()) if info.inputs_dir.exists() else []:
            state.source_inputs.append(
                ProjectSource(
                    kind="folder" if child.is_dir() else "file",
                    path=str(child.resolve()),
                    name=child.name,
                )
            )
        self.save(state)
        return state

    def _dedupe_destination(self, destination: Path) -> Path:
        if not destination.exists():
            return destination
        stem = destination.stem
        suffix = destination.suffix
        parent = destination.parent
        index = 2
        while True:
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1
