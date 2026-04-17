from __future__ import annotations

import re


DEFAULT_FINAL_PROMPT_LANGUAGE = "en"
SUPPORTED_FINAL_PROMPT_LANGUAGES = ("en", "zh")


STYLE_GUIDANCE = {
    "realism": {
        "en": {
            "asset_tail": "Style: cinematic realism, convincing materials and believable lighting, avoid cartoon stylization.",
            "keyscene_tail": "Cinematic realism.",
        },
        "zh": {
            "asset_tail": "风格：电影级写实，真实材质与可信光照，避免卡通化。",
            "keyscene_tail": "电影感写实。",
        },
    },
    "3d-anime": {
        "en": {
            "asset_tail": "Style: high-quality 3D anime look, keep stylized proportions with clear materials and volumetric light.",
            "keyscene_tail": "High-quality 3D anime look.",
        },
        "zh": {
            "asset_tail": "风格：高质量3D动漫质感，保留动漫设计比例，材质与体积光清晰。",
            "keyscene_tail": "3D动漫质感。",
        },
    },
    "2d-anime-cartoon": {
        "en": {
            "asset_tail": "Style: high-quality 2D anime illustration look, clean linework, clear shadow design, avoid photographic realism.",
            "keyscene_tail": "High-quality 2D anime look.",
        },
        "zh": {
            "asset_tail": "风格：高质量2D动漫插画质感，线稿干净，绘制阴影明确，避免写实摄影感。",
            "keyscene_tail": "2D动漫质感。",
        },
    },
}


CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ASCII_RE = re.compile(r"[A-Za-z]")
ENGLISH_PROMPT_KEYWORD_RE = re.compile(
    r"\b("
    r"wide shot|medium shot|medium wide shot|medium close-up|close-up|insert|over-the-shoulder|"
    r"cinematic realism|3d anime|2d anime|soft natural light|background|foreground|midground|"
    r"scene|character|prop|vehicle|track|road|documentary"
    r")\b",
    flags=re.IGNORECASE,
)


