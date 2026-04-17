from __future__ import annotations

import re
from dataclasses import dataclass, field

from load_recap_production import GeneratedAsset, RecapAsset, RecapBeat
from prompt_language import (
    DEFAULT_FINAL_PROMPT_LANGUAGE,
    contains_cjk,
    ensure_sentence as ensure_localized_sentence,
    normalize_final_prompt_language,
    render_prompt_fragment,
    style_tail as localized_style_tail,
)

SHOT_MODE_STAGING = "staging_keyscene"
SHOT_MODE_IDENTITY = "identity_emotion_keyscene"
SHOT_MODE_INSERT = "insert_object_keyscene"
SHOT_MODE_VEHICLE = "vehicle_keyscene"
VEHICLE_PRESET_STANDING = "standing_beside_vehicle"
VEHICLE_PRESET_RIDING = "riding_on_road"
VEHICLE_PRESET_TRACK = "bike_on_track"
VEHICLE_PRESET_WORKSHOP = "workshop_vehicle_interaction"
VEHICLE_PRESET_DETAIL = "vehicle_detail"
CAMERA_MOTION_TERMS = (
    "pan right",
    "pan left",
    "slow dolly out",
    "slow push in",
    "handheld drift",
    "tracking",
    "slow dolly in",
    "slow dolly out",
)
SHOT_TYPE_COMPOSITION = {
    "wide shot": {"en": "wide shot", "zh": "宽构图"},
    "medium shot": {"en": "medium shot", "zh": "中景"},
    "medium wide shot": {"en": "medium wide shot", "zh": "中宽景"},
    "medium close-up": {"en": "medium close-up", "zh": "中近景"},
    "close-up": {"en": "close-up", "zh": "特写"},
    "insert": {"en": "insert shot", "zh": "插入镜头"},
    "over-the-shoulder": {"en": "over-the-shoulder composition", "zh": "越肩构图"},
}
VEHICLE_TERMS = (
    "摩托",
    "赛车",
    "赛道",
    "bike",
    "motorcycle",
    "car",
    "车身",
    "发动机",
    "排气",
    "轮胎",
    "前叉",
    "handlebar",
    "wheel",
    "track",
    "road",
    "lane",
    "kove",
    "zxmoto",
    "820rr-rs",
)
VEHICLE_SCALE_RULES = {
    "en": (
        "Keep the vehicle at believable full-vehicle scale relative to the rider",
        "Keep the vehicle at realistic size and do not oversize it",
        "Keep believable proportions between the vehicle and the road, lane, or track width",
        "Keep a natural camera distance and do not let the vehicle fill the frame",
        "Leave visible surrounding environment around the vehicle",
    ),
    "zh": (
        "车辆与骑手保持真实整车比例",
        "车身符合真实世界尺寸，不要过度放大",
        "车辆与道路、车道或赛道宽度关系正常",
        "车辆与镜头保持自然距离，不要贴满画面",
        "画面周围保留可见环境空间",
    ),
}


@dataclass(frozen=True, slots=True)
class PromptBuildResult:
    prompt: str
    prompt_source: str
    confidence: str
    notes: tuple[str, ...]
    final_prompt_language: str = DEFAULT_FINAL_PROMPT_LANGUAGE
    source_structured_input: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


def build_asset_prompt(
    asset: RecapAsset,
    *,
    style_target: str,
    final_prompt_language: str = DEFAULT_FINAL_PROMPT_LANGUAGE,
) -> PromptBuildResult:
    final_prompt_language, _ = normalize_final_prompt_language(final_prompt_language)
    if asset.asset_type == "character":
        prompt = build_character_prompt(asset, style_target=style_target, final_prompt_language=final_prompt_language)
    elif asset.asset_type in {"scene", "environment"}:
        prompt = build_scene_prompt(asset, style_target=style_target, final_prompt_language=final_prompt_language)
    else:
        prompt = build_prop_prompt(asset, style_target=style_target, final_prompt_language=final_prompt_language)

    notes = [
        "Built from structured asset fields following the FLUX.2 klein prose-first prompt pattern.",
        f"Final prompt rendered in `{final_prompt_language}`.",
    ]
    source = "structured asset fields"
    confidence = "structured"
    if not asset.subject_content and asset.prompt:
        notes.append("Used fallback text from the recap asset visual prompt because structured subject content was sparse.")
        source = "structured asset visual-prompt fallback"
        confidence = "fallback"
    return PromptBuildResult(
        prompt=prompt,
        prompt_source=source,
        confidence=confidence,
        notes=tuple(notes),
        final_prompt_language=final_prompt_language,
        source_structured_input={
            "asset_type": asset.asset_type,
            "asset_id": asset.asset_id,
            "asset_name": asset.name,
            "core_feature": asset.core_feature,
            "subject_content": asset.subject_content,
            "description": asset.description,
            "style_lighting": asset.style_lighting,
            "prompt_fields": dict(asset.prompt_fields),
            "fallback_visual_prompt": asset.prompt,
        },
    )


