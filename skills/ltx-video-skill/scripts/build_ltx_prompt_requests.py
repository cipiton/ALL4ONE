from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ltx_skill_module_loader import load_local_module

RecapShot = load_local_module("load_recap_production").RecapShot


SHOT_TYPE_MAP = {
    "wide shot": "wide shot",
    "medium shot": "medium shot",
    "medium close-up": "medium close-up",
    "close-up": "close-up",
    "over-the-shoulder": "over-the-shoulder",
    "insert": "insert shot",
    "montage": "montage shot",
}

CAMERA_MOTION_MAP = {
    "static": "静止机位",
    "slow pan right": "镜头缓慢向右平移，跟着主体移动",
    "slow pan left": "镜头缓慢向左平移，跟着主体移动",
    "slow push in": "镜头缓慢推进，压近主体的反应",
    "slow dolly in": "镜头缓慢推近，逐步贴近主体",
    "slow dolly out": "镜头缓慢拉远，把关系和空间一起带出来",
    "handheld drift": "轻微手持跟随，保留贴身晃动",
    "slow tilt down": "镜头缓慢下倾，顺着动作落向关键细节",
    "slow tilt up": "镜头缓慢上仰，把视线带向上方变化",
}

DURATION_HINT_MAP = {
    "short": "2-3s",
    "medium": "3-5s",
    "long": "4-6s",
}

SHOT_MODE_CLOSEUP = "closeup_emotion"
SHOT_MODE_DIALOGUE = "dialogue_speaking"
SHOT_MODE_INSERT = "insert_prop_detail"
SHOT_MODE_STAGING = "staging_environment"
SHOT_MODE_ACTION = "action_movement"

ACTION_TOKENS = (
    "追",
    "冲",
    "跑",
    "停",
    "转",
    "回头",
    "抬",
    "摘",
    "说",
    "开口",
    "逼近",
    "挥",
    "拉",
    "推",
    "撞",
    "看",
    "盯",
    "举",
    "接",
    "焊",
    "切",
    "抓",
    "发力",
    "稳住",
    "站",
    "骑",
)

DIALOGUE_TOKENS = (
    "说",
    "开口",
    "回答",
    "喊",
    "问",
    "低声",
    "嘴唇",
    "台词",
    "面对镜头",
    "采访者",
    "对白",
    "一句话",
)

ACTING_CUE_HINTS = (
    ("倔强", "下颌绷紧，肩背前压"),
    ("疲惫", "呼吸发重，肩膀轻微下沉"),
    ("愤怒", "手指收紧，脖颈绷住"),
    ("紧张", "短暂停顿，视线快速扫动"),
    ("犹豫", "先停半拍，再慢慢抬眼"),
    ("警觉", "头部微转，眼神先一步锁定"),
    ("悲伤", "目光下落，呼吸压住不外露"),
    ("危险", "身体先僵一下，再迅速做出反应"),
    ("好奇", "眉头轻抬，身体微微前探"),
    ("坚定", "站姿稳住，动作不回撤"),
)

AUDIO_HINTS = (
    ("暴雨", "暴雨连续敲打车顶和地面"),
    ("雨幕", "雨点密集拍在玻璃和金属上"),
    ("焊枪", "焊接火花噼啪炸开"),
    ("火花", "焊接火花持续炸响"),
    ("发动机", "发动机闷响后迅速拉高"),
    ("摩托", "摩托发动机持续发闷地轰鸣"),
    ("赛车", "引擎高频拉升后带出尾音"),
    ("人群", "远处人群声浪一层层推过来"),
    ("看台", "看台欢呼在背景里卷起"),
    ("洞", "空洞空间里带着闷响回声"),
    ("加油站", "空站点里只有雨声和机械回响"),
    ("车内", "车厢里闷住的呼吸和雨刷摩擦声叠在一起"),
)

RECAP_CLEANUP_PATTERNS = (
    r"高精度3D CG风格",
    r"高精度3D CG",
    r"3D CG",
    r"高清4k",
    r"画面重点是",
    r"画面强调",
    r"突出",
    r"纪录片式",
    r"整体保持",
    r"形成强反差",
)

