from __future__ import annotations

import math
import re
from pathlib import Path

from .models import InputDocument


READ_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk", "utf-16", "latin-1")


class InputLoadError(RuntimeError):
    """Raised when the runtime cannot load the requested input."""


def resolve_input_paths(raw_path: str, supported_extensions: list[str]) -> list[Path]:
    candidate = Path(raw_path.strip().strip('"')).expanduser().resolve()
    if not candidate.exists():
        raise InputLoadError(f"Input path does not exist: {candidate}")

    allowed = {extension.lower() for extension in supported_extensions}
    if candidate.is_file():
        if candidate.suffix.lower() not in allowed:
            raise InputLoadError(
                f"Unsupported file type '{candidate.suffix}'. Supported: {', '.join(sorted(allowed))}."
            )
        return [candidate]

    if not candidate.is_dir():
        raise InputLoadError(f"Input path is neither a file nor a directory: {candidate}")

    files = sorted(
        [path for path in candidate.iterdir() if path.is_file() and path.suffix.lower() in allowed],
        key=lambda path: path.name.casefold(),
    )
    if not files:
        raise InputLoadError(
            f"No supported files found in {candidate}. Folder mode is non-recursive."
        )
    return files


def load_input_document(path: Path, index: int = 1, total: int = 1) -> InputDocument:
    text = read_text_with_fallbacks(path)
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        raise InputLoadError(f"Input file is empty: {path}")

    return InputDocument(
        path=path,
        text=normalized,
        character_count=len(normalized),
        line_count=normalized.count("\n") + 1,
        estimated_tokens=estimate_token_length(normalized),
        index=index,
        total=total,
    )


def read_text_with_fallbacks(path: Path) -> str:
    last_error: Exception | None = None
    for encoding in READ_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise InputLoadError(f"Could not decode text file: {path}") from last_error


def estimate_token_length(text: str) -> int:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    non_cjk_chars = max(0, len(text) - cjk_chars)
    return max(1, cjk_chars + math.ceil(non_cjk_chars / 4))


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    total = len(text)
    while start < total:
        target_end = min(total, start + chunk_size)
        end = target_end
        if target_end < total:
            boundary = text.rfind("\n", start + int(chunk_size * 0.6), target_end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= total:
            break

        next_start = max(0, end - overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks
