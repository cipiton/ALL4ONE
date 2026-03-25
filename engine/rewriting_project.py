from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from . import terminal_ui
from .input_loader import load_input_document, read_resource_text, resolve_input_paths
from .llm_client import call_chat_completion, load_config_from_env, parse_json_response
from .models import DocumentResult, PromptMessage, SkillDefinition
from .prompts import build_step_prompt_messages
from .skill_loader import load_reference_texts
from .writer import safe_stem, write_json_file, write_text_file


SESSION_NAME_PATTERN = re.compile(r"^(?P<prefix>.+?)__\d{8}_\d{6}(?:_\d{2})?$")
BIBLE_STORAGE_DIRNAME = "bibles"


def should_offer_rewriting_project_mode(
    skill: SkillDefinition,
    input_paths: list[Path],
    *,
    input_root_path: Path | None,
) -> bool:
    if skill.name != "rewriting":
        return False
    if input_root_path is not None and input_root_path.is_dir() and len(input_paths) > 1:
        return True
    if len(input_paths) == 1 and input_paths[0].suffix.lower() == ".txt":
        return True
    return False


def prompt_rewriting_launch(repo_root: Path) -> tuple[Path, list[Path], dict[str, Any]]:
    outputs_root = repo_root / "outputs" / "rewriting"
    default_mode = "rewrite_with_bible" if _list_available_bibles(outputs_root) else "build_bible_and_rewrite"

    while True:
        project_mode = terminal_ui.prompt_for_rewriting_mode(default_mode)
        if project_mode == "build_bible":
            plan_path = _prompt_required_plan_path()
            supplemental_script_paths = _prompt_optional_script_paths()
            return plan_path, [plan_path], {
                "rewriting_project_mode": project_mode,
                "plan_path": str(plan_path),
                "supplemental_script_paths": [str(path) for path in supplemental_script_paths],
            }

        if project_mode == "rewrite_with_bible":
            selected_bible = _prompt_for_existing_bible(outputs_root)
            if selected_bible is None:
                print("No refresh bibles are available yet. Choose 1 or 3 to create one first.")
                default_mode = "build_bible_and_rewrite"
                continue
            script_root_path, script_paths = _prompt_required_script_input()
            return script_root_path, script_paths, {
                "rewriting_project_mode": project_mode,
                "selected_bible_path": str(selected_bible),
            }

        if project_mode == "build_bible_and_rewrite":
            plan_path = _prompt_required_plan_path()
            supplemental_script_paths = _prompt_optional_script_paths()
            script_root_path, script_paths = _prompt_required_script_input()
            supplemental_script_paths = _merge_unique_paths(supplemental_script_paths, script_paths)
            return script_root_path, script_paths, {
                "rewriting_project_mode": project_mode,
                "plan_path": str(plan_path),
                "supplemental_script_paths": [str(path) for path in supplemental_script_paths],
            }

        default_mode = "build_bible_and_rewrite"