MODE_RULES = {
    SHOT_MODE_CLOSEUP: {
        "detail": "细看脸部、视线、呼吸和手部细动作，不展开过多环境说明。",
        "camera": "镜头优先贴着人物反应，可以轻推近，也可以明确写静止机位。",
        "audio": "只有当呼吸、雨声或嘴唇发声会强化镜头时才写音效。",
        "acting": "把情绪改写成目光、停顿、吞咽、握紧、抬眼、压呼吸等可见动作。",
        "sentence_target": "4-6",
    },
    SHOT_MODE_DIALOGUE: {
        "detail": "优先写说话前后的可见动作、嘴唇动作、停顿、对视和回应。",
        "camera": "镜头要说明是越肩、缓推、静止对准说话者，或跟着说话时的小位移。",
        "audio": "如果台词、雨声、引擎声或室内底噪有用，可以简短写出。",
        "acting": "台词要配合口型、呼吸、停顿、头部动作和目光转移。",
        "sentence_target": "5-7",
    },
    SHOT_MODE_INSERT: {
        "detail": "只保留道具或局部动作必要细节，不把整场景重新讲一遍。",
        "camera": "镜头要写成特写、下倾、静止观察或顺着手部动作贴近。",
        "audio": "只在金属摩擦、雨点、按钮、引擎或焊接声会强化动作时加入。",
        "acting": "如果有人手入镜，只写手部力度和接触变化。",
        "sentence_target": "4-5",
    },
    SHOT_MODE_STAGING: {
        "detail": "优先交代空间关系，再写谁先动、谁后动、环境如何跟着变。",
        "camera": "镜头要说明是静止建立空间还是平移/拉远把动作带出来。",
        "audio": "只有环境声能帮助读懂空间时加入。",
        "acting": "人物反应只写对空间关系有帮助的动作。",
        "sentence_target": "4-6",
    },
    SHOT_MODE_ACTION: {
        "detail": "先写开场状态，再写主体运动、二次反应和动作后的空间变化。",
        "camera": "镜头要明确跟随、平移、推进、上仰或静止等待动作冲进来。",
        "audio": "通常要保留关键运动声、引擎声、雨声或撞击声，但保持简短。",
        "acting": "把紧张和冲劲写成发力、稳住、转头、收紧、失衡后再找回控制。",
        "sentence_target": "5-7",
    },
}


@dataclass(frozen=True, slots=True)
class LtxPromptRequest:
    structured_input: dict[str, Any]
    messages: list[Any]
    fallback_payload: dict[str, str]


def build_ltx_prompt_request(shot: RecapShot, *, total_shots: int, shot_index: int) -> LtxPromptRequest:
    shot_mode = classify_shot_mode(shot)
    structured_input = {
        "episode_id": shot.episode_id,
        "shot_id": shot.shot_id,
        "shot_number": shot_index,
        "total_shots": total_shots,
        "generation_mode": "image-to-video",
        "prompt_language": "zh",
        "source_contract": shot.source_contract,
        "shot_type": normalize_shot_type(shot.shot_type),
        "shot_mode": shot_mode,
        "duration_hint": infer_duration_hint(shot.pace_weight),
        "priority": compact_text(shot.priority, limit=24),
        "beat_role": compact_text(shot.beat_role, limit=24),
        "asset_focus": compact_text(shot.asset_focus, limit=24),
        "summary": compact_text(shot.summary, limit=220),
        "anchor_text": compact_text(shot.anchor_text, limit=120),
        "visual_prompt": compact_text(shot.visual_prompt, limit=320),
        "motion_prompt_source": compact_text(shot.video_prompt, limit=320),
        "still_prompt_source": compact_text(shot.anchor_prompt, limit=320),
        "linked_assets": list(shot.linked_assets),
        "linked_asset_context": extract_linked_asset_context(shot),
        "camera_motion_source": normalize_camera_motion(shot.camera_motion),
        "mood_source": compact_text(shot.mood, limit=72),
        "derived_acting_cues": derive_acting_cues(shot),
        "derived_audio_hint": derive_audio_description(shot, shot_mode=shot_mode),
        "derived_environment_motion": derive_environment_motion(shot, shot_mode=shot_mode),
        "mode_guidance": MODE_RULES[shot_mode],
        "official_rules": {
            "paragraph": "single flowing paragraph",
            "tense": "present tense action",
            "sequence": "opening state -> primary movement -> secondary reaction -> camera behavior",
            "sentence_range": MODE_RULES[shot_mode]["sentence_target"],
            "focus": "what happens next, not recap narration",
        },
    }
    fallback_payload = build_fallback_payload(shot, shot_mode=shot_mode)
    return LtxPromptRequest(
        structured_input=structured_input,
        messages=build_director_messages(structured_input),
        fallback_payload=fallback_payload,
    )