def build_keyscene_prompt(
    beat: RecapBeat,
    *,
    style_target: str,
    final_prompt_language: str = DEFAULT_FINAL_PROMPT_LANGUAGE,
    shot_mode: str,
    vehicle_preset: str | None,
    scene_asset: GeneratedAsset | None,
    character_asset: GeneratedAsset | None,
    prop_asset: GeneratedAsset | None,
    scene_strategy: str,
    character_strategy: str,
    prop_strategy: str,
) -> PromptBuildResult:
    final_prompt_language, _ = normalize_final_prompt_language(final_prompt_language)
    selected_references = [asset for asset in (scene_asset, character_asset, prop_asset) if asset is not None]
    if not selected_references:
        raise ValueError("Keyscene prompting requires at least one generated reference asset.")

    notes = [
        f"scene={scene_strategy}",
        f"character={character_strategy}",
        f"prop={prop_strategy}",
        f"shot_mode={shot_mode}",
        "Compressed for FLUX.2 klein image editing: describe the target relation and let references carry appearance.",
        f"Final prompt rendered in `{final_prompt_language}`.",
    ]

    prompt_template = shot_mode
    anti_oversize_rules: tuple[str, ...] = ()
    if shot_mode == SHOT_MODE_VEHICLE:
        prompt_template = "vehicle_keyscene"
        prompt_parts = build_vehicle_keyscene_prompt_parts(
            beat,
            style_target=style_target,
            final_prompt_language=final_prompt_language,
            vehicle_preset=vehicle_preset or classify_vehicle_shot_preset(beat),
            scene_asset=scene_asset,
            character_asset=character_asset,
            prop_asset=prop_asset,
        )
        core_beat = prompt_parts["core_action"]
        relation_clause = prompt_parts["scale_clause"]
        blocking_clause = prompt_parts["blocking_clause"]
        framing_clause = prompt_parts["framing_clause"]
        style_clause = prompt_parts["style_clause"]
        anti_oversize_rules = tuple(prompt_parts["anti_oversize_rules"])
        prompt = collapse_whitespace(
            " ".join(part for part in (core_beat, relation_clause, blocking_clause, framing_clause, style_clause) if part)
        )
        notes.append(f"vehicle_preset={vehicle_preset}")
        notes.append("Vehicle-shot template focuses on physical scale, blocking, and anti-oversize staging.")
    else:
        core_beat = compress_keyscene_core_beat(beat, final_prompt_language=final_prompt_language)
        relation_clause = build_keyscene_relation_clause(
            beat,
            final_prompt_language=final_prompt_language,
            shot_mode=shot_mode,
            scene_asset=scene_asset,
            character_asset=character_asset,
            prop_asset=prop_asset,
        )
        framing_clause = build_still_image_framing_clause(
            beat,
            shot_mode=shot_mode,
            final_prompt_language=final_prompt_language,
        )
        style_clause = style_tail(style_target, keyscene=True, final_prompt_language=final_prompt_language)
        blocking_clause = ""
        prompt = collapse_whitespace(
            " ".join(part for part in (core_beat, relation_clause, framing_clause, style_clause) if part)
        )
    legacy_prompt = build_legacy_keyscene_prompt(
        beat,
        style_target=style_target,
        final_prompt_language=final_prompt_language,
        scene_asset=scene_asset,
        character_asset=character_asset,
        prop_asset=prop_asset,
        scene_strategy=scene_strategy,
        character_strategy=character_strategy,
        prop_strategy=prop_strategy,
    )

    source = "structured beat fields"
    confidence = "structured"
    if scene_strategy.endswith("fallback") or character_strategy.endswith("fallback") or prop_strategy.endswith("fallback"):
        confidence = "fallback"
        source = "structured beat fields with asset fallback selection"
        notes.append("Used at least one fallback-generated asset reference because no exact beat match was available.")

    return PromptBuildResult(
        prompt=prompt,
        prompt_source=source,
        confidence=confidence,
        notes=tuple(notes),
        final_prompt_language=final_prompt_language,
        source_structured_input={
            "beat_id": beat.beat_id,
            "summary": beat.summary,
            "visual_prompt": beat.visual_prompt,
            "shot_type": beat.shot_type,
            "camera_motion": beat.camera_motion,
            "mood": beat.mood,
            "anchor_text": beat.anchor_text,
            "asset_focus": beat.asset_focus,
            "selected_reference_assets": {
                "scene": structured_asset_snapshot(scene_asset),
                "character": structured_asset_snapshot(character_asset),
                "prop": structured_asset_snapshot(prop_asset),
            },
        },
        metadata={
            "shot_mode": shot_mode,
            "prompt_template": prompt_template,
            "vehicle_shot": shot_mode == SHOT_MODE_VEHICLE,
            "vehicle_preset": vehicle_preset,
            "core_beat": core_beat,
            "relation_clause": relation_clause,
            "blocking_clause": blocking_clause,
            "framing_clause": framing_clause,
            "style_clause": style_clause,
            "anti_oversize_rules": list(anti_oversize_rules),
            "raw_source_description": raw_keyscene_source_description(beat),
            "prompt_length": prompt_length(prompt),
            "legacy_prompt": legacy_prompt,
            "legacy_prompt_length": prompt_length(legacy_prompt),
            "camera_motion_removed": contains_camera_motion_terms(legacy_prompt) and not contains_camera_motion_terms(prompt),
            "reference_count": len(selected_references),
        },
    )


def build_character_prompt(
    asset: RecapAsset,
    *,
    style_target: str,
    final_prompt_language: str,
) -> str:
    subject = render_source_text(
        first_text(asset.subject_content, asset.description, asset.prompt),
        language=final_prompt_language,
        fallback="a grounded story-driven character reference" if final_prompt_language == "en" else "一个有故事感的角色参考",
    )
    core = render_entity_label(
        first_text(asset.core_feature, asset.name),
        language=final_prompt_language,
        kind="character",
    )
    lighting = render_source_text(
        normalize_lighting(asset.style_lighting),
        language=final_prompt_language,
        fallback="soft controlled light" if final_prompt_language == "en" else "柔和可控的光线",
    )
    sentences = []
    if final_prompt_language == "en":
        sentences.extend(
            [
                ensure_sentence(
                    f"{core} standing as a full-body identity reference against a clean light background, with {subject} as the main subject",
                    language=final_prompt_language,
                ),
                ensure_sentence(
                    "Keep the face, hair silhouette, clothing outline, hand details, and full posture clearly readable, prioritizing character recognition before secondary detail",
                    language=final_prompt_language,
                ),
            ]
        )
        if lighting:
            sentences.append(
                ensure_sentence(
                    f"Use {lighting} so the face, fabric, and silhouette read clearly without letting the background take over",
                    language=final_prompt_language,
                )
            )
        description = render_source_text(cleanup_story_text(asset.description), language=final_prompt_language)
        if description:
            sentences.append(
                ensure_sentence(
                    f"Keep the mood restrained and story-driven so the character immediately feels lived-in: {description}",
                    language=final_prompt_language,
                )
            )
    else:
        sentences.extend(
            [
                ensure_sentence(
                    f"{core}以单人全身身份参考图的方式站在干净简洁的浅色背景前，主体是{subject}",
                    language=final_prompt_language,
                ),
                ensure_sentence(
                    "角色的脸型、发型、服装轮廓、手部痕迹和整体体态都要清晰可读，画面重点先放在人物识别上，再补充细节",
                    language=final_prompt_language,
                ),
            ]
        )
        if lighting:
            sentences.append(
                ensure_sentence(
                    f"光线采用{lighting}，让面部、衣料和轮廓有明确层次，但不要把背景做得喧宾夺主",
                    language=final_prompt_language,
                )
            )
        description = render_source_text(cleanup_story_text(asset.description), language=final_prompt_language)
        if description:
            sentences.append(
                ensure_sentence(
                    f"氛围保持克制而有故事感，让人一眼看出这是长期在这个世界里奔波的人物：{description}",
                    language=final_prompt_language,
                )
            )
    sentences.append(style_tail(style_target, keyscene=False, final_prompt_language=final_prompt_language))
    return collapse_whitespace(" ".join(sentence for sentence in sentences if sentence))


