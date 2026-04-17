from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.llm_client import call_chat_completion, describe_model_route, load_config_from_env, parse_json_response
from engine.models import PromptMessage
from engine.output_paths import resolve_story_title_from_path
from engine.writer import safe_stem


EPISODE_MARKER_RE = re.compile(r"^\s*第\s*(\d+)\s*集(?:\s*[：:].*)?\s*$")
SECTION_LABEL_RE = re.compile(r"^\s*(前置钩子|核心剧情|结尾悬念)\s*[：:]\s*(.*)$")
TIMESTAMPED_FOLDER_RE = re.compile(r"^(?P<title>.+?)__(?:\d{8}_\d{6}(?:_\d{2})?)$")
TERMINAL_PUNCTUATION_RE = re.compile(r"([。！？!?]+)$")
CLAUSE_SPLIT_RE = re.compile(r"[，,；;]")

SECTION_KEY_BY_LABEL = {
    "前置钩子": "hook",
    "核心剧情": "core",
    "结尾悬念": "cliffhanger",
}
SUSPENSE_TOKENS = ("到底", "究竟", "难道", "会不会", "能不能", "怎么", "为何", "偏偏", "竟然", "居然")
REVEAL_PREFIXES = ("但", "可", "却", "偏偏", "结果", "谁知", "没想到", "就在这时", "下一秒", "而", "直到")

ALLOWED_NARRATOR_GENDERS = ("female", "male")
ALLOWED_TONES = (
    "revengeful",
    "cold",
    "suspenseful",
    "tragic",
    "bitter",
    "triumphant",
    "high_energy_recap",
    "reflective",
)
ALLOWED_PACES = ("slow", "medium", "medium_fast", "fast")
ALLOWED_ENERGIES = ("low", "medium", "high")
ALLOWED_PRESET_VOICES = {
    "female": ("Vivian", "Serena"),
    "male": ("Dylan", "Uncle_Fu"),
}

DEFAULT_NARRATOR_GENDER = "female"
DEFAULT_TONE = "high_energy_recap"
DEFAULT_PACE = "medium_fast"
DEFAULT_ENERGY = "medium"
DEFAULT_PROMPT_TEXT = "中文剧情旁白，节奏明快，表达清晰，重点句更有力，不要拖沓，不要像普通朗读。"
PROMPT_PREFIX_BY_GENDER = {
    "female": "中文女旁白",
    "male": "中文男旁白",
}
PROMPT_TONE_FRAGMENT = {
    "revengeful": "带复仇感，语气冷狠",
    "cold": "语气冷静克制，压迫感明显",
    "suspenseful": "带悬念感，句尾略收",
    "tragic": "情绪沉痛，带悲剧感",
    "bitter": "带委屈和讽刺感",
    "triumphant": "带反击得势感",
    "high_energy_recap": "像高能剧情复盘，抓人",
    "reflective": "更内敛，更有回望感",
}
PROMPT_PACE_FRAGMENT = {
    "slow": "节奏偏慢",
    "medium": "节奏适中",
    "medium_fast": "节奏中快",
    "fast": "节奏偏快",
}
PROMPT_ENERGY_FRAGMENT = {
    "low": "力度克制",
    "medium": "重点句更有力",
    "high": "情绪推动更强",
}

ENUM_ALIASES = {
    "narrator_gender": {
        "female": "female",
        "woman": "female",
        "女": "female",
        "女声": "female",
        "male": "male",
        "man": "male",
        "男": "male",
        "男声": "male",
    },
    "tone": {
        "revengeful": "revengeful",
        "revenge": "revengeful",
        "sarcastic": "revengeful",
        "dramatic": "revengeful",
        "cold": "cold",
        "serious": "cold",
        "heavy": "cold",
        "suspenseful": "suspenseful",
        "suspense": "suspenseful",
        "tragic": "tragic",
        "bitter": "bitter",
        "triumphant": "triumphant",
        "high_energy_recap": "high_energy_recap",
        "high-energy_recap": "high_energy_recap",
        "high energy recap": "high_energy_recap",
        "energetic recap": "high_energy_recap",
        "reflective": "reflective",
    },
    "pace": {
        "slow": "slow",
        "medium": "medium",
        "medium_fast": "medium_fast",
        "medium-fast": "medium_fast",
        "medium fast": "medium_fast",
        "fast": "fast",
    },
    "energy": {
        "low": "low",
        "medium": "medium",
        "high": "high",
    },
}


@dataclass(frozen=True)
class EpisodeNarration:
    episode_number: int
    narration_text: str


@dataclass(frozen=True)
class EpisodeSections:
    hook: str
    core: str
    cliffhanger: str
    fallback: str


@dataclass(frozen=True)
class EpisodeNarrationAnalysis:
    narrator_gender: str
    tone: str
    pace: str
    energy: str
    tts_prompt: str
    selected_voice: str
    analysis_source: str


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
    del step_number, runtime_values, state

    series_title = derive_series_title(document.path)
    episodes = parse_recap_episodes(document.text)
    if not episodes:
        raise ValueError(
            "No episodes were detected. Expected episode markers like '第 1 集', '第 2 集', and '第 3 集'."
        )

    tts_python = resolve_tts_python_executable(repo_root)
    runner_script = resolve_tts_runner_script(repo_root)
    analysis_config, analysis_notes = initialize_episode_analysis(repo_root, skill)
    analysis_cache_dir = output_dir / "_analysis_cache"

    series_output_dir = output_dir
    temp_text_dir = output_dir / "temp"
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

        analysis = analyze_episode_narration(
            analysis_config=analysis_config,
            episode_text=episode.narration_text,
            cache_dir=analysis_cache_dir,
        )
        print(
            f"[episode {index}/{total}] analysis episode={episode.episode_number} "
            f"gender={analysis.narrator_gender} tone={analysis.tone} "
            f"pace={analysis.pace} energy={analysis.energy} "
            f"voice={analysis.selected_voice} source={analysis.analysis_source}"
        )
        print(f"[episode {index}/{total}] prompt_text={analysis.tts_prompt}")
        print(
            f"[episode {index}/{total}] generating narration for episode {episode.episode_number} "
            f"-> {output_filename}"
        )
        invoke_tts_runner(
            python_executable=tts_python,
            runner_script=runner_script,
            text_file=episode_text_path,
            output_path=output_path,
            voice=analysis.selected_voice,
            prompt_text=analysis.tts_prompt,
        )

        duration = format_duration_mmss(read_wav_duration_seconds(output_path))
        manifest_episodes.append(
            {
                "episode_number": episode.episode_number,
                "output_file": output_filename,
                "duration": duration,
                "status": "success",
                "selected_voice": analysis.selected_voice,
                "inferred_gender": analysis.narrator_gender,
                "inferred_tone": analysis.tone,
                "inferred_pace": analysis.pace,
                "inferred_energy": analysis.energy,
                "prompt_text": analysis.tts_prompt,
                "analysis_source": analysis.analysis_source,
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

    notes = [
        f"Parsed {len(episodes)} episode(s) from {document.path.name}.",
        f"Generated {len(manifest_episodes)} WAV file(s) under {series_output_dir}.",
        f"Wrote per-episode text files under {temp_text_dir}.",
        f"Qwen runner: {runner_script}",
    ]
    notes.extend(analysis_notes)

    return {
        "primary_output": manifest_path,
        "output_files": {
            "primary": manifest_path,
            "manifest": manifest_path,
            "series_output_dir": series_output_dir,
            "temp_episode_dir": temp_text_dir,
        },
        "notes": notes,
        "status": "completed",
    }


def derive_series_title(document_path: Path) -> str:
    story_title = resolve_story_title_from_path(document_path)
    if story_title:
        sanitized = safe_stem(story_title)
        if sanitized:
            return sanitized

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
        sections = parse_episode_sections("\n".join(block_lines))
        narration_text = polish_episode_narration(sections)
        if not narration_text:
            raise ValueError(
                f"Episode {episode_number} is empty after narration polishing."
            )
        episodes.append(EpisodeNarration(episode_number=episode_number, narration_text=narration_text))

    return episodes


def parse_episode_sections(block_text: str) -> EpisodeSections:
    buckets: dict[str, list[str]] = {
        "hook": [],
        "core": [],
        "cliffhanger": [],
        "fallback": [],
    }
    current_key = "fallback"

    for raw_line in block_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        label_match = SECTION_LABEL_RE.match(line)
        if label_match:
            current_key = SECTION_KEY_BY_LABEL[label_match.group(1)]
            line = label_match.group(2).strip()
            if not line:
                continue

        buckets[current_key].append(line)

    return EpisodeSections(
        hook=normalize_section_source("\n".join(buckets["hook"])),
        core=normalize_section_source("\n".join(buckets["core"])),
        cliffhanger=normalize_section_source("\n".join(buckets["cliffhanger"])),
        fallback=normalize_section_source("\n".join(buckets["fallback"])),
    )


def normalize_section_source(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\u3000", " ")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalized.strip()


def polish_episode_narration(sections: EpisodeSections) -> str:
    polished_parts: list[str] = []

    hook_text = polish_hook_text(sections.hook)
    if hook_text:
        polished_parts.append(hook_text)

    core_source = sections.core
    if not core_source and sections.fallback:
        core_source = sections.fallback
    core_text = polish_core_text(core_source)
    if core_text:
        polished_parts.append(core_text)

    cliffhanger_text = polish_cliffhanger_text(sections.cliffhanger)
    if cliffhanger_text:
        polished_parts.append(cliffhanger_text)

    return "\n".join(part for part in polished_parts if part).strip()


def polish_hook_text(text: str) -> str:
    return polish_section_text(text, threshold=18, force_short=True, suspense_bias=True)


def polish_core_text(text: str) -> str:
    return polish_section_text(text, threshold=28, force_short=False, suspense_bias=False)


def polish_cliffhanger_text(text: str) -> str:
    return polish_section_text(text, threshold=16, force_short=True, suspense_bias=True)


def polish_section_text(
    text: str,
    *,
    threshold: int,
    force_short: bool,
    suspense_bias: bool,
) -> str:
    source = normalize_section_source(text)
    if not source:
        return ""

    sentences = split_source_sentences(source)
    spoken_units: list[str] = []
    for sentence in sentences:
        spoken_units.extend(split_sentence_into_spoken_units(sentence, threshold=threshold, force_short=force_short))

    cleaned_units: list[str] = []
    for unit in spoken_units:
        cleaned_unit = cleanup_spoken_unit(unit)
        if cleaned_unit:
            cleaned_units.append(cleaned_unit)
    if not cleaned_units:
        return ""

    final_punctuation = choose_final_punctuation(source, suspense_bias=suspense_bias)
    rendered_lines: list[str] = []
    for index, unit in enumerate(cleaned_units):
        punctuation = final_punctuation if index == len(cleaned_units) - 1 else "。"
        rendered_lines.append(f"{unit}{punctuation}")
    return "".join(rendered_lines)


def split_source_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    current: list[str] = []
    quote_depth = 0
    for char in text:
        current.append(char)
        if char in "“\"":
            quote_depth += 1
            continue
        if char in "”\"":
            quote_depth = max(0, quote_depth - 1)
            continue
        if quote_depth == 0 and char in "。！？!?；;":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return sentences or ([text.strip()] if text.strip() else [])


def split_sentence_into_spoken_units(sentence: str, *, threshold: int, force_short: bool) -> list[str]:
    stripped = sentence.strip()
    if not stripped:
        return []

    core_text = TERMINAL_PUNCTUATION_RE.sub("", stripped).strip()
    if not core_text:
        return []
    if any(marker in core_text for marker in ("“", "”", "\"")):
        return [core_text]

    clauses = [part.strip() for part in CLAUSE_SPLIT_RE.split(core_text) if part.strip()]
    if len(clauses) <= 1 and len(core_text) <= threshold + 6:
        return [core_text]

    units: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for clause in clauses:
        clause_length = len(clause)
        should_break = bool(
            current_parts
            and (
                current_length + clause_length > threshold
                or (force_short and current_length >= max(10, (threshold * 3) // 4))
                or clause.startswith(REVEAL_PREFIXES)
            )
        )
        if should_break:
            units.append("，".join(current_parts))
            current_parts = [clause]
            current_length = clause_length
            continue

        current_parts.append(clause)
        current_length += clause_length

    if current_parts:
        units.append("，".join(current_parts))

    return units


def cleanup_spoken_unit(text: str) -> str:
    cleaned = text.strip(" ，,；;。！？!?")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"([，,]){2,}", "，", cleaned)
    cleaned = re.sub(r"(。){2,}", "。", cleaned)
    return cleaned.strip()


def choose_final_punctuation(text: str, *, suspense_bias: bool) -> str:
    stripped = text.strip().rstrip("”\"' ")
    if stripped.endswith(("？", "?")):
        return "？"
    if stripped.endswith(("！", "!")):
        return "！"
    if suspense_bias and any(token in text for token in SUSPENSE_TOKENS):
        return "？"
    return "。"


def initialize_episode_analysis(repo_root: Path, skill) -> tuple[Any | None, list[str]]:
    try:
        config = load_config_from_env(repo_root, skill=skill, route_role="step_execution")
    except Exception as exc:  # noqa: BLE001
        note = (
            "Narration analysis fallback only: "
            f"{str(exc).strip() or exc.__class__.__name__}"
        )
        print(f"[recap_to_tts] {note}")
        return None, [note]

    route_description = describe_model_route(repo_root, skill=skill, route_role="step_execution")
    note = f"Narration analysis route: {route_description}"
    print(f"[recap_to_tts] {note}")
    return config, [note]


def analyze_episode_narration(
    *,
    analysis_config: Any | None,
    episode_text: str,
    cache_dir: Path | None = None,
) -> EpisodeNarrationAnalysis:
    cache_path = resolve_analysis_cache_path(cache_dir, episode_text)
    cached_analysis = load_cached_episode_analysis(cache_path)
    if cached_analysis is not None:
        return cached_analysis

    if analysis_config is None:
        return build_fallback_episode_analysis()

    messages = build_episode_analysis_messages(episode_text)
    try:
        response = call_chat_completion(
            analysis_config,
            messages,
            json_mode=True,
            temperature=0.0,
        )
        payload = parse_json_response(response)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        print(f"[recap_to_tts] narration analysis failed; using fallback defaults. {detail}")
        return build_fallback_episode_analysis()

    analysis = validate_episode_analysis_payload(payload)
    write_cached_episode_analysis(cache_path, analysis)
    return analysis


def build_episode_analysis_messages(episode_text: str) -> list[PromptMessage]:
    schema = {
        "narrator_gender": "female|male",
        "tone": list(ALLOWED_TONES),
        "pace": list(ALLOWED_PACES),
        "energy": list(ALLOWED_ENERGIES),
        "tts_prompt": "简短中文字符串",
    }
    return [
        PromptMessage(
            role="system",
            content=(
                "你是 ONE4ALL recap_to_tts 的分集旁白分析器。"
                "你要为整集旁白选择单一 narrator voice 偏好。"
                "只考虑整集旁白，不做角色分声线，不做多角色切换。"
                "返回且只返回一个 JSON 对象。"
                "必须严格从给定枚举中选择 narrator_gender、tone、pace、energy。"
                "不要输出 voice 名称，不要输出解释。"
                "tts_prompt 必须是简短中文，适合 Qwen TTS custom_voice instruct，"
                "聚焦语气、节奏、力度，不要堆砌形容词，不要像写说明文。"
            ),
        ),
        PromptMessage(
            role="user",
            content=(
                "请阅读下面这段中文剧情旁白，并返回最适合这一整集旁白的稳定配置。\n"
                "如果拿不准，也必须从枚举中选最接近的一项。\n\n"
                f"JSON schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                f"Episode narration:\n{episode_text}"
            ),
        ),
    ]


def validate_episode_analysis_payload(payload: dict[str, object]) -> EpisodeNarrationAnalysis:
    narrator_gender, gender_used_fallback = normalize_enum_value(
        payload.get("narrator_gender"),
        allowed_values=ALLOWED_NARRATOR_GENDERS,
        alias_map=ENUM_ALIASES["narrator_gender"],
        default_value=DEFAULT_NARRATOR_GENDER,
    )
    tone, tone_used_fallback = normalize_enum_value(
        payload.get("tone"),
        allowed_values=ALLOWED_TONES,
        alias_map=ENUM_ALIASES["tone"],
        default_value=DEFAULT_TONE,
    )
    pace, pace_used_fallback = normalize_enum_value(
        payload.get("pace"),
        allowed_values=ALLOWED_PACES,
        alias_map=ENUM_ALIASES["pace"],
        default_value=DEFAULT_PACE,
    )
    energy, energy_used_fallback = normalize_enum_value(
        payload.get("energy"),
        allowed_values=ALLOWED_ENERGIES,
        alias_map=ENUM_ALIASES["energy"],
        default_value=DEFAULT_ENERGY,
    )
    llm_prompt_text = sanitize_tts_prompt_text(payload.get("tts_prompt"))
    prompt_used_fallback = not bool(llm_prompt_text)
    if prompt_used_fallback:
        prompt_text = DEFAULT_PROMPT_TEXT
    else:
        prompt_text = build_stable_tts_prompt(
            narrator_gender=narrator_gender,
            tone=tone,
            pace=pace,
            energy=energy,
        )
    selected_voice = select_preset_voice(
        narrator_gender=narrator_gender,
        tone=tone,
        pace=pace,
        energy=energy,
    )
    analysis_source = (
        "llm"
        if not any((gender_used_fallback, tone_used_fallback, pace_used_fallback, energy_used_fallback, prompt_used_fallback))
        else "llm_with_fallback"
    )
    return EpisodeNarrationAnalysis(
        narrator_gender=narrator_gender,
        tone=tone,
        pace=pace,
        energy=energy,
        tts_prompt=prompt_text,
        selected_voice=selected_voice,
        analysis_source=analysis_source,
    )


def normalize_enum_value(
    value: object,
    *,
    allowed_values: tuple[str, ...],
    alias_map: dict[str, str],
    default_value: str,
) -> tuple[str, bool]:
    if isinstance(value, str):
        cleaned = value.strip().casefold().replace("-", "_")
        cleaned = re.sub(r"\s+", "_", cleaned)
        resolved = alias_map.get(cleaned, cleaned)
        if resolved in allowed_values:
            return resolved, False
    return default_value, True


def sanitize_tts_prompt_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.replace("\r\n", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = cleaned.strip("，,；;。！？!? ")
    if not cleaned:
        return ""
    if not any("\u4e00" <= char <= "\u9fff" for char in cleaned):
        return ""
    if len(cleaned) > 64:
        return ""
    return f"{cleaned}。"


def build_stable_tts_prompt(*, narrator_gender: str, tone: str, pace: str, energy: str) -> str:
    prefix = PROMPT_PREFIX_BY_GENDER.get(narrator_gender, "中文剧情旁白")
    tone_fragment = PROMPT_TONE_FRAGMENT.get(tone, "表达清晰")
    pace_fragment = PROMPT_PACE_FRAGMENT.get(pace, "节奏明快")
    energy_fragment = PROMPT_ENERGY_FRAGMENT.get(energy, "重点句更有力")
    return (
        f"{prefix}，{tone_fragment}，{pace_fragment}，{energy_fragment}，"
        "表达清晰，不要拖沓，不要像普通朗读。"
    )


def select_preset_voice(*, narrator_gender: str, tone: str, pace: str, energy: str) -> str:
    if narrator_gender == "female":
        if tone in {"tragic", "reflective"}:
            return "Serena"
        return "Vivian"

    if tone == "cold":
        return "Uncle_Fu"
    if tone in {"tragic", "reflective"} and pace in {"slow", "medium"} and energy in {"low", "medium"}:
        return "Uncle_Fu"
    return "Dylan"


def build_fallback_episode_analysis() -> EpisodeNarrationAnalysis:
    narrator_gender = DEFAULT_NARRATOR_GENDER
    tone = DEFAULT_TONE
    pace = DEFAULT_PACE
    energy = DEFAULT_ENERGY
    return EpisodeNarrationAnalysis(
        narrator_gender=narrator_gender,
        tone=tone,
        pace=pace,
        energy=energy,
        tts_prompt=DEFAULT_PROMPT_TEXT,
        selected_voice=select_preset_voice(
            narrator_gender=narrator_gender,
            tone=tone,
            pace=pace,
            energy=energy,
        ),
        analysis_source="fallback",
    )


def resolve_analysis_cache_path(cache_dir: Path | None, episode_text: str) -> Path | None:
    if cache_dir is None:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(episode_text.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def load_cached_episode_analysis(cache_path: Path | None) -> EpisodeNarrationAnalysis | None:
    if cache_path is None or not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None

    narrator_gender = str(payload.get("narrator_gender") or "").strip()
    tone = str(payload.get("tone") or "").strip()
    pace = str(payload.get("pace") or "").strip()
    energy = str(payload.get("energy") or "").strip()
    tts_prompt = str(payload.get("tts_prompt") or "").strip()
    selected_voice = str(payload.get("selected_voice") or "").strip()
    if narrator_gender not in ALLOWED_NARRATOR_GENDERS:
        return None
    if tone not in ALLOWED_TONES:
        return None
    if pace not in ALLOWED_PACES:
        return None
    if energy not in ALLOWED_ENERGIES:
        return None
    if selected_voice != select_preset_voice(
        narrator_gender=narrator_gender,
        tone=tone,
        pace=pace,
        energy=energy,
    ):
        return None
    if not tts_prompt:
        return None
    source = str(payload.get("analysis_source") or "llm").strip() or "llm"
    return EpisodeNarrationAnalysis(
        narrator_gender=narrator_gender,
        tone=tone,
        pace=pace,
        energy=energy,
        tts_prompt=tts_prompt,
        selected_voice=selected_voice,
        analysis_source=f"cached_{source}",
    )


def write_cached_episode_analysis(cache_path: Path | None, analysis: EpisodeNarrationAnalysis) -> None:
    if cache_path is None or not analysis.analysis_source.startswith("llm"):
        return
    payload = {
        "narrator_gender": analysis.narrator_gender,
        "tone": analysis.tone,
        "pace": analysis.pace,
        "energy": analysis.energy,
        "tts_prompt": analysis.tts_prompt,
        "selected_voice": analysis.selected_voice,
        "analysis_source": analysis.analysis_source,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    voice: str,
    prompt_text: str,
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
        voice,
        "--prompt_text",
        prompt_text,
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
