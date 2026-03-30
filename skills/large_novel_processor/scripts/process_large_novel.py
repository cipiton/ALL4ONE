from __future__ import annotations

import re
from pathlib import Path
from typing import Any


CHAPTER_HEADING_RE = re.compile(
    r"^(?P<title>(?:第[0-9零一二三四五六七八九十百千万两〇○OＯ]+[章节回卷篇部集]|"
    r"序章|楔子|引子|前言|后记|尾声|终章|最终章|大结局|番外|番外篇|Chapter\s+\d+)"
    r"[^\n]{0,40})\s*$",
    flags=re.IGNORECASE,
)
NUMERIC_CHAPTER_HEADING_RE = re.compile(r"^\s*(\d{1,4})\s*$")


def run(
    *,
    repo_root: Path,
    skill,
    document,
    output_dir: Path,
    step_number: int,
    runtime_values: dict[str, Any],
    state,
) -> dict[str, Any]:
    del repo_root, skill, step_number, state

    split_mode = str(runtime_values.get("split_mode") or "chapter").strip().lower()
    if split_mode not in {"chapter", "chunk"}:
        raise ValueError(f"Unsupported split mode: {split_mode}")

    chunk_size = int(runtime_values.get("chunk_size") or 20)
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    chapters, preface = split_into_chapters(document.text)
    if not chapters:
        raise ValueError(
            "No chapter headings were detected. Accepted formats include headings like '第1章', 'Chapter 1', or standalone numeric chapter lines such as '1', '2', or '001'."
        )

    if preface:
        chapters[0]["text"] = f"{preface.rstrip()}\n\n{chapters[0]['text']}".strip()

    if split_mode == "chapter":
        generated_dir = output_dir / "chapters"
        generated = write_chapter_files(generated_dir, chapters)
    else:
        generated_dir = output_dir / "chunks"
        generated = write_chunk_files(generated_dir, chapters, chunk_size=chunk_size)

    index_path = write_index(
        output_dir / "index.txt",
        input_name=document.path.name,
        split_mode=split_mode,
        chunk_size=chunk_size,
        chapters=chapters,
        generated=generated,
        generated_dir=generated_dir,
        preface_merged=bool(preface),
    )

    return {
        "primary_output": index_path,
        "output_files": {
            "primary": index_path,
            "index": index_path,
            "prepared_content_dir": generated_dir,
        },
        "notes": [
            f"Detected {len(chapters)} chapter heading(s).",
            f"Prepared {len(generated)} file(s) in {generated_dir.name}/ using {split_mode} mode.",
        ],
        "status": "completed",
    }


def split_into_chapters(text: str) -> tuple[list[dict[str, Any]], str]:
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    markers: list[dict[str, Any]] = []
    numeric_candidates: list[dict[str, Any]] = []
    offset = 0

    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if is_explicit_chapter_heading(stripped):
            markers.append(
                {
                    "line_index": line_index,
                    "offset": offset,
                    "title": stripped,
                }
            )
        elif is_numeric_heading_candidate(stripped):
            numeric_candidates.append(
                {
                    "line_index": line_index,
                    "offset": offset,
                    "title": stripped,
                    "value": int(stripped),
                }
            )
        offset += len(line) + 1

    if not markers and is_numeric_heading_pattern(numeric_candidates):
        markers = [
            {
                "line_index": candidate["line_index"],
                "offset": candidate["offset"],
                "title": candidate["title"],
            }
            for candidate in numeric_candidates
        ]

    if not markers:
        return [], ""

    chapters: list[dict[str, Any]] = []
    for index, marker in enumerate(markers, start=1):
        start_offset = marker["offset"]
        end_offset = markers[index]["offset"] if index < len(markers) else len(normalized)
        chapter_text = normalized[start_offset:end_offset].strip()
        chapters.append(
            {
                "number": index,
                "title": marker["title"],
                "text": chapter_text,
            }
        )

    first_offset = markers[0]["offset"]
    preface = normalized[:first_offset].strip()
    return chapters, preface


def is_explicit_chapter_heading(value: str) -> bool:
    if not value:
        return False
    if len(value) > 48:
        return False
    return bool(CHAPTER_HEADING_RE.match(value))