def execute_rewriting_project(
    repo_root: Path,
    skill: SkillDefinition,
    input_paths: list[Path],
    *,
    input_root_path: Path | None,
    session_dir: Path,
    launch_options: dict[str, Any],
    verbose: bool,
) -> tuple[Path, list[DocumentResult]] | None:
    project_mode = str(launch_options.get("rewriting_project_mode") or "").strip()
    selected_bible_override = _optional_path(launch_options.get("selected_bible_path"))
    plan_override = _optional_path(launch_options.get("plan_path"))
    supplemental_override = _resolve_optional_paths(launch_options.get("supplemental_script_paths"))

    is_folder_project = input_root_path is not None and input_root_path.is_dir() and len(input_paths) > 1
    if is_folder_project and not project_mode:
        folder_mode = terminal_ui.prompt_for_folder_processing_mode(len(input_paths))
        if folder_mode == "individual":
            return None

    existing_bible_path = selected_bible_override or _find_latest_refresh_bible(repo_root, session_dir)
    if not project_mode:
        default_mode = _infer_default_mode(input_paths, existing_bible_path)
        while True:
            project_mode = terminal_ui.prompt_for_rewriting_mode(default_mode)
            if project_mode == "rewrite_with_bible" and existing_bible_path is None:
                print("No existing refresh bible was found for this project. Choose 1 or 3.")
                default_mode = "build_bible_and_rewrite"
                continue
            break

    plan_path: Path | None = None
    script_paths: list[Path] = []
    supplemental_script_paths: list[Path] = list(supplemental_override)

    primary_is_plan = len(input_paths) == 1 and _looks_like_adaptation_plan_path(input_paths[0])
    if primary_is_plan:
        if plan_path is None:
            plan_path = plan_override or input_paths[0]
        if not launch_options:
            if project_mode == "build_bible":
                supplemental_script_paths = _prompt_optional_script_paths()
            elif project_mode == "rewrite_with_bible":
                script_paths = _prompt_required_script_paths()
            elif project_mode == "build_bible_and_rewrite":
                supplemental_script_paths = _prompt_optional_script_paths()
                script_paths = _prompt_required_script_paths()
                supplemental_script_paths = _merge_unique_paths(supplemental_script_paths, script_paths)
    else:
        script_paths = list(input_paths)
        if project_mode in {"build_bible", "build_bible_and_rewrite"} and plan_path is None:
            plan_path = plan_override
        if project_mode in {"build_bible", "build_bible_and_rewrite"} and plan_path is None:
            plan_path = _prompt_required_plan_path()
        if project_mode in {"build_bible", "build_bible_and_rewrite"} and not supplemental_script_paths:
            supplemental_script_paths = list(script_paths)

    intermediate_dir = session_dir / "intermediate"
    final_dir = session_dir / "final"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    if project_mode in {"build_bible", "build_bible_and_rewrite"}:
        if plan_path is None:
            raise RuntimeError("A Skill 4 final adaptation plan is required to build the refresh bible.")
        bible_payload = _build_refresh_bible(
            repo_root,
            skill,
            plan_path=plan_path,
            supplemental_script_paths=supplemental_script_paths,
        )
        bible_json_path = write_json_file(intermediate_dir, "refresh_bible.json", bible_payload)
        bible_text = _render_refresh_bible_text(bible_payload)
        bible_text_path = write_text_file(intermediate_dir, "refresh_bible.txt", bible_text)
        _write_canonical_bible(repo_root, bible_payload, bible_text)
    else:
        bible_payload = json.loads(existing_bible_path.read_text(encoding="utf-8"))
        bible_json_path = write_json_file(intermediate_dir, "refresh_bible.json", bible_payload)
        bible_text = _render_refresh_bible_text(bible_payload)
        bible_text_path = write_text_file(intermediate_dir, "refresh_bible.txt", bible_text)

    manifest_payload: dict[str, Any] = {
        "mode": project_mode,
        "input_root_path": str(input_root_path) if input_root_path is not None else None,
        "plan_path": str(plan_path) if plan_path else None,
        "supplemental_script_paths": [str(path) for path in supplemental_script_paths],
        "refresh_bible_json": str(bible_json_path),
        "refresh_bible_txt": str(bible_text_path),
        "final_outputs": [],
        "failures": [],
    }

    if project_mode == "build_bible":
        write_json_file(intermediate_dir, "rewrite_project_manifest.json", manifest_payload)
        return session_dir, [
            DocumentResult(
                document_path=plan_path or input_paths[0],
                output_directory=session_dir,
                status="completed",
                primary_output=bible_json_path,
            )
        ]

    if not script_paths:
        raise RuntimeError("No script files were provided for rewriting.")

    results: list[DocumentResult] = []
    total_files = len(script_paths)
    for file_index, script_path in enumerate(script_paths, start=1):
        if verbose:
            print(_format_rewriting_file_progress(file_index, total_files, script_path.name))
        try:
            final_output_path = _rewrite_script_with_bible(
                repo_root,
                skill,
                script_path,
                bible_text=bible_text,
                final_dir=final_dir,
                intermediate_dir=intermediate_dir,
                file_index=file_index,
                total_files=total_files,
                verbose=verbose,
            )
            manifest_payload["final_outputs"].append(
                {"input": str(script_path), "output": str(final_output_path)}
            )
            results.append(
                DocumentResult(
                    document_path=script_path,
                    output_directory=session_dir,
                    status="completed",
                    primary_output=final_output_path,
                )
            )
        except Exception as exc:  # noqa: BLE001
            manifest_payload["failures"].append({"input": str(script_path), "error": str(exc)})
            results.append(
                DocumentResult(
                    document_path=script_path,
                    output_directory=session_dir,
                    status="error",
                    error_message=str(exc),
                )
            )

    write_json_file(intermediate_dir, "rewrite_project_manifest.json", manifest_payload)
    if verbose:
        success_count = sum(1 for result in results if result.status == "completed")
        failure_count = sum(1 for result in results if result.status != "completed")
        print(
            f"[rewriting project] completed files={total_files} success={success_count} "
            f"failure={failure_count} output_root={session_dir}"
        )
    return session_dir, results