ZH_TO_EN_PHRASES = [
    ("高精度3D CG风格", "high-fidelity 3D CG style"),
    ("高质量3D动漫质感", "high-quality 3D anime look"),
    ("高质量2D动漫插画质感", "high-quality 2D anime illustration look"),
    ("电影级写实", "cinematic realism"),
    ("电影感写实", "cinematic realism"),
    ("柔和自然光", "soft natural light"),
    ("光影质感真实细腻", "realistic and nuanced lighting"),
    ("光影质感细腻、层次丰富", "refined lighting with layered depth"),
    ("光影质感细腻", "refined lighting"),
    ("真实材质与可信光照", "convincing materials and believable lighting"),
    ("体积光清晰", "clear volumetric light"),
    ("线稿干净", "clean linework"),
    ("绘制阴影明确", "clear cel-shaded shadows"),
    ("避免写实摄影感", "avoid photographic realism"),
    ("避免卡通化", "avoid cartoon stylization"),
    ("纯白背景", "pure white background"),
    ("浅色背景", "light background"),
    ("干净简洁的浅色背景", "a clean light background"),
    ("单人全身身份参考图", "a full-body single-character identity reference"),
    ("单张环境参考图", "a single environment reference image"),
    ("单个道具参考图", "a single prop reference image"),
    ("高清4k", "high-resolution 4K detail"),
    ("细节丰富", "rich detail"),
    ("正面朝向", "front-facing"),
    ("平视机位", "eye-level camera"),
    ("中性站姿", "neutral standing pose"),
    ("单张干净角色身份参考图", "a clean single-character identity reference"),
    ("纪录片式", "documentary-style"),
    ("纪录片式强追逐感", "documentary chase energy"),
    ("纪录片现场感", "documentary immediacy"),
    ("风吹日晒", "sun-weathered"),
    ("半透明黄色雨衣", "translucent yellow raincoat"),
    ("半透明黄色雨衣", "translucent yellow raincoat"),
    ("半透明黄色", "translucent yellow"),
    ("黄色雨衣", "yellow raincoat"),
    ("黄雨衣", "yellow raincoat"),
    ("灰黑色背心", "charcoal tank top"),
    ("厚帆布围裙", "heavy canvas apron"),
    ("耐磨工作裤", "durable work pants"),
    ("赛车夹克", "racing jacket"),
    ("团队Polo", "team polo"),
    ("浅色衬衫", "light shirt"),
    ("户外采访服装", "field interview clothing"),
    ("专业赛车头盔", "professional racing helmet"),
    ("白色旧头盔", "worn white helmet"),
    ("旧头盔", "worn helmet"),
    ("旧款125摩托", "old 125cc motorcycle"),
    ("破旧125cc小踏板摩托车", "battered 125cc scooter"),
    ("破125小踏板摩托车", "battered 125cc scooter"),
    ("125cc小踏板摩托车", "125cc scooter"),
    ("木箱工具", "wooden tool crate"),
    ("焊枪", "welding torch"),
    ("钛合金螺栓", "titanium bolts"),
    ("赛车头盔", "racing helmet"),
    ("高架桥下石灰岩洞", "limestone cave under an overpass"),
    ("城市桥下通道", "underpass corridor"),
    ("达喀尔沙漠赛道", "Dakar desert track"),
    ("赛道维修区", "track pit lane"),
    ("锈迹加油站", "rusted gas station"),
    ("湖南乡道暴雨路段", "storm-soaked Hunan country road"),
    ("重庆高架桥下石灰岩洞", "limestone cave under a Chongqing overpass"),
    ("重庆城市桥下通道", "Chongqing underpass corridor"),
    ("暴雨山路", "stormy mountain road"),
    ("沙漠拉力赛赛道", "desert rally track"),
    ("乡村雨夜公路", "rural road at night in the rain"),
    ("昏暗小工棚", "dim workshop shed"),
    ("工厂车间", "factory workshop"),
    ("采访者", "the interviewer"),
    ("采访车", "press van"),
    ("新闻车", "news van"),
    ("新闻采访者", "news interviewer"),
    ("年轻机械狂热者", "young mechanical obsessive"),
    ("常和摩托与工位绑在一起", "closely tied to motorcycles and the workbench"),
    ("瘦高中国青年", "a lean Chinese young man"),
    ("深色外套中年男性", "a middle-aged man in a dark jacket"),
    ("黄色摩托车", "a yellow motorcycle"),
    ("真实道路尺度", "believable road scale"),
    ("车辆可在一条车道内运动", "a vehicle can move within a single lane"),
    ("雨夜公路与泥浆路面", "a rain-soaked road with muddy ground"),
    ("角色", "character"),
    ("场景", "scene"),
    ("环境", "environment"),
    ("道具", "prop"),
    ("人物", "character"),
    ("物件", "object"),
    ("车辆", "vehicle"),
    ("摩托车", "motorcycle"),
    ("摩托", "motorcycle"),
    ("赛车", "race bike"),
    ("发动机", "engine"),
    ("头盔", "helmet"),
    ("图纸", "blueprints"),
    ("工作台", "workbench"),
    ("机油", "engine oil"),
    ("工具", "tools"),
    ("赛道", "track"),
    ("道路", "road"),
    ("车道", "lane"),
    ("护栏", "guardrails"),
    ("看台", "grandstand"),
    ("地面", "ground"),
    ("环境空间", "environmental space"),
    ("中景", "midground"),
    ("下中部", "lower mid-frame"),
    ("近景", "close range"),
    ("背景", "background"),
    ("前景", "foreground"),
    ("宽构图", "wide shot"),
    ("中宽景", "medium wide shot"),
    ("中景", "medium shot"),
    ("中近景", "medium close-up"),
    ("特写", "close-up"),
    ("插入镜头", "insert shot"),
    ("越肩构图", "over-the-shoulder composition"),
    ("视觉中心", "visual center"),
    ("主体位置", "subject placement"),
    ("场景层次", "scene depth"),
    ("关键动作关系", "key action relationship"),
    ("空间关系清楚", "clear spatial relationships"),
    ("动作关系直接", "direct action relationships"),
    ("真实整车比例", "true full-vehicle proportions"),
    ("真实赛道比例", "true track proportions"),
    ("真实尺寸关系", "true physical scale"),
    ("不过度放大", "not oversized"),
    ("不要把", "do not turn"),
    ("周围保留可见环境", "keep visible surrounding space"),
    ("赛道向背景延伸", "the track recedes into the background"),
    ("道路向背景延伸", "the road recedes into the background"),
    ("突出", "emphasize"),
    ("保留", "preserve"),
    ("清楚", "clear"),
    ("真实", "true"),
    ("自然", "natural"),
    ("整车完整可见", "the full vehicle remains visible"),
    ("人物和车辆同框", "the character and vehicle share the frame"),
    ("留出完整车身和周围空间", "leave room for the full vehicle and surrounding space"),
    ("机械与工作区关系清楚", "keep the machine and work area relationship clear"),
    ("保留地面和工位边界", "preserve the ground plane and workstation edges"),
    ("局部机械保持真实尺寸和厚度关系", "keep mechanical details at believable thickness and scale"),
    ("不要把零件夸张成失真巨物", "do not exaggerate parts into distorted giant objects"),
    ("保留一点安装环境或支撑关系", "retain some mounting context or support relationship"),
    ("紧迫", "urgent"),
    ("暴雨压迫感", "storm pressure"),
    ("疲惫", "exhausted"),
    ("倔强", "stubborn"),
    ("克制", "restrained"),
    ("成熟", "mature"),
    ("沉稳", "steady"),
    ("孤独", "lonely"),
    ("危险", "dangerous"),
    ("紧张", "tense"),
    ("荒凉", "bleak"),
    ("瘦高", "lean and tall"),
    ("清瘦", "lean"),
    ("结实", "sturdy"),
    ("高挑", "tall"),
    ("黑色短发", "short black hair"),
    ("短发", "short hair"),
    ("脸型偏窄", "narrow face"),
    ("脸部轮廓更硬朗", "sharper facial structure"),
    ("脸部轮廓清晰", "clear facial structure"),
    ("皮肤略显风吹日晒", "sun-weathered skin"),
    ("皮肤略粗粝", "slightly rough skin"),
    ("双手常年沾染机油痕迹", "hands marked by engine oil"),
    ("衣物上带有焊点灼痕与油渍", "clothing marked by welding burns and oil stains"),
    ("整体带有长途奔波后的疲惫感", "an overall sense of fatigue from long travel"),
    ("整体呈现经过赛场历练后的干练成熟感", "an overall seasoned and capable race-day presence"),
    ("整体气质偏纪录片采访工作状态", "an overall practical documentary-interviewer presence"),
    ("衣着实用简洁", "practical and simple clothing"),
    ("只保留一个环境提示", "keep only one environmental cue"),
]


