from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TOTAL_EPISODE_PATTERNS = (
    re.compile(r"^\|\s*合计\s*\|[^|\n]*\|\s*(\d{1,4})\s*\|", re.MULTILINE),
    re.compile(r"总集数[：:]\s*(\d{1,4})\s*集"),
    re.compile(r"总集数（默认(\d{1,4})集）"),
)
EPISODE_ROW_PATTERN = re.compile(r"^\|\s*(\d{1,4})\s*\|", re.MULTILINE)
EPISODE_RANGE_PATTERN = re.compile(r"^\s*(\d{1,4})(?:\s*-\s*(\d{1,4}))?\s*$")
SESSION_NAME_PATTERN = re.compile(r"^(?P<prefix>.+?)__\d{8}_\d{6}(?:_\d{2})?$")
EPISODE_FILENAME_PATTERN = re.compile(
    r"^(?P<kind>episode|episodes)_(?P<start>\d{2,4})(?:_(?P<end>\d{2,4}))?(?P<regen>_regen)?\.txt$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class EpisodeSelection:
    total_episodes: int
    episodes: list[int]

    @property
    def is_full_range(self) -> bool:
        return self.episodes == list(range(1, self.total_episodes + 1))

    @property
    def is_contiguous(self) -> bool:
        if not self.episodes:
            return False
        return self.episodes == list(range(self.start_episode, self.end_episode + 1))

    @property
    def start_episode(self) -> int:
        return self.episodes[0]

    @property
    def end_episode(self) -> int:
        return self.episodes[-1]


@dataclass(slots=True)
class EpisodeFileReference:
    path: Path
    start_episode: int
    end_episode: int
    is_regeneration: bool

    @property
    def span_size(self) -> int:
        return self.end_episode - self.start_episode + 1


def infer_total_planned_episodes(text: str) -> int | None:
    for pattern in TOTAL_EPISODE_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1))

    episode_numbers = [int(match.group(1)) for match in EPISODE_ROW_PATTERN.finditer(text)]
    if episode_numbers:
        return max(episode_numbers)
    return None


def parse_episode_selection(
    raw_value: str | None,
    total_episodes: int,
    *,
    allow_blank_all: bool = True,
) -> EpisodeSelection:
    normalized = (raw_value or "").strip().lower()
    if normalized in {"", "all"}:
        if not allow_blank_all and normalized == "":
            raise ValueError(
                "Select specific episodes for regeneration, for example '15', '15-16', or '15,18,22'."
            )
        return EpisodeSelection(total_episodes=total_episodes, episodes=list(range(1, total_episodes + 1)))

    episode_numbers: set[int] = set()
    for token in (item.strip() for item in normalized.split(",")):
        if not token:
            continue
        match = EPISODE_RANGE_PATTERN.match(token)
        if not match:
            raise ValueError(
                "Enter blank, 'all', a single episode like '60', a range like '1-10', "
                "or a comma list like '15,18,22'."
            )

        start_episode = int(match.group(1))
        end_episode = int(match.group(2) or match.group(1))
        if start_episode < 1 or end_episode < 1:
            raise ValueError("Episode numbers must be >= 1.")
        if start_episode > end_episode:
            raise ValueError("Episode range start must be <= end.")
        if end_episode > total_episodes:
            raise ValueError(f"Requested episodes exceed the detected total of {total_episodes}.")
        episode_numbers.update(range(start_episode, end_episode + 1))

    if not episode_numbers:
        raise ValueError("Select at least one episode.")

    return EpisodeSelection(total_episodes=total_episodes, episodes=sorted(episode_numbers))


def build_episode_batches(
    selection: EpisodeSelection,
    episodes_per_file: int,
    *,
    preserve_exact_selection: bool = False,
) -> list[tuple[int, int]]:
    batches: list[tuple[int, int]] = []
    for span_start, span_end in compress_episode_ranges(selection.episodes):
        if preserve_exact_selection:
            batches.append((span_start, span_end))
            continue
        current_start = span_start
        while current_start <= span_end:
            current_end = min(span_end, current_start + episodes_per_file - 1)
            batches.append((current_start, current_end))
            current_start = current_end + 1
    return batches


def format_episode_range(start_episode: int, end_episode: int, *, total_episodes: int) -> str:
    width = max(2, len(str(total_episodes)))
    if start_episode == end_episode:
        return f"{start_episode:0{width}d}"
    return f"{start_episode:0{width}d}-{end_episode:0{width}d}"


def format_episode_selection(selection: EpisodeSelection) -> str:
    if selection.is_full_range:
        return "all"
    width = max(2, len(str(selection.total_episodes)))
    ranges = compress_episode_ranges(selection.episodes)
    rendered: list[str] = []
    for start_episode, end_episode in ranges:
        if start_episode == end_episode:
            rendered.append(f"{start_episode:0{width}d}")
        else:
            rendered.append(f"{start_episode:0{width}d}-{end_episode:0{width}d}")
    return ",".join(rendered)


def format_batch_filename(
    start_episode: int,
    end_episode: int,
    *,
    total_episodes: int,
    regeneration: bool = False,
) -> str:
    width = max(2, len(str(total_episodes)))
    suffix = "_regen" if regeneration else ""
    if start_episode == end_episode:
        return f"episode_{start_episode:0{width}d}{suffix}.txt"
    return f"episodes_{start_episode:0{width}d}_{end_episode:0{width}d}{suffix}.txt"