def _infer_default_mode(input_paths: list[Path], existing_bible_path: Path | None) -> str:
    if len(input_paths) == 1 and _looks_like_adaptation_plan_path(input_paths[0]):
        return "build_bible"
    if existing_bible_path is not None:
        return "rewrite_with_bible"
    return "build_bible_and_rewrite"


def _looks_like_adaptation_plan_path(path: Path) -> bool:
    lowered_name = path.name.casefold()
    if any(token in lowered_name for token in ("adaptation_plan", "final_adaptation_plan", "改编方案", "adaptation")):
        return True
    try:
        text = read_resource_text(path)
    except Exception:  # noqa: BLE001
        return False
    lowered_text = text.casefold()
    markers = ("### 表1", "### 表2", "角色圣经", "改编定位", "总集数", "阶段节奏")
    return any(marker.casefold() in lowered_text for marker in markers)


def _prompt_required_plan_path() -> Path:
    while True:
        raw_path = terminal_ui.prompt_for_path(
            "Enter the Skill 4 final adaptation plan path (.txt; blank to cancel): ",
            required=True,
        )
        try:
            return resolve_input_paths(str(raw_path), [".txt"])[0]
        except Exception as exc:  # noqa: BLE001
            print(f"Invalid plan path: {exc}")


def _prompt_required_script_paths() -> list[Path]:
    while True:
        raw_path = terminal_ui.prompt_for_path(
            "Enter the script file or folder path to rewrite (.txt; blank to cancel): ",
            required=True,
        )
        try:
            return resolve_input_paths(str(raw_path), [".txt"], folder_mode="non_recursive")
        except Exception as exc:  # noqa: BLE001
            print(f"Invalid script path: {exc}")


def _prompt_required_script_input() -> tuple[Path, list[Path]]:
    while True:
        raw_path = terminal_ui.prompt_for_path(
            "Enter the script file or folder path to rewrite (.txt; blank to cancel): ",
            required=True,
        )
        try:
            resolved_paths = resolve_input_paths(str(raw_path), [".txt"], folder_mode="non_recursive")
            return Path(str(raw_path)), resolved_paths
        except Exception as exc:  # noqa: BLE001
            print(f"Invalid script path: {exc}")


def _prompt_optional_script_paths() -> list[Path]:
    raw_path = terminal_ui.prompt_for_path(
        "Optional supplemental script file or folder (.txt; blank to skip): ",
        required=False,
    )
    if not raw_path:
        return []
    try:
        return resolve_input_paths(str(raw_path), [".txt"], folder_mode="non_recursive")
    except Exception as exc:  # noqa: BLE001
        print(f"Skipping supplemental scripts: {exc}")
        return []


def _prompt_for_existing_bible(outputs_root: Path) -> Path | None:
    options = _list_available_bibles(outputs_root)
    selected = terminal_ui.prompt_for_existing_bible(options)
    return Path(selected) if selected else None


