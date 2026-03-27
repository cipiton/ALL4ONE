from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ProjectInfo:
    name: str
    root: Path
    inputs_dir: Path
    outputs_dir: Path


def default_workspace_root() -> Path:
    documents_dir = Path.home() / "Documents"
    if documents_dir.exists():
        return (documents_dir / "ONE4ALL_Workspace").resolve()
    return (Path.home() / "ONE4ALL_Workspace").resolve()


class WorkspaceManager:
    def __init__(self, workspace_root: str | Path) -> None:
        self.set_workspace_root(workspace_root)

    def set_workspace_root(self, workspace_root: str | Path) -> None:
        candidate = Path(workspace_root).expanduser()
        if not candidate.is_absolute():
            candidate = candidate.resolve()
        self.workspace_root = candidate

    def ensure_workspace_root(self) -> Path:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        return self.workspace_root

    def list_projects(self) -> list[ProjectInfo]:
        root = self.ensure_workspace_root()
        projects: list[ProjectInfo] = []
        for candidate in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name.casefold()):
            inputs_dir = candidate / "inputs"
            outputs_dir = candidate / "outputs"
            if inputs_dir.exists() or outputs_dir.exists():
                projects.append(ProjectInfo(candidate.name, candidate, inputs_dir, outputs_dir))
        return projects

    def get_project(self, name: str) -> ProjectInfo:
        clean_name = _normalize_project_name(name)
        root = self.ensure_workspace_root() / clean_name
        return ProjectInfo(clean_name, root, root / "inputs", root / "outputs")

    def create_project(self, name: str) -> ProjectInfo:
        project = self.get_project(name)
        project.inputs_dir.mkdir(parents=True, exist_ok=True)
        project.outputs_dir.mkdir(parents=True, exist_ok=True)
        return project


def _normalize_project_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not cleaned:
        raise ValueError("Project name cannot be empty.")
    safe = re.sub(r'[<>:"/\\|?*]+', "_", cleaned).strip(" .")
    if not safe:
        raise ValueError("Project name contains no usable characters.")
    return safe