def build_scene_prompt(
    asset: RecapAsset,
    *,
    style_target: str,
    final_prompt_language: str,
) -> str:
    subject = render_source_text(
        first_text(asset.subject_content, asset.description, asset.prompt),
        language=final_prompt_language,
        fallback="a reusable story environment" if final_prompt_language == "en" else "一个可复用的叙事环境",
    )
    lighting = render_source_text(normalize_lighting(asset.style_lighting), language=final_prompt_language)
    scene_name = render_entity_label(first_text(asset.name, asset.asset_id), language=final_prompt_language, kind="scene")
    sentences = []
    if final_prompt_language == "en":
        sentences.extend(
            [
                ensure_sentence(
                    f"{scene_name} presented as a single environment reference image, with {subject} as the main environment focus",
                    language=final_prompt_language,
                ),
                ensure_sentence(
                    "Establish the environment first, then add spatial depth, ground texture, distant information, and reusable story detail, without introducing unrelated characters",
                    language=final_prompt_language,
                ),
            ]
        )
        if lighting:
            sentences.append(
                ensure_sentence(
                    f"Use {lighting} to clarify spatial depth, material reflections, and atmosphere",
                    language=final_prompt_language,
                )
            )
        description = render_source_text(cleanup_story_text(asset.description), language=final_prompt_language)
        if description:
            sentences.append(
                ensure_sentence(
                    f"Keep the atmosphere unified and aligned with the story function of this location: {description}",
                    language=final_prompt_language,
                )
            )
    else:
        sentences.extend(
            [
                ensure_sentence(
                    f"{scene_name}作为单张环境参考图展开，主体是{subject}",
                    language=final_prompt_language,
                ),
                ensure_sentence(
                    "先明确环境本身，再补充空间层次、地面质感、远景信息和可复用的叙事细节，不要塞入无关人物",
                    language=final_prompt_language,
                ),
            ]
        )
        if lighting:
            sentences.append(
                ensure_sentence(
                    f"光线采用{lighting}，让画面的空间深度、材质反射和空气感都更明确",
                    language=final_prompt_language,
                )
            )
        description = render_source_text(cleanup_story_text(asset.description), language=final_prompt_language)
        if description:
            sentences.append(
                ensure_sentence(
                    f"整体气氛保持统一，服务于这个场景的故事功能：{description}",
                    language=final_prompt_language,
                )
            )
    sentences.append(style_tail(style_target, keyscene=False, final_prompt_language=final_prompt_language))
    return collapse_whitespace(" ".join(sentence for sentence in sentences if sentence))


def build_prop_prompt(
    asset: RecapAsset,
    *,
    style_target: str,
    final_prompt_language: str,
) -> str:
    subject = render_source_text(
        first_text(asset.subject_content, asset.description, asset.prompt),
        language=final_prompt_language,
        fallback="a functional story prop" if final_prompt_language == "en" else "一个有功能感的故事道具",
    )
    lighting = render_source_text(normalize_lighting(asset.style_lighting), language=final_prompt_language)
    prop_name = render_entity_label(first_text(asset.name, asset.asset_id), language=final_prompt_language, kind="prop")
    sentences = []
    if final_prompt_language == "en":
        sentences.extend(
            [
                ensure_sentence(
                    f"{prop_name} centered as a single prop reference image, with {subject} as the main prop description",
                    language=final_prompt_language,
                ),
                ensure_sentence(
                    "Clarify the overall silhouette, material behavior, and structural relationships first, then add wear, fabrication traces, or functional details while keeping the background clean",
                    language=final_prompt_language,
                ),
            ]
        )
        if lighting:
            sentences.append(
                ensure_sentence(
                    f"Use {lighting} so the light response across metal, plastic, fabric, or paper stays clear",
                    language=final_prompt_language,
                )
            )
        description = render_source_text(cleanup_story_text(asset.description), language=final_prompt_language)
        if description:
            sentences.append(
                ensure_sentence(
                    f"Keep the narrative weight of the prop without turning it into a complex scene: {description}",
                    language=final_prompt_language,
                )
            )
    else:
        sentences.extend(
            [
                ensure_sentence(
                    f"{prop_name}以单个道具参考图的方式居中呈现，主体是{subject}",
                    language=final_prompt_language,
                ),
                ensure_sentence(
                    "先把道具的整体轮廓、材质和结构关系说清楚，再补充磨损、加工痕迹或功能性细节，保持背景简洁干净",
                    language=final_prompt_language,
                ),
            ]
        )
        if lighting:
            sentences.append(
                ensure_sentence(
                    f"光线采用{lighting}，让金属、塑料、布料或纸面的受光关系足够明确",
                    language=final_prompt_language,
                )
            )
        description = render_source_text(cleanup_story_text(asset.description), language=final_prompt_language)
        if description:
            sentences.append(
                ensure_sentence(
                    f"让画面保留这个道具在故事里的重量，但不要把它拍成复杂场景：{description}",
                    language=final_prompt_language,
                )
            )
    sentences.append(style_tail(style_target, keyscene=False, final_prompt_language=final_prompt_language))
    return collapse_whitespace(" ".join(sentence for sentence in sentences if sentence))


