from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PREFIX = "ltx_video_skill__"


def load_local_module(module_name: str) -> ModuleType:
    module_key = f"{MODULE_PREFIX}{module_name}"
    existing = sys.modules.get(module_key)
    if existing is not None:
        return existing

    module_path = SCRIPT_DIR / f"{module_name}.py"
    if not module_path.is_file():
        raise ModuleNotFoundError(f"Local LTX module not found: {module_path}")

    spec = importlib.util.spec_from_file_location(module_key, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load local LTX module spec for {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    spec.loader.exec_module(module)
    return module
