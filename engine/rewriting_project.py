from __future__ import annotations

import json
import math
import re
from datetime import datetime
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
    session_dir: Path | None,
    launch_options: dict[str, Any],
    verbose: bool,
) -> tuple[Path, list[DocumentResult]] | None:
    project_mode = str(launch_options.get("rewriting_project_mode") or "").strip()
    rewrite_render_mode = str(launch_options.get("rewrite_render_mode") or "final").strip().lower() or "final"
    selected_bible_override = _optional_path(launch_options.get("selected_bible_path"))
    plan_override = _optional_path(launch_options.get("plan_path"))
    supplemental_override = _resolve_optional_paths(launch_options.get("supplemental_script_paths"))

    is_folder_project = input_root_path is not None and input_root_path.is_dir() and len(input_paths) > 1
    if is_folder_project and not project_mode:
        folder_mode = terminal_ui.prompt_for_folder_processing_mode(len(input_paths))
        if folder_mode == "individual":
            return None

    existing_bible_path = selected_bible_override
    if existing_bible_path is None and session_dir is not None:
        existing_bible_path = _find_latest_refresh_bible(repo_root, session_dir)
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

    if project_mode in {"build_bible", "build_bible_and_rewrite"}:
        if plan_path is None:
            raise RuntimeError("A Skill 4 final adaptation plan is required to build the refresh bible.")
        bible_payload = _build_refresh_bible(
            repo_root,
            skill,
            plan_path=plan_path,
            supplemental_script_paths=supplemental_script_paths,
            verbose=verbose,
        )
        bible_text = _render_refresh_bible_text(bible_payload)
        canonical_bible_json_path, canonical_bible_text_path = _write_canonical_bible(repo_root, bible_payload, bible_text)
    else:
        if session_dir is None:
            raise RuntimeError("A session directory is required for rewrite mode.")
        raw_bible_payload = json.loads(existing_bible_path.read_text(encoding="utf-8"))
        bible_payload = _normalize_refresh_bible_payload(
            raw_bible_payload,
            plan_path=_resolve_plan_path_for_existing_bible(existing_bible_path, raw_bible_payload),
        )
        if "source_metadata" in raw_bible_payload:
            bible_payload["source_metadata"] = raw_bible_payload["source_metadata"]

    if project_mode == "build_bible":
        canonical_dir = canonical_bible_json_path.parent
        write_json_file(
            canonical_dir,
            "bible_metadata.json",
            {
                "mode": project_mode,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "plan_path": str(plan_path) if plan_path else None,
                "source_title": bible_payload.get("source_title"),
                "refreshed_project_title": bible_payload.get("refreshed_project_title"),
                "title_policy": bible_payload.get("title_policy"),
                "supplemental_script_paths": [str(path) for path in supplemental_script_paths],
                "refresh_bible_json": str(canonical_bible_json_path),
                "refresh_bible_txt": str(canonical_bible_text_path),
            },
        )
        if verbose:
            print(f"[rewriting project] bible created at {canonical_dir}")
        return canonical_dir, [
            DocumentResult(
                document_path=plan_path or input_paths[0],
                output_directory=canonical_dir,
                status="completed",
                primary_output=canonical_bible_json_path,
            )
        ]

    if session_dir is None:
        raise RuntimeError("A session directory is required for rewrite mode.")

    intermediate_dir = session_dir / "intermediate"
    final_dir = session_dir / "final"
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    if project_mode == "build_bible_and_rewrite":
        bible_json_path = write_json_file(intermediate_dir, "refresh_bible.json", bible_payload)
        bible_text_path = write_text_file(intermediate_dir, "refresh_bible.txt", bible_text)
    else:
        bible_json_path = write_json_file(intermediate_dir, "refresh_bible.json", bible_payload)
        bible_text = _render_refresh_bible_text(bible_payload)
        bible_text_path = write_text_file(intermediate_dir, "refresh_bible.txt", bible_text)

    manifest_payload: dict[str, Any] = {
        "mode": project_mode,
        "input_root_path": str(input_root_path) if input_root_path is not None else None,
        "plan_path": str(plan_path) if plan_path else None,
        "rewrite_render_mode": rewrite_render_mode,
        "supplemental_script_paths": [str(path) for path in supplemental_script_paths],
        "refresh_bible_json": str(bible_json_path),
        "refresh_bible_txt": str(bible_text_path),
        "final_outputs": [],
        "failures": [],
    }

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
                rewrite_render_mode=rewrite_render_mode,
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
            source_title = str(payload.get("source_title") or payload.get("project_title") or candidate.name)
            refreshed_title = _clean_text(payload.get("refreshed_project_title"))
            label = source_title
            if refreshed_title and refreshed_title != source_title:
                label = f"{source_title} -> {refreshed_title}"
        except Exception:  # noqa: BLE001
            pass
        options.append((label, str(bible_path)))
    return options


