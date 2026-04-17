from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_ID_RE = re.compile(r"^\d{8}_\d{6}(?:_\d{2})?$")
LEGACY_SESSION_RE = re.compile(r"^(?P<title>.+?)__(?P<run_id>\d{8}_\d{6}(?:_\d{2})?)$")


@dataclass(frozen=True, slots=True)
class StoryStageDefinition:
    skill_name: str
    stage_folder: str


@dataclass(frozen=True, slots=True)
class StoryRunContext:
    story_title: str
    story_slug: str
    run_id: str
    run_root: Path
    stage_folder: str | None = None
    stage_dir: Path | None = None
    source_input_path: Path | None = None


STORY_STAGES: tuple[StoryStageDefinition, ...] = (
    StoryStageDefinition(skill_name="recap_analysis", stage_folder="01_recap_analysis"),
    StoryStageDefinition(skill_name="recap_production", stage_folder="02_recap_production"),
    StoryStageDefinition(skill_name="recap_to_tts", stage_folder="03_recap_to_tts"),
    StoryStageDefinition(skill_name="recap_to_comfy_bridge", stage_folder="04_recap_to_comfy_bridge"),
    StoryStageDefinition(skill_name="recap_to_assets_zimage", stage_folder="05_assets_t2i"),
    StoryStageDefinition(skill_name="recap_to_keyscene_kontext", stage_folder="06_keyscene_i2i"),
    StoryStageDefinition(skill_name="clips_flf2v", stage_folder="07_clips_flf2v"),
    StoryStageDefinition(skill_name="final", stage_folder="08_final"),
)
STORY_STAGE_BY_SKILL = {definition.skill_name: definition for definition in STORY_STAGES}
LEGACY_STORY_STAGE_FOLDERS_BY_SKILL: dict[str, tuple[str, ...]] = {
    "recap_production": ("01_recap_production",),
    "recap_to_tts": ("02_recap_to_tts",),
    "recap_to_comfy_bridge": ("03_recap_to_comfy_bridge",),
    "recap_to_assets_zimage": ("04_assets_t2i",),
    "recap_to_keyscene_kontext": ("05_keyscene_i2i",),
    "clips_flf2v": ("06_clips_flf2v",),
    "final": ("07_final",),
}
STORY_STAGE_BY_FOLDER = {
    definition.stage_folder: definition
    for definition in STORY_STAGES
}
for skill_name, legacy_folders in LEGACY_STORY_STAGE_FOLDERS_BY_SKILL.items():
    definition = STORY_STAGE_BY_SKILL[skill_name]
    for legacy_folder in legacy_folders:
        STORY_STAGE_BY_FOLDER[legacy_folder] = definition
STORY_STAGE_FOLDERS = set(STORY_STAGE_BY_FOLDER)
STORY_MANIFEST_FILENAME = "manifest.json"


def is_story_pipeline_skill(skill_name: str) -> bool:
    return str(skill_name).strip() in STORY_STAGE_BY_SKILL


def get_story_stage_folder(skill_name: str) -> str | None:
    definition = STORY_STAGE_BY_SKILL.get(str(skill_name).strip())
    return definition.stage_folder if definition is not None else None


def story_slug_from_title(title: str) -> str:
    slug = _sanitize_path_component(title).replace("_", "-").strip("-")
    return slug or "story"


def infer_story_title(input_root_path: Path | None, input_paths: list[Path]) -> str:
    for candidate in _build_candidate_paths(input_root_path, input_paths):
        story_context = detect_story_run_context(candidate)
        if story_context is not None and story_context.story_title:
            return story_context.story_title

        legacy = detect_legacy_story_run(candidate)
        if legacy is not None and legacy.story_title:
            return legacy.story_title

    if input_root_path is not None:
        metadata_root = _locate_project_metadata_root(input_root_path)
        if metadata_root is not None:
            for resolver in (
                _read_title_from_index,
                _read_title_from_ingestion_report,
                _read_title_from_project_state,
            ):
                title = resolver(metadata_root)
                if title:
                    return title

    title_from_chunks = _infer_title_from_chunk_paths(input_paths)
    if title_from_chunks:
        return title_from_chunks

    if input_root_path is not None:
        cleaned = _normalize_title_candidate(
            input_root_path.name if input_root_path.is_dir() else input_root_path.stem
        )
        if cleaned:
            return cleaned

    for path in input_paths:
        cleaned = _normalize_title_candidate(path.stem)
        if cleaned:
            return cleaned
    return "story"


