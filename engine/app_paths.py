from __future__ import annotations

import sys
from pathlib import Path


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _resolve_source_anchor(anchor_path: str | Path | None = None) -> Path:
    if anchor_path is None:
        return Path(__file__).resolve().parent.parent

    anchor = Path(anchor_path).resolve()
    if anchor.is_dir():
        return anchor
    return anchor.parent


def get_bundle_root(anchor_path: str | Path | None = None) -> Path:
    if is_frozen_app():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return _resolve_source_anchor(anchor_path)


def get_app_root(anchor_path: str | Path | None = None) -> Path:
    if is_frozen_app():
        return Path(sys.executable).resolve().parent
    return _resolve_source_anchor(anchor_path)


def get_runtime_context(anchor_path: str | Path | None = None) -> dict[str, Path | bool]:
    return {
        "frozen": is_frozen_app(),
        "bundle_root": get_bundle_root(anchor_path),
        "app_root": get_app_root(anchor_path),
    }
