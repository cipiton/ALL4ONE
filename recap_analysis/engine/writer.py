from __future__ import annotations

from datetime import datetime
from pathlib import Path


def write_report(output_dir: Path, input_path: Path, report_text: str) -> Path:
    """Persist the report without silently overwriting existing files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{input_path.stem}_analysis.txt"
    candidate = output_dir / base_name

    if candidate.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = output_dir / f"{input_path.stem}_analysis_{timestamp}.txt"
        increment = 1
        while candidate.exists():
            candidate = output_dir / f"{input_path.stem}_analysis_{timestamp}_{increment}.txt"
            increment += 1

    candidate.write_text(report_text, encoding="utf-8")
    return candidate
