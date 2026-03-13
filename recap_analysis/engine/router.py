from __future__ import annotations

import math
import re
from pathlib import Path

from .models import DocumentChunk, InputDocument

READ_ENCODINGS = ("utf-8", "utf-8-sig", "gbk", "gb2312", "utf-16", "latin-1")


class InputRoutingError(RuntimeError):
    """Raised when the runtime cannot read the input text."""


def read_txt_document(file_path: Path) -> InputDocument:
    """Read a `.txt` document with simple encoding fallbacks."""
    if not file_path.exists():
        raise InputRoutingError(f"输入文件不存在: {file_path}")
    if file_path.suffix.lower() != ".txt":
        raise InputRoutingError(f"仅支持 .txt 输入: {file_path.name}")

    last_error: Exception | None = None
    text = ""
    for encoding in READ_ENCODINGS:
        try:
            text = file_path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    else:
        raise InputRoutingError(f"无法读取文本文件编码: {file_path}") from last_error

    normalized_text = text.replace("\r\n", "\n").strip()
    if not normalized_text:
        raise InputRoutingError(f"输入文件为空: {file_path}")

    line_count = normalized_text.count("\n") + 1
    estimated_tokens = estimate_token_length(normalized_text)
    return InputDocument(
        path=file_path,
        text=normalized_text,
        character_count=len(normalized_text),
        line_count=line_count,
        estimated_tokens=estimated_tokens,
    )


def chunk_document_text(
    text: str, chunk_size: int, overlap: int, stem: str = "chunk"
) -> list[DocumentChunk]:
    """Create deterministic chunks, preferring newline boundaries."""
    if len(text) <= chunk_size:
        return [
            DocumentChunk(
                chunk_id=f"{stem}-001",
                index=1,
                start_char=0,
                end_char=len(text),
                text=text,
                character_count=len(text),
                estimated_tokens=estimate_token_length(text),
            )
        ]

    chunks: list[DocumentChunk] = []
    start = 0
    index = 1
    total_length = len(text)

    while start < total_length:
        target_end = min(start + chunk_size, total_length)
        end = target_end
        if target_end < total_length:
            boundary = text.rfind("\n", start + int(chunk_size * 0.6), target_end)
            if boundary > start:
                end = boundary

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{stem}-{index:03d}",
                    index=index,
                    start_char=start,
                    end_char=end,
                    text=chunk_text,
                    character_count=len(chunk_text),
                    estimated_tokens=estimate_token_length(chunk_text),
                )
            )
            index += 1

        if end >= total_length:
            break

        next_start = max(0, end - overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def estimate_token_length(text: str) -> int:
    """Return a rough token-ish estimate suitable for planning."""
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    non_cjk_chars = max(0, len(text) - cjk_chars)
    return max(1, cjk_chars + math.ceil(non_cjk_chars / 4))