def compress_episode_ranges(episodes: Iterable[int]) -> list[tuple[int, int]]:
    ordered = sorted(dict.fromkeys(int(value) for value in episodes))
    if not ordered:
        return []

    ranges: list[tuple[int, int]] = []
    start_episode = ordered[0]
    previous_episode = ordered[0]
    for episode in ordered[1:]:
        if episode == previous_episode + 1:
            previous_episode = episode
            continue
        ranges.append((start_episode, previous_episode))
        start_episode = episode
        previous_episode = episode
    ranges.append((start_episode, previous_episode))
    return ranges


def collect_regeneration_context(
    session_dir: Path,
    *,
    total_episodes: int,
    target_episodes: Iterable[int],
    max_chars_per_reference: int = 4_000,
) -> dict[str, str]:
    selected = sorted(dict.fromkeys(int(value) for value in target_episodes))
    if not selected:
        return {}

    references = _find_prior_episode_references(session_dir)
    if not references:
        return {}

    selected_blocks = _collect_reference_blocks(
        references,
        selected,
        total_episodes=total_episodes,
        max_chars_per_reference=max_chars_per_reference,
    )

    neighbor_candidates: list[int] = []
    for episode in selected:
        if episode > 1:
            neighbor_candidates.append(episode - 1)
        if episode < total_episodes:
            neighbor_candidates.append(episode + 1)

    neighboring_blocks = _collect_reference_blocks(
        references,
        neighbor_candidates,
        total_episodes=total_episodes,
        max_chars_per_reference=max_chars_per_reference,
        exclude_paths={path for path, _ in selected_blocks},
    )

    payload: dict[str, str] = {}
    if selected_blocks:
        payload["existing_episode_reference"] = "\n\n".join(text for _, text in selected_blocks)
    if neighboring_blocks:
        payload["neighboring_episode_context"] = "\n\n".join(text for _, text in neighboring_blocks)
    if payload:
        payload["consistency_policy"] = (
            "Preserve series continuity with the adaptation plan, the character bible, any prior episode drafts, "
            "and the neighboring episode references below unless the regeneration instruction explicitly changes them."
        )
    return payload


def _find_prior_episode_references(session_dir: Path) -> list[EpisodeFileReference]:
    skill_root = session_dir.parent
    prefix = _extract_session_prefix(session_dir.name)
    candidates: list[Path] = []
    for candidate in skill_root.iterdir():
        if not candidate.is_dir() or candidate == session_dir:
            continue
        if prefix and _extract_session_prefix(candidate.name) != prefix:
            continue
        candidates.append(candidate)

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    references: list[EpisodeFileReference] = []
    for candidate in candidates:
        for file_path in candidate.rglob("*.txt"):
            parsed = _parse_episode_output_filename(file_path.name)
            if parsed is None:
                continue
            start_episode, end_episode, is_regeneration = parsed
            references.append(
                EpisodeFileReference(
                    path=file_path,
                    start_episode=start_episode,
                    end_episode=end_episode,
                    is_regeneration=is_regeneration,
                )
            )
    return references


def _extract_session_prefix(session_name: str) -> str:
    match = SESSION_NAME_PATTERN.match(session_name)
    if match:
        return match.group("prefix")
    return ""


def _parse_episode_output_filename(filename: str) -> tuple[int, int, bool] | None:
    match = EPISODE_FILENAME_PATTERN.match(filename)
    if not match:
        return None
    start_episode = int(match.group("start"))
    end_episode = int(match.group("end") or match.group("start"))
    return start_episode, end_episode, bool(match.group("regen"))


def _collect_reference_blocks(
    references: list[EpisodeFileReference],
    episodes: Iterable[int],
    *,
    total_episodes: int,
    max_chars_per_reference: int,
    exclude_paths: set[Path] | None = None,
) -> list[tuple[Path, str]]:
    exclude_paths = exclude_paths or set()
    selected_blocks: list[tuple[Path, str]] = []
    seen_paths: set[Path] = set(exclude_paths)
    for episode in sorted(dict.fromkeys(int(value) for value in episodes)):
        candidate = _select_best_reference(references, episode, exclude_paths=seen_paths)
        if candidate is None:
            continue
        snippet = _build_reference_snippet(
            candidate,
            episode,
            total_episodes=total_episodes,
            max_chars=max_chars_per_reference,
        )
        selected_blocks.append((candidate.path, snippet))
        seen_paths.add(candidate.path)
    return selected_blocks


def _select_best_reference(
    references: list[EpisodeFileReference],
    episode: int,
    *,
    exclude_paths: set[Path],
) -> EpisodeFileReference | None:
    candidates = [
        reference
        for reference in references
        if reference.path not in exclude_paths and reference.start_episode <= episode <= reference.end_episode
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda reference: (
            reference.span_size,
            0 if reference.is_regeneration else 1,
            -reference.path.stat().st_mtime,
        )
    )
    return candidates[0]


def _build_reference_snippet(
    reference: EpisodeFileReference,
    episode: int,
    *,
    total_episodes: int,
    max_chars: int,
) -> str:
    try:
        text = reference.path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    snippet = text[:max_chars].strip()
    if len(text) > len(snippet):
        snippet = f"{snippet}\n..."
    range_label = format_episode_range(
        reference.start_episode,
        reference.end_episode,
        total_episodes=total_episodes,
    )
    return (
        f"[EP{episode:0{max(2, len(str(total_episodes)))}d} reference from {reference.path.name} "
        f"(covers {range_label})]\n{snippet or '(empty reference)'}"
    )