EN_TO_ZH_PHRASES = [
    ("wide shot", "宽构图"),
    ("medium wide shot", "中宽景"),
    ("medium close-up", "中近景"),
    ("medium shot", "中景"),
    ("close-up", "特写"),
    ("insert shot", "插入镜头"),
    ("insert", "插入镜头"),
    ("over-the-shoulder composition", "越肩构图"),
    ("over-the-shoulder", "越肩构图"),
    ("cinematic realism", "电影感写实"),
    ("high-quality 3D anime look", "高质量3D动漫质感"),
    ("high-quality 2D anime illustration look", "高质量2D动漫插画质感"),
    ("high-quality 2D anime look", "2D动漫质感"),
    ("soft natural light", "柔和自然光"),
    ("realistic and nuanced lighting", "真实细腻的光影"),
    ("believable lighting", "可信光照"),
    ("clean linework", "线稿干净"),
    ("documentary-style", "纪录片式"),
    ("documentary", "纪录片式"),
    ("visual center", "视觉中心"),
    ("midground", "中景"),
    ("background", "背景"),
    ("foreground", "前景"),
    ("character", "角色"),
    ("scene", "场景"),
    ("prop", "道具"),
    ("vehicle", "车辆"),
    ("track", "赛道"),
    ("road", "道路"),
    ("lane", "车道"),
    ("guardrails", "护栏"),
    ("grandstand", "看台"),
    ("yellow raincoat", "黄雨衣"),
    ("worn white helmet", "白色旧头盔"),
    ("worn helmet", "旧头盔"),
    ("old 125cc motorcycle", "旧款125摩托"),
    ("battered 125cc scooter", "破旧125小踏板摩托车"),
    ("wooden tool crate", "木箱工具"),
    ("welding torch", "焊枪"),
    ("titanium bolts", "钛合金螺栓"),
]


ZH_TO_EN_REGEX_REPLACEMENTS = [
    (re.compile(r"(\d+)岁左右的中国男性"), r"a Chinese man around \1 years old"),
    (re.compile(r"(\d+)岁左右的中国女性"), r"a Chinese woman around \1 years old"),
    (re.compile(r"(\d+)岁左右"), r"around \1 years old"),
    (re.compile(r"(\d+)多岁到(\d+)岁之间的中国男性"), r"a Chinese man in his late \1s to early \2s"),
    (re.compile(r"(\d+)多岁到(\d+)岁之间"), r"in the late \1s to early \2s"),
    (re.compile(r"(\d+)多岁左右的中国男性"), r"a Chinese man in his \1s"),
    (re.compile(r"(\d+)多岁左右"), r"in the \1s"),
    (re.compile(r"(\d+)多岁"), r"in the \1s"),
]