def build_director_messages(structured_input: dict[str, Any]) -> list[Any]:
    from engine.models import PromptMessage

    schema = {
        "episode_id": "string",
        "shot_id": "string",
        "shot_type": "string",
        "shot_mode": "string",
        "scene_setup": "string",
        "character_definition": "string",
        "action_sequence": "string",
        "camera_motion": "string",
        "environment_motion": "string",
        "audio_description": "string",
        "acting_cues": "string",
        "duration_hint": "string",
        "final_prompt": "string",
    }
    system = (
        "You are the ONE4ALL LTX 2.3 prompt director. "
        "Transform one recap beat into one LTX-style shot prompt for image-to-video prompting. "
        "Follow the official LTX 2.3 prompting guidance: single flowing paragraph, present-tense visible action, clear shot language, "
        "camera movement relative to the subject, audio only when useful, and a natural movement sequence from beginning to end. "
        "Return JSON only.\n\n"
        "Hard rules:\n"
        "- One shot = one prompt.\n"
        "- The final prompt must be one coherent paragraph.\n"
        "- Write 4-8 descriptive sentences by default, matching the requested shot mode and duration.\n"
        "- Use immediate present-tense Chinese phrasing.\n"
        "- Write visible action progression: opening state, primary movement/change, secondary movement/reaction, then camera behavior.\n"
        "- Use physical acting cues instead of abstract emotion labels.\n"
        "- Camera language must be explicit: slow push in, pan, handheld follow, static frame, tilt, over-the-shoulder, or another clear equivalent.\n"
        "- If this is image-to-video, focus on what moves next, what the camera does next, and what secondary motion or sound emerges next.\n"
        "- Do not rewrite the beat like recap narration.\n"
        "- Do not explain theme, meaning, destiny, symbolism, or backstory.\n"
        "- Do not overload the shot with too many actions, conflicting light logic, complex physics, readable text, or new story facts.\n"
        "- Do not re-describe static elements that the source image would already show unless they are needed to clarify the next movement.\n"
        "- Keep all output values in Chinese except the canonical shot_type and shot_mode labels.\n"
        "- If a field is not useful, return an empty string, not commentary.\n"
    )
    user = (
        "Convert this beat into the target schema for a later LTX clip stage.\n"
        f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        "Field guidance:\n"
        "- motion_prompt_source: if present, treat it as the preferred motion-first source for what happens next in the shot.\n"
        "- still_prompt_source / visual_prompt: use these only to anchor static setup that the motion needs; do not over-describe them again.\n"
        "- scene_setup: one short sentence that anchors only the motion-relevant setup.\n"
        "- character_definition: only the visual identity needed for motion or acting clarity.\n"
        "- action_sequence: a natural visible sequence from the opening state to the end of the shot.\n"
        "- camera_motion: explicit camera behavior relative to the subject, or a clear static-frame choice.\n"
        "- environment_motion: rain, sparks, dust, crowd, cloth, smoke, reflections, or other secondary motion only when useful.\n"
        "- audio_description: short ambient or sync sound cue only when useful.\n"
        "- acting_cues: visible facial/body cues such as pause, glance, breath, jaw tension, grip change, head turn, lip movement.\n"
        "- final_prompt: one flowing paragraph in Chinese, 4-8 sentences, motion-directed, physically plausible, and not recap-like.\n\n"
        f"Shot input:\n{json.dumps(structured_input, ensure_ascii=False, indent=2)}"
    )
    return [
        PromptMessage(role="system", content=system),
        PromptMessage(role="user", content=user),
    ]