def _list_available_bibles(outputs_root: Path) -> list[tuple[str, str]]:
    bibles_root = outputs_root / BIBLE_STORAGE_DIRNAME
    if not bibles_root.exists():
        return []

    options: list[tuple[str, str]] = []
    for candidate in sorted((path for path in bibles_root.iterdir() if path.is_dir()), key=lambda path: path.name.casefold()):
        bible_path = candidate / "refresh_bible.json"
        if not bible_path.exists():
            continue
        label = candidate.name
        try:
            payload = json.loads(bible_path.read_text(encoding="utf-8"))
            label = str(payload.get("project_title") or candidate.name)
        except Exception:  # noqa: BLE001
            pass
        options.append((label, str(bible_path)))
    return options


def _write_canonical_bible(repo_root: Path, payload: dict[str, Any], bible_text: str) -> tuple[Path, Path]:
    project_name = safe_stem(str(payload.get("project_title") or "project"))
    bibles_root = repo_root / "outputs" / "rewriting" / BIBLE_STORAGE_DIRNAME / project_name
    bibles_root.mkdir(parents=True, exist_ok=True)
    json_path = write_json_file(bibles_root, "refresh_bible.json", payload)
    txt_path = write_text_file(bibles_root, "refresh_bible.txt", bible_text)
    return json_path, txt_path


def _optional_path(value: Any) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


def _resolve_optional_paths(value: Any) -> list[Path]:
    if not value:
        return []
    if isinstance(value, (str, Path)):
        return [Path(str(value))]
    if isinstance(value, list):
        return [Path(str(item)) for item in value if item not in (None, "")]
    return []


def _merge_unique_paths(*path_lists: list[Path]) -> list[Path]:
    merged: list[Path] = []
    seen: set[Path] = set()
    for path_list in path_lists:
        for path in path_list:
            resolved = path.resolve()
            if resolved in seen:
                continue
            merged.append(path)
            seen.add(resolved)
    return merged


def _render_progress_bar(current: int, total: int, *, width: int = 10) -> str:
    if total <= 0:
        filled = 0
    else:
        filled = min(width, max(1, math.ceil((current / total) * width)))
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def _format_rewriting_file_progress(current: int, total: int, file_name: str) -> str:
    return f"[rewriting project] {_render_progress_bar(current, total)} {current}/{total} files | current: {file_name}"


def _build_refresh_bible(
    repo_root: Path,
    skill: SkillDefinition,
    *,
    plan_path: Path,
    supplemental_script_paths: list[Path],
) -> dict[str, Any]:
    plan_text = read_resource_text(plan_path).strip()
    script_payload = _build_script_evidence_payload(supplemental_script_paths)
    config = load_config_from_env(repo_root, skill=skill, route_role="step_execution")
    messages = [
        PromptMessage(
            role="system",
            content=(
                "You are building a refresh bible for a coordinated rewrite project. "
                "Return only a JSON object with no extra commentary."
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "Build a practical refresh bible using the adaptation plan as the primary canon source. "
                "Use supplemental script evidence only to enrich on-page usage and terminology.\n\n"
                "Required JSON schema:\n"
                "{\n"
                '  "project_title": "string",\n'
                '  "source_metadata": {\n'
                '    "adaptation_plan_used": true,\n'
                '    "supplemental_script_sources": ["string"]\n'
                "  },\n"
                '  "characters": [{"original_name": "string", "refreshed_name": "string", "aliases": ["string"], "role": "string", "notes": "string"}],\n'
                '  "relationships": [{"between": ["string"], "original_framing": "string", "refreshed_framing": "string", "notes": "string"}],\n'
                '  "objects_systems_artifacts": [{"original_term": "string", "refreshed_term": "string", "notes": "string"}],\n'
                '  "factions_organizations": [{"original_term": "string", "refreshed_term": "string", "notes": "string"}],\n'
                '  "locations": [{"original_term": "string", "refreshed_term": "string", "notes": "string"}],\n'
                '  "forbidden_terms": ["string"],\n'
                '  "naming_style_rules": ["string"],\n'
                '  "consistency_rules": ["string"],\n'
                '  "supplemental_observations": ["string"]\n'
                "}\n\n"
                f"Adaptation plan path: {plan_path}\n\n"
                f"Adaptation plan:\n{plan_text}\n\n"
                f"Supplemental script evidence:\n{script_payload}"
            ),
        ),
    ]
    response = call_chat_completion(config, messages, json_mode=True)
    payload = parse_json_response(response)
    if not isinstance(payload, dict):
        raise RuntimeError("Refresh bible generation did not return a JSON object.")

    payload["project_title"] = str(payload.get("project_title") or plan_path.stem)
    payload["source_metadata"] = {
        "adaptation_plan_used": True,
        "adaptation_plan_path": str(plan_path),
        "supplemental_script_sources": [str(path) for path in supplemental_script_paths],
    }
    return payload