def resolve_story_stage_output(
    outputs_root: Path,
    skill_name: str,
    *,
    input_root_path: Path | None,
    input_paths: list[Path],
) -> StoryRunContext:
    if not is_story_pipeline_skill(skill_name):
        raise ValueError(f"Skill is not configured for story-first outputs: {skill_name}")

    stage_folder = get_story_stage_folder(skill_name)
    if stage_folder is None:
        raise ValueError(f"Missing stage folder mapping for skill: {skill_name}")

    existing_context = _find_existing_story_run_context(input_root_path, input_paths)
    if existing_context is not None:
        story_title = existing_context.story_title or infer_story_title(input_root_path, input_paths)
        story_slug = existing_context.story_slug or story_slug_from_title(story_title)
        run_id = existing_context.run_id
    else:
        story_title = infer_story_title(input_root_path, input_paths)
        story_slug = story_slug_from_title(story_title)
        legacy_context = _find_existing_legacy_story_run(input_root_path, input_paths)
        if legacy_context is not None:
            run_id = legacy_context.run_id
            if not story_title:
                story_title = legacy_context.story_title
            if not story_slug:
                story_slug = legacy_context.story_slug
        else:
            run_id = _next_story_run_id(outputs_root / "stories" / story_slug)

    run_root = (outputs_root / "stories" / story_slug / run_id).resolve()
    stage_dir = (run_root / stage_folder).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    stage_dir.mkdir(parents=True, exist_ok=True)

    context = StoryRunContext(
        story_title=story_title,
        story_slug=story_slug,
        run_id=run_id,
        run_root=run_root,
        stage_folder=stage_folder,
        stage_dir=stage_dir,
        source_input_path=_select_manifest_source_input(run_root, input_root_path, input_paths),
    )
    ensure_story_run_manifest(context)
    return context


def detect_story_run_context(path: Path) -> StoryRunContext | None:
    resolved = path.expanduser().resolve()
    current = resolved if resolved.is_dir() else resolved.parent

    for candidate in (current, *current.parents):
        if candidate.name in STORY_STAGE_FOLDERS:
            run_root = candidate.parent
            stage_folder = candidate.name
        elif RUN_ID_RE.fullmatch(candidate.name or ""):
            run_root = candidate
            stage_folder = None
        else:
            continue

        story_root = run_root.parent
        if story_root.parent.name != "stories":
            continue

        manifest = load_story_run_manifest(run_root)
        story_title = ""
        source_input_path: Path | None = None
        if manifest:
            story_title = str(manifest.get("story_title") or "").strip()
            raw_source = str(manifest.get("source_input_path") or "").strip()
            if raw_source:
                source_input_path = Path(raw_source)

        if not story_title:
            story_title = _humanize_story_slug(story_root.name)

        return StoryRunContext(
            story_title=story_title or story_root.name,
            story_slug=story_root.name,
            run_id=run_root.name,
            run_root=run_root,
            stage_folder=stage_folder,
            stage_dir=run_root / stage_folder if stage_folder else None,
            source_input_path=source_input_path,
        )
    return None


def detect_legacy_story_run(path: Path) -> StoryRunContext | None:
    resolved = path.expanduser().resolve()
    current = resolved if resolved.is_dir() else resolved.parent
    for candidate in (current, *current.parents):
        match = LEGACY_SESSION_RE.match(candidate.name)
        if not match:
            continue
        story_title = _normalize_title_candidate(match.group("title")) or match.group("title")
        story_slug = story_slug_from_title(story_title)
        return StoryRunContext(
            story_title=story_title,
            story_slug=story_slug,
            run_id=match.group("run_id"),
            run_root=candidate,
        )
    return None


