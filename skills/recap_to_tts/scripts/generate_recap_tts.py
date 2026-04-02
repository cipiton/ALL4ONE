from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.writer import safe_stem


EPISODE_MARKER_RE = re.compile(r"^\s*第\s*(\d+)\s*集(?:\s*[：:].*)?\s*$")
SECTION_LABEL_RE = re.compile(r"^\s*(前置钩子|核心剧情|结尾悬念)\s*[：:]\s*(.*)$")
TIMESTAMPED_FOLDER_RE = re.compile(r"^(?P<title>.+?)__(?:\d{8}_\d{6}(?:_\d{2})?)$")


@dataclass(frozen=True)
class EpisodeNarration:
    episode_number: int
    narration_text: str


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
    del skill, step_number, runtime_values, state

    series_title = derive_series_title(document.path)
    episodes = parse_recap_episodes(document.text)
    if not episodes:
        raise ValueError(
            "No episodes were detected. Expected episode markers like '第 1 集', '第 2 集', and '第 3 集'."
        )

    tts_python = resolve_tts_python_executable(repo_root)
    runner_script = resolve_tts_runner_script(repo_root)

    series_output_dir = output_dir / series_title
    temp_text_dir = output_dir / "temp" / series_title
    series_output_dir.mkdir(parents=True, exist_ok=True)
    temp_text_dir.mkdir(parents=True, exist_ok=True)

    manifest_episodes: list[dict[str, Any]] = []
    total = len(episodes)

    for index, episode in enumerate(episodes, start=1):
        episode_tag = f"ep{episode.episode_number:02d}"
        output_filename = f"{series_title}_{episode_tag}.wav"
        output_path = series_output_dir / output_filename
        episode_text_path = temp_text_dir / f"{series_title}_{episode_tag}.txt"
        episode_text_path.write_text(episode.narration_text.rstrip() + "\n", encoding="utf-8")

        print(
            f"[episode {index}/{total}] generating narration for episode {episode.episode_number} "
            f"-> {output_filename}"
        )
        invoke_tts_runner(
            python_executable=tts_python,
            runner_script=runner_script,
            text_file=episode_text_path,
            output_path=output_path,
        )

        duration = format_duration_mmss(read_wav_duration_seconds(output_path))
        manifest_episodes.append(
            {
                "episode_number": episode.episode_number,
                "output_file": output_filename,
                "duration": duration,
                "status": "success",
            }
        )

    manifest_payload = {
        "series_title": series_title,
        "source_file": document.path.name,
        "episodes": manifest_episodes,
    }
    manifest_path = series_output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "primary_output": manifest_path,
        "output_files": {
            "primary": manifest_path,
            "manifest": manifest_path,
            "series_output_dir": series_output_dir,
            "temp_episode_dir": temp_text_dir,
        },
        "notes": [
            f"Parsed {len(episodes)} episode(s) from {document.path.name}.",
            f"Generated {len(manifest_episodes)} WAV file(s) under {series_output_dir.name}/.",
            f"Wrote per-episode text files under temp/{series_title}/.",
            f"Qwen runner: {runner_script}",
        ],
        "status": "completed",
    }


def derive_series_title(document_path: Path) -> str:
    parent_name = document_path.parent.name.strip()
    if parent_name:
        match = TIMESTAMPED_FOLDER_RE.match(parent_name)
        if match:
            candidate = match.group("title").strip()
            sanitized = safe_stem(candidate)
            if sanitized:
                return sanitized

    fallback = safe_stem(document_path.stem)
    if fallback:
        return fallback
    raise ValueError(f"Could not derive a valid series title from input path: {document_path}")