def build_mood_line(beat: RecapBeat, *, final_prompt_language: str) -> str:
    parts: list[str] = []
    shot_type = render_source_text(beat.shot_type, language=final_prompt_language)
    camera_motion = render_source_text(beat.camera_motion, language=final_prompt_language)
    mood = render_source_text(beat.mood, language=final_prompt_language)
    anchor_text = render_source_text(beat.anchor_text, language=final_prompt_language)
    if final_prompt_language == "en":
        if shot_type:
            parts.append(f"Keep the shot feeling close to {shot_type}")
        if camera_motion:
            parts.append(f"Retain the energy of {camera_motion}")
        if mood:
            parts.append(f"The emotional base is {mood}")
        if anchor_text:
            parts.append(f'The narrative hook centers on "{anchor_text}"')
        if not parts:
            return ""
        return ensure_sentence(", ".join(parts), language=final_prompt_language)
    if shot_type:
        parts.append(f"镜头感保持{shot_type}")
    if camera_motion:
        parts.append(f"运动感觉接近{camera_motion}")
    if mood:
        parts.append(f"情绪基调是{mood}")
    if anchor_text:
        parts.append(f"核心叙事钩子围绕“{anchor_text}”")
    if not parts:
        return ""
    return ensure_sentence("，".join(parts), language=final_prompt_language)


def build_legacy_keyscene_prompt(
    beat: RecapBeat,
    *,
    style_target: str,
    final_prompt_language: str,
    scene_asset: GeneratedAsset | None,
    character_asset: GeneratedAsset | None,
    prop_asset: GeneratedAsset | None,
    scene_strategy: str,
    character_strategy: str,
    prop_strategy: str,
) -> str:
    references: list[str] = []
    relationship_parts: list[str] = []
    scene_name = render_generated_asset_label(scene_asset, language=final_prompt_language, kind="scene")
    character_name = render_generated_asset_label(character_asset, language=final_prompt_language, kind="character")
    prop_name = render_generated_asset_label(prop_asset, language=final_prompt_language, kind="prop")

    if scene_asset is not None:
        if final_prompt_language == "en":
            references.append("Reference 1 defines scene composition and lighting")
            relationship_parts.append(f"Preserve the space, shot logic, and light relationship from reference 1 for {scene_name}")
        else:
            references.append("图1用于场景构图与光线")
            relationship_parts.append(f"保留图1里“{scene_name}”的空间、镜头和光照关系")
    if character_asset is not None:
        ref_number = len(references) + 1
        if final_prompt_language == "en":
            references.append(f"Reference {ref_number} defines character appearance")
            relationship_parts.append(
                f"Preserve identity, wardrobe, and facial recognition traits from reference {ref_number} for {character_name}"
            )
        else:
            references.append(f"图{ref_number}用于角色外观")
            relationship_parts.append(f"保留图{ref_number}里“{character_name}”的身份、服装和脸部识别特征")
    if prop_asset is not None:
        ref_number = len(references) + 1
        if final_prompt_language == "en":
            references.append(f"Reference {ref_number} defines prop design")
            relationship_parts.append(
                f"Preserve design, material, and structure from reference {ref_number} for {prop_name}"
            )
        else:
            references.append(f"图{ref_number}用于道具设计")
            relationship_parts.append(f"保留图{ref_number}里“{prop_name}”的设计、材质和结构")

    beat_action = render_source_text(
        first_text(beat.summary, beat.anchor_text, beat.visual_prompt),
        language=final_prompt_language,
        fallback="a coherent story instant" if final_prompt_language == "en" else "一个清楚的叙事瞬间",
    )
    beat_context = render_source_text(cleanup_story_text(beat.visual_prompt), language=final_prompt_language)
    mood_line = build_mood_line(beat, final_prompt_language=final_prompt_language)
    prompt_parts = []
    if references:
        joiner = "; " if final_prompt_language == "en" else "，"
        prompt_parts.append(ensure_sentence(joiner.join(references), language=final_prompt_language))
    if final_prompt_language == "en":
        prompt_parts.append(ensure_sentence(f"Turn this moment into one complete keyscene still: {beat_action}", language=final_prompt_language))
    else:
        prompt_parts.append(ensure_sentence(f"把这一幕处理成一个完整的关键场景：{beat_action}", language=final_prompt_language))
    if beat_context:
        if final_prompt_language == "en":
            prompt_parts.append(ensure_sentence(f"Preserve the narrative relationship of the frame: {beat_context}", language=final_prompt_language))
        else:
            prompt_parts.append(ensure_sentence(f"重点保留这段画面的叙事关系：{beat_context}", language=final_prompt_language))
    if relationship_parts:
        joiner = "; " if final_prompt_language == "en" else "，"
        prompt_parts.append(ensure_sentence(joiner.join(relationship_parts), language=final_prompt_language))
    if mood_line:
        prompt_parts.append(mood_line)
    prompt_parts.append(style_tail(style_target, keyscene=True, final_prompt_language=final_prompt_language))
    return collapse_whitespace(" ".join(part for part in prompt_parts if part).strip())


def classify_keyscene_shot_mode(
    beat: RecapBeat,
    *,
    has_character: bool,
    has_prop: bool,
) -> str:
    shot_type = str(beat.shot_type or "").strip().casefold()
    asset_focus = str(beat.asset_focus or "").strip().casefold()
    beat_text = f"{beat.summary}\n{beat.visual_prompt}\n{beat.anchor_text}".casefold()
    if is_vehicle_shot(beat):
        return SHOT_MODE_VEHICLE
    if "insert" in shot_type or asset_focus == "object":
        return SHOT_MODE_INSERT
    if any(token in shot_type for token in ("close-up", "close up", "medium close-up", "medium close up", "over-the-shoulder")):
        return SHOT_MODE_IDENTITY
    if asset_focus == "character":
        return SHOT_MODE_IDENTITY
    if any(token in beat_text for token in ("眼神", "侧脸", "直视", "回头", "表情", "嘴唇", "脸上", "screen glow")) and has_character:
        return SHOT_MODE_IDENTITY
    if has_prop and not has_character and asset_focus in {"object", "montage"}:
        return SHOT_MODE_INSERT
    return SHOT_MODE_STAGING