def build_fallback_payload(shot: RecapShot, *, shot_mode: str) -> dict[str, str]:
    payload = {
        "episode_id": shot.episode_id,
        "shot_id": shot.shot_id,
        "shot_type": normalize_shot_type(shot.shot_type),
        "shot_mode": shot_mode,
        "scene_setup": derive_scene_setup(shot, shot_mode=shot_mode),
        "character_definition": derive_character_definition(shot, shot_mode=shot_mode),
        "action_sequence": derive_action_sequence(shot, shot_mode=shot_mode),
        "camera_motion": derive_camera_motion(shot, shot_mode=shot_mode),
        "environment_motion": derive_environment_motion(shot, shot_mode=shot_mode),
        "audio_description": derive_audio_description(shot, shot_mode=shot_mode),
        "acting_cues": derive_acting_cues(shot),
        "duration_hint": infer_duration_hint(shot.pace_weight),
    }
    payload["final_prompt"] = assemble_final_prompt_from_payload(payload)
    return payload


def assemble_final_prompt_from_payload(payload: dict[str, str]) -> str:
    shot_mode = payload.get("shot_mode", SHOT_MODE_ACTION)
    scene_setup = cleanup_source_text(payload.get("scene_setup"))
    character_definition = cleanup_source_text(payload.get("character_definition"))
    action_sequence = cleanup_source_text(payload.get("action_sequence"))
    camera_motion = cleanup_source_text(payload.get("camera_motion"))
    environment_motion = cleanup_source_text(payload.get("environment_motion"))
    audio_description = cleanup_source_text(payload.get("audio_description"))
    acting_cues = cleanup_source_text(payload.get("acting_cues"))

    sentences: list[str] = []
    if shot_mode == SHOT_MODE_INSERT:
        sentences.extend(
            [
                ensure_sentence(scene_setup or "镜头先稳住关键物件所在的位置"),
                ensure_sentence(character_definition or "只有必要的人手或接触关系进入画面"),
                ensure_sentence(action_sequence or "关键细节开始发生变化，动作从接触瞬间继续往下推进"),
                ensure_sentence(camera_motion or "镜头顺着局部动作压近关键细节"),
                ensure_sentence(acting_cues or environment_motion or "周围只保留少量能衬出动作的细小变化"),
            ]
        )
    elif shot_mode == SHOT_MODE_DIALOGUE:
        sentences.extend(
            [
                ensure_sentence(scene_setup or "镜头先稳住说话双方的空间关系"),
                ensure_sentence(character_definition or "人物的视线和口型已经准备进入说话动作"),
                ensure_sentence(action_sequence or "人物开口说话，句子往前推，动作跟着台词一点点展开"),
                ensure_sentence(acting_cues or "说话前后保留停顿、换气、目光转移和细小头部动作"),
                ensure_sentence(camera_motion or "镜头保持稳定地贴住说话者的反应"),
            ]
        )
    elif shot_mode == SHOT_MODE_CLOSEUP:
        sentences.extend(
            [
                ensure_sentence(scene_setup or "镜头先贴住人物此刻的面部和上半身"),
                ensure_sentence(character_definition or "人物的视线、呼吸和手部小动作都是可见的"),
                ensure_sentence(action_sequence or "动作从一个短暂停顿开始，再继续往前推进"),
                ensure_sentence(acting_cues or "情绪通过目光、下颌、呼吸和握紧的变化显出来"),
                ensure_sentence(camera_motion or "镜头缓慢推进，压近人物的反应"),
            ]
        )
    elif shot_mode == SHOT_MODE_STAGING:
        sentences.extend(
            [
                ensure_sentence(scene_setup or "镜头先把人物和环境的空间关系交代清楚"),
                ensure_sentence(character_definition or "主体站在空间里，下一步动作已经开始蓄势"),
                ensure_sentence(action_sequence or "先有主体动作，再有空间里的第二层变化跟上"),
                ensure_sentence(environment_motion or acting_cues or "环境里的细小变化继续推动这一个镜头"),
                ensure_sentence(camera_motion or "镜头保持静止，等动作把空间关系带出来"),
            ]
        )
    else:
        sentences.extend(
            [
                ensure_sentence(scene_setup or "镜头先稳住主体即将发力的开场状态"),
                ensure_sentence(character_definition or "人物和关键物件的关系已经清楚落进画面"),
                ensure_sentence(action_sequence or "主体动作立刻往前推进，速度和方向都清楚可见"),
                ensure_sentence(acting_cues or environment_motion or "动作带出身体反应和周围环境的二次变化"),
                ensure_sentence(camera_motion or "镜头跟着主体继续往前走，保持动作连贯"),
            ]
        )

    if environment_motion and not any(environment_motion in sentence for sentence in sentences):
        sentences.append(ensure_sentence(environment_motion))
    if audio_description and should_include_audio_in_prompt(shot_mode, audio_description=audio_description):
        sentences.append(ensure_sentence(audio_description))

    sentences = [sentence for sentence in sentences if sentence]
    max_sentences = 8
    min_sentences = 4
    if len(sentences) > max_sentences:
        sentences = sentences[:max_sentences]
    while len(sentences) < min_sentences:
        if shot_mode == SHOT_MODE_DIALOGUE:
            sentences.append(ensure_sentence("说话停顿和视线回勾继续把镜头往下拉"))
        elif shot_mode == SHOT_MODE_INSERT:
            sentences.append(ensure_sentence("镜头只保留和下一步动作有关的局部变化"))
        else:
            sentences.append(ensure_sentence("镜头里的动作顺着同一个方向继续完成"))
    return " ".join(sentences)


