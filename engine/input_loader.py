from __future__ import annotations

import math
import re
import zipfile
from xml.etree import ElementTree
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


def read_resource_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv"}:
        return read_text_with_fallbacks(path)
    if suffix == ".docx":
        return _read_docx_text(path)
    if suffix == ".xlsx":
        return _read_xlsx_text(path)
    return (
        f"Binary resource available at {path.name}.\n"
        f"Extension: {suffix or '(none)'}\n"
        f"Size: {path.stat().st_size} bytes"
    )


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


def _read_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise InputLoadError(f"Could not read DOCX resource: {path}") from exc

    root = ElementTree.fromstring(xml_bytes)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs).strip()


def _read_xlsx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings = _load_xlsx_shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            namespace = {
                "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            }
            sheet_names = [
                sheet.attrib.get("name", f"Sheet {index}")
                for index, sheet in enumerate(workbook.findall(".//main:sheet", namespace), start=1)
            ]

            lines: list[str] = []
            for index, sheet_name in enumerate(sheet_names, start=1):
                sheet_path = f"xl/worksheets/sheet{index}.xml"
                if sheet_path not in archive.namelist():
                    continue
                sheet_root = ElementTree.fromstring(archive.read(sheet_path))
                lines.append(f"[{sheet_name}]")
                for row in sheet_root.findall(".//main:row", namespace):
                    values: list[str] = []
                    for cell in row.findall("main:c", namespace):
                        value = _read_xlsx_cell_value(cell, shared_strings, namespace)
                        if value:
                            values.append(value)
                    if values:
                        lines.append("\t".join(values))
                lines.append("")
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise InputLoadError(f"Could not read XLSX resource: {path}") from exc

    return "\n".join(line for line in lines if line is not None).strip()


def _load_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(".//main:si", namespace):
        text = "".join(node.text or "" for node in item.findall(".//main:t", namespace)).strip()
        strings.append(text)
    return strings


def _read_xlsx_cell_value(
    cell: ElementTree.Element,
    shared_strings: list[str],
    namespace: dict[str, str],
) -> str:
    raw_value = cell.findtext("main:v", default="", namespaces=namespace).strip()
    if not raw_value:
        return ""
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(raw_value)]
        except (ValueError, IndexError):
            return raw_value
    return raw_value
