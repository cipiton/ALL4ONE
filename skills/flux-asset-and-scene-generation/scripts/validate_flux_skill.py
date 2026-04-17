from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from build_flux_prompts import build_asset_prompt, build_keyscene_prompt
from flux_generate import BatchGenerationJob, FluxImageGenerator, build_generation_config
from load_recap_production import GeneratedAsset, GeneratedAssetIndex, RecapAsset, RecapBeat
from prompt_language import prompt_uses_single_language
from run_flux_generation import AssetMatch, plan_keyscene_selection, validate_scene_selection
from run_flux_generation import resolve_final_prompt_language_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate vehicle-shot prompt compression and reference policy for the FLUX skill.")
    parser.add_argument("--live-vehicle-batch", action="store_true", help="Also run a real FLUX 4B vehicle batch using local fixture references.")
    return parser.parse_args()


def main() -> int:
    configure_utf8_console()
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    validation_root = repo_root / "outputs" / ".internal" / "flux_skill_validation"
    fixture_root = repo_root / "outputs" / ".internal" / "keyscene_validation" / "fixtures" / "missing_storyboard_run" / "05_assets_t2i"
    if not fixture_root.exists():
        raise FileNotFoundError(f"Vehicle validation fixture assets were not found: {fixture_root}")

    asset_index = build_fixture_asset_index(fixture_root)
    bundle = build_fixture_bundle()
    beats = build_vehicle_test_beats()
    asset_language_examples = build_asset_language_examples(bundle)
    keyscene_language_examples = build_keyscene_language_examples(bundle=bundle, asset_index=asset_index, beat=beats[0])
    config_language_resolution = validate_config_language_resolution()

    examples: dict[str, dict[str, object]] = {}
    prompts_without_motion = True
    prompts_with_scale_language = True
    road_track_visibility = True
    vehicle_template_used = True
    reference_counts: dict[str, int] = {}
    prop_drop_decisions: dict[str, str | None] = {}
    live_manifest_path = None

    for beat in beats:
        plan = plan_keyscene_selection(
            bundle=bundle,
            asset_index=asset_index,
            beat=beat,
            scene_validation_mode="warn",
        )
        prompt_result = build_keyscene_prompt(
            beat,
            style_target="3d-anime",
            final_prompt_language="zh",
            shot_mode=plan.shot_mode,
            vehicle_preset=plan.vehicle_preset,
            scene_asset=plan.selected_assets["scene"],
            character_asset=plan.selected_assets["character"],
            prop_asset=plan.selected_assets["prop"],
            scene_strategy=plan.scene.strategy,
            character_strategy=plan.character.strategy,
            prop_strategy=plan.prop.strategy,
        )
        examples[beat.beat_id] = {
            "shot_mode": plan.shot_mode,
            "vehicle_preset": plan.vehicle_preset,
            "reference_policy": plan.reference_policy,
            "reference_count": len(plan.reference_paths),
            "dropped_prop_reason": plan.dropped_prop_reason,
            "before_prompt": prompt_result.metadata["legacy_prompt"],
            "after_prompt": prompt_result.prompt,
            "prompt_length": prompt_result.metadata["prompt_length"],
            "legacy_prompt_length": prompt_result.metadata["legacy_prompt_length"],
            "anti_oversize_rules": prompt_result.metadata["anti_oversize_rules"],
            "framing_clause": prompt_result.metadata["framing_clause"],
            "selected_assets": {
                role: (asset.asset_name if asset is not None else None)
                for role, asset in plan.selected_assets.items()
            },
            "validation_warnings": list(plan.validation_warnings),
        }
        reference_counts[beat.beat_id] = len(plan.reference_paths)
        prop_drop_decisions[beat.beat_id] = plan.dropped_prop_reason
        prompts_without_motion = prompts_without_motion and all(
            token not in prompt_result.prompt.casefold()
            for token in ("pan right", "pan left", "slow dolly out", "slow push in", "handheld drift", "tracking")
        )
        prompts_with_scale_language = prompts_with_scale_language and any(
            token in prompt_result.prompt
            for token in ("真实整车比例", "真实赛道比例", "真实尺寸关系", "不过度放大", "不要把")
        )
        if beat.beat_id in {"vehicle_riding_road", "vehicle_track_race"}:
            road_track_visibility = road_track_visibility and any(
                token in prompt_result.prompt for token in ("赛道向背景", "道路向背景", "护栏", "周围保留可见环境", "车道")
            )
        vehicle_template_used = vehicle_template_used and plan.shot_mode == "vehicle_keyscene"

    mismatch_beat = beats[2]
    mismatch_plan = plan_keyscene_selection(
        bundle=bundle,
        asset_index=asset_index,
        beat=mismatch_beat,
        scene_validation_mode="warn",
    )
    wrong_scene = next(item for item in asset_index.items_by_group["scenes"] if item.asset_name == "昏暗小工棚")
    mismatch_warnings = validate_scene_selection(
        beat=mismatch_beat,
        selected_match=AssetMatch(
            asset=wrong_scene,
            strategy="forced_mismatch_for_validation",
            note="Forced mismatch for validation.",
            score=0,
            matched_terms=(),
            candidate_scores=mismatch_plan.scene.candidate_scores,
        ),
        candidate_scores=mismatch_plan.scene.candidate_scores,
        mode="warn",
    )

    if args.live_vehicle_batch:
        live_manifest_path = run_live_vehicle_batch(
            validation_root=validation_root,
            beats=beats,
            bundle=bundle,
            asset_index=asset_index,
        )

    summary = {
        "fixture_root": str(fixture_root.resolve()),
        "asset_prompt_language_examples": asset_language_examples,
        "asset_prompts_are_single_language": all(
            item["single_language"] for item in asset_language_examples.values()
        ),
        "keyscene_prompt_language_examples": keyscene_language_examples,
        "keyscene_prompts_are_single_language": all(
            item["single_language"] for item in keyscene_language_examples.values()
        ),
        "config_language_resolution": config_language_resolution,
        "vehicle_examples": examples,
        "vehicle_template_used_for_examples": vehicle_template_used,
        "prompts_are_shorter": all(
            example["prompt_length"] < example["legacy_prompt_length"] for example in examples.values()
        ),
        "scale_language_present": prompts_with_scale_language,
        "motion_camera_language_removed": prompts_without_motion,
        "road_track_readability_language_present": road_track_visibility,
        "reference_counts": reference_counts,
        "prop_drop_decisions": prop_drop_decisions,
        "scene_mismatch_warnings": mismatch_warnings,
        "live_vehicle_batch_manifest": str(live_manifest_path.resolve()) if live_manifest_path is not None else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_asset_language_examples(bundle) -> dict[str, dict[str, object]]:
    assets = {
        "character_en": (bundle.assets_by_group["characters"][0], "en"),
        "character_zh": (bundle.assets_by_group["characters"][0], "zh"),
        "scene_en": (bundle.assets_by_group["scenes"][0], "en"),
        "scene_zh": (bundle.assets_by_group["scenes"][0], "zh"),
        "prop_en": (bundle.assets_by_group["props"][0], "en"),
        "prop_zh": (bundle.assets_by_group["props"][0], "zh"),
    }
    examples: dict[str, dict[str, object]] = {}
    for label, (asset, language) in assets.items():
        result = build_asset_prompt(asset, style_target="3d-anime", final_prompt_language=language)
        examples[label] = {
            "asset_id": asset.asset_id,
            "final_prompt_language": result.final_prompt_language,
            "prompt": result.prompt,
            "single_language": prompt_uses_single_language(result.prompt, language),
        }
    return examples


def build_keyscene_language_examples(*, bundle, asset_index: GeneratedAssetIndex, beat: RecapBeat) -> dict[str, dict[str, object]]:
    plan = plan_keyscene_selection(
        bundle=bundle,
        asset_index=asset_index,
        beat=beat,
        scene_validation_mode="warn",
    )
    examples: dict[str, dict[str, object]] = {}
    for language in ("en", "zh"):
        result = build_keyscene_prompt(
            beat,
            style_target="3d-anime",
            final_prompt_language=language,
            shot_mode=plan.shot_mode,
            vehicle_preset=plan.vehicle_preset,
            scene_asset=plan.selected_assets["scene"],
            character_asset=plan.selected_assets["character"],
            prop_asset=plan.selected_assets["prop"],
            scene_strategy=plan.scene.strategy,
            character_strategy=plan.character.strategy,
            prop_strategy=plan.prop.strategy,
        )
        examples[f"keyscene_{language}"] = {
            "beat_id": beat.beat_id,
            "final_prompt_language": result.final_prompt_language,
            "prompt": result.prompt,
            "single_language": prompt_uses_single_language(result.prompt, language),
        }
    return examples


def validate_config_language_resolution() -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    with tempfile.TemporaryDirectory() as temp_root:
        temp_path = Path(temp_root)
        missing_resolved, missing_warning = resolve_final_prompt_language_from_config(temp_path)
        results["missing_setting"] = {
            "resolved": missing_resolved,
            "warning": missing_warning,
            "uses_default_english": missing_resolved == "en",
        }

        invalid_repo = temp_path / "invalid"
        invalid_repo.mkdir(parents=True, exist_ok=True)
        (invalid_repo / "config.ini").write_text("[generation]\nfinal_prompt_language = invalid\n", encoding="utf-8")
        invalid_resolved, invalid_warning = resolve_final_prompt_language_from_config(invalid_repo)
        results["invalid_setting"] = {
            "resolved": invalid_resolved,
            "warning": invalid_warning,
            "falls_back_to_english": invalid_resolved == "en" and bool(invalid_warning),
        }

        zh_repo = temp_path / "zh"
        zh_repo.mkdir(parents=True, exist_ok=True)
        (zh_repo / "config.ini").write_text("[generation]\nfinal_prompt_language = zh\n", encoding="utf-8")
        zh_resolved, zh_warning = resolve_final_prompt_language_from_config(zh_repo)
        results["zh_setting"] = {
            "resolved": zh_resolved,
            "warning": zh_warning,
            "uses_zh": zh_resolved == "zh",
        }
    return results


def configure_utf8_console() -> None:
    stream = getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except OSError:
            pass


def build_fixture_bundle():
    return SimpleNamespace(
        assets_by_group={
            "characters": [
                recap_asset("character", "character_张雪", "张雪", "年轻机械狂热者，常和摩托与工位绑在一起。", "瘦高中国青年。"),
                recap_asset("character", "character_采访者", "采访者", "新闻采访者。", "深色外套中年男性。"),
            ],
            "props": [
                recap_asset("prop", "prop_黄摩托", "黄摩托", "一辆黄摩托，完整车身和真实道路尺度。", "黄色摩托车。"),
                recap_asset("prop", "prop_白色头盔", "白色头盔", "普通头盔。", "白色旧头盔。"),
                recap_asset("prop", "prop_焊枪", "焊枪", "焊接工具。", "焊枪。"),
            ],
            "scenes": [
                recap_asset("scene", "scene_乡村雨夜公路", "乡村雨夜公路", "雨夜公路与泥浆路面，车辆可在一条车道内运动。", "乡村雨夜公路。"),
                recap_asset("scene", "scene_沙漠拉力赛赛道", "沙漠拉力赛赛道", "沙漠赛道、护栏、赛段空间与远景。", "沙漠拉力赛赛道。"),
                recap_asset("scene", "scene_昏暗小工棚", "昏暗小工棚", "昏暗小工棚与工作台。", "昏暗小工棚。"),
                recap_asset("scene", "scene_Kove工厂车间", "Kove工厂车间", "现代车间与工位。", "Kove工厂车间。"),
            ],
        }
    )


def build_fixture_asset_index(fixture_root: Path) -> GeneratedAssetIndex:
    items_by_group = {
        "characters": [
            generated_asset("character", "张雪", fixture_root / "characters" / "character_张雪.png"),
            generated_asset("character", "采访者", fixture_root / "characters" / "character_采访者.png"),
        ],
        "props": [
            generated_asset("prop", "黄摩托", fixture_root / "props" / "prop_黄摩托.png"),
            generated_asset("prop", "白色头盔", fixture_root / "props" / "prop_白色头盔.png"),
            generated_asset("prop", "焊枪", fixture_root / "props" / "prop_焊枪.png"),
        ],
        "scenes": [
            generated_asset("scene", "乡村雨夜公路", fixture_root / "scenes" / "scene_乡村雨夜公路.png"),
            generated_asset("scene", "沙漠拉力赛赛道", fixture_root / "scenes" / "scene_沙漠拉力赛赛道.png"),
            generated_asset("scene", "昏暗小工棚", fixture_root / "scenes" / "scene_昏暗小工棚.png"),
            generated_asset("scene", "Kove工厂车间", fixture_root / "scenes" / "scene_Kove工厂车间.png"),
        ],
    }
    return GeneratedAssetIndex(root_dir=fixture_root.resolve(), items_by_group=items_by_group, searched_paths=[fixture_root.resolve()])


def build_vehicle_test_beats() -> list[RecapBeat]:
    return [
        beat(
            beat_id="vehicle_riding_road",
            summary="张雪骑着黄摩托在暴雨乡路上追赶前车。",
            visual_prompt="暴雨乡路，黄摩托保持完整车身进入画面，泥路与车道空间清楚，远处道路继续延伸。",
            shot_type="wide shot",
            camera_motion="pan right",
            mood="urgent, raw",
            anchor_text="暴雨里，黄摩托贴着乡路往前咬。",
            asset_focus="interaction",
        ),
        beat(
            beat_id="vehicle_standing_bike",
            summary="张雪站在黄摩托旁，准备再次上路。",
            visual_prompt="人物与黄摩托同框，整车完整可见，车身不要夸张放大，周围留出停靠空间和地面。",
            shot_type="medium shot",
            camera_motion="slow push in",
            mood="tense, exhausted",
            anchor_text="他站在车旁，下一秒就要重新发动车。",
            asset_focus="interaction",
        ),
        beat(
            beat_id="vehicle_track_race",
            summary="黄摩托冲进沙漠拉力赛赛道，赛道边界和远景清楚可见。",
            visual_prompt="车辆位于赛道中景，赛道向背景延伸，护栏和赛段空间保留，车身不要变成贴脸巨物。",
            shot_type="wide shot",
            camera_motion="tracking",
            mood="charged, high-stakes",
            anchor_text="它终于跑进了真正的赛道。",
            asset_focus="interaction",
        ),
    ]


def recap_asset(asset_type: str, asset_id: str, name: str, description: str, subject_content: str) -> RecapAsset:
    return RecapAsset(
        asset_type=asset_type,
        asset_id=asset_id,
        name=name,
        description=description,
        core_feature=name,
        subject_content=subject_content,
        style_lighting="",
        prompt="",
        prompt_fields={},
        order=1,
        source_payload={},
    )


def generated_asset(asset_type: str, name: str, path: Path) -> GeneratedAsset:
    return GeneratedAsset(asset_type=asset_type, asset_id=f"{asset_type}_{name}", asset_name=name, path=path.resolve())


def beat(
    *,
    beat_id: str,
    summary: str,
    visual_prompt: str,
    shot_type: str,
    camera_motion: str,
    mood: str,
    anchor_text: str,
    asset_focus: str,
) -> RecapBeat:
    return RecapBeat(
        beat_id=beat_id,
        episode_number=1,
        summary=summary,
        visual_prompt=visual_prompt,
        shot_type=shot_type,
        camera_motion=camera_motion,
        mood=mood,
        anchor_text=anchor_text,
        priority="",
        beat_role="",
        pace_weight="",
        asset_focus=asset_focus,
        source_payload={},
    )


def run_live_vehicle_batch(*, validation_root: Path, beats: list[RecapBeat], bundle, asset_index: GeneratedAssetIndex) -> Path:
    output_root = validation_root / "vehicle_live_batch"
    keyscene_dir = output_root / "keyscenes"
    keyscene_dir.mkdir(parents=True, exist_ok=True)
    generator = FluxImageGenerator("klein_cli")
    jobs: list[BatchGenerationJob] = []
    for index, beat in enumerate(beats, start=1):
        plan = plan_keyscene_selection(
            bundle=bundle,
            asset_index=asset_index,
            beat=beat,
            scene_validation_mode="warn",
        )
        prompt_result = build_keyscene_prompt(
            beat,
            style_target="3d-anime",
            final_prompt_language="zh",
            shot_mode=plan.shot_mode,
            vehicle_preset=plan.vehicle_preset,
            scene_asset=plan.selected_assets["scene"],
            character_asset=plan.selected_assets["character"],
            prop_asset=plan.selected_assets["prop"],
            scene_strategy=plan.scene.strategy,
            character_strategy=plan.character.strategy,
            prop_strategy=plan.prop.strategy,
        )
        config = build_generation_config(
            backend="klein_cli",
            mode="keyscene",
            model_id=None,
            steps=2,
            guidance_scale=1.0,
            width=512,
            height=768,
            seed=1000 + index,
        )
        jobs.append(
            BatchGenerationJob(
                prompt=prompt_result.prompt,
                output_path=keyscene_dir / f"{beat.beat_id}.png",
                config=config,
                references=tuple(plan.reference_paths),
                job_id=beat.beat_id,
            )
        )
    generator.generate_batch(jobs)
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "flux_vehicle_validation_manifest_v1",
                "item_count": len(jobs),
                "model": "black-forest-labs/FLUX.2-klein-4B",
                "output_root": str(output_root.resolve()),
                "items": [
                    {
                        "beat_id": job.job_id,
                        "output_path": str(job.output_path.resolve()),
                    }
                    for job in jobs
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


if __name__ == "__main__":
    raise SystemExit(main())