def is_vehicle_shot(beat: RecapBeat) -> bool:
    beat_text = f"{beat.summary}\n{beat.visual_prompt}\n{beat.anchor_text}\n{beat.asset_focus}".casefold()
    if any(term in beat_text for term in VEHICLE_TERMS):
        return True
    return False


def classify_vehicle_shot_preset(beat: RecapBeat) -> str:
    shot_type = str(beat.shot_type or "").strip().casefold()
    beat_text = f"{beat.summary}\n{beat.visual_prompt}\n{beat.anchor_text}\n{beat.asset_focus}".casefold()
    if any(term in beat_text for term in ("赛道", "track", "终点线", "维修区", "发车")):
        return VEHICLE_PRESET_TRACK
    if any(term in beat_text for term in ("发动机", "排气", "前叉", "轮胎", "把手", "传动", "engine", "wheel", "handlebar")):
        return VEHICLE_PRESET_DETAIL if ("insert" in shot_type or "close-up" in shot_type or "close up" in shot_type) else VEHICLE_PRESET_WORKSHOP
    if any(term in beat_text for term in ("站在自制摩托旁", "站在车旁", "站在摩托旁", "车旁", "旁边", "beside")):
        return VEHICLE_PRESET_STANDING
    if any(term in beat_text for term in ("工坊", "检修", "修车", "台架", "车边", "焊", "build", "workshop")):
        return VEHICLE_PRESET_WORKSHOP
    return VEHICLE_PRESET_RIDING


def compress_keyscene_core_beat(beat: RecapBeat, *, final_prompt_language: str) -> str:
    source = cleanup_story_text(first_text(beat.summary, beat.anchor_text, beat.visual_prompt))
    if not source:
        return ensure_sentence(
            "Bring the references together into one coherent keyscene still"
            if final_prompt_language == "en"
            else "把参考内容整理成同一瞬间的关键场景",
            language=final_prompt_language,
        )
    source = re.sub(r"[，,。]\s*画面[^，。]*", "", source)
    source = re.sub(r"[，,。]\s*突出[^，。]*", "", source)
    rendered = render_source_text(source, language=final_prompt_language)
    if not rendered:
        rendered = (
            "Bring the references together into one coherent keyscene still"
            if final_prompt_language == "en"
            else "把参考内容整理成同一瞬间的关键场景"
        )
    return ensure_sentence(rendered, language=final_prompt_language)


def build_keyscene_relation_clause(
    beat: RecapBeat,
    *,
    final_prompt_language: str,
    shot_mode: str,
    scene_asset: GeneratedAsset | None,
    character_asset: GeneratedAsset | None,
    prop_asset: GeneratedAsset | None,
) -> str:
    scene_name = render_generated_asset_label(scene_asset, language=final_prompt_language, kind="scene")
    character_name = render_generated_asset_label(character_asset, language=final_prompt_language, kind="character")
    prop_name = render_generated_asset_label(prop_asset, language=final_prompt_language, kind="prop")

    if shot_mode == SHOT_MODE_INSERT:
        if scene_asset is not None and prop_asset is not None:
            if final_prompt_language == "en":
                return ensure_sentence(
                    f"Push {prop_name} into the main subject position and keep only a partial environmental context and light relationship from {scene_name}",
                    language=final_prompt_language,
                )
            return ensure_sentence(f"把{prop_name}压成画面主体，只保留{scene_name}的局部环境和受光关系", language=final_prompt_language)
        if prop_asset is not None:
            if final_prompt_language == "en":
                return ensure_sentence(
                    f"Push {prop_name} into the main subject position and preserve contact detail and material response",
                    language=final_prompt_language,
                )
            return ensure_sentence(f"把{prop_name}压成画面主体，保留局部接触和材质反应", language=final_prompt_language)
        return ensure_sentence(
            "Push the key object into the main subject position and keep only necessary environment cues"
            if final_prompt_language == "en"
            else "把关键物件压成画面主体，只保留必要的环境线索",
            language=final_prompt_language,
        )

    if shot_mode == SHOT_MODE_IDENTITY:
        if scene_asset is not None and character_asset is not None and prop_asset is not None:
            if final_prompt_language == "en":
                return ensure_sentence(
                    f"Make {character_name} the visual center inside {scene_name}, with {prop_name} serving only as a supporting foreground cue",
                    language=final_prompt_language,
                )
            return ensure_sentence(f"让{character_name}在{scene_name}里成为视觉中心，{prop_name}只作为近景支撑线索", language=final_prompt_language)
        if scene_asset is not None and character_asset is not None:
            if final_prompt_language == "en":
                return ensure_sentence(
                    f"Make {character_name} the visual center inside {scene_name}, keeping only one environment cue",
                    language=final_prompt_language,
                )
            return ensure_sentence(f"让{character_name}在{scene_name}里成为视觉中心，只保留一个环境提示", language=final_prompt_language)
        if character_asset is not None:
            return ensure_sentence(
                f"Make {character_name} the visual center, prioritizing expression and pose"
                if final_prompt_language == "en"
                else f"让{character_name}成为视觉中心，重点放在表情和姿态",
                language=final_prompt_language,
            )
        return ensure_sentence(
            "Make the character the visual center, prioritizing expression and pose"
            if final_prompt_language == "en"
            else "让人物成为视觉中心，重点放在表情和姿态",
            language=final_prompt_language,
        )

    if scene_asset is not None and character_asset is not None and prop_asset is not None:
        if final_prompt_language == "en":
            return ensure_sentence(
                f"Let {character_name} and {prop_name} share the same instant inside {scene_name}, with clear spatial and action relationships",
                language=final_prompt_language,
            )
        return ensure_sentence(f"让{character_name}与{prop_name}在{scene_name}里形成同一瞬间，空间关系清楚，动作关系直接", language=final_prompt_language)
    if scene_asset is not None and character_asset is not None:
        if final_prompt_language == "en":
            return ensure_sentence(
                f"Place {character_name} inside the spatial logic of {scene_name}, with clear subject placement and environmental pressure",
                language=final_prompt_language,
            )
        return ensure_sentence(f"让{character_name}落进{scene_name}的空间关系里，主体位置和环境压迫感清楚", language=final_prompt_language)
    if scene_asset is not None and prop_asset is not None:
        if final_prompt_language == "en":
            return ensure_sentence(
                f"Place {prop_name} inside {scene_name} with a clear object-to-environment relationship",
                language=final_prompt_language,
            )
        return ensure_sentence(f"让{prop_name}落进{scene_name}里，物件与环境关系清楚", language=final_prompt_language)
    return ensure_sentence(
        "Bring the references together into a clear story instant"
        if final_prompt_language == "en"
        else "把参考内容整理成一个清楚的叙事瞬间",
        language=final_prompt_language,
    )