def _build_script_evidence_payload(paths: list[Path], *, max_files: int = 6, max_chars_per_file: int = 2_500) -> str:
    if not paths:
        return "No supplemental script evidence."
    blocks: list[str] = []
    for path in paths[:max_files]:
        try:
            text = read_resource_text(path).strip()
        except Exception:  # noqa: BLE001
            continue
        snippet = text[:max_chars_per_file]
        if len(text) > len(snippet):
            snippet = f"{snippet}\n..."
        blocks.append(f"[{path.name}]\n{snippet}")
    return "\n\n".join(blocks) if blocks else "No readable supplemental script evidence."


def _render_refresh_bible_text(payload: dict[str, Any]) -> str:
    lines = [
        f"项目标题：{payload.get('project_title', '未命名项目')}",
        "",
        "来源信息：",
    ]
    source_metadata = payload.get("source_metadata") or {}
    lines.append(f"- adaptation_plan_used: {source_metadata.get('adaptation_plan_used', False)}")
    lines.append(f"- adaptation_plan_path: {source_metadata.get('adaptation_plan_path', '')}")
    supplemental = source_metadata.get("supplemental_script_sources") or []
    lines.append(f"- supplemental_script_sources: {', '.join(str(item) for item in supplemental) or 'none'}")
    lines.append("")

    lines.append("角色：")
    for item in payload.get("characters") or []:
        lines.append(
            f"- {item.get('original_name', '')} -> {item.get('refreshed_name', '')}; "
            f"aliases={','.join(item.get('aliases') or [])}; role={item.get('role', '')}; notes={item.get('notes', '')}"
        )
    lines.append("")

    lines.append("关系：")
    for item in payload.get("relationships") or []:
        between = ",".join(str(value) for value in item.get("between") or [])
        lines.append(
            f"- {between}; original={item.get('original_framing', '')}; "
            f"refreshed={item.get('refreshed_framing', '')}; notes={item.get('notes', '')}"
        )
    lines.append("")

    lines.append("物件/系统/设定：")
    for key in ("objects_systems_artifacts", "factions_organizations", "locations"):
        for item in payload.get(key) or []:
            lines.append(
                f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; notes={item.get('notes', '')}"
            )
    lines.append("")

    lines.append("禁用词：")
    for item in payload.get("forbidden_terms") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("命名/风格规则：")
    for item in payload.get("naming_style_rules") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("一致性规则：")
    for item in payload.get("consistency_rules") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("补充观察：")
    for item in payload.get("supplemental_observations") or []:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _rewrite_script_with_bible(
    repo_root: Path,
    skill: SkillDefinition,
    script_path: Path,
    *,
    bible_text: str,
    final_dir: Path,
    intermediate_dir: Path,
    file_index: int,
    total_files: int,
    verbose: bool,
) -> Path:
    document = load_input_document(script_path)
    script_intermediate_dir = intermediate_dir / safe_stem(script_path.stem)
    script_intermediate_dir.mkdir(parents=True, exist_ok=True)

    runtime_values = {
        "shared_project_mode": True,
        "refresh_bible_available": True,
        "refresh_bible_policy": (
            "Use the refresh bible as the canonical rename and consistency source. "
            "Do not invent new names or replacement terms unless the bible explicitly allows it."
        ),
    }

    executed_steps = [
        (1, [("【原始剧本/文本】", document.text), ("【共享刷新圣经】", bible_text)]),
        (3, None),
        (4, None),
    ]

    normalized_text = _run_rewriting_step(
        repo_root,
        skill,
        step_number=executed_steps[0][0],
        step_index=1,
        total_steps=len(executed_steps),
        file_index=file_index,
        total_files=total_files,
        document=document,
        runtime_values=runtime_values,
        input_blocks=executed_steps[0][1] or [],
        verbose=verbose,
    )
    write_text_file(script_intermediate_dir, "01_normalized_source.txt", normalized_text)

    revised_draft = _run_rewriting_step(
        repo_root,
        skill,
        step_number=executed_steps[1][0],
        step_index=2,
        total_steps=len(executed_steps),
        file_index=file_index,
        total_files=total_files,
        document=document,
        runtime_values=runtime_values,
        input_blocks=[("【规范化原稿】", normalized_text), ("【洗稿方案】", bible_text)],
        verbose=verbose,
    )
    write_text_file(script_intermediate_dir, "03_revised_script_draft.txt", revised_draft)

    final_text = _run_rewriting_step(
        repo_root,
        skill,
        step_number=executed_steps[2][0],
        step_index=3,
        total_steps=len(executed_steps),
        file_index=file_index,
        total_files=total_files,
        document=document,
        runtime_values=runtime_values,
        input_blocks=[("【洗稿方案】", bible_text), ("【洗稿后剧本草稿】", revised_draft)],
        verbose=verbose,
    )
    write_text_file(script_intermediate_dir, "04_revised_script_final.txt", final_text)
    return write_text_file(final_dir, script_path.name, final_text)