def classify_shot_mode(shot: RecapShot) -> str:
    shot_type = normalize_shot_type(shot.shot_type).casefold()
    asset_focus = cleanup_source_text(shot.asset_focus).casefold()
    source = shot.combined_text.casefold()
    if "insert" in shot_type or asset_focus in {"object", "prop"}:
        return SHOT_MODE_INSERT
    has_closeup_framing = any(token in shot_type for token in ("close-up", "medium close-up"))
    has_dialogue = has_dialogue_signals(shot)
    if has_closeup_framing:
        return SHOT_MODE_DIALOGUE if has_dialogue else SHOT_MODE_CLOSEUP
    if "over-the-shoulder" in shot_type and has_dialogue:
        return SHOT_MODE_DIALOGUE
    if "over-the-shoulder" in shot_type:
        return SHOT_MODE_CLOSEUP
    if has_dialogue:
        return SHOT_MODE_DIALOGUE
    if asset_focus in {"environment", "staging"} or "wide shot" in shot_type:
        if has_strong_movement(shot):
            return SHOT_MODE_ACTION
        return SHOT_MODE_STAGING
    if has_strong_movement(shot):
        return SHOT_MODE_ACTION
    if asset_focus == "character":
        return SHOT_MODE_CLOSEUP
    return SHOT_MODE_STAGING