def build_still_image_framing_clause(beat: RecapBeat, *, shot_mode: str, final_prompt_language: str) -> str:
    shot_type = str(beat.shot_type or "").strip().casefold()
    composition_entry = SHOT_TYPE_COMPOSITION.get(shot_type)
    composition = composition_entry.get(final_prompt_language) if composition_entry else None
    if not composition:
        composition = {
            SHOT_MODE_STAGING: {"en": "wide shot", "zh": "宽构图"},
            SHOT_MODE_IDENTITY: {"en": "medium close-up", "zh": "中近景"},
            SHOT_MODE_INSERT: {"en": "insert shot", "zh": "插入镜头"},
        }.get(shot_mode, {"en": "medium shot", "zh": "中景"}).get(final_prompt_language, "medium shot")

    if shot_mode == SHOT_MODE_INSERT:
        return ensure_sentence(
            f"{composition}, emphasize the object, hand contact, and localized light"
            if final_prompt_language == "en"
            else f"{composition}，突出物件、手部接触和局部光线",
            language=final_prompt_language,
        )
    if shot_mode == SHOT_MODE_IDENTITY:
        return ensure_sentence(
            f"{composition}, emphasize expression, pose, and one supporting scene cue"
            if final_prompt_language == "en"
            else f"{composition}，突出表情、姿态和一个支持性的场景线索",
            language=final_prompt_language,
        )
    return ensure_sentence(
        f"{composition}, emphasize subject placement, scene depth, and one key action relationship"
        if final_prompt_language == "en"
        else f"{composition}，突出主体位置、场景层次和一个关键动作关系",
        language=final_prompt_language,
    )