def _run_rewriting_step(
    repo_root: Path,
    skill: SkillDefinition,
    *,
    step_number: int,
    step_index: int,
    total_steps: int,
    file_index: int,
    total_files: int,
    document,
    runtime_values: dict[str, Any],
    input_blocks: list[tuple[str, str]],
    verbose: bool,
) -> str:
    step = skill.get_step(step_number)
    config = load_config_from_env(
        repo_root,
        skill=skill,
        step=step,
        model_override=step.model_override,
    )
    if verbose:
        file_scope = f"file {file_index}/{total_files}" if total_files > 1 else "file 1/1"
        print(f"  step {step_index}/{total_steps}: {step.title} model={config.model} ({file_scope})")
    reference_ids: list[str] = []
    if step.prompt_reference_id:
        reference_ids.append(step.prompt_reference_id)
    for reference in skill.references.values():
        if reference.reference_id in reference_ids:
            continue
        if reference.load == "always" or (reference.step_numbers and step.number in reference.step_numbers):
            reference_ids.append(reference.reference_id)
    reference_texts = load_reference_texts(skill, reference_ids)
    messages = build_step_prompt_messages(
        skill,
        step,
        document,
        reference_texts,
        runtime_values,
        input_blocks=input_blocks,
    )
    response = call_chat_completion(config, messages, json_mode=False)
    return response.text


def _find_latest_refresh_bible(repo_root: Path, session_dir: Path) -> Path | None:
    project_name = safe_stem(_session_prefix(session_dir.name))
    canonical_bible = repo_root / "outputs" / "rewriting" / BIBLE_STORAGE_DIRNAME / project_name / "refresh_bible.json"
    if canonical_bible.exists():
        return canonical_bible

    skill_root = session_dir.parent
    current_prefix = _session_prefix(session_dir.name)
    candidates: list[Path] = []
    for candidate in skill_root.iterdir():
        if not candidate.is_dir() or candidate == session_dir or candidate.name == BIBLE_STORAGE_DIRNAME:
            continue
        if current_prefix and _session_prefix(candidate.name) != current_prefix:
            continue
        bible_path = candidate / "intermediate" / "refresh_bible.json"
        if bible_path.exists():
            candidates.append(bible_path)
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _session_prefix(session_name: str) -> str:
    match = SESSION_NAME_PATTERN.match(session_name)
    if match:
        return match.group("prefix")
    return session_name