def derive_scene_setup(shot: RecapShot, *, shot_mode: str) -> str:
    visual = strip_recap_language(cleanup_source_text(shot.visual_prompt))
    clauses = split_clauses(visual)
    if shot_mode == SHOT_MODE_INSERT:
        for clause in clauses:
            if any(token in clause for token in ("特写", "发动机", "局部", "手指", "金属部件")):
                return trim_clause(f"镜头先压住{clause}", limit=48)
        return "镜头先压住关键物件的局部位置"
    if shot_mode == SHOT_MODE_DIALOGUE:
        for clause in clauses:
            if any(token in clause for token in ("车内", "雨棚", "面对", "采访者", "镜头")):
                return trim_clause(clause, limit=48)
        return "镜头先稳住人物即将说话的对位关系"
    if shot_mode == SHOT_MODE_CLOSEUP:
        for clause in clauses:
            if clause.startswith(("高精度", "3D", "CG")):
                continue
            if any(token in clause for token in ("张雪", "少年", "人物", "面部", "眼神", "头盔", "脸", "呼吸", "手")):
                return trim_clause(clause, limit=48)
        for clause in clauses:
            if clause.startswith(("高精度", "3D", "CG")):
                continue
            if any(token in clause for token in ("近景", "面部", "眼神", "头盔", "脸")):
                return trim_clause(clause, limit=48)
        return "镜头先贴住人物此刻的近距离状态"
    if shot_mode == SHOT_MODE_STAGING:
        for clause in clauses:
            if any(token in clause for token in ("车内", "加油站", "赛道", "雨路", "洞", "桥下")):
                return trim_clause(clause, limit=52)
        return "镜头先把主体和环境的空间关系稳住"
    for clause in clauses:
        if any(token in clause for token in ("乡道", "赛道", "雨路", "桥下", "洞", "加油站")):
            return trim_clause(clause, limit=52)
    return "镜头先稳住主体即将发力的开场位置"


def derive_character_definition(shot: RecapShot, *, shot_mode: str) -> str:
    visual = cleanup_source_text(shot.visual_prompt)
    if shot_mode == SHOT_MODE_INSERT:
        if any(token in visual for token in ("手", "手指", "掌心", "握")):
            return "只保留必要的手部接触和力度变化"
        return "人物只以必要的接触关系进入画面"
    if shot_mode == SHOT_MODE_DIALOGUE:
        return "人物的嘴唇、眼神和头部微动作都保持可见"
    if shot_mode == SHOT_MODE_CLOSEUP:
        return "人物的视线、呼吸、下颌和手部细动作都要看得见"
    if shot_mode == SHOT_MODE_STAGING:
        return "主体在空间中的站位和下一步动作方向要先看清"
    return "人物和关键物件的相对位置先被镜头交代清楚"


def derive_action_sequence(shot: RecapShot, *, shot_mode: str) -> str:
    cp_video = shot.source_payload.get("cp_video_prompt") if isinstance(shot.source_payload, dict) else {}
    if not isinstance(cp_video, dict):
        cp_video = {}
    summary = strip_recap_language(cleanup_source_text(shot.summary))
    anchor = strip_recap_language(cleanup_source_text(shot.anchor_text))
    visual = strip_recap_language(cleanup_source_text(shot.visual_prompt))
    cp_action = cleanup_source_text(cp_video.get("character_action"))
    cp_environment = cleanup_source_text(cp_video.get("environment_motion"))
    base = first_non_empty(cp_action, summary, anchor, visual)
    base = trim_clause(base, limit=96)
    if shot_mode == SHOT_MODE_DIALOGUE:
        if anchor:
            return f"人物先压住一口气，再抬起动作截断误解，嘴唇把“{trim_clause(anchor, limit=18)}”这句短话直接推出去，对面的反应立刻被钉住"
        return "人物先停半拍，再开口把话推出去，话音落下时对面的人跟着停住动作"
    if shot_mode == SHOT_MODE_INSERT:
        if anchor:
            return f"镜头先跟住手部或机械接触，再把“{trim_clause(anchor, limit=18)}”对应的关键细节推到画面中央，随后留下持续的震动或受力反应"
        return "手部或关键部件先进入接触，再立刻带出局部变化，最后留下余势"
    if shot_mode == SHOT_MODE_CLOSEUP:
        if summary and has_action_language(summary):
            return f"{trim_clause(summary, limit=72)}，动作继续压进更细的目光、呼吸或手部变化里"
        if anchor:
            return f"人物先停半拍，再用视线或呼吸把“{trim_clause(anchor, limit=18)}”这一下反应推出去，最后留下更细小的后续动作"
        return "人物先停半拍，再抬眼或转头，接着用更细小的反应把动作推完"
    if base and has_action_language(base):
        if cp_environment:
            return f"{base}，再带出{trim_clause(cp_environment, limit=28)}"
        return f"{base}，动作从开场状态继续往前推进，再带出第二层变化"
    if shot_mode == SHOT_MODE_STAGING:
        return "主体先落在空间里，再开始动作，随后把周围关系一起带动"
    return "主体先发力冲出去，再稳住动作，最后把周围空间的变化一起带出来"