def build_vehicle_keyscene_prompt_parts(
    beat: RecapBeat,
    *,
    style_target: str,
    final_prompt_language: str,
    vehicle_preset: str,
    scene_asset: GeneratedAsset | None,
    character_asset: GeneratedAsset | None,
    prop_asset: GeneratedAsset | None,
) -> dict[str, object]:
    scene_name = render_generated_asset_label(scene_asset, language=final_prompt_language, kind="scene")
    character_name = render_generated_asset_label(character_asset, language=final_prompt_language, kind="character")
    vehicle_name = render_vehicle_label_from_context(
        prop_asset.asset_name if prop_asset is not None else vehicle_label_from_beat(beat),
        language=final_prompt_language,
    )
    style_clause = style_tail(style_target, keyscene=True, final_prompt_language=final_prompt_language)
    anti_oversize_rules = vehicle_anti_oversize_rules(vehicle_preset, final_prompt_language=final_prompt_language)

    if vehicle_preset == VEHICLE_PRESET_STANDING:
        return {
            "core_action": ensure_sentence(
                f"{character_name} stands beside {vehicle_name} in the same story instant"
                if final_prompt_language == "en"
                else f"{character_name}站在{vehicle_name}旁，和车辆处在同一瞬间",
                language=final_prompt_language,
            ),
            "scale_clause": ensure_sentence(
                (
                    f"Keep {vehicle_name} at believable full-vehicle scale relative to {character_name}, without oversizing it or letting it fill the frame"
                    if final_prompt_language == "en"
                    else f"{vehicle_name}保持与{character_name}匹配的真实整车比例，不过度放大，也不要压满画面"
                ),
                language=final_prompt_language,
            ),
            "blocking_clause": ensure_sentence(
                (
                    f"Place {character_name} and {vehicle_name} in the midground of {scene_name}, with the vehicle occupying a natural parked scale and visible ground and surrounding space"
                    if final_prompt_language == "en"
                    else f"{character_name}与{vehicle_name}落在{scene_name}的中景，车辆自然占据一处停车或停靠尺度，周围保留地面和环境空间"
                ),
                language=final_prompt_language,
            ),
            "framing_clause": vehicle_framing_clause(beat, vehicle_preset=vehicle_preset, final_prompt_language=final_prompt_language),
            "style_clause": style_clause,
            "anti_oversize_rules": anti_oversize_rules,
        }
    if vehicle_preset == VEHICLE_PRESET_TRACK:
        return {
            "core_action": ensure_sentence(
                f"{vehicle_name} completes the action instant on the track"
                if final_prompt_language == "en"
                else f"{vehicle_name}在赛道上完成这一瞬间动作",
                language=final_prompt_language,
            ),
            "scale_clause": ensure_sentence(
                (
                    f"Keep {vehicle_name} at true track scale, with the full vehicle visible and believable relative to the rider and track width"
                    if final_prompt_language == "en"
                    else f"{vehicle_name}保持真实赛道比例，车身完整，不过度放大，与骑手和赛道宽度关系正常"
                ),
                language=final_prompt_language,
            ),
            "blocking_clause": ensure_sentence(
                (
                    "Keep the vehicle in the midground or lower mid-frame, clearly inside one track space, with the track receding into the background and barriers or grandstand remaining visible"
                    if final_prompt_language == "en"
                    else "车辆位于中景或下中部，清楚落在一条赛道空间里，赛道向背景延伸，护栏或看台保持可见"
                ),
                language=final_prompt_language,
            ),
            "framing_clause": vehicle_framing_clause(beat, vehicle_preset=vehicle_preset, final_prompt_language=final_prompt_language),
            "style_clause": style_clause,
            "anti_oversize_rules": anti_oversize_rules,
        }
    if vehicle_preset == VEHICLE_PRESET_WORKSHOP:
        return {
            "core_action": ensure_sentence(
                f"{character_name} works on or inspects {vehicle_name} inside {scene_name}"
                if final_prompt_language == "en"
                else f"{character_name}在{scene_name}里围绕{vehicle_name}操作或检修",
                language=final_prompt_language,
            ),
            "scale_clause": ensure_sentence(
                (
                    f"Keep {vehicle_name} at believable scale and do not enlarge the full vehicle or machine into a face-filling giant object"
                    if final_prompt_language == "en"
                    else f"{vehicle_name}保持真实尺寸关系，不要把整车或机械放大成贴脸巨物"
                ),
                language=final_prompt_language,
            ),
            "blocking_clause": ensure_sentence(
                (
                    f"Keep {vehicle_name} in the midground of a workstation or work area, with tools, ground plane, and workspace still visible so the machine stays integrated with the environment"
                    if final_prompt_language == "en"
                    else f"{vehicle_name}位于工位或工作区中景，周围保留工具、地面和工作间空间，机械与环境保持连贯"
                ),
                language=final_prompt_language,
            ),
            "framing_clause": vehicle_framing_clause(beat, vehicle_preset=vehicle_preset, final_prompt_language=final_prompt_language),
            "style_clause": style_clause,
            "anti_oversize_rules": anti_oversize_rules,
        }
    if vehicle_preset == VEHICLE_PRESET_DETAIL:
        return {
            "core_action": ensure_sentence(
                f"Emphasize the key mechanical detail of {vehicle_name}"
                if final_prompt_language == "en"
                else f"突出{vehicle_name}的关键机械细节",
                language=final_prompt_language,
            ),
            "scale_clause": ensure_sentence(
                (
                    "Keep the local mechanism at believable size and thickness relationships, without exaggerating the parts into distorted giant objects"
                    if final_prompt_language == "en"
                    else "局部机械保持真实尺寸和厚度关系，不要把零件夸张成失真巨物"
                ),
                language=final_prompt_language,
            ),
            "blocking_clause": ensure_sentence(
                (
                    "Keep the detail in close range while retaining some mounting context, support structure, or hand relationship so it does not become a floating poster close-up"
                    if final_prompt_language == "en"
                    else "局部细节位于近景，但仍保留一点安装环境、支架或手部关系，避免海报式漂浮特写"
                ),
                language=final_prompt_language,
            ),
            "framing_clause": vehicle_framing_clause(beat, vehicle_preset=vehicle_preset, final_prompt_language=final_prompt_language),
            "style_clause": style_clause,
            "anti_oversize_rules": anti_oversize_rules,
        }
    return {
        "core_action": ensure_sentence(
            f"{character_name} rides or controls {vehicle_name} in this instant"
            if final_prompt_language == "en"
            else f"{character_name}骑着或控制{vehicle_name}完成这一瞬间动作",
            language=final_prompt_language,
        ),
        "scale_clause": ensure_sentence(
            (
                f"Keep {vehicle_name} at believable full-vehicle scale relative to {character_name}, with normal proportions against the road or lane width"
                if final_prompt_language == "en"
                else f"{vehicle_name}保持与{character_name}匹配的真实整车比例，不过度放大，和道路或车道宽度关系正常"
            ),
            language=final_prompt_language,
        ),
        "blocking_clause": ensure_sentence(
            (
                f"Keep the vehicle and character in the midground or lower mid-frame, clearly grounded in the road space of {scene_name}, with the road receding into the background and visible surrounding space"
                if final_prompt_language == "en"
                else f"车辆和人物位于中景或下中部，清楚落在{scene_name}的道路空间里，道路向背景延伸，周围保留可见环境"
            ),
            language=final_prompt_language,
        ),
        "framing_clause": vehicle_framing_clause(beat, vehicle_preset=vehicle_preset, final_prompt_language=final_prompt_language),
        "style_clause": style_clause,
        "anti_oversize_rules": anti_oversize_rules,
    }


def vehicle_framing_clause(beat: RecapBeat, *, vehicle_preset: str, final_prompt_language: str) -> str:
    shot_type = str(beat.shot_type or "").strip().casefold()
    if vehicle_preset == VEHICLE_PRESET_DETAIL:
        composition = "close-up" if final_prompt_language == "en" and "close" in shot_type else (
            "insert shot" if final_prompt_language == "en" else ("特写" if "close" in shot_type else "插入镜头")
        )
        return ensure_sentence(
            f"{composition}, emphasize mechanical detail and localized light"
            if final_prompt_language == "en"
            else f"{composition}，突出机械细节与局部受光",
            language=final_prompt_language,
        )
    if vehicle_preset == VEHICLE_PRESET_TRACK:
        composition = "wide shot" if final_prompt_language == "en" and "wide" in shot_type else (
            "medium wide shot" if final_prompt_language == "en" else ("宽构图" if "wide" in shot_type else "中宽景")
        )
        return ensure_sentence(
            f"{composition}, let the track recede clearly into the background and keep the vehicle in the midground instead of a giant poster-like foreground"
            if final_prompt_language == "en"
            else f"{composition}，赛道向背景清楚延伸，车辆保持在中景，不做巨幅海报式前景",
            language=final_prompt_language,
        )
    if vehicle_preset == VEHICLE_PRESET_STANDING:
        composition = "medium wide shot" if final_prompt_language == "en" and "medium" in shot_type else (
            "wide shot" if final_prompt_language == "en" else ("中宽景" if "medium" in shot_type else "宽构图")
        )
        return ensure_sentence(
            f"{composition}, keep the character and vehicle in the same frame with room for the full vehicle and surrounding space"
            if final_prompt_language == "en"
            else f"{composition}，人物和车辆同框，留出完整车身和周围空间",
            language=final_prompt_language,
        )
    if vehicle_preset == VEHICLE_PRESET_WORKSHOP:
        composition = "medium shot" if final_prompt_language == "en" and "medium" in shot_type else (
            "medium wide shot" if final_prompt_language == "en" else ("中景" if "medium" in shot_type else "中宽景")
        )
        return ensure_sentence(
            f"{composition}, keep the machine and work area relationship clear and preserve the ground plane and workstation edges"
            if final_prompt_language == "en"
            else f"{composition}，机械与工作区关系清楚，保留地面和工位边界",
            language=final_prompt_language,
        )
    composition = "wide shot" if final_prompt_language == "en" and "wide" in shot_type else (
        "medium wide shot" if final_prompt_language == "en" else ("宽构图" if "wide" in shot_type else "中宽景")
    )
    return ensure_sentence(
        f"{composition}, keep the vehicle in the lower mid-frame or midground, with the road receding clearly into the background"
        if final_prompt_language == "en"
        else f"{composition}，车辆位于下中部或中景，道路清楚后退到背景",
        language=final_prompt_language,
    )