def parse_recap_episodes(text: str) -> list[EpisodeNarration]:
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    markers: list[tuple[int, int]] = []
    seen_episode_numbers: set[int] = set()

    for line_index, line in enumerate(lines):
        match = EPISODE_MARKER_RE.match(line.strip())
        if not match:
            continue
        episode_number = int(match.group(1))
        if episode_number in seen_episode_numbers:
            raise ValueError(f"Duplicate episode marker detected: 第 {episode_number} 集")
        seen_episode_numbers.add(episode_number)
        markers.append((episode_number, line_index))

    episodes: list[EpisodeNarration] = []
    for index, (episode_number, line_index) in enumerate(markers):
        next_line_index = markers[index + 1][1] if index + 1 < len(markers) else len(lines)
        block_lines = lines[line_index + 1 : next_line_index]
        narration_text = clean_episode_block("\n".join(block_lines))
        if not narration_text:
            raise ValueError(
                f"Episode {episode_number} is empty after removing narration labels and blank lines."
            )
        episodes.append(EpisodeNarration(episode_number=episode_number, narration_text=narration_text))

    return episodes


def clean_episode_block(block_text: str) -> str:
    cleaned_lines: list[str] = []
    previous_blank = True

    for raw_line in block_text.split("\n"):
        line = raw_line.strip()
        if not line:
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue

        label_match = SECTION_LABEL_RE.match(line)
        if label_match:
            line = label_match.group(2).strip()
            if not line:
                previous_blank = True
                continue

        cleaned_lines.append(line)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def resolve_tts_root(repo_root: Path) -> Path:
    tts_root = (repo_root / "TTS_qwen").resolve()
    if not tts_root.exists():
        raise RuntimeError(f"TTS_qwen workspace not found: {tts_root}")
    return tts_root


def resolve_tts_python_executable(repo_root: Path) -> Path:
    override = os.environ.get("ONE4ALL_QWEN_TTS_PYTHON", "").strip()
    if override:
        python_path = Path(override).expanduser().resolve()
        if not python_path.exists():
            raise RuntimeError(f"ONE4ALL_QWEN_TTS_PYTHON does not exist: {python_path}")
        return python_path

    tts_root = resolve_tts_root(repo_root)
    candidates = [
        tts_root / ".venv" / "Scripts" / "python.exe",
        tts_root / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise RuntimeError(
        "Could not find the isolated Qwen TTS Python executable. Expected "
        f"`{tts_root}\\.venv\\Scripts\\python.exe` or set ONE4ALL_QWEN_TTS_PYTHON explicitly."
    )


def resolve_tts_runner_script(repo_root: Path) -> Path:
    override = os.environ.get("ONE4ALL_QWEN_TTS_RUNNER", "").strip()
    if override:
        runner_path = Path(override).expanduser().resolve()
        if not runner_path.exists():
            raise RuntimeError(f"ONE4ALL_QWEN_TTS_RUNNER does not exist: {runner_path}")
        return runner_path

    runner_path = resolve_tts_root(repo_root) / "tts_runner.py"
    if not runner_path.exists():
        raise RuntimeError(f"Qwen TTS runner not found: {runner_path}")
    return runner_path.resolve()


def invoke_tts_runner(
    *,
    python_executable: Path,
    runner_script: Path,
    text_file: Path,
    output_path: Path,
) -> None:
    command = [
        str(python_executable),
        str(runner_script),
        "--text-file",
        str(text_file),
        "--output",
        str(output_path),
        "--mode",
        "custom_voice",
        "--voice",
        "Ryan",
    ]
    completed = subprocess.run(
        command,
        cwd=str(runner_script.parent),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stdout:
        print(stdout)
    if completed.returncode != 0:
        if stderr:
            print(stderr, file=sys.stderr)
        detail_parts = []
        if stdout:
            detail_parts.append(f"stdout: {stdout}")
        if stderr:
            detail_parts.append(f"stderr: {stderr}")
        detail = " | ".join(detail_parts) if detail_parts else "no subprocess output"
        raise RuntimeError(
            f"Qwen TTS generation failed for {output_path.name} (exit code {completed.returncode}). {detail}"
        )

    if not output_path.exists():
        raise RuntimeError(f"Qwen TTS runner completed but did not create the WAV file: {output_path}")


def read_wav_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            frame_rate = wav_file.getframerate()
    except (wave.Error, OSError) as exc:
        raise RuntimeError(f"Could not read WAV duration from {path}") from exc

    if frame_rate <= 0:
        raise RuntimeError(f"Invalid WAV frame rate in {path}")
    return frame_count / frame_rate


def format_duration_mmss(duration_seconds: float) -> str:
    total_seconds = max(0, int(round(duration_seconds)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