def derive_camera_motion(shot: RecapShot, *, shot_mode: str) -> str:
    normalized = normalize_camera_motion(shot.camera_motion)
    if normalized:
        return normalized
    if shot_mode == SHOT_MODE_DIALOGUE:
        return "镜头轻微缓推，始终贴着说话者的口型和视线"
    if shot_mode == SHOT_MODE_CLOSEUP:
        return "镜头缓慢推进，压近人物面部和手部反应"
    if shot_mode == SHOT_MODE_INSERT:
        return "镜头保持静止，等手部动作把细节变化带出来"
    if shot_mode == SHOT_MODE_STAGING:
        return "镜头保持静止，让主体动作自己把空间关系推开"
    return "镜头跟着主体的方向平稳移动，把动作从开头带到结尾"


def derive_environment_motion(shot: RecapShot, *, shot_mode: str) -> str:
    cp_video = shot.source_payload.get("cp_video_prompt") if isinstance(shot.source_payload, dict) else {}
    if isinstance(cp_video, dict):
        cp_environment = cleanup_source_text(cp_video.get("environment_motion"))
        if cp_environment:
            return cp_environment
    text = cleanup_source_text(shot.visual_prompt)
    for token, phrase in (
        ("暴雨", "暴雨连续砸下，积水和泥浆被轮胎不断掀开"),
        ("雨幕", "密集雨幕一直压着视线往下落"),
        ("雨刷", "雨刷在玻璃前来回抽动"),
        ("火花", "火花持续炸开，照亮周围一圈暗面"),
        ("焊", "焊接电弧一下下闪亮，把空气里的烟气带活"),
        ("烟雾", "烟气在热浪里慢慢拧动"),
        ("风", "风把衣角、尘沙或雨线一起拽动"),
        ("泥浆", "泥浆被动作不断甩起又砸回地面"),
        ("沙粒", "沙粒被气流卷起，从主体身后往外散"),
        ("风沙", "风沙被动作带起，沿着空间边缘扫过去"),
        ("沙漠", "沙粒被轮胎或风压卷起，一路往后拖开"),
        ("人群", "周围人群跟着这一刻的变化轻微骚动"),
        ("看台", "看台上的旗帜和人影跟着动作一起起伏"),
    ):
        if token in text:
            return phrase
    if shot_mode == SHOT_MODE_ACTION:
        return "周围空间被主体动作带出连续的二次变化"
    return ""


def derive_audio_description(shot: RecapShot, *, shot_mode: str) -> str:
    cp_video = shot.source_payload.get("cp_video_prompt") if isinstance(shot.source_payload, dict) else {}
    if isinstance(cp_video, dict):
        motion_focus = cleanup_source_text(cp_video.get("motion_focus"))
        if "引擎" in motion_focus or "发动机" in motion_focus:
            return "引擎声先压住背景，再把动作往前推出去"
    text = cleanup_source_text(shot.combined_text)
    for token, phrase in AUDIO_HINTS:
        if token in text:
            return phrase
    if shot_mode == SHOT_MODE_DIALOGUE:
        return "先听到一口压住的呼吸，再接上清楚的人声"
    return ""


