from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # pragma: no cover - optional dependency fallback
    DND_FILES = "DND_Files"
    TkinterDnD = None


if TkinterDnD is not None:

    class DnDWindow(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs) -> None:
            ctk.CTk.__init__(self, *args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)


    DRAG_DROP_AVAILABLE = True
else:

    class DnDWindow(ctk.CTk):
        pass


    DRAG_DROP_AVAILABLE = False


def register_file_drop(widget, callback: Callable) -> bool:
    if not DRAG_DROP_AVAILABLE or widget is None:
        return False
    try:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", callback)
        return True
    except Exception:
        return False


def extract_drop_paths(widget, raw_data: str) -> list[Path]:
    if not raw_data:
        return []
    try:
        raw_items = widget.tk.splitlist(raw_data)
    except Exception:
        raw_items = [raw_data]

    paths: list[Path] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        cleaned = str(raw_item).strip().strip("{}").strip()
        if not cleaned:
            continue
        candidate = Path(cleaned).expanduser()
        marker = str(candidate)
        if marker not in seen:
            paths.append(candidate)
            seen.add(marker)
    return paths
