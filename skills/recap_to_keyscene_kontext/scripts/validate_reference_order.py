from __future__ import annotations

import copy
import json
from pathlib import Path

from run_keyscene_kontext import (
    AssetFile,
    SelectedAsset,
    _build_reference_order_plan,
    _load_json,
    substitute_workflow,
)


def _selected(role: str) -> SelectedAsset:
    group = {"character": "characters", "scene": "scenes", "prop": "props"}[role]
    asset = AssetFile(
        group=group,
        kind=role,
        asset_id=f"{role}_demo",
        asset_name=f"{role}_demo",
        path=Path(f"C:/demo/{role}.png"),
        relpath=f"{group}/{role}.png",
        source={"source": "validation"},
    )
    return SelectedAsset(asset=asset, strategy="validation", score=100, notes=())


def _build_case(mode: str, roles: tuple[str, ...]) -> dict[str, object]:
    skill_dir = Path(__file__).resolve().parents[1]
    template = _load_json(skill_dir / "assets" / "i2iscenes.json")
    selected = {
        "character": _selected("character") if "character" in roles else SelectedAsset(None, "missing", 0, ("missing",)),
        "scene": _selected("scene") if "scene" in roles else SelectedAsset(None, "missing", 0, ("missing",)),
        "prop": _selected("prop") if "prop" in roles else SelectedAsset(None, "missing", 0, ("missing",)),
    }
    workflow_inputs = {
        role: f"{role}.png" if role in roles else ""
        for role in ("character", "scene", "prop")
    }
    beat = {
        "shot_id": f"validation_{mode}",
        "camera": {"shot_type": "wide shot"},
        "asset_focus": "interaction",
    }
    plan = _build_reference_order_plan(
        beat=beat,
        selected=selected,
        workflow_asset_inputs=workflow_inputs,
        requested_mode=mode,
    )
    substitutions = substitute_workflow(
        copy.deepcopy(template),
        reference_plan=plan,
        prompt="validation",
        filename_prefix="validation/reference_order",
        width=576,
        height=1024,
        seed=1,
    )
    return {
        "mode": mode,
        "roles_present": list(roles),
        "ordered_roles": [candidate.role for candidate in plan.candidates],
        "stitch_mapping": substitutions["reference_injection"]["stitch_mapping"],
    }


def main() -> int:
    report = {
        "three_reference_modes": [
            _build_case("identity_first", ("character", "scene", "prop")),
            _build_case("staging_first", ("character", "scene", "prop")),
            _build_case("object_first", ("character", "scene", "prop")),
        ],
        "fallback_cases": [
            _build_case("identity_first", ("character",)),
            _build_case("staging_first", ("scene", "character")),
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