def load_story_run_manifest(run_root: Path) -> dict[str, Any] | None:
    manifest_path = run_root / STORY_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ensure_story_run_manifest(context: StoryRunContext) -> Path:
    manifest_path = context.run_root / STORY_MANIFEST_FILENAME
    payload = load_story_run_manifest(context.run_root) or _build_default_manifest(context)

    payload["story_title"] = context.story_title
    payload["story_slug"] = context.story_slug
    payload["run_id"] = context.run_id
    payload["run_root"] = str(context.run_root)
    payload["updated_at"] = _timestamp_now()
    if not payload.get("created_at"):
        payload["created_at"] = payload["updated_at"]

    existing_source = str(payload.get("source_input_path") or "").strip()
    if not existing_source and context.source_input_path is not None:
        payload["source_input_path"] = str(context.source_input_path)

    stage_folders = dict(payload.get("stage_folders") or {})
    for definition in STORY_STAGES:
        stage_folders[definition.skill_name] = definition.stage_folder
    payload["stage_folders"] = stage_folders

    stages = dict(payload.get("stages") or {})
    for definition in STORY_STAGES:
        existing_stage = dict(stages.get(definition.stage_folder) or {})
        existing_stage.setdefault("skill_name", definition.skill_name)
        existing_stage.setdefault("stage_folder", definition.stage_folder)
        existing_stage.setdefault("status", "pending")
        existing_stage.setdefault("output_directory", str(context.run_root / definition.stage_folder))
        existing_stage.setdefault("generated_files", [])
        existing_stage.setdefault("output_files", {})
        stages[definition.stage_folder] = existing_stage
    payload["stages"] = stages
    payload["completion_status"] = _summarize_manifest_status(payload)
    payload["generated_files"] = _collect_generated_files(payload)

    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def sync_story_run_manifest_from_state(state, output_dir: Path) -> Path | None:
    story_context = detect_story_run_context(output_dir)
    if story_context is None or not is_story_pipeline_skill(str(getattr(state, "skill_name", ""))):
        return None

    if story_context.stage_folder is None:
        return None

    manifest_path = ensure_story_run_manifest(
        StoryRunContext(
            story_title=story_context.story_title,
            story_slug=story_context.story_slug,
            run_id=story_context.run_id,
            run_root=story_context.run_root,
            stage_folder=story_context.stage_folder,
            stage_dir=story_context.stage_dir,
            source_input_path=_manifest_source_from_state(story_context.run_root, state),
        )
    )
    payload = load_story_run_manifest(story_context.run_root) or _build_default_manifest(story_context)
    stages = dict(payload.get("stages") or {})
    stage_payload = dict(stages.get(story_context.stage_folder) or {})
    stage_payload["skill_name"] = str(state.skill_name)
    stage_payload["stage_folder"] = story_context.stage_folder
    stage_payload["status"] = str(state.status)
    stage_payload["output_directory"] = str(output_dir)
    stage_payload["input_path"] = str(getattr(state, "input_path", ""))
    stage_payload["working_input_path"] = str(getattr(state, "working_input_path", ""))
    stage_payload["primary_output"] = _normalize_manifest_path(
        story_context.run_root,
        getattr(state, "primary_output_path", None),
    )
    stage_payload["output_files"] = {
        str(key): _normalize_manifest_path(story_context.run_root, value)
        for key, value in dict(getattr(state, "output_files", {}) or {}).items()
    }
    stage_payload["generated_files"] = _dedupe_preserve_order(
        path for path in stage_payload["output_files"].values() if path
    )
    stage_payload["notes"] = [str(item) for item in list(getattr(state, "notes", []) or [])]
    stage_payload["detected_step"] = int(getattr(state, "detected_step", 0) or 0)
    stage_payload["step_title"] = str(getattr(state, "step_title", "") or "")
    stage_payload["updated_at"] = _timestamp_now()
    if getattr(state, "error_message", None):
        stage_payload["error_message"] = str(state.error_message)

    stages[story_context.stage_folder] = stage_payload
    payload["stages"] = stages
    payload["updated_at"] = stage_payload["updated_at"]

    existing_source = str(payload.get("source_input_path") or "").strip()
    if not existing_source:
        source_from_state = _manifest_source_from_state(story_context.run_root, state)
        if source_from_state is not None:
            payload["source_input_path"] = str(source_from_state)

    payload["completion_status"] = _summarize_manifest_status(payload)
    payload["generated_files"] = _collect_generated_files(payload)
    Path(manifest_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return Path(manifest_path)


def find_story_stage_state_paths(outputs_root: Path, skill_name: str) -> list[Path]:
    stage_folder = get_story_stage_folder(skill_name)
    stories_root = outputs_root / "stories"
    if stage_folder is None or not stories_root.exists():
        return []
    return list(stories_root.glob(f"*/*/{stage_folder}/.internal/state.json"))


def resolve_run_id_from_output_dir(output_dir: Path) -> str:
    context = detect_story_run_context(output_dir)
    if context is not None:
        return context.run_id
    return output_dir.name


def resolve_story_title_from_path(path: Path) -> str | None:
    story_context = detect_story_run_context(path)
    if story_context is not None and story_context.story_title:
        return story_context.story_title
    legacy = detect_legacy_story_run(path)
    if legacy is not None and legacy.story_title:
        return legacy.story_title
    return None


def _build_default_manifest(context: StoryRunContext) -> dict[str, Any]:
    return {
        "schema": "one4all_story_run_manifest_v1",
        "story_title": context.story_title,
        "story_slug": context.story_slug,
        "run_id": context.run_id,
        "run_root": str(context.run_root),
        "source_input_path": str(context.source_input_path) if context.source_input_path else None,
        "created_at": _timestamp_now(),
        "updated_at": _timestamp_now(),
        "stage_folders": {definition.skill_name: definition.stage_folder for definition in STORY_STAGES},
        "stages": {},
        "completion_status": "pending",
        "generated_files": [],
    }


def _find_existing_story_run_context(
    input_root_path: Path | None,
    input_paths: list[Path],
) -> StoryRunContext | None:
    for candidate in _build_candidate_paths(input_root_path, input_paths):
        context = detect_story_run_context(candidate)
        if context is not None:
            return context
    return None


def _find_existing_legacy_story_run(
    input_root_path: Path | None,
    input_paths: list[Path],
) -> StoryRunContext | None:
    for candidate in _build_candidate_paths(input_root_path, input_paths):
        context = detect_legacy_story_run(candidate)
        if context is not None:
            return context
    return None


def _build_candidate_paths(input_root_path: Path | None, input_paths: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    if input_root_path is not None:
        candidates.append(input_root_path)
    for path in input_paths:
        if path not in candidates:
            candidates.append(path)
    return candidates


def _next_story_run_id(story_root: Path) -> str:
    base_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    attempt = 0
    while True:
        candidate = base_run_id if attempt == 0 else f"{base_run_id}_{attempt:02d}"
        if not (story_root / candidate).exists():
            return candidate
        attempt += 1


def _select_manifest_source_input(
    run_root: Path,
    input_root_path: Path | None,
    input_paths: list[Path],
) -> Path | None:
    for candidate in _build_candidate_paths(input_root_path, input_paths):
        if not _is_within(candidate, run_root):
            return candidate

    existing = load_story_run_manifest(run_root)
    if existing is None:
        return None
    raw_source = str(existing.get("source_input_path") or "").strip()
    return Path(raw_source) if raw_source else None


def _manifest_source_from_state(run_root: Path, state) -> Path | None:
    for raw_path in (
        getattr(state, "input_path", None),
        getattr(state, "working_input_path", None),
    ):
        if raw_path in (None, ""):
            continue
        candidate = Path(str(raw_path))
        if not _is_within(candidate, run_root):
            return candidate
    return None


def _collect_generated_files(payload: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for stage in dict(payload.get("stages") or {}).values():
        if not isinstance(stage, dict):
            continue
        for item in list(stage.get("generated_files") or []):
            text = str(item).strip()
            if text and text not in files:
                files.append(text)
    return files


def _summarize_manifest_status(payload: dict[str, Any]) -> str:
    stages = [
        stage
        for stage in dict(payload.get("stages") or {}).values()
        if isinstance(stage, dict)
    ]
    statuses = [str(stage.get("status") or "pending") for stage in stages]
    if any(status == "error" for status in statuses):
        return "error"
    if any(status in {"running", "awaiting_input"} for status in statuses):
        return "running"
    if any(status == "completed_step" for status in statuses):
        return "in_progress"
    if any(status == "completed" for status in statuses):
        return "active"
    return "pending"


def _normalize_manifest_path(run_root: Path, value: Any) -> str | None:
    raw = str(value).strip() if value not in (None, "") else ""
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser().resolve()
    except OSError:
        candidate = Path(raw)

    if _is_within(candidate, run_root):
        try:
            return str(candidate.relative_to(run_root))
        except ValueError:
            return str(candidate)
    return str(candidate)


def _dedupe_preserve_order(values) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        ordered.append(text)
        seen.add(text)
    return ordered


def _sanitize_path_component(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", str(value).strip())
    slug = slug.strip("._-")
    return slug[:80] or "story"


def _humanize_story_slug(story_slug: str) -> str:
    cleaned = str(story_slug).replace("-", " ").replace("_", " ").strip()
    return cleaned or story_slug


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _locate_project_metadata_root(input_root_path: Path) -> Path | None:
    candidates: list[Path] = []
    if input_root_path.is_dir():
        candidates.append(input_root_path)
        parent = input_root_path.parent
        if input_root_path.name.casefold() in {"chunks", "chapters"} and parent != input_root_path:
            candidates.append(parent)
    else:
        parent = input_root_path.parent
        candidates.append(parent)
        if parent.name.casefold() in {"chunks", "chapters"}:
            candidates.append(parent.parent)
        if parent.name.casefold() in {"final", "intermediate"}:
            candidates.append(parent.parent)

    for candidate in candidates:
        if not candidate.exists():
            continue
        if any((candidate / name).exists() for name in ("index.txt", "ingestion_report.txt")):
            return candidate
        if (candidate / "intermediate" / "project_state.json").exists():
            return candidate
    return None


def _read_title_from_index(root: Path) -> str | None:
    index_path = root / "index.txt"
    if not index_path.exists():
        return None
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError:
        return None
    patterns = (
        re.compile(r"^Input file:\s*(.+)$", re.MULTILINE),
        re.compile(r"^Source title:\s*(.+)$", re.MULTILINE),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        title = _normalize_title_candidate(match.group(1))
        if title:
            return title
    return None


def _read_title_from_ingestion_report(root: Path) -> str | None:
    for candidate in (root / "ingestion_report.txt", root / "intermediate" / "ingestion_report.txt"):
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^Source path:\s*(.+)$", text, flags=re.MULTILINE)
        if not match:
            continue
        title = _normalize_title_candidate(Path(match.group(1).strip()).stem)
        if title:
            return title
    return None


def _read_title_from_project_state(root: Path) -> str | None:
    for candidate in (root / "project_state.json", root / "intermediate" / "project_state.json"):
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        title = _normalize_title_candidate(str(payload.get("title", "")))
        if title:
            return title
        source_metadata = payload.get("source_metadata")
        if isinstance(source_metadata, dict):
            source_path = source_metadata.get("source_path")
            if source_path:
                title = _normalize_title_candidate(Path(str(source_path)).stem)
                if title:
                    return title
    return None


def _infer_title_from_chunk_paths(input_paths: list[Path]) -> str | None:
    stems = [path.stem for path in input_paths if path.name.casefold() != "index.txt"]
    if not stems:
        return None

    cleaned_candidates: list[str] = []
    for stem in stems[: min(len(stems), 6)]:
        title = _clean_chunk_stem(stem)
        if title:
            cleaned_candidates.append(title)

    if not cleaned_candidates:
        return None

    first = cleaned_candidates[0]
    if all(candidate == first for candidate in cleaned_candidates[1:]):
        return first
    return None


def _clean_chunk_stem(stem: str) -> str | None:
    cleaned = re.sub(r"^\d{3}[_-]+", "", stem.strip())
    cleaned = re.sub(r"[_-]*chunk(?:s)?$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[_-]*chapters?[_-]?\d+(?:[_-]\d+)?$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[_-]*part[_-]?\d+$", "", cleaned, flags=re.IGNORECASE)
    return _normalize_title_candidate(cleaned)


def _normalize_title_candidate(value: str) -> str | None:
    raw = str(value).strip().strip('"').strip("'")
    if not raw:
        return None
    path_like = Path(raw)
    candidate = path_like.stem if path_like.suffix else raw
    candidate = _strip_technical_folder_name(candidate)
    candidate = candidate.strip(" _-")
    if not candidate:
        return None
    if candidate.casefold() in {"chunks", "chapters", "project", "run", "output"}:
        return None
    return candidate


def _strip_technical_folder_name(value: str) -> str:
    cleaned = str(value).strip()
    cleaned = re.sub(
        r"^(?:project[_-]+)?(?:chunks?|chapters?)(?:__|[_-])\d{8}_\d{6}(?:_\d{2})?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^(?:chunks?|chapters?)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" _-")
