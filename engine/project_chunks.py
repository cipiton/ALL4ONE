from __future__ import annotations

from pathlib import Path
from typing import Any

from .input_loader import chunk_text, load_input_document
from .models import InputDocument
from .project_outputs import build_ingestion_report
from .writer import safe_stem, write_text_file


AUTO_SPLIT_CHUNK_SIZE = 300_000
AUTO_SPLIT_OVERLAP = 1000


def prepare_project_chunks(
    input_paths: list[Path],
    *,
    input_root_path: Path | None,
    intermediate_dir: Path,
) -> tuple[list[InputDocument], dict[str, Any]]:
    if len(input_paths) > 1:
        chunk_paths = [path for path in input_paths if path.name.casefold() != "index.txt"]
        chunks = [load_input_document(path, index=index, total=len(chunk_paths)) for index, path in enumerate(chunk_paths, start=1)]
        metadata = {
            "mode": "chunk_folder",
            "source_path": str(input_root_path or chunk_paths[0].parent),
            "chunk_count": len(chunks),
            "overlap_chars": 0,
        }
        _write_ingestion_report(intermediate_dir, metadata, chunks)
        return chunks, metadata

    source_document = load_input_document(input_paths[0])
    chunk_dir = intermediate_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_texts = chunk_text(source_document.text, AUTO_SPLIT_CHUNK_SIZE, AUTO_SPLIT_OVERLAP)
    chunk_paths: list[Path] = []
    for index, text in enumerate(chunk_texts, start=1):
        chunk_path = write_text_file(
            chunk_dir,
            f"{index:03d}_{safe_stem(source_document.path.stem)}_chunk.txt",
            text,
        )
        chunk_paths.append(chunk_path)

    chunks = [load_input_document(path, index=index, total=len(chunk_paths)) for index, path in enumerate(chunk_paths, start=1)]
    metadata = {
        "mode": "auto_split",
        "source_path": str(source_document.path),
        "chunk_count": len(chunks),
        "overlap_chars": AUTO_SPLIT_OVERLAP,
        "estimated_tokens": source_document.estimated_tokens,
    }
    _write_ingestion_report(intermediate_dir, metadata, chunks)
    return chunks, metadata


def _write_ingestion_report(intermediate_dir: Path, metadata: dict[str, Any], chunks: list[InputDocument]) -> None:
    chunk_infos = [
        {
            "index": chunk.index,
            "total": chunk.total,
            "name": chunk.path.name,
            "character_count": chunk.character_count,
            "estimated_tokens": chunk.estimated_tokens,
        }
        for chunk in chunks
    ]
    write_text_file(intermediate_dir, "ingestion_report.txt", build_ingestion_report(metadata, chunk_infos))