def vehicle_anti_oversize_rules(vehicle_preset: str, *, final_prompt_language: str) -> list[str]:
    if vehicle_preset == VEHICLE_PRESET_DETAIL:
        return (
            [
                "Keep the local detail at believable thickness and scale",
                "Do not exaggerate parts into surreal giant objects",
                "Retain some mounting context or support relationship",
            ]
            if final_prompt_language == "en"
            else [
                "局部细节保持真实厚度与尺寸关系",
                "不要把零件夸张成超现实巨物",
                "保留一点安装环境或支撑关系",
            ]
        )
    if vehicle_preset == VEHICLE_PRESET_TRACK:
        return (
            [
                "Keep the vehicle and rider at believable track scale",
                "Keep the vehicle grounded within one track width",
                "Keep barriers, track edges, and background space visible",
            ]
            if final_prompt_language == "en"
            else [
                "车辆与骑手保持真实赛道比例",
                "车辆落在一条赛道宽度内",
                "护栏、赛道边界和背景空间保持可见",
            ]
        )
    return list(VEHICLE_SCALE_RULES.get(final_prompt_language, VEHICLE_SCALE_RULES["en"]))


def vehicle_label_from_beat(beat: RecapBeat) -> str:
    beat_text = f"{beat.summary}\n{beat.visual_prompt}\n{beat.anchor_text}"
    for label in (
        "820RR-RS发动机",
        "820RR-RS",
        "Kove摩托",
        "ZXMOTO赛车",
        "旧款125摩托",
        "黄摩托",
        "白摩托",
        "摩托车",
        "摩托",
        "赛车",
        "机车",
        "发动机",
    ):
        if label.casefold() in beat_text.casefold():
            return label
    return "车辆"


def style_tail(style_target: str, *, keyscene: bool, final_prompt_language: str) -> str:
    return localized_style_tail(style_target, keyscene=keyscene, language=final_prompt_language)


def normalize_lighting(value: str) -> str:
    text = cleanup_story_text(value)
    if not text:
        return ""
    if text.startswith("风格及光线"):
        return text.split("：", 1)[-1].strip()
    return text


def cleanup_story_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\s*2D\s*AI漫剧风格[，,\s]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*3D\s*AI漫剧风格[，,\s]*", "", text, flags=re.IGNORECASE)
    for term in CAMERA_MOTION_TERMS:
        text = re.sub(rf"\b{re.escape(term)}\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ，,。")


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def render_source_text(value: str, *, language: str, fallback: str = "") -> str:
    text = render_prompt_fragment(value, language=language, fallback=fallback)
    return collapse_whitespace(text)


def render_entity_label(value: str, *, language: str, kind: str) -> str:
    fallback = {
        "character": {"en": "the character", "zh": "角色"},
        "scene": {"en": "the scene", "zh": "场景"},
        "prop": {"en": "the prop", "zh": "道具"},
        "vehicle": {"en": "the vehicle", "zh": "车辆"},
    }.get(kind, {"en": "the subject", "zh": "主体"})
    rendered = render_source_text(value, language=language, fallback=fallback.get(language, fallback["en"]))
    if language == "en" and contains_cjk(rendered):
        return fallback["en"]
    if language == "zh":
        cleaned = collapse_whitespace(re.sub(r"[A-Za-z][A-Za-z0-9._-]*", " ", rendered)).strip(" ，,。")
        if cleaned:
            rendered = cleaned
    return rendered or fallback.get(language, fallback["en"])


def render_generated_asset_label(asset: GeneratedAsset | None, *, language: str, kind: str) -> str:
    if asset is None:
        return render_entity_label("", language=language, kind=kind)
    return render_entity_label(asset.asset_name, language=language, kind=kind)


def render_vehicle_label_from_context(value: str, *, language: str) -> str:
    return render_entity_label(value, language=language, kind="vehicle")


def structured_asset_snapshot(asset: GeneratedAsset | None) -> dict[str, object] | None:
    if asset is None:
        return None
    return {
        "asset_id": asset.asset_id,
        "asset_name": asset.asset_name,
        "asset_type": asset.asset_type,
        "path": str(asset.path),
    }


def raw_keyscene_source_description(beat: RecapBeat) -> str:
    parts = [
        cleanup_story_text(beat.summary),
        cleanup_story_text(beat.visual_prompt),
        cleanup_story_text(beat.anchor_text),
        cleanup_story_text(beat.mood),
        cleanup_story_text(beat.shot_type),
        cleanup_story_text(beat.camera_motion),
    ]
    return " | ".join(part for part in parts if part)


def prompt_length(prompt: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", str(prompt or "")))


def contains_camera_motion_terms(text: str) -> bool:
    lowered = str(text or "").casefold()
    return any(term in lowered for term in CAMERA_MOTION_TERMS)


def ensure_sentence(value: str, *, language: str) -> str:
    return ensure_localized_sentence(value, language=language)