def derive_acting_cues(shot: RecapShot) -> str:
    source = cleanup_source_text(f"{shot.summary} {shot.visual_prompt} {shot.mood}")
    cues = []
    for token, phrase in ACTING_CUE_HINTS:
        if token in source and phrase not in cues:
            cues.append(phrase)
    if any(token in source for token in ("回头", "转头")):
        cues.append("头部先转过去，视线再追上目标")
    if any(token in source for token in ("握", "抓", "捏")):
        cues.append("手指收紧后再松开一点")
    if any(token in source for token in ("呼吸", "喘")):
        cues.append("呼吸明显变重，再硬压回去")
    if any(token in source for token in ("说", "开口", "喊")):
        cues.append("嘴唇先动，句子推出去时下颌跟着收紧")
    if not cues and cleanup_source_text(shot.mood):
        cues.append("先停半拍，再用目光和呼吸把反应带出来")
    return "，".join(cues[:2])


def should_include_audio_in_prompt(shot_mode: str, *, audio_description: str) -> bool:
    if not audio_description:
        return False
    if shot_mode in {SHOT_MODE_ACTION, SHOT_MODE_DIALOGUE, SHOT_MODE_CLOSEUP}:
        return True
    if shot_mode == SHOT_MODE_INSERT:
        return any(token in audio_description for token in ("金属", "按钮", "引擎", "焊"))
    return False


def has_strong_movement(shot: RecapShot) -> bool:
    text = cleanup_source_text(shot.combined_text)
    return any(token in text for token in ACTION_TOKENS)


def has_action_language(text: str) -> bool:
    return any(token in text for token in ACTION_TOKENS)


def has_dialogue_signals(shot: RecapShot) -> bool:
    summary = cleanup_source_text(shot.summary)
    anchor = cleanup_source_text(shot.anchor_text)
    visual = cleanup_source_text(shot.visual_prompt)
    combined = " ".join(part for part in (summary, anchor, visual) if part)
    if any(token in combined for token in DIALOGUE_TOKENS):
        return True
    return False


def normalize_shot_type(value: str) -> str:
    lowered = str(value or "").strip().casefold()
    return SHOT_TYPE_MAP.get(lowered, lowered or "shot")


def normalize_camera_motion(value: str) -> str:
    lowered = str(value or "").strip().casefold()
    if not lowered:
        return ""
    return CAMERA_MOTION_MAP.get(lowered, "")


def infer_duration_hint(value: str) -> str:
    lowered = str(value or "").strip().casefold()
    return DURATION_HINT_MAP.get(lowered, "3-5s")


def compact_text(value: str, *, limit: int) -> str:
    text = cleanup_source_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，,；;。 ")


def strip_recap_language(text: str) -> str:
    cleaned = cleanup_source_text(text)
    if not cleaned:
        return ""
    for pattern in RECAP_CLEANUP_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"^从.+?视角", "", cleaned)
    cleaned = re.sub(r"^镜头(?:更)?贴近", "", cleaned)
    cleaned = re.sub(r"^画面(?:里|中)?", "", cleaned)
    cleaned = re.sub(r"[“”\"].+?[”\"]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip("，,；;。 ")


def cleanup_source_text(value: str) -> str:
    text = str(value or "").replace("\r\n", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip("，,；;。 ")


def trim_clause(value: str, *, limit: int) -> str:
    text = cleanup_source_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip("，,；;。 ")


def first_non_empty(*values: str) -> str:
    for value in values:
        text = cleanup_source_text(value)
        if text:
            return text
    return ""


def split_clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[，,；;。]+", text) if part.strip()]


def ensure_sentence(value: str) -> str:
    text = cleanup_source_text(value)
    if not text:
        return ""
    return text + "。"


def extract_linked_asset_context(shot: RecapShot) -> list[dict[str, str]]:
    source_payload = shot.source_payload if isinstance(shot.source_payload, dict) else {}
    raw_items = source_payload.get("cp_linked_asset_context")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for raw_item in raw_items[:6]:
        if not isinstance(raw_item, dict):
            continue
        asset_name = compact_text(str(raw_item.get("asset_name") or ""), limit=48)
        asset_type = compact_text(str(raw_item.get("asset_type") or ""), limit=24)
        description = compact_text(str(raw_item.get("short_description") or ""), limit=72)
        if asset_name or asset_type or description:
            items.append(
                {
                    "asset_name": asset_name,
                    "asset_type": asset_type,
                    "short_description": description,
                }
            )
    return items