PUNCTUATION_REPLACEMENTS = {
    "，": ", ",
    "。": ". ",
    "；": "; ",
    "：": ": ",
    "、": ", ",
    "（": " (",
    "）": ") ",
    "“": "\"",
    "”": "\"",
    "‘": "'",
    "’": "'",
}


def normalize_final_prompt_language(value: str | None) -> tuple[str, str | None]:
    raw = str(value or "").strip().lower()
    if not raw:
        return DEFAULT_FINAL_PROMPT_LANGUAGE, None
    if raw in SUPPORTED_FINAL_PROMPT_LANGUAGES:
        return raw, None
    return (
        DEFAULT_FINAL_PROMPT_LANGUAGE,
        f"Unsupported final_prompt_language `{value}`. Falling back to `{DEFAULT_FINAL_PROMPT_LANGUAGE}`.",
    )


def prompt_uses_single_language(text: str, language: str) -> bool:
    if language == "en":
        return not contains_cjk(text)
    return not ENGLISH_PROMPT_KEYWORD_RE.search(str(text or ""))


def contains_cjk(text: str) -> bool:
    return bool(CJK_RE.search(str(text or "")))


def contains_latin_letters(text: str) -> bool:
    return bool(ASCII_RE.search(str(text or "")))


def style_tail(style_target: str, *, keyscene: bool, language: str) -> str:
    style_group = STYLE_GUIDANCE.get(style_target, STYLE_GUIDANCE["2d-anime-cartoon"])
    localized = style_group.get(language, style_group[DEFAULT_FINAL_PROMPT_LANGUAGE])
    return localized["keyscene_tail" if keyscene else "asset_tail"]


def ensure_sentence(value: str, *, language: str) -> str:
    text = collapse_whitespace(value).strip(" ，,。.;；")
    if not text:
        return ""
    ending = "." if language == "en" else "。"
    return f"{text}{ending}"


def render_prompt_fragment(value: str, *, language: str, fallback: str = "") -> str:
    text = cleanup_prompt_source(value)
    if not text:
        return fallback
    if language == "zh":
        return _render_chinese_fragment(text, fallback=fallback)
    return _render_english_fragment(text, fallback=fallback)


def cleanup_prompt_source(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for source, target in PUNCTUATION_REPLACEMENTS.items():
        text = text.replace(source, target)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _render_english_fragment(text: str, *, fallback: str) -> str:
    rendered = text
    for pattern, replacement in ZH_TO_EN_REGEX_REPLACEMENTS:
        rendered = pattern.sub(replacement, rendered)
    rendered = _replace_phrases(rendered, ZH_TO_EN_PHRASES)
    rendered = rendered.replace("3D CG", "3D CG")
    rendered = re.sub(r"\bCG\b", "CG", rendered)
    rendered = re.sub(r"[^0-9A-Za-z.,;:()/'\"!?\-_\s]+", " ", rendered)
    rendered = collapse_whitespace(rendered)
    rendered = re.sub(r"\s*([,.;:])\s*", r"\1 ", rendered)
    rendered = re.sub(r"\s+\)", ")", rendered)
    rendered = re.sub(r"\(\s+", "(", rendered)
    rendered = re.sub(r"(?:,\s*){2,}", ", ", rendered)
    rendered = re.sub(r"(?:\.\s*){2,}", ". ", rendered)
    rendered = rendered.strip(" ,.;")
    if not rendered:
        return fallback
    return rendered


def _render_chinese_fragment(text: str, *, fallback: str) -> str:
    rendered = _replace_phrases(text, EN_TO_ZH_PHRASES)
    rendered = re.sub(r"\s+", " ", rendered)
    rendered = rendered.replace(" ,", "，")
    rendered = rendered.replace(", ", "，")
    rendered = rendered.replace(". ", "。")
    rendered = rendered.replace(";", "；")
    rendered = collapse_whitespace(rendered).strip(" ，,。.;；")
    return rendered or fallback


def _replace_phrases(text: str, replacements: list[tuple[str, str]]) -> str:
    rendered = text
    for source, target in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        rendered = rendered.replace(source, target)
    return rendered