def is_numeric_heading_candidate(value: str) -> bool:
    if not value:
        return False
    if len(value.strip()) > 4:
        return False
    return bool(NUMERIC_CHAPTER_HEADING_RE.match(value))


def is_numeric_heading_pattern(candidates: list[dict[str, Any]]) -> bool:
    if len(candidates) < 3:
        return False

    values = [int(candidate["value"]) for candidate in candidates]
    line_indexes = [int(candidate["line_index"]) for candidate in candidates]

    increasing_pairs = sum(1 for previous, current in zip(values, values[1:]) if current > previous)
    consecutive_pairs = sum(1 for previous, current in zip(values, values[1:]) if current == previous + 1)
    spaced_pairs = sum(1 for previous, current in zip(line_indexes, line_indexes[1:]) if current - previous >= 3)

    total_pairs = len(candidates) - 1
    if total_pairs <= 0:
        return False

    # Require a repeated standalone numeric pattern that behaves like chapter numbering,
    # instead of isolated paragraph numbers or numbered list fragments.
    return (
        increasing_pairs >= max(2, total_pairs - 1)
        and consecutive_pairs >= max(2, total_pairs // 2)
        and spaced_pairs >= max(2, total_pairs // 2)
    )


def write_chapter_files(output_dir: Path, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []
    for chapter in chapters:
        filename = f"{chapter['number']:03d}_{slugify(chapter['title'])}.txt"
        path = output_dir / filename
        path.write_text(chapter["text"].strip() + "\n", encoding="utf-8")
        generated.append(
            {
                "type": "chapter",
                "file": path,
                "chapter_start": chapter["number"],
                "chapter_end": chapter["number"],
                "title": chapter["title"],
            }
        )
    return generated


def write_chunk_files(
    output_dir: Path,
    chapters: list[dict[str, Any]],
    *,
    chunk_size: int,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict[str, Any]] = []

    for chunk_index, start in enumerate(range(0, len(chapters), chunk_size), start=1):
        group = chapters[start : start + chunk_size]
        start_number = group[0]["number"]
        end_number = group[-1]["number"]
        filename = f"{chunk_index:03d}_chapters_{start_number:03d}-{end_number:03d}.txt"
        path = output_dir / filename
        combined_text = "\n\n".join(chapter["text"].strip() for chapter in group if chapter["text"].strip())
        path.write_text(combined_text.rstrip() + "\n", encoding="utf-8")
        generated.append(
            {
                "type": "chunk",
                "file": path,
                "chapter_start": start_number,
                "chapter_end": end_number,
                "titles": [chapter["title"] for chapter in group],
            }
        )
    return generated


def write_index(
    path: Path,
    *,
    input_name: str,
    split_mode: str,
    chunk_size: int,
    chapters: list[dict[str, Any]],
    generated: list[dict[str, Any]],
    generated_dir: Path,
    preface_merged: bool,
) -> Path:
    lines = [
        "Large Novel Processor",
        f"Input file: {input_name}",
        f"Split mode: {split_mode}",
        f"Chunk size: {chunk_size}",
        f"Detected chapters: {len(chapters)}",
        f"Generated directory: {generated_dir.name}",
        f"Preface merged into first chapter: {'yes' if preface_merged else 'no'}",
        "",
        "[Detected Chapters]",
    ]

    for chapter in chapters:
        lines.append(f"{chapter['number']:03d}. {chapter['title']}")

    lines.extend(["", "[Generated Files]"])
    for item in generated:
        if item["type"] == "chapter":
            lines.append(
                f"{item['chapter_start']:03d}. {Path(item['file']).relative_to(path.parent)} | {item['title']}"
            )
            continue
        title_start = item["titles"][0]
        title_end = item["titles"][-1]
        lines.append(
            f"{Path(item['file']).relative_to(path.parent)} | chapters {item['chapter_start']:03d}-{item['chapter_end']:03d} | {title_start} -> {title_end}"
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value.strip())
    cleaned = cleaned.strip("._") or "chapter"
    return cleaned[:80]
