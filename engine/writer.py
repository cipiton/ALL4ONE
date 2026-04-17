from __future__ import annotations  
  
import json  
import re  
from datetime import datetime  
from pathlib import Path  
from typing import Any  
  
from .models import InputDocument, SkillDefinition  
from .output_paths import is_story_pipeline_skill, resolve_story_stage_output
  
  
def create_session_directory(  
    outputs_root: Path,  
    skill_name: str,  
    input_root_path: Path | None = None,  
    input_paths: list[Path] | None = None,
) -> tuple[str, Path]:  
    if is_story_pipeline_skill(skill_name):
        context = resolve_story_stage_output(
            outputs_root,
            skill_name,
            input_root_path=input_root_path,
            input_paths=list(input_paths or []),
        )
        if context.stage_dir is None:
            raise ValueError(f"Story-first output resolution did not return a stage directory for {skill_name}")
        return context.run_id, context.stage_dir

    skill_root = outputs_root / skill_name  
    skill_root.mkdir(parents=True, exist_ok=True)  
  
    base_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')  
    session_prefix = safe_stem(_derive_session_label(skill_name, input_root_path, input_paths or []))  
    attempt = 0  
    while True:  
        timestamp = base_timestamp if attempt == 0 else f'{base_timestamp}_{attempt:02d}'  
        session_name = f'{session_prefix}__{timestamp}' if session_prefix else timestamp  
        session_dir = skill_root / session_name  
        try:  
            session_dir.mkdir(parents=True, exist_ok=False)  
            return timestamp, session_dir  
        except FileExistsError:  
            attempt += 1  
  
  
def _derive_session_label(skill_name: str, input_root_path: Path | None, input_paths: list[Path]) -> str:  
    if input_root_path is None:  
        return 'run'  
    if skill_name != "large_novel_processor":
        inferred_project_title = _infer_project_title(input_root_path, input_paths)
        if inferred_project_title:
            return inferred_project_title
        candidate = input_root_path.name if input_root_path.suffix == '' else input_root_path.stem
        cleaned_candidate = _strip_technical_folder_name(candidate)
        if cleaned_candidate:
            return cleaned_candidate
        return "project"
    candidate = input_root_path.name if input_root_path.suffix == '' else input_root_path.stem  
    return candidate or 'run'  


def _infer_project_title(input_root_path: Path, input_paths: list[Path]) -> str | None:
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

    cleaned = _strip_technical_folder_name(input_root_path.name if input_root_path.is_dir() else input_root_path.stem)
    return cleaned or None


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
        for key in ("title",):
            title = _normalize_title_candidate(str(payload.get(key, "")))
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
    raw = value.strip().strip('"').strip("'")
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
    cleaned = value.strip()
    cleaned = re.sub(r"^(?:project[_-]+)?(?:chunks?|chapters?)(?:__|[_-])\d{8}_\d{6}(?:_\d{2})?$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:chunks?|chapters?)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" _-")
  
  
def create_document_directory(session_dir: Path, document: InputDocument) -> Path:  
    directory = session_dir / 'documents' / f'{document.index:03d}_{safe_stem(document.path.stem)}'  
    directory.mkdir(parents=True, exist_ok=True)  
    return directory  
  
  
def create_internal_directory(base_dir: Path) -> Path:  
    internal_dir = base_dir / '.internal'  
    internal_dir.mkdir(parents=True, exist_ok=True)  
    return internal_dir  
  
  
def render_output_filename(  
    template: str,  
    document: InputDocument,  
    *,  
    step_number: int | None = None,  
) -> str:  
    rendered = template.format(  
        input_name=document.path.name,  
        input_stem=safe_stem(document.path.stem),  
        step_number=step_number if step_number is not None else '',  
    )  
    return rendered or f'{safe_stem(document.path.stem)}.txt' 
  
  
def write_text_file(output_dir: Path, filename: str, content: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = _resolve_output_path(output_dir, filename)
    target.write_text(content, encoding='utf-8')
    return target


def write_json_file(output_dir: Path, filename: str, payload: Any) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = _resolve_output_path(output_dir, filename)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return target
  
  
def render_section_report(  
    skill: SkillDefinition,  
    document: InputDocument,  
    sections: dict[str, Any],  
    *,  
    model_name: str,  
) -> str:  
    lines = [  
        f'Skill: {skill.display_name}',  
        f'Input file: {document.path.name}',  
        f'Model: {model_name}',  
        '',  
    ]  
    ordered_sections = skill.output_config.sections or list(sections)  
    seen: set[str] = set()  
  
    for section_name in ordered_sections:  
        seen.add(section_name)  
        lines.append(section_name)  
        lines.append(stringify(sections.get(section_name)))  
        lines.append('')  
  
    for section_name, value in sections.items():  
        if section_name in seen:  
            continue  
        lines.append(section_name)  
        lines.append(stringify(value))  
        lines.append('')  
  
    return '\n'.join(lines).rstrip() + '\n'  
  
  
def safe_stem(value: str) -> str:  
    slug = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff._-]+', '_', value.strip())  
    slug = slug.strip('._') or 'document'  
    return slug[:80]  
  
  
def stringify(value: Any) -> str:
    if value is None:
        return '未明确提及'
    if isinstance(value, str):  
        stripped = value.strip()  
        return stripped or '未明确提及'  
    if isinstance(value, list):
        parts = [stringify(item) for item in value]
        return ';'.join(part for part in parts if part and part != '未明确提及') or '未明确提及'
    return str(value).strip() or '未明确提及'


def _resolve_output_path(output_dir: Path, filename: str) -> Path:
    base_dir = output_dir.resolve()
    target = (base_dir / filename).resolve()
    try:
        target.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError(f"Output filename escapes the output directory: {filename}") from exc
    return target