def _write_canonical_bible(repo_root: Path, payload: dict[str, Any], bible_text: str) -> tuple[Path, Path]:
    project_name = safe_stem(str(payload.get("source_title") or payload.get("project_title") or "project"))
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
    verbose: bool,
) -> dict[str, Any]:
    plan_text = read_resource_text(plan_path).strip()
    script_payload = _build_script_evidence_payload(supplemental_script_paths)
    config = load_config_from_env(repo_root, skill=skill, route_role="final_deliverable")
    if verbose:
        print(f"[rewriting project] building refresh bible route=final_deliverable model={config.model}")
    messages = [
        PromptMessage(
            role="system",
            content=(
                "你正在为中文短剧/网文洗稿项目构建『刷新圣经』。"
                "这个圣经必须成为后续洗稿的唯一规范来源。"
                "默认命名策略必须是中文原名 -> 中文刷新名，而不是英文音译。"
                "除非用户明确要求其他语言，否则禁止输出英文化音译、拼音化主名、或中英混排主名。"
                "这不是保守标准化，而是真正的 canon refresh。"
                "对于主要角色和主要专有名词，默认必须改成新的中文规范名。"
                "只有在明确 preserve/lock 条件成立时，才允许保持原名，并且必须填写 preserve_reason。"
                "如果无法可靠刷新，也不能改成英文；要么给出新的中文名，要么明确写 preserve_original=true 与 preserve_reason。"
                "返回且只返回 JSON 对象。"
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "请基于改编方案构建一份强约束、可直接执行的中文洗稿刷新圣经。"
                "改编方案是主 canon，补充剧本只用于补强页面级别的称呼、术语和重复名词。"
                "目标不是做宽松建议表，而是做后续洗稿必须遵守的规范映射。"
                "默认输出模式为 final：成稿只使用刷新后的规范中文名，不输出“新名（旧名）”混合写法。"
                "只有在 audit 模式下才允许保留校对型括注，但默认不要这样做。\n\n"
                "强制策略：\n"
                "- 主要角色默认必须刷新成新的中文规范名，不能大面积保持原名\n"
                "- 主要组织、势力、系统、契约、能力、法宝、地点、称号、重复术语也默认必须刷新成新的中文规范名\n"
                "- 保持不变只能作为例外，并且要写清 preserve_reason\n"
                "- 不要把“原名不变”当成默认安全选项\n\n"
                "必须覆盖并刷新这些类别：\n"
                "1. 核心人物与别名/称谓\n"
                "2. 关系标签与身份称呼\n"
                "3. 组织/阵营/势力/门派/机构\n"
                "4. 世界观专有名词\n"
                "5. 系统/契约/能力/路径/术式\n"
                "6. 道具/法宝/关键物件\n"
                "7. 地点/场景/关键空间\n"
                "8. 称号/职级/权力标签\n"
                "9. 口头禅/签名术语/重复台词标签\n\n"
                "命名要求：\n"
                "- 刷新名默认必须是中文或中文风格命名\n"
                "- 贴合中文网文/短剧语感，简洁、可记、易读\n"
                "- 角色之间要有身份、气质、阵营上的区分度\n"
                "- 势力、系统、能力、法宝、地点也要保持题材一致性\n"
                "- 不要输出 Yu Xiao、Lilith 这类英文主名；若拿不准，请保留中文而不是英文化\n\n"
                "Required JSON schema:\n"
                "Required JSON schema:\n"
                "{\n"
                '  "source_title": "string",\n'
                '  "refreshed_project_title": "string",\n'
                '  "title_policy": "preserve_original_title | both | generate_refreshed_title",\n'
                '  "source_metadata": {\n'
                '    "adaptation_plan_used": true,\n'
                '    "supplemental_script_sources": ["string"]\n'
                "  },\n"
                '  "naming_policy": {"target_language": "zh-CN", "default_render_mode": "final", "transliteration_policy": "forbid_english_transliteration", "fallback_policy": "keep_original_chinese_if_uncertain"},\n'
                '  "characters": [{"original_name": "string", "refreshed_name": "string", "aliases": ["string"], "titles": ["string"], "role": "string", "notes": "string", "consistency_rule": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "relationship_labels": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "organizations_factions": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "world_terms": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "systems_contracts_powers": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "artifacts_props": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "locations": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "titles_ranks_labels": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "signature_terms": [{"original_term": "string", "refreshed_term": "string", "alternate_forms": ["string"], "notes": "string", "preserve_original": false, "preserve_reason": ""}],\n'
                '  "relationships": [{"between": ["string"], "original_framing": "string", "refreshed_framing": "string", "notes": "string"}],\n'
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

    payload = _repair_unfreshened_major_terms(repo_root, skill, payload, verbose=verbose)
    payload = _normalize_refresh_bible_payload(payload, plan_path=plan_path)
    payload["source_title"] = str(payload.get("source_title") or plan_path.stem)
    payload["project_title"] = payload["source_title"]
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
    source_title = str(payload.get("source_title") or payload.get("project_title") or "未命名项目")
    refreshed_project_title = _clean_text(payload.get("refreshed_project_title"))
    title_policy = _clean_text(payload.get("title_policy")) or "preserve_original_title"
    lines = [
        f"原始项目标题：{source_title}",
        f"刷新项目标题：{refreshed_project_title or '未启用/未生成'}",
        f"标题处理策略：{title_policy}",
        "",
        "来源信息：",
    ]
    source_metadata = payload.get("source_metadata") or {}
    lines.append(f"- adaptation_plan_used: {source_metadata.get('adaptation_plan_used', False)}")
    lines.append(f"- adaptation_plan_path: {source_metadata.get('adaptation_plan_path', '')}")
    supplemental = source_metadata.get("supplemental_script_sources") or []
    lines.append(f"- supplemental_script_sources: {', '.join(str(item) for item in supplemental) or 'none'}")
    lines.append("")

    naming_policy = payload.get("naming_policy") or {}
    lines.append("命名策略：")
    lines.append(f"- target_language: {naming_policy.get('target_language', 'zh-CN')}")
    lines.append(f"- default_render_mode: {naming_policy.get('default_render_mode', 'final')}")
    lines.append(f"- transliteration_policy: {naming_policy.get('transliteration_policy', 'forbid_english_transliteration')}")
    lines.append(f"- fallback_policy: {naming_policy.get('fallback_policy', 'keep_original_chinese_if_uncertain')}")
    lines.append("")

    lines.append("核心人物命名映射：")
    for item in payload.get("characters") or []:
        lines.append(
            f"- {item.get('original_name', '')} -> {item.get('refreshed_name', '')}; "
            f"aliases={','.join(item.get('aliases') or [])}; "
            f"titles={','.join(item.get('titles') or [])}; role={item.get('role', '')}; "
            f"notes={item.get('notes', '')}; consistency={item.get('consistency_rule', '')}; "
            f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
        )
    lines.append("")

    lines.append("关系与称谓规则：")
    for item in payload.get("relationships") or []:
        between = ",".join(str(value) for value in item.get("between") or [])
        lines.append(
            f"- {between}; original={item.get('original_framing', '')}; "
            f"refreshed={item.get('refreshed_framing', '')}; notes={item.get('notes', '')}"
        )
    for item in payload.get("relationship_labels") or []:
        lines.append(
            f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
            f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}; "
            f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
        )
    lines.append("")

    lines.append("组织/阵营/势力映射：")
    for item in payload.get("organizations_factions") or []:
        lines.append(
            f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
            f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}; "
            f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
        )
    lines.append("")

    lines.append("世界观专有名词映射：")
    for item in payload.get("world_terms") or []:
        lines.append(
            f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
            f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}"
        )
    lines.append("")

    lines.append("道具/系统/能力映射：")
    for key in ("systems_contracts_powers", "artifacts_props", "objects_systems_artifacts"):
        for item in payload.get(key) or []:
            lines.append(
                f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
                f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}; "
                f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
            )
    lines.append("")

    lines.append("地点映射：")
    for item in payload.get("locations") or []:
        lines.append(
            f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
            f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}; "
            f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
        )
    lines.append("")

    lines.append("称号/职级/身份标签映射：")
    for item in payload.get("titles_ranks_labels") or []:
        lines.append(
            f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
            f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}; "
            f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
        )
    lines.append("")

    lines.append("签名术语与重复标签映射：")
    for item in payload.get("signature_terms") or []:
        lines.append(
            f"- {item.get('original_term', '')} -> {item.get('refreshed_term', '')}; "
            f"alts={','.join(item.get('alternate_forms') or [])}; notes={item.get('notes', '')}; "
            f"preserve={item.get('preserve_original', False)}; preserve_reason={item.get('preserve_reason', '')}"
        )
    lines.append("")

    lines.append("禁用词与避让规则：")
    for item in payload.get("forbidden_terms") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("命名/风格规则：")
    for item in payload.get("naming_style_rules") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("统一使用规则：")
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
    rewrite_render_mode: str,
    verbose: bool,
) -> Path:
    document = load_input_document(script_path)
    script_intermediate_dir = intermediate_dir / safe_stem(script_path.stem)
    script_intermediate_dir.mkdir(parents=True, exist_ok=True)

    runtime_values = {
        "shared_project_mode": True,
        "refresh_bible_available": True,
        "rewrite_render_mode": rewrite_render_mode,
        "naming_target_language": "zh-CN",
        "bilingual_audit_allowed": rewrite_render_mode == "audit",
        "refresh_bible_policy": (
            "Use the refresh bible as the canonical Chinese naming and terminology source of truth. "
            "In final mode, only use refreshed canonical terms in the output. "
            "Do not invent new names or fallback to original terms unless the bible explicitly allows it."
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
        input_blocks=[("【规范化原稿】", normalized_text), ("【共享刷新圣经】", bible_text)],
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
        input_blocks=[("【共享刷新圣经】", bible_text), ("【洗稿后剧本草稿】", revised_draft)],
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


def _resolve_plan_path_for_existing_bible(existing_bible_path: Path, payload: dict[str, Any]) -> Path:
    source_metadata = payload.get("source_metadata") or {}
    adaptation_plan_path = _clean_text(source_metadata.get("adaptation_plan_path"))
    if adaptation_plan_path:
        return Path(adaptation_plan_path)
    return existing_bible_path


def _normalize_refresh_bible_payload(payload: dict[str, Any], *, plan_path: Path) -> dict[str, Any]:
    normalized = dict(payload)
    source_title = _clean_text(normalized.get("source_title")) or _clean_text(normalized.get("project_title")) or plan_path.stem
    refreshed_project_title = _clean_text(normalized.get("refreshed_project_title"))
    title_policy = _clean_text(normalized.get("title_policy"))
    if not title_policy:
        title_policy = "both" if refreshed_project_title and refreshed_project_title != source_title else "preserve_original_title"
    normalized["source_title"] = source_title
    normalized["project_title"] = source_title
    normalized["refreshed_project_title"] = refreshed_project_title
    normalized["title_policy"] = title_policy
    normalized["naming_policy"] = {
        "target_language": "zh-CN",
        "default_render_mode": "final",
        "transliteration_policy": "forbid_english_transliteration",
        "fallback_policy": "major_terms_refresh_by_default_preserve_only_with_reason",
    }
    normalized.setdefault(
        "consistency_rules",
        [
            "默认 final 模式只使用刷新后的规范中文名，不使用中英混排或新名（旧名）样式。",
            "共享刷新圣经高于单文件临时改写判断，后续洗稿必须统一遵守。",
            "主要角色和主要专有名词默认必须刷新，保持原名必须给出 preserve_reason。",
        ],
    )
    normalized.setdefault(
        "naming_style_rules",
        [
            "默认采用中文到中文的刷新命名，不做英文音译主名。",
            "命名需贴合题材、阵营、身份和短剧阅读习惯。",
            "主要角色名默认应与原名区分开，形成新的项目规范名。",
        ],
    )

    normalized["characters"] = _normalize_character_records(normalized.get("characters"))
    normalized["relationship_labels"] = _normalize_term_records(normalized.get("relationship_labels"))
    normalized["organizations_factions"] = _normalize_term_records(
        normalized.get("organizations_factions") or normalized.get("factions_organizations")
    )
    normalized["world_terms"] = _normalize_term_records(normalized.get("world_terms"))
    normalized["systems_contracts_powers"] = _normalize_term_records(
        normalized.get("systems_contracts_powers") or normalized.get("objects_systems_artifacts")
    )
    normalized["artifacts_props"] = _normalize_term_records(normalized.get("artifacts_props"))
    normalized["locations"] = _normalize_term_records(normalized.get("locations"))
    normalized["titles_ranks_labels"] = _normalize_term_records(normalized.get("titles_ranks_labels"))
    normalized["signature_terms"] = _normalize_term_records(normalized.get("signature_terms"))
    normalized["relationships"] = _normalize_relationship_records(normalized.get("relationships"))
    normalized["forbidden_terms"] = _normalize_string_list(normalized.get("forbidden_terms"))
    normalized["supplemental_observations"] = _normalize_string_list(normalized.get("supplemental_observations"))
    normalized["naming_style_rules"] = _normalize_string_list(normalized.get("naming_style_rules"))
    normalized["consistency_rules"] = _normalize_string_list(normalized.get("consistency_rules"))
    return normalized


def _normalize_character_records(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        original_name = _clean_text(item.get("original_name"))
        if not original_name:
            continue
        refreshed_name = _normalize_refreshed_term(original_name, item.get("refreshed_name"))
        preserve_original = bool(item.get("preserve_original"))
        preserve_reason = _clean_text(item.get("preserve_reason"))
        if refreshed_name == original_name and not preserve_original:
            preserve_original = True
            preserve_reason = preserve_reason or "强制保留：自动刷新未能稳定生成，需人工复核"
        normalized.append(
            {
                "original_name": original_name,
                "refreshed_name": refreshed_name,
                "aliases": _normalize_alias_list(item.get("aliases"), original_name=original_name),
                "titles": _normalize_alias_list(item.get("titles"), original_name=original_name),
                "role": _clean_text(item.get("role")),
                "notes": _clean_text(item.get("notes")),
                "consistency_rule": _clean_text(item.get("consistency_rule"))
                or f"默认使用“{refreshed_name}”作为唯一主称呼。",
                "preserve_original": preserve_original,
                "preserve_reason": preserve_reason,
            }
        )
    return normalized


def _normalize_term_records(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        original_term = _clean_text(item.get("original_term"))
        if not original_term:
            continue
        refreshed_term = _normalize_refreshed_term(original_term, item.get("refreshed_term"))
        preserve_original = bool(item.get("preserve_original"))
        preserve_reason = _clean_text(item.get("preserve_reason"))
        if refreshed_term == original_term and not preserve_original:
            preserve_original = True
            preserve_reason = preserve_reason or "强制保留：自动刷新未能稳定生成，需人工复核"
        normalized.append(
            {
                "original_term": original_term,
                "refreshed_term": refreshed_term,
                "alternate_forms": _normalize_alias_list(item.get("alternate_forms"), original_name=original_term),
                "notes": _clean_text(item.get("notes")),
                "preserve_original": preserve_original,
                "preserve_reason": preserve_reason,
            }
        )
    return normalized


def _normalize_relationship_records(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        between = [_clean_text(entry) for entry in item.get("between") or []]
        between = [entry for entry in between if entry]
        normalized.append(
            {
                "between": between,
                "original_framing": _clean_text(item.get("original_framing")),
                "refreshed_framing": _normalize_refreshed_term(
                    _clean_text(item.get("original_framing")) or _clean_text(item.get("refreshed_framing")),
                    item.get("refreshed_framing"),
                ),
                "notes": _clean_text(item.get("notes")),
            }
        )
    return normalized


def _normalize_alias_list(value: Any, *, original_name: str) -> list[str]:
    aliases = _normalize_string_list(value)
    normalized: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        cleaned = _clean_text(alias)
        if not cleaned:
            continue
        if _contains_cjk(original_name) and _looks_english_heavy(cleaned):
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        normalized.append(cleaned)
        seen.add(key)
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        candidates = [value]
    else:
        candidates = [str(item) for item in value if item not in (None, "")]
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = _clean_text(candidate)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        normalized.append(cleaned)
        seen.add(key)
    return normalized


def _normalize_refreshed_term(original_term: str, refreshed_value: Any) -> str:
    refreshed_term = _clean_text(refreshed_value)
    if not refreshed_term:
        return original_term
    if _contains_cjk(original_term):
        stripped = _extract_preferred_chinese_form(original_term, refreshed_term)
        if stripped:
            return stripped
        if _looks_english_heavy(refreshed_term):
            return original_term
    return refreshed_term


def _repair_unfreshened_major_terms(
    repo_root: Path,
    skill: SkillDefinition,
    payload: dict[str, Any],
    *,
    verbose: bool,
) -> dict[str, Any]:
    repair_candidates = _collect_refresh_repair_candidates(payload)
    if not repair_candidates:
        return payload

    config = load_config_from_env(repo_root, skill=skill, route_role="final_deliverable")
    if verbose:
        print(
            f"[rewriting project] repairing mandatory refresh mappings route=final_deliverable model={config.model} "
            f"count={len(repair_candidates)}"
        )
    messages = [
        PromptMessage(
            role="system",
            content=(
                "你正在修复中文刷新圣经中『仍未真正刷新』的主要名词。"
                "默认必须把主要角色和主要专有名词改成新的中文规范名。"
                "禁止输出英文、拼音、或中英混合主名。"
                "只有确实必须保留原名时，才允许 preserve_original=true，并必须写 preserve_reason。"
                "返回且只返回 JSON。"
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "下面这些主要名词目前仍然没有完成真正的中文刷新，请逐项修复。\n"
                "要求：\n"
                "- 默认给出新的中文规范名，且与原名不同\n"
                "- 保持题材、阵营、身份、气质和记忆点\n"
                "- 不要英文化\n"
                "- 若确需保留原名，必须明确 preserve_original=true 与 preserve_reason\n\n"
                "返回 JSON schema:\n"
                "{\n"
                '  "repairs": [\n'
                '    {"category": "string", "index": 0, "refreshed_term": "string", "alternate_forms": ["string"], "preserve_original": false, "preserve_reason": "", "notes": "string"}\n'
                "  ]\n"
                "}\n\n"
                f"Candidates:\n{json.dumps(repair_candidates, ensure_ascii=False, indent=2)}"
            ),
        ),
    ]
    response = call_chat_completion(config, messages, json_mode=True)
    repaired_payload = parse_json_response(response)
    if not isinstance(repaired_payload, dict):
        return payload
    repairs = repaired_payload.get("repairs")
    if not isinstance(repairs, list):
        return payload
    _apply_refresh_repairs(payload, repairs)
    return payload


def _collect_refresh_repair_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    categories = {
        "characters": ("original_name", "refreshed_name"),
        "organizations_factions": ("original_term", "refreshed_term"),
        "world_terms": ("original_term", "refreshed_term"),
        "systems_contracts_powers": ("original_term", "refreshed_term"),
        "artifacts_props": ("original_term", "refreshed_term"),
        "locations": ("original_term", "refreshed_term"),
        "titles_ranks_labels": ("original_term", "refreshed_term"),
        "signature_terms": ("original_term", "refreshed_term"),
    }
    candidates: list[dict[str, Any]] = []
    for category, (original_key, refreshed_key) in categories.items():
        for index, item in enumerate(payload.get(category) or []):
            if not isinstance(item, dict):
                continue
            original_term = _clean_text(item.get(original_key))
            refreshed_term = _clean_text(item.get(refreshed_key))
            preserve_original = bool(item.get("preserve_original"))
            if not original_term or preserve_original:
                continue
            if refreshed_term == original_term or not refreshed_term:
                candidates.append(
                    {
                        "category": category,
                        "index": index,
                        "original_term": original_term,
                        "current_refreshed_term": refreshed_term or original_term,
                        "notes": _clean_text(item.get("notes")),
                    }
                )
    return candidates


def _apply_refresh_repairs(payload: dict[str, Any], repairs: list[Any]) -> None:
    for repair in repairs:
        if not isinstance(repair, dict):
            continue
        category = _clean_text(repair.get("category"))
        try:
            index = int(repair.get("index"))
        except Exception:  # noqa: BLE001
            continue
        items = payload.get(category)
        if not isinstance(items, list) or index < 0 or index >= len(items):
            continue
        item = items[index]
        if not isinstance(item, dict):
            continue
        refreshed_term = _clean_text(repair.get("refreshed_term"))
        alternate_forms = _normalize_string_list(repair.get("alternate_forms"))
        preserve_original = bool(repair.get("preserve_original"))
        preserve_reason = _clean_text(repair.get("preserve_reason"))
        notes = _clean_text(repair.get("notes"))
        if "original_name" in item:
            if refreshed_term:
                item["refreshed_name"] = refreshed_term
            item["aliases"] = _merge_string_lists_local(item.get("aliases"), alternate_forms)
        else:
            if refreshed_term:
                item["refreshed_term"] = refreshed_term
            item["alternate_forms"] = _merge_string_lists_local(item.get("alternate_forms"), alternate_forms)
        item["preserve_original"] = preserve_original
        if preserve_reason:
            item["preserve_reason"] = preserve_reason
        if notes:
            item["notes"] = notes


def _merge_string_lists_local(existing: Any, additions: list[str]) -> list[str]:
    return _normalize_string_list([*(_normalize_string_list(existing)), *additions])


def _extract_preferred_chinese_form(original_term: str, refreshed_term: str) -> str | None:
    if _contains_cjk(refreshed_term) and not _looks_like_hybrid_term(refreshed_term):
        return refreshed_term
    for candidate in re.findall(r"[一-龥A-Za-z0-9·]+", refreshed_term):
        if _contains_cjk(candidate):
            if candidate == original_term or not _looks_english_heavy(candidate):
                return candidate
    return None


def _clean_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _looks_english_heavy(value: str) -> bool:
    letters = sum(1 for char in value if char.isalpha() and char.isascii())
    cjk = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
    return letters > 0 and cjk == 0


def _looks_like_hybrid_term(value: str) -> bool:
    return _contains_cjk(value) and any(char.isalpha() and char.isascii() for char in value)
